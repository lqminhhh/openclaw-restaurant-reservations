import json
from pathlib import Path
from typing import Any, Dict

from vapi_client import start_outbound_reservation_call

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_request_from_file(path: str) -> Dict[str, Any]:
    request_path = Path(path)
    if not request_path.is_absolute():
        request_path = PROJECT_ROOT / path

    if not request_path.exists():
        raise FileNotFoundError(f"Request file not found: {request_path}")

    return json.loads(request_path.read_text(encoding="utf-8"))


def trigger_reservation_from_file(path: str = "config/sample_request.json") -> Dict[str, Any]:
    request_data = load_request_from_file(path)
    call_result = start_outbound_reservation_call(request_data)

    call_id = (
        call_result.get("id")
        or call_result.get("call", {}).get("id")
        or call_result.get("callId")
    )

    return {
        "ok": True,
        "message": "Reservation call started",
        "call_id": call_id,
        "request": request_data,
        "vapi_response": call_result,
    }


if __name__ == "__main__":
    result = trigger_reservation_from_file()
    print(json.dumps(result, indent=2))