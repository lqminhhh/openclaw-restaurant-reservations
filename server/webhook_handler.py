"""Normalize incoming Vapi webhook payloads into stable local reservation artifacts.

This module filters noisy events, extracts transcript and metadata from final call events,
derives a simplified reservation result, and writes the result to local output files.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_CALLS_DIR = PROJECT_ROOT / os.getenv("RAW_CALLS_DIR", "outputs/calls")
RESERVATIONS_DIR = PROJECT_ROOT / os.getenv("RESERVATIONS_DIR", "outputs/reservations")

RAW_CALLS_DIR.mkdir(parents=True, exist_ok=True)
RESERVATIONS_DIR.mkdir(parents=True, exist_ok=True)

FINAL_EVENT_TYPES = {
    "call.completed",
    "call.ended",
    "end-of-call-report",
    "call_summary",
}

IMPORTANT_RAW_EVENT_TYPES = {
    "assistant_started",
    "status-update",
    "user-interrupted",
    "end-of-call-report",
    "call.completed",
    "call.ended",
    "call_summary",
}

NOISY_EVENT_TYPES = {
    "speech-update",
    "conversation-update",
}


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format.

    Parameters:
        None.
    Returns:
        str: The current UTC timestamp formatted as an ISO string.
    """
    return datetime.now(timezone.utc).isoformat()


def timestamp_slug() -> str:
    """Create a filesystem-safe UTC timestamp string for output filenames.

    Parameters:
        None.
    Returns:
        str: A compact UTC timestamp including microseconds.
    """
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def safe_get(obj: Any, path: list[str], default: Any = None) -> Any:
    """Safely walk a nested dictionary path and return a default when the path is missing.

    Parameters:
        obj (Any): The starting object, usually a parsed webhook payload.
        path (list[str]): The ordered list of dictionary keys to follow.
        default (Any): The fallback value to return if the path cannot be fully resolved.
    Returns:
        Any: The resolved nested value or the provided default.
    """
    current = obj
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def write_json(path: Path, data: Dict[str, Any]) -> None:
    """Write a dictionary to disk as pretty-printed JSON.

    Parameters:
        path (Path): Destination path for the JSON file.
        data (Dict[str, Any]): The dictionary to serialize.
    Returns:
        None: The function writes the file to disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def write_text(path: Path, content: str) -> None:
    """Write plain text content to disk, creating parent directories if needed.

    Parameters:
        path (Path): Destination path for the text file.
        content (str): Text content to write.
    Returns:
        None: The function writes the file to disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def extract_event_type(payload: Dict[str, Any]) -> str:
    """Extract the most useful event type label from a webhook payload.

    Parameters:
        payload (Dict[str, Any]): The parsed webhook payload from Vapi.
    Returns:
        str: The best available event type string, or `unknown` if one cannot be found.
    """
    return str(
        safe_get(payload, ["message", "type"])
        or payload.get("type")
        or "unknown"
    )


def extract_call_id(payload: Dict[str, Any]) -> Optional[str]:
    """Extract the Vapi call ID from the various payload shapes seen in webhook events.

    Parameters:
        payload (Dict[str, Any]): The parsed webhook payload from Vapi.
    Returns:
        Optional[str]: The call ID if one is present, otherwise `None`.
    """
    call_id = (
        safe_get(payload, ["message", "call", "id"])
        or safe_get(payload, ["call", "id"])
        or safe_get(payload, ["message", "artifact", "variableValues", "call", "id"])
        or safe_get(payload, ["message", "artifact", "variables", "call", "id"])
        or payload.get("callId")
        or payload.get("id")
    )
    return str(call_id) if call_id else None


