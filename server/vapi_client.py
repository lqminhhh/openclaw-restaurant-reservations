import json
import os
from pathlib import Path
from typing import Any, Dict

import requests
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = PROJECT_ROOT / "prompts" / "vapi_reservation_prompt.md"

VAPI_API_KEY = os.getenv("VAPI_API_KEY")
VAPI_BASE_URL = os.getenv("VAPI_BASE_URL", "https://api.vapi.ai")
VAPI_ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID")
VAPI_PHONE_NUMBER_ID = os.getenv("VAPI_PHONE_NUMBER_ID")

def load_prompt_template() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "You are a polite and concise AI phone assistant calling a restaurant "
        "to make a reservation."
    )


def build_runtime_prompt(request_data: Dict[str, Any]) -> str:
    base_prompt = load_prompt_template()

    restaurant_name = request_data["restaurant_name"]
    reservation_name = request_data["reservation_name"]
    party_size = request_data["party_size"]
    date = request_data["date"]
    preferred_time = request_data["preferred_time"]
    fallback_times = request_data.get("fallback_times", [])
    special_requests = request_data.get("special_requests", "")
    user_callback = request_data.get("user_callback", "")

    fallback_text = ", ".join(fallback_times) if fallback_times else "No fallback times provided."
    special_request_text = special_requests if special_requests else "None"
    callback_text = user_callback if user_callback else "Not provided"

    runtime_block = f"""
    Reservation details for this call:
    - Restaurant: {restaurant_name}
    - Reservation name: {reservation_name}
    - Party size: {party_size}
    - Requested date: {date}
    - Preferred time: {preferred_time}
    - Fallback times: {fallback_text}
    - Special requests: {special_request_text}
    - Callback number: {callback_text}

    Instructions for this specific call:
    - You are calling {restaurant_name}.
    - Request a reservation for {party_size} people under the name {reservation_name}.
    - Ask for {date} at {preferred_time}.
    - If unavailable, try fallback times one at a time in this order: {fallback_text}
    - Mention special requests only if appropriate.
    - Do not invent confirmation details.
    - Before ending, clearly restate the final outcome.
    """

    return base_prompt.strip() + "\n" + runtime_block.strip()


def validate_request_data(request_data: Dict[str, Any]) -> None:
    required_fields = [
        "restaurant_name",
        "restaurant_phone",
        "reservation_name",
        "party_size",
        "date",
        "preferred_time",
    ]
    missing = [field for field in required_fields if not request_data.get(field)]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    if not VAPI_API_KEY:
        raise ValueError("Missing VAPI_API_KEY in environment variables")

    if not VAPI_ASSISTANT_ID:
        raise ValueError("Missing VAPI_ASSISTANT_ID in environment variables")

    if not VAPI_PHONE_NUMBER_ID:
        raise ValueError("Missing VAPI_PHONE_NUMBER_ID in environment variables")


def start_outbound_reservation_call(request_data: Dict[str, Any]) -> Dict[str, Any]:
    validate_request_data(request_data)

    runtime_prompt = build_runtime_prompt(request_data)

    headers = {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "assistantId": VAPI_ASSISTANT_ID,
        "phoneNumberId": VAPI_PHONE_NUMBER_ID,
        "customer": {
            "number": request_data["restaurant_phone"]
        },
        "assistantOverrides": {
            "model": {
                "provider": "openai",
                "model": "gpt-4.1",
                "messages": [
                    {
                        "role": "system",
                        "content": runtime_prompt
                    }
                ]
            }
        },
        "metadata": {
            "restaurant_name": request_data.get("restaurant_name"),
            "restaurant_phone": request_data.get("restaurant_phone"),
            "reservation_name": request_data.get("reservation_name"),
            "party_size": request_data.get("party_size"),
            "date": request_data.get("date"),
            "time": request_data.get("preferred_time"),
            "preferred_time": request_data.get("preferred_time"),
            "fallback_times": request_data.get("fallback_times", []),
            "special_requests": request_data.get("special_requests"),
            "user_callback": request_data.get("user_callback"),
        }
    }

    response = requests.post(
        f"{VAPI_BASE_URL}/call",
        headers=headers,
        json=payload,
        timeout=30,
    )

    try:
        response_data = response.json()
    except Exception:
        response_data = {"raw_text": response.text}

    if not response.ok:
        raise RuntimeError(
            f"Vapi call creation failed: {response.status_code} - {response_data}"
        )

    return response_data


if __name__ == "__main__":
    sample_path = PROJECT_ROOT / "config" / "sample_request.json"
    data = json.loads(sample_path.read_text(encoding="utf-8"))
    result = start_outbound_reservation_call(data)
    print(json.dumps(result, indent=2))