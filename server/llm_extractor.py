import json
import os
from typing import Any, Dict

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

client = OpenAI(api_key=OPENAI_API_KEY)


def extract_reservation_result_with_llm(
    transcript: str,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        raise ValueError("Missing OPENAI_API_KEY in environment variables")

    prompt = f"""
    You are extracting the final outcome of a restaurant reservation phone call.

    You are given:
    1. The original reservation request metadata
    2. The final phone call transcript

    Return ONLY valid JSON with exactly these keys:
    - reservation_status
    - restaurant_name
    - reservation_name
    - party_size
    - date
    - requested_time
    - confirmed_time
    - special_requests
    - notes
    - confidence

    Allowed values for reservation_status:
    - confirmed
    - unavailable
    - callback_needed
    - voicemail_left
    - book_online
    - unknown

    Rules:
    - If the requested time was unavailable but another time was accepted and confirmed, set reservation_status to "confirmed" and set confirmed_time to the accepted time.
    - Use the transcript as the source of truth for the final confirmed time.
    - Do not invent details not supported by the transcript or metadata.
    - If no reservation was completed, set confirmed_time to null.
    - confidence should be one of: high, medium, low.
    - Output JSON only, no markdown.

    Metadata:
    {json.dumps(metadata, ensure_ascii=False, indent=2)}

    Transcript:
    {transcript}
    """.strip()

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You extract structured reservation outcomes from call transcripts."},
            {"role": "user", "content": prompt},
        ],
    )

    content = response.choices[0].message.content
    parsed = json.loads(content)

    required_keys = {
        "reservation_status",
        "restaurant_name",
        "reservation_name",
        "party_size",
        "date",
        "requested_time",
        "confirmed_time",
        "special_requests",
        "notes",
        "confidence",
    }

    missing = required_keys - set(parsed.keys())
    if missing:
        raise ValueError(f"LLM extraction missing keys: {sorted(missing)}")

    return parsed