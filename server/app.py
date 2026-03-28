"""Expose the local HTTP API used by OpenClaw and Vapi for this skill.

This FastAPI app starts outbound reservation calls, receives Vapi webhook events,
and returns per-call results so OpenClaw can check them later.
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path
from dotenv import load_dotenv
import os
import json

from webhook_handler import process_vapi_webhook
from vapi_client import start_outbound_reservation_call

load_dotenv()

APP_PORT = int(os.getenv("APP_PORT", "3000"))
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "outputs" / "reservations"
BY_CALL_ID_DIR = RESULTS_DIR / "by_call_id"
BY_CALL_ID_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Restaurant Reservation Webhook Server")


@app.get("/health")
async def health() -> dict:
    """Return a lightweight health response for the local FastAPI service.

    Parameters:
        None.
    Returns:
        dict: Basic service metadata including status and configured port.
    """
    return {
        "status": "ok",
        "service": "restaurant-reservation-webhook",
        "port": APP_PORT,
    }


@app.post("/webhook/vapi")
async def vapi_webhook(request: Request):
    """Receive a Vapi webhook payload and hand it to the local webhook processor.

    Parameters:
        request (Request): The incoming FastAPI request carrying the webhook JSON body.
    Returns:
        JSONResponse: A success payload with saved file paths, or a 400 response for invalid JSON.
    """
    try:
        payload = await request.json()
    except Exception:
        body = await request.body()
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "Invalid JSON payload",
                "raw_body": body.decode("utf-8", errors="ignore"),
            },
        )

    result = process_vapi_webhook(payload)

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "message": "Webhook received",
            "saved_raw_file": result.get("raw_file"),
            "saved_normalized_file": result.get("normalized_file"),
            "event_type": result.get("event_type"),
            "call_id": result.get("call_id"),
            "skipped_normalization": result.get("skipped_normalization", False),
        },
    )


@app.post("/start-reservation")
async def start_reservation(request: Request):
    """Start an outbound reservation call using the JSON body sent by the caller.

    Parameters:
        request (Request): The incoming FastAPI request containing reservation details.
    Returns:
        dict: A start confirmation with the resolved `call_id` for later result lookup.
    """
    try:
        request_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    try:
        call_result = start_outbound_reservation_call(request_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    call_id = (
        call_result.get("id")
        or call_result.get("call", {}).get("id")
        or call_result.get("callId")
    )

    return {
        "ok": True,
        "status": "started",
        "call_id": call_id,
        "message": "Reservation call started.",
    }


@app.get("/reservation-result/{call_id}")
async def reservation_result(call_id: str):
    """Fetch the saved normalized result for a specific reservation call.

    Parameters:
        call_id (str): The Vapi call ID used as the lookup key in the results directory.
    Returns:
        dict: A pending status if the result file does not exist yet, or a completed payload with the stored result.
    """
    result_path = BY_CALL_ID_DIR / f"{call_id}.json"

    if not result_path.exists():
        return {
            "ok": True,
            "status": "pending",
            "call_id": call_id,
            "message": "Reservation result not ready yet."
        }

    try:
        result_data = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read result: {e}")

    return {
        "ok": True,
        "status": "completed",
        "call_id": call_id,
        "result": result_data,
    }
