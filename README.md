# Restaurant Reservation OpenClaw Skill

This repository contains a local OpenClaw skill that starts restaurant reservation phone calls through Vapi, receives the final webhook result through a FastAPI server, stores the result locally, and lets OpenClaw check the result in a follow-up message.

The current MVP flow is:

1. OpenClaw starts the reservation call and returns immediately with a `call_id`
2. Vapi places the outbound call
3. Vapi sends the final webhook result to the local FastAPI server
4. The server stores the final normalized result by `call_id`
5. OpenClaw checks the result later in a second message

## Repo Layout

- `SKILL.md`: OpenClaw skill instructions
- `server/app.py`: FastAPI app with the local HTTP endpoints
- `server/vapi_client.py`: Vapi outbound call client
- `server/webhook_handler.py`: webhook processor and result normalizer
- `server/openclaw_bridge.py`: simple local script to trigger a call from a JSON file
- `prompts/vapi_reservation_prompt.md`: base prompt used for outbound calls
- `config/sample_request.json`: sample reservation request
- `outputs/`: generated raw and normalized call artifacts

## Prerequisites

Install these before setting up the project:

- Python 3.11 or newer
- `ngrok`
- a Vapi account
- an OpenClaw installation that can load local skills
- optionally, a Twilio number or Twilio trial if you want more reliable outbound testing

Notes:

- Free Vapi-managed phone numbers can hit daily outbound limits.
- For real outbound calling, importing your own Twilio number into Vapi is usually more reliable.

## 1. Clone the Repository

```bash
git clone <YOUR_REPO_URL>
cd restaurant-reservation
```

If you are installing this as a local OpenClaw skill, place this folder inside your local OpenClaw `skills/` directory or wherever your OpenClaw installation expects local skills to live.

## 2. Add This Skill to OpenClaw

OpenClaw loads skills from these locations:

1. `<workspace>/skills`
2. `~/.openclaw/skills`
3. any extra directories configured in `~/.openclaw/openclaw.json`

For this project, the simplest option is one of these:

### Option A: Workspace-local skill

Copy or clone this folder into your OpenClaw workspace under:

```bash
<your-openclaw-workspace>/skills/restaurant-reservation
```

This is the best option if you want the skill to be available only in one workspace.

### Option B: Shared local skill

Copy or clone this folder into:

```bash
~/.openclaw/skills/restaurant-reservation
```

This is the best option if you want the skill to be available across multiple OpenClaw workspaces on the same machine.

### Refresh OpenClaw

After placing the folder in one of those locations:

1. restart your OpenClaw session, or
2. ask OpenClaw to refresh skills

OpenClaw should then discover the `restaurant-reservation` skill from `SKILL.md`.

If it still does not appear in the skill list:

- verify the folder name is `restaurant-reservation`
- verify `SKILL.md` exists at the top level of that folder
- verify the YAML frontmatter in `SKILL.md` is valid
- start a new OpenClaw session after copying the skill

## 3. Create and Activate a Virtual Environment

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Upgrade pip if you want:

```bash
python -m pip install --upgrade pip
```

## 4. Install Python Dependencies

Install the project dependencies:

```bash
pip install -r requirements.txt
```

The core runtime dependencies are:

- `fastapi`
- `uvicorn`
- `python-dotenv`
- `requests`

The repo also includes optional helper dependencies for scripts that may still exist in the workspace, such as `openai` and the Google auth libraries.

## 5. Install ngrok

On macOS with Homebrew:

```bash
brew install ngrok
```

Verify it is installed:

```bash
ngrok version
```

If Homebrew is not installed, use the official download page:

<https://ngrok.com/downloads>

## 6. Create Your `.env`

Create a `.env` file in the project root.

Use this template:

```env
VAPI_API_KEY=your_vapi_api_key
VAPI_ASSISTANT_ID=your_vapi_assistant_id
VAPI_PHONE_NUMBER_ID=your_vapi_phone_number_id
VAPI_BASE_URL=https://api.vapi.ai
APP_PORT=3000
RAW_CALLS_DIR=outputs/calls
RESERVATIONS_DIR=outputs/reservations
```

