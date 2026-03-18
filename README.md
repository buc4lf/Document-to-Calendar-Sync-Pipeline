Architecture
```
DockerWolf                              JarvisWolf
┌─────────────────────────┐             ┌───────────────────┐
│ paperless-ngx           │             │ Ollama API        │
│ /documents/archive/  ───┼── text ───→ │ gemma3:27b        │
│ /documents/originals/ ──┼── image ──→ │ (multimodal)      │
│                         │             └───────┬───────────┘
│ pipeline.py (cron)      │                     │
│   ├─ text_extractor.py  │     structured JSON │
│   ├─ ollama_client.py ──┼─────────────────────┘
│   ├─ gcal_client.py ────┼──→ Google Calendar API
│   └─ config.py          │
└─────────────────────────┘
```
Processing flow per file:
1) Try text extraction from archive PDF (fast, no LLM needed for OCR)
2) If text is too short/garbled → fall back to sending original image to gemma3:27b via multimodal vision
3) LLM returns structured JSON with event details
4) Check Google Calendar for duplicate events (date + title match)
5) Create new events or update existing ones
6) After all files done: unload multimodal, reload default model

Setup
1. Install Python dependencies
```bash
cd /home/wesley/doc-calendar-sync
pip install -r requirements.txt

# Optional (for vision fallback on scanned PDFs):
sudo apt install tesseract-ocr poppler-utils
pip install pytesseract pdf2image
```
2. Set up Google Calendar API
  A) Go to Google Cloud Console
  B) Create a new project (or select an existing one)
  C) Navigate to APIs & Services → Library
  D) Search for and enable Google Calendar API
  E) Go to APIs & Services → Credentials
  F) Click Create Credentials → OAuth client ID
  G) Select Desktop application, give it a name, click Create
  H) Download the JSON file
  I) Save it as `/home/wesley/doc-calendar-sync/credentials.json`


3. Run the setup helper
```bash
python3 setup_auth.py
```
This will:
Verify Ollama connectivity to JarvisWolf
Check that paperless-ngx directories exist
Walk you through Google OAuth consent (opens a browser)
Check optional dependencies
4. Test a run
```bash
python3 pipeline.py
```
Check the output and `pipeline.log` for results.
5. Set up the cron job
```bash
crontab -e
```
Add this line to run every hour:
```cron
0 * * * * cd /home/wesley/doc-calendar-sync && /usr/bin/python3 pipeline.py >> /home/wesley/doc-calendar-sync/cron.log 2>&1
```
Configuration
Edit `config.py` to customize:
Setting	Default	Description
`OLLAMA_HOST`	`http://JarvisWolf:11434`	Ollama API endpoint
`PROCESSING_MODEL`	`gemma3:27b`	Model for event extraction
`DEFAULT_MODEL`	`qwen3-vl:8b-instruct`	Model to reload after processing
`MIN_TEXT_LENGTH`	`50`	Chars needed before vision fallback
`CALENDAR_ID`	`primary`	Google Calendar to write to
`DUPLICATE_CHECK_DAYS`	`365`	Window for duplicate detection
Files
File	Purpose
`pipeline.py`	Main entry point — file discovery, orchestration
`config.py`	All configurable settings
`ollama_client.py`	Ollama model management + LLM event extraction
`gcal_client.py`	Google Calendar auth, duplicate check, event CRUD
`text_extractor.py`	PDF text extraction + OCR fallback
`setup_auth.py`	Interactive first-time setup helper
`processed_docs.json`	Tracks which files have been processed
`pipeline.log`	Runtime log
Troubleshooting
"Cannot reach Ollama" — Make sure Ollama is running on JarvisWolf and
listening on all interfaces. Check `OLLAMA_HOST` in config.py. You may need
the IP address instead of hostname.
"No events found" — Check `pipeline.log` for the raw LLM response.
The document might not contain recognizable events, or the text extraction
may have failed. Try lowering `MIN_TEXT_LENGTH`.
Duplicate events being created — The duplicate checker matches on date
and title substring. If documents describe the same event with very different
wording, you may need to refine the matching logic in `gcal_client.py`.
"Token expired" — Delete `token.json` and re-run `setup_auth.py` to
re-authenticate with Google.
Failed files — Files that error out are marked with `events_found: -1`
in `processed_docs.json`. Delete that entry to retry them on the next run.
