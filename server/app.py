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
    return {
        "status": "ok",
        "service": "restaurant-reservation-webhook",
        "port": APP_PORT,
    }


@app.post("/webhook/vapi")
async def vapi_webhook(request: Request):
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