What each variable means:

- `VAPI_API_KEY`: your Vapi API key
- `VAPI_ASSISTANT_ID`: the assistant to use for outbound calls
- `VAPI_PHONE_NUMBER_ID`: the Vapi or imported Twilio phone number used as the outbound caller ID
- `VAPI_BASE_URL`: normally `https://api.vapi.ai`
- `APP_PORT`: local FastAPI port
- `RAW_CALLS_DIR`: folder for selected raw webhook payloads
- `RESERVATIONS_DIR`: folder for normalized reservation results

How to find the Vapi IDs:

- `VAPI_ASSISTANT_ID`: open the assistant in the Vapi dashboard and copy the ID from the URL or assistant details
- `VAPI_PHONE_NUMBER_ID`: open the phone number in the Vapi dashboard and copy the ID from the URL or phone number details

## 7. Configure Vapi

You need three pieces configured in Vapi:

1. an assistant
2. a phone number
3. a server URL for webhooks

### Assistant

Create or reuse a Vapi assistant. The code sends outbound calls with:

- `assistantId`
- `phoneNumberId`
- a runtime system prompt override

### Phone Number

You need a phone number attached to Vapi for outbound calling.

Options:

- a Vapi-managed number
- an imported Twilio number

Important:

- Vapi-managed free numbers can hit daily outbound call limits
- imported Twilio numbers are the safer path for repeated outbound testing

### Server URL / Webhook URL

Your local FastAPI app exposes:

```text
POST /webhook/vapi
```

Once `ngrok` is running, set your Vapi assistant-level server URL to:

```text
https://YOUR-NGROK-URL/webhook/vapi
```

If Vapi uses the label `Server URL` instead of `Webhook URL`, use that field.

## 8. Start the FastAPI Server

From the project root:

```bash
source .venv/bin/activate
cd server
uvicorn app:app --reload --port 3000
```

Expected local endpoints:

- `GET http://localhost:3000/health`
- `POST http://localhost:3000/start-reservation`
- `GET http://localhost:3000/reservation-result/{call_id}`
- `POST http://localhost:3000/webhook/vapi`

Health check:

```bash
curl http://localhost:3000/health
```

## 9. Start ngrok

From another terminal:

```bash
ngrok http 3000
```

Copy the public HTTPS URL and use it in Vapi:

```text
https://YOUR-NGROK-URL/webhook/vapi
```

If you restart ngrok, the URL changes unless you have a reserved domain. Update Vapi when that happens.

## 10. Test the Webhook Locally First

Before testing a real phone call, verify the webhook pipeline.

Run:

```bash
curl -X POST http://localhost:3000/webhook/vapi \
  -H "Content-Type: application/json" \
  -d '{
    "type": "test.webhook",
    "call": {
      "id": "test-call-123",
      "metadata": {
        "restaurant_name": "Test Bistro",
        "restaurant_phone": "+16145551234",
        "reservation_name": "Alex",
        "party_size": 2,
        "date": "2026-03-28",
        "time": "7:00 PM",
        "special_requests": "Indoor seating",
        "user_callback": "+16145550000"
      }
    },
    "analysis": {
      "summary": "Reservation confirmed for 2 people on March 28 at 7:00 PM under Alex."
    }
  }'
```

Then check:

- `outputs/calls/`
- `outputs/reservations/latest.json`
- `outputs/reservations/latest_summary.txt`

## 11. Start a Reservation Call Manually

You can test the backend directly without OpenClaw.

Example:

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
    "user_callback": "+16145550000"
  }'