def extract_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract reservation metadata and call-level numbers from a webhook payload.

    Parameters:
        payload (Dict[str, Any]): The parsed webhook payload from Vapi.
    Returns:
        Dict[str, Any]: A normalized metadata dictionary used by later summary and persistence steps.
    """
    metadata = (
        safe_get(payload, ["message", "call", "metadata"])
        or safe_get(payload, ["call", "metadata"])
        or safe_get(payload, ["message", "metadata"])
        or payload.get("metadata")
        or {}
    )

    if not isinstance(metadata, dict):
        metadata = {}

    customer_number = (
        safe_get(payload, ["message", "customer", "number"])
        or safe_get(payload, ["message", "call", "customer", "number"])
        or safe_get(payload, ["customer", "number"])
    )

    vapi_number = (
        safe_get(payload, ["message", "phoneNumber", "number"])
        or safe_get(payload, ["phoneNumber", "number"])
    )

    assistant_name = (
        safe_get(payload, ["message", "assistant", "name"])
        or safe_get(payload, ["assistant", "name"])
    )

    return {
        "restaurant_name": metadata.get("restaurant_name"),
        "restaurant_phone": metadata.get("restaurant_phone"),
        "reservation_name": metadata.get("reservation_name"),
        "party_size": metadata.get("party_size"),
        "date": metadata.get("date"),
        "requested_time": metadata.get("time") or metadata.get("preferred_time"),
        "fallback_times": metadata.get("fallback_times"),
        "special_requests": metadata.get("special_requests"),
        "user_callback": metadata.get("user_callback"),
        "customer_number": customer_number,
        "vapi_number": vapi_number,
        "assistant_name": assistant_name,
    }


def extract_conversation_messages(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Pull the raw conversation message list from any supported payload location.

    Parameters:
        payload (Dict[str, Any]): The parsed webhook payload from Vapi.
    Returns:
        list[Dict[str, Any]]: The message list if found, otherwise an empty list.
    """
    messages = (
        safe_get(payload, ["message", "artifact", "messages"])
        or safe_get(payload, ["message", "messages"])
        or safe_get(payload, ["artifact", "messages"])
        or safe_get(payload, ["messages"])
        or []
    )
    return messages if isinstance(messages, list) else []


def normalize_role(role: Optional[str]) -> str:
    """Normalize message role names into the local transcript format.

    Parameters:
        role (Optional[str]): The original role label from the webhook message.
    Returns:
        str: A normalized role label such as `assistant`, `user`, or `unknown`.
    """
    if not role:
        return "unknown"
    role = role.lower()
    if role == "bot":
        return "assistant"
    return role


def find_transcript(payload: Dict[str, Any]) -> Optional[str]:
    """Convert the message list inside a webhook payload into a plain-text transcript.

    Parameters:
        payload (Dict[str, Any]): The parsed webhook payload from Vapi.
    Returns:
        Optional[str]: A newline-delimited transcript string, or `None` if no messages are available.
    """
    messages = extract_conversation_messages(payload)
    if not messages:
        return None

    lines = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue

        role = normalize_role(msg.get("role"))

        if role == "system":
            continue

        text = msg.get("message") or msg.get("content")
        if isinstance(text, str) and text.strip():
            lines.append(f"{role}: {text.strip()}")

    return "\n".join(lines) if lines else None


def find_summary(payload: Dict[str, Any]) -> Optional[str]:
    """Extract any summary text already attached to the webhook payload.

    Parameters:
        payload (Dict[str, Any]): The parsed webhook payload from Vapi.
    Returns:
        Optional[str]: The first non-empty summary string found, or `None`.
    """
    candidates = [
        safe_get(payload, ["message", "analysis", "summary"]),
        safe_get(payload, ["message", "summary"]),
        safe_get(payload, ["analysis", "summary"]),
        safe_get(payload, ["summary"]),
    ]

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    return None


def classify_status(summary: Optional[str], transcript: Optional[str]) -> str:
    """Infer a simplified reservation outcome label from the summary and transcript text.

    Parameters:
        summary (Optional[str]): Summary text extracted from the webhook payload, if available.
        transcript (Optional[str]): Plain-text transcript extracted from the webhook payload, if available.
    Returns:
        str: One of the local status labels such as `confirmed`, `unavailable`, or `unknown`.
    """
    text = " ".join([summary or "", transcript or ""]).lower()

    confirmed_phrases = [
        "reservation is confirmed",
        "confirmed",
        "all set",
        "booked",
        "we have you down",
        "it's booked",
        "you are booked",
        "reservation is set",
        "it works for",
        "we can get your reservation",
        "we can make that possible",
        "we got all the information",
        "see you there",
        "that works"
    ]

    unavailable_phrases = [
        "unavailable",
        "no availability",
        "fully booked",
        "no tables",
        "nothing available",
        "we don't have anything",
        "not available",
        "still not working",
    ]

    if any(phrase in text for phrase in confirmed_phrases):
        return "confirmed"

    if any(phrase in text for phrase in unavailable_phrases):
        return "unavailable"

    if any(phrase in text for phrase in [
        "voicemail",
        "leave a message",
        "left a message",
    ]):
        return "voicemail_left"

    if any(phrase in text for phrase in [
        "book online",
        "online only",
        "use our website",
        "website only",
    ]):
        return "book_online"

    if any(phrase in text for phrase in [
        "call back",
        "callback",
        "call us back",
    ]):
        return "callback_needed"

    return "unknown"


