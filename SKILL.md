---
name: restaurant-reservation
description: Use this skill when the user wants to book a table, make a restaurant reservation, call a restaurant to check availability, or place a dining reservation by phone. This MVP version starts the reservation call immediately, returns right away, and checks the final result in a follow-up user message.
---

# Restaurant Reservation

## Overview

This skill handles restaurant reservation phone calls through a local backend and Vapi.

This MVP uses a simple 2-message flow:

1. First message: start the reservation call
2. Second message: check the final result

This design keeps the interaction simple and avoids making OpenClaw wait while the phone call is still in progress.

## Trigger Condition

Trigger this skill when the user wants to:

- book a table
- make a restaurant reservation
- call a restaurant to reserve a table
- check restaurant availability by phone
- place a dining reservation through a phone call

Trigger this skill only when the request is specifically about a restaurant reservation phone call that should use the local backend and Vapi flow.

Do not trigger this skill for:

- inbound call flows
- non-restaurant phone calls
- restaurant research without placing a call
- general scheduling unrelated to dining reservations

## MVP Interaction Model

This skill should be used in 2 steps.

### Step 1: Start the call

When the user provides reservation details, OpenClaw should:

1. Collect the required reservation information
2. Call the local backend endpoint:
   - `POST http://localhost:3000/start-reservation`
3. Save the returned `call_id`
4. Return immediately to the user

OpenClaw should not wait for the full phone call to finish in the same response.

Suggested response style:

> I started the reservation call for the restaurant. Ask me again shortly and I’ll check the result.

### Step 2: Check the result

When the user follows up with something like:

- “check the reservation result”
- “did the restaurant confirm?”
- “what happened with the reservation?”

OpenClaw should:

1. Reuse the most recent saved `call_id` from this conversation
2. Call the local backend endpoint:
   - `GET http://localhost:3000/reservation-result/{call_id}`
3. If the backend returns `pending`, tell the user the call is still in progress
4. If the backend returns `completed`, analyze the transcript and return the final reservation outcome

## Inputs

The skill expects the following fields when starting a reservation:

- `restaurant_name`
- `restaurant_phone`
- `reservation_name`
- `party_size`
- `date`
- `preferred_time`
- `fallback_times`
- `special_requests`
- `user_callback`

Example input:

```json
{
  "restaurant_name": "Dragon Village",
  "restaurant_phone": "+16145551234",
  "reservation_name": "Alex",
  "party_size": 5,
  "date": "Friday",
  "preferred_time": "7:00 PM",
  "fallback_times": ["7:30 PM", "8:00 PM", "8:30 PM"],
  "special_requests": "Indoor seating if possible",
  "user_callback": "+17404048938"
}
```

## Backend API Flow

### Start reservation

OpenClaw sends:

```bash
curl -X POST http://localhost:3000/start-reservation \
  -H "Content-Type: application/json" \
  -d '{
    "restaurant_name": "Dragon Village",
    "restaurant_phone": "+16145551234",
    "reservation_name": "Alex",
    "party_size": 5,
    "date": "Friday",
    "preferred_time": "7:00 PM",
    "fallback_times": ["7:30 PM", "8:00 PM", "8:30 PM"],
    "special_requests": "Indoor seating if possible",
    "user_callback": "+17404048938"
  }'
```

Example response:

```json
{
  "ok": true,
  "status": "started",
  "call_id": "019d3081-418d-7000-afe9-0e38881c0ee4",
  "message": "Reservation call started."
}
```

### Check reservation result

OpenClaw sends:

```bash
curl http://localhost:3000/reservation-result/YOUR_CALL_ID
```

If the call is still in progress, the backend returns:

```json
{
  "ok": true,
  "status": "pending",
  "call_id": "019d3081-418d-7000-afe9-0e38881c0ee4",
  "message": "Reservation result not ready yet."
}
```

If the call has finished, the backend returns:

```json
{
  "ok": true,
  "status": "completed",
  "call_id": "019d3081-418d-7000-afe9-0e38881c0ee4",
  "result": {
    "call_id": "019d3081-418d-7000-afe9-0e38881c0ee4",
    "status": "completed",
    "event_type": "end-of-call-report",
    "request": {
      "restaurant_name": "Dragon Village",
      "restaurant_phone": "+16145551234",
      "reservation_name": "Alex",
      "party_size": 5,
      "date": "Friday",
      "preferred_time": "7:00 PM",
      "fallback_times": ["7:30 PM", "8:00 PM", "8:30 PM"],
      "special_requests": "Indoor seating if possible",
      "user_callback": "+17404048938"
    },
    "transcript": "assistant: ...\nuser: ...",
    "summary": null,
    "assistant_name": "Restaurant Reservation Agent",
    "customer_number": "+17404048938",
    "vapi_number": "+16504510603",
    "received_at": "2026-03-27T19:51:17.466710+00:00"
  }
}
```

## How OpenClaw Should Interpret the Completed Result

When the backend returns `status: completed`, OpenClaw should analyze:

- the original request inside `result.request`
- the final call transcript inside `result.transcript`
- the optional `result.summary`, if available

OpenClaw should then return structured JSON with these keys:

- `reservation_status`
- `restaurant_name`
- `reservation_name`
- `party_size`
- `date`
- `requested_time`
- `confirmed_time`
- `special_requests`
- `notes`
- `confidence`

Allowed values for `reservation_status`:

- `confirmed`
- `unavailable`
- `callback_needed`
- `voicemail_left`
- `book_online`
- `unknown`

Suggested interpretation instruction:

```text
You are analyzing the final result of a restaurant reservation phone call.

You are given:
1. The original reservation request
2. The final phone call transcript
3. Optional summary metadata

Your task is to determine the final reservation outcome and return structured JSON.

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
- Use the transcript as the source of truth for the final outcome.
- Interpret noisy phone transcripts semantically rather than literally.
- Use the summary only if it helps clarify the transcript.
- Use request metadata for unchanged reservation fields.
- If the requested time was unavailable but another time was accepted and confirmed, set reservation_status to "confirmed" and set confirmed_time to the accepted time.
- If no reservation was completed, set confirmed_time to null.
- Do not invent details not supported by the transcript or request.
- confidence must be one of: high, medium, low.
- Output JSON only.
```

## Conversation Memory Requirement

OpenClaw should save the returned `call_id` from the first message and reuse it in the follow-up message.

For this MVP, the follow-up message should check the most recent reservation call in the current conversation unless the user explicitly refers to a different `call_id`.



## Main Scripts Used

### `server/app.py`
Main backend entrypoint used by OpenClaw.

Responsible for:
- health check
- starting reservation calls
- returning reservation results
- receiving Vapi webhooks

### `server/vapi_client.py`
Internal helper used by the backend to:
- build the runtime reservation prompt
- create outbound Vapi calls
- attach metadata to the call

### `server/webhook_handler.py`
Internal helper used by the backend to:
- process final Vapi webhooks
- extract transcript + metadata
- store results by `call_id`

## Local Setup

### Start backend

```bash
cd skills/restaurant-reservation/server
uvicorn app:app --reload --port 3000
```

### Start ngrok

```bash
ngrok http 3000
```

### Configure Vapi webhook URL

Set the Vapi server/webhook URL to:

```text
https://YOUR-NGROK-URL/webhook/vapi
```



## Outputs

The backend writes results to:

- `outputs/calls/` — selected raw webhook events
- `outputs/reservations/latest.json` — latest completed result
- `outputs/reservations/latest_summary.txt` — latest human-readable summary
- `outputs/reservations/by_call_id/<call_id>.json` — per-call result for OpenClaw lookup

OpenClaw should use `GET /reservation-result/{call_id}` as the source of truth for the final result instead of relying on `latest.json`.



## Expected Final Behavior

The intended MVP flow is:

`user provides reservation info -> OpenClaw starts the call and returns immediately -> user follows up to check result -> OpenClaw fetches the stored result -> OpenClaw interprets the transcript and returns whether the restaurant confirmed or not`



## Notes

- This skill intentionally uses a 2-message interaction because phone calls are asynchronous.
- OpenClaw should not block while waiting for the call to finish.
- The backend is responsible for calling and storing results.
- OpenClaw is responsible for the final semantic interpretation shown to the user.
