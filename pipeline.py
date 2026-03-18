#!/usr/bin/env python3
"""
Document-to-Calendar Sync Pipeline
====================================
Scans paperless-ngx document directories for new files, extracts event
information using an Ollama LLM, and syncs events to Google Calendar.

Designed to run as an hourly cron job on DockerWolf.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import config
import ollama_client
import text_extractor
import gcal_client

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("pipeline")


# ---------------------------------------------------------------------------
# Processed-files tracker (JSON)
# ---------------------------------------------------------------------------

def load_processed() -> dict:
    """Load the set of already-processed file paths and their metadata."""
    path = Path(config.PROCESSED_LOG)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            logger.warning("Corrupt processed log — starting fresh")
    return {}


def save_processed(data: dict) -> None:
    Path(config.PROCESSED_LOG).write_text(json.dumps(data, indent=2))


def mark_processed(data: dict, filepath: str, events_found: int) -> None:
    data[filepath] = {
        "processed_at": datetime.now().isoformat(),
        "events_found": events_found,
    }


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_new_files(processed: dict) -> list[str]:
    """Walk archive and originals directories, return unprocessed files."""
    new_files = []

    for directory in [config.ARCHIVE_DIR, config.ORIGINALS_DIR]:
        dir_path = Path(directory)
        if not dir_path.exists():
            logger.warning("Directory does not exist: %s", directory)
            continue

        for fpath in dir_path.rglob("*"):
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in config.SUPPORTED_EXTENSIONS:
                continue
            key = str(fpath)
            if key not in processed:
                new_files.append(key)

    logger.info("Found %d new file(s) to process", len(new_files))
    return new_files


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------

def process_file(filepath: str) -> int:
    """
    Process a single document file:
      1. Extract text (PDF text extraction first)
      2. If text is insufficient, try vision-based extraction
      3. Send to LLM to extract events
      4. Check Google Calendar for duplicates
      5. Create new events
    Returns the number of events created/updated.
    """
    logger.info("Processing: %s", filepath)
    path = Path(filepath)
    events_created = 0

    # ----- Step 1: Try text extraction -----
    text = text_extractor.extract_text(filepath)
    events = []

    if text_extractor.is_text_sufficient(text):
        logger.info("Good text extracted (%d chars), using text-based LLM extraction", len(text))
        events = ollama_client.extract_events_from_text(text)
    else:
        logger.info("Insufficient text (%d chars), falling back to vision", len(text))

        # For PDFs, we need to convert to image first for vision
        if path.suffix.lower() == ".pdf":
            image_path = _pdf_to_image(filepath)
            if image_path:
                events = ollama_client.extract_events_from_image(image_path)
                # Clean up temp image
                Path(image_path).unlink(missing_ok=True)
        else:
            # Already an image file
            events = ollama_client.extract_events_from_image(filepath)

    if not events:
        logger.info("No events found in: %s", filepath)
        return 0

    logger.info("Extracted %d event(s) from: %s", len(events), filepath)

    # ----- Step 2: Deduplicate and push to Google Calendar -----
    for event_data in events:
        title = event_data.get("title", "Unknown")
        try:
            existing_id = gcal_client.find_duplicate(event_data)

            if existing_id:
                logger.info("Event '%s' already exists (id: %s) — updating", title, existing_id)
                gcal_client.update_event(existing_id, event_data)
            else:
                logger.info("Creating new event: '%s'", title)
                gcal_client.create_event(event_data)

            events_created += 1
        except Exception as e:
            logger.error("Failed to sync event '%s': %s", title, e)

    return events_created


def _pdf_to_image(pdf_path: str) -> str | None:
    """Convert the first page of a PDF to a temporary PNG for vision extraction."""
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, first_page=1, last_page=1, dpi=200)
        if images:
            tmp_path = f"/tmp/doc_cal_sync_{Path(pdf_path).stem}.png"
            images[0].save(tmp_path, "PNG")
            return tmp_path
    except ImportError:
        logger.error("pdf2image not installed — cannot convert PDF to image for vision fallback")
    except Exception as e:
        logger.error("PDF-to-image conversion failed: %s", e)
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logger.info("=" * 60)
    logger.info("Document-to-Calendar Sync starting")
    logger.info("=" * 60)

    # Load state
    processed = load_processed()
    new_files = discover_new_files(processed)

    if not new_files:
        logger.info("No new files to process. Exiting.")
        return

    # Swap to processing model on JarvisWolf
    logger.info("Preparing Ollama: swapping to %s", config.PROCESSING_MODEL)
    try:
        ollama_client.swap_to_processing_model()
    except Exception as e:
        logger.error("Failed to swap Ollama model: %s", e)
        logger.error("Aborting — cannot proceed without LLM.")
        return

    total_events = 0

    try:
        for filepath in new_files:
            try:
                count = process_file(filepath)
                mark_processed(processed, filepath, count)
                total_events += count
            except Exception as e:
                logger.error("Error processing %s: %s", filepath, e)
                # Still mark it so we don't retry endlessly;
                # mark with -1 to indicate failure
                mark_processed(processed, filepath, -1)

        save_processed(processed)

    finally:
        # Always restore default model, even if we crash
        logger.info("Restoring default Ollama model: %s", config.DEFAULT_MODEL)
        try:
            ollama_client.restore_default_model()
        except Exception as e:
            logger.error("Failed to restore default model: %s", e)

    logger.info("Done. Processed %d file(s), synced %d event(s).", len(new_files), total_events)


if __name__ == "__main__":
    main()