def should_normalize_event(event_type: str, payload: Dict[str, Any]) -> bool:
    """Decide whether a webhook event contains enough signal to produce a normalized result.

    Parameters:
        event_type (str): The extracted event type label for the webhook payload.
        payload (Dict[str, Any]): The parsed webhook payload from Vapi.
    Returns:
        bool: `True` when the event should generate or update a normalized reservation artifact.
    """
    if event_type in FINAL_EVENT_TYPES:
        return True

    call_status = (
        safe_get(payload, ["message", "call", "status"])
        or safe_get(payload, ["call", "status"])
        or ""
    )
    if isinstance(call_status, str) and call_status.lower() in {"ended", "completed"}:
        return True

    return False


def should_save_raw_event(event_type: str, payload: Dict[str, Any]) -> bool:
    """Decide whether a raw webhook payload should be written to the raw events folder.

    Parameters:
        event_type (str): The extracted event type label for the webhook payload.
        payload (Dict[str, Any]): The parsed webhook payload from Vapi.
    Returns:
        bool: `True` when the raw payload is useful enough to save for debugging.
    """
    if event_type in IMPORTANT_RAW_EVENT_TYPES:
        return True

    if event_type in NOISY_EVENT_TYPES:
        return False

    call_status = (
        safe_get(payload, ["message", "call", "status"])
        or safe_get(payload, ["call", "status"])
        or ""
    )
    if isinstance(call_status, str) and call_status.lower() in {"ended", "completed"}:
        return True

    return False


def sanitize_filename(value: str) -> str:
    """Convert an arbitrary string into a filesystem-safe filename fragment.

    Parameters:
        value (str): The original string value to sanitize.
    Returns:
        str: A version of the string containing only alphanumeric characters, hyphens, underscores, and substitutions.
    """
    return "".join(c if c.isalnum() or c in {"-", "_"} else "_" for c in value)


def normalize_time_string(t: str) -> str:
    """Normalize a loosely formatted time string into a more consistent display format.

    Parameters:
        t (str): The original time string extracted from transcript text.
    Returns:
        str: A normalized time string with consistent spacing and AM/PM capitalization.
    """
    t = t.strip()
    t = re.sub(r"\s+", " ", t)
    t = t.replace("am", "AM").replace("pm", "PM").replace("Am", "AM").replace("Pm", "PM")
    if re.match(r"^\d{1,2}(?::\d{2})?(AM|PM)$", t):
        t = t[:-2] + " " + t[-2:]
    return t


def find_time_mentions(text: str) -> list[str]:
    """Extract time mentions from transcript text using numeric and simple word-based patterns.

    Parameters:
        text (str): Transcript text to scan for time references.
    Returns:
        list[str]: A de-duplicated list of normalized time mentions in discovery order.
    """
    numeric = re.findall(r"\b(?:[1-9]|1[0-2])(?::[0-5][0-9])?\s?(?:AM|PM|am|pm)\b", text)
    word_map = {
        "one": "1:00 PM",
        "two": "2:00 PM",
        "three": "3:00 PM",
        "four": "4:00 PM",
        "five": "5:00 PM",
        "six": "6:00 PM",
        "seven": "7:00 PM",
        "eight": "8:00 PM",
        "nine": "9:00 PM",
        "ten": "10:00 PM",
        "eleven": "11:00 PM",
        "twelve": "12:00 PM",
    }

    word_based = []
    lowered = text.lower()
    for word, mapped in word_map.items():
        if re.search(rf"\b{word}\s*(pm|p\.m\.)\b", lowered):
            word_based.append(mapped)

    results = [normalize_time_string(x) for x in numeric] + word_based

    seen = []
    for t in results:
        if t not in seen:
            seen.append(t)
    return seen


def extract_confirmed_time(transcript: Optional[str], requested_time: Optional[str]) -> Optional[str]:
    """Infer the most likely confirmed reservation time from the transcript.

    Parameters:
        transcript (Optional[str]): The call transcript text, if available.
        requested_time (Optional[str]): The original requested reservation time from metadata.
    Returns:
        Optional[str]: The inferred confirmed time, or the requested time / `None` when no better signal is found.
    """
    if not transcript:
        return requested_time

    lines = transcript.splitlines()

    confirmation_keywords = [
        "confirmed",
        "reservation is set",
        "reservation is confirmed",
        "works for",
        "that works",
        "we can get your reservation",
        "we can make that possible",
        "we got all the information",
        "see you there",
        "just to confirm",
    ]

    candidate_lines = []
    for line in lines:
        lower = line.lower()
        if any(k in lower for k in confirmation_keywords):
            candidate_lines.append(line)

    for line in reversed(candidate_lines):
        mentions = find_time_mentions(line)
        if mentions:
            return mentions[-1]

    all_mentions = find_time_mentions(transcript)
    if all_mentions:
        if requested_time and len(all_mentions) > 1:
            for t in reversed(all_mentions):
                if normalize_time_string(t) != normalize_time_string(requested_time):
                    return t
        return all_mentions[-1]

    return requested_time

