"""
Configuration for Document-to-Calendar Sync Pipeline
=====================================================
Edit these values to match your environment.
"""

# ---------------------------------------------------------------------------
# Paperless-ngx document paths (on DockerWolf)
# ---------------------------------------------------------------------------
ARCHIVE_DIR = "/home/wesley/docker/paperlessngx/media/documents/archive"
ORIGINALS_DIR = "/home/wesley/docker/paperlessngx/media/documents/originals"

# ---------------------------------------------------------------------------
# Ollama settings (on JarvisWolf)
# ---------------------------------------------------------------------------
OLLAMA_HOST = "http://JarvisWolf:11434"  # Change to IP if hostname doesn't resolve
PROCESSING_MODEL = "gemma3:27b"
DEFAULT_MODEL = "qwen3-vl:8b-instruct"  # Model to reload after processing

# Minimum characters of extracted text before we fall back to vision/image mode
MIN_TEXT_LENGTH = 50

# ---------------------------------------------------------------------------
# Google Calendar
# ---------------------------------------------------------------------------
GOOGLE_CREDENTIALS_FILE = "/home/wesley/doc-calendar-sync/credentials.json"
GOOGLE_TOKEN_FILE = "/home/wesley/doc-calendar-sync/token.json"
CALENDAR_ID = "primary"  # or a specific calendar ID

# Scopes needed for the Google Calendar API
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar"]

# ---------------------------------------------------------------------------
# Processing state
# ---------------------------------------------------------------------------
PROCESSED_LOG = "/home/wesley/doc-calendar-sync/processed_docs.json"
LOG_FILE = "/home/wesley/doc-calendar-sync/pipeline.log"

# ---------------------------------------------------------------------------
# Pipeline behavior
# ---------------------------------------------------------------------------
# How many days into the future to consider for duplicate checking
DUPLICATE_CHECK_DAYS = 365

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}