```

Expected response:

```json
{
  "ok": true,
  "status": "started",
  "call_id": "YOUR_CALL_ID",
  "message": "Reservation call started."
}
```

Then check the result later:

```bash
curl http://localhost:3000/reservation-result/YOUR_CALL_ID
```

If the call is still running, you will get:

```json
{
  "ok": true,
  "status": "pending",
  "call_id": "YOUR_CALL_ID",
  "message": "Reservation result not ready yet."
}
```

If the call is done, you will get:

```json
{
  "ok": true,
  "status": "completed",
  "call_id": "YOUR_CALL_ID",
  "result": {
    "...": "..."
  }
}
```

## 12. Use It Through OpenClaw

This skill is designed for a 2-message MVP.

### Message 1: start the call

Example:

```text
Use the restaurant-reservation skill.

Start a restaurant reservation call using the local backend and return immediately after the call is started.

Reservation details:
- restaurant_name: Dragon Village
- restaurant_phone: +16145551234
- reservation_name: Alex
- party_size: 5
- date: Friday
- preferred_time: 7:00 PM
- fallback_times: 7:30 PM, 8:00 PM, 8:30 PM
- special_requests: Indoor seating if possible
- user_callback: +16145550000

Return:
- whether the call was started
- the call_id
- a short message telling me to ask again later to check the result
```

### Message 2: check the result

Example:

```text
Use the restaurant-reservation skill.

Check the reservation result for the most recent reservation call in this conversation.

If the backend result is still pending, tell me the call is still in progress.
If the backend result is completed, analyze the transcript and return:
- structured JSON for the reservation outcome
- a short plain-English summary
```

### Fallback if no saved `call_id`

Example:

```text
Use the restaurant-reservation skill.

Check the reservation result now.

If there is no saved call_id from this conversation, do not guess. Tell me that you need either:
- a previously started reservation call in this conversation, or
- an explicit call_id to check
```

## 13. Output Files

The server writes these runtime artifacts:

- `outputs/calls/`: selected raw webhook payloads
- `outputs/reservations/latest.json`: latest normalized completed result
- `outputs/reservations/latest_summary.txt`: latest text summary
- `outputs/reservations/by_call_id/<call_id>.json`: per-call normalized result

For OpenClaw, the source of truth is:

```text
GET /reservation-result/{call_id}
```

Do not rely on `latest.json` when a `call_id` is available, because another call may overwrite it.

## Troubleshooting

### `ngrok: command not found`

Install ngrok and verify:

```bash
ngrok version
```

### Vapi returns `Numbers Bought On Vapi Have A Daily Outbound Call Limit`

This usually means you are using a free Vapi-managed number that has hit its daily outbound quota.

Common fixes:

- wait for quota reset
- switch to a different number
- import your own Twilio number into Vapi

### `/reservation-result/{call_id}` stays `pending`

Check:

- FastAPI server is still running
- ngrok is still running
- Vapi server URL points to the current ngrok URL
- the call actually completed

### The transcript is noisy or the reservation name is slightly wrong

Phone transcripts are imperfect. OpenClaw should treat the transcript semantically, but if name fidelity matters for your workflow, tune the Vapi prompt and re-test.

### Call connected but did not reach a restaurant

Double-check the destination number. Test calls to personal numbers or voicemail can still validate the pipeline, but they do not prove a real restaurant reservation flow.

## References

- Python `venv` docs: <https://docs.python.org/3/library/venv.html>
- FastAPI docs: <https://fastapi.tiangolo.com/>
- Uvicorn docs: <https://www.uvicorn.org/>
- python-dotenv docs: <https://pypi.org/project/python-dotenv/>
- Requests docs: <https://requests.readthedocs.io/en/latest/>
- ngrok downloads: <https://ngrok.com/downloads>
- Vapi phone calling overview: <https://docs.vapi.ai/phone-calling>
- Vapi outbound calling: <https://docs.vapi.ai/phone-calling/outbound-calls>
- Vapi server URLs: <https://docs.vapi.ai/server-url>
- Vapi setting server URLs: <https://docs.vapi.ai/server-url/setting-server-urls>
- Vapi import number from Twilio: <https://docs.vapi.ai/phone-numbers/import-twilio/>
- Gmail API Python quickstart: <https://developers.google.com/workspace/gmail/api/quickstart/python>