def build_summary_text(normalized: Dict[str, Any]) -> str:
    """Build a human-readable text summary from a normalized reservation result.

    Parameters:
        normalized (Dict[str, Any]): The normalized reservation artifact written by this module.
    Returns:
        str: A plain-text summary suitable for quick inspection.
    """
    request = normalized.get("request", {}) or {}

    lines = [
        f"Reservation status: {normalized.get('status') or 'Unknown'}",
        f"Restaurant: {request.get('restaurant_name') or 'Unknown'}",
        f"Reservation name: {request.get('reservation_name') or 'Unknown'}",
        f"Party size: {request.get('party_size') or 'Unknown'}",
        f"Date: {request.get('date') or 'Unknown'}",
        f"Requested time: {request.get('preferred_time') or 'Unknown'}",
        f"Fallback times: {', '.join(request.get('fallback_times', [])) if request.get('fallback_times') else 'None'}",
        f"Special requests: {request.get('special_requests') or 'None'}",
        f"Callback number: {request.get('user_callback') or 'Unknown'}",
        "",
        "Transcript:",
        normalized.get("transcript") or "No transcript available.",
    ]
    return "\n".join(lines)

def process_vapi_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Process a Vapi webhook payload and update local raw and normalized artifacts.

    Parameters:
        payload (Dict[str, Any]): The parsed webhook payload sent by Vapi.
    Returns:
        Dict[str, Any]: A summary of what was saved, including file paths, event type, call ID, and normalization status.
    """
    ts = timestamp_slug()
    event_type = extract_event_type(payload)
    call_id = extract_call_id(payload) or f"no_call_id_{ts}"

    safe_event_type = sanitize_filename(event_type)
    safe_call_id = sanitize_filename(call_id)

    raw_path = None
    if should_save_raw_event(event_type, payload):
        raw_filename = f"{ts}_{safe_call_id}_{safe_event_type}.json"
        raw_path = RAW_CALLS_DIR / raw_filename
        write_json(raw_path, payload)

    if not should_normalize_event(event_type, payload):
        return {
            "raw_file": str(raw_path) if raw_path else None,
            "normalized_file": None,
            "event_type": event_type,
            "call_id": call_id,
            "skipped_normalization": True,
        }

    summary = find_summary(payload)
    transcript = find_transcript(payload)
    metadata = extract_metadata(payload)
    status = classify_status(summary, transcript)

    requested_time = metadata.get("requested_time")
    confirmed_time = extract_confirmed_time(transcript, requested_time)

    normalized = {
        "call_id": call_id,
        "status": "completed",
        "event_type": event_type,
        "request": {
            "restaurant_name": metadata.get("restaurant_name"),
            "restaurant_phone": metadata.get("restaurant_phone"),
            "reservation_name": metadata.get("reservation_name"),
            "party_size": metadata.get("party_size"),
            "date": metadata.get("date"),
            "preferred_time": metadata.get("requested_time"),
            "fallback_times": metadata.get("fallback_times"),
            "special_requests": metadata.get("special_requests"),
            "user_callback": metadata.get("user_callback"),
        },
        "transcript": transcript,
        "summary": summary,
        "assistant_name": metadata.get("assistant_name"),
        "customer_number": metadata.get("customer_number"),
        "vapi_number": metadata.get("vapi_number"),
        "received_at": utc_now_iso(),
    }
    by_call_id_dir = RESERVATIONS_DIR / "by_call_id"
    by_call_id_dir.mkdir(parents=True, exist_ok=True)

    normalized_timestamped_path = RESERVATIONS_DIR / f"{ts}_{safe_call_id}.json"
    normalized_latest_path = RESERVATIONS_DIR / "latest.json"
    summary_latest_path = RESERVATIONS_DIR / "latest_summary.txt"
    normalized_by_call_id_path = by_call_id_dir / f"{call_id}.json"

    write_json(normalized_timestamped_path, normalized)
    write_json(normalized_latest_path, normalized)
    write_json(normalized_by_call_id_path, normalized)
    write_text(summary_latest_path, build_summary_text(normalized))

    return {
        "raw_file": str(raw_path) if raw_path else None,
        "normalized_file": str(normalized_latest_path),
        "summary_file": str(summary_latest_path),
        "event_type": event_type,
        "call_id": call_id,
        "skipped_normalization": False,
    }
