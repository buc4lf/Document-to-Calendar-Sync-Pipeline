#!/usr/bin/env python3
"""
First-time setup helper for Document-to-Calendar Sync.

Run this interactively to:
  1. Verify Ollama connectivity
  2. Verify paperless-ngx directory access
  3. Complete Google OAuth consent flow
  4. Install optional dependencies
"""

import subprocess
import sys
from pathlib import Path

import config


def check_ollama():
    print("\n[1/4] Checking Ollama connectivity...")
    try:
        import requests
        resp = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=10)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        print(f"  ✓ Ollama is reachable at {config.OLLAMA_HOST}")
        print(f"  ✓ Available models: {', '.join(models)}")
        if config.PROCESSING_MODEL not in models:
            print(f"  ⚠ Processing model '{config.PROCESSING_MODEL}' not found!")
            print(f"    Run: ollama pull {config.PROCESSING_MODEL}")
        if config.DEFAULT_MODEL not in models:
            print(f"  ⚠ Default model '{config.DEFAULT_MODEL}' not found!")
            print(f"    Run: ollama pull {config.DEFAULT_MODEL}")
    except Exception as e:
        print(f"  ✗ Cannot reach Ollama: {e}")
        print(f"    Make sure Ollama is running on JarvisWolf and accessible at {config.OLLAMA_HOST}")


def check_directories():
    print("\n[2/4] Checking paperless-ngx directories...")
    for name, path in [("Archive", config.ARCHIVE_DIR), ("Originals", config.ORIGINALS_DIR)]:
        p = Path(path)
        if p.exists():
            count = sum(1 for f in p.rglob("*") if f.is_file() and f.suffix.lower() in config.SUPPORTED_EXTENSIONS)
            print(f"  ✓ {name}: {path} ({count} supported files)")
        else:
            print(f"  ✗ {name}: {path} — NOT FOUND")


def check_google_auth():
    print("\n[3/4] Setting up Google Calendar authentication...")
    creds_path = Path(config.GOOGLE_CREDENTIALS_FILE)
    if not creds_path.exists():
        print(f"  ✗ Credentials file not found: {config.GOOGLE_CREDENTIALS_FILE}")
        print()
        print("  To set up Google Calendar API access:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Create a new project (or select existing)")
        print("  3. Enable the 'Google Calendar API'")
        print("  4. Go to 'Credentials' → 'Create Credentials' → 'OAuth client ID'")
        print("  5. Choose 'Desktop application'")
        print("  6. Download the JSON file")
        print(f"  7. Save it as: {config.GOOGLE_CREDENTIALS_FILE}")
        print()
        print("  Then re-run this setup script.")
        return

    print(f"  ✓ Credentials file found: {config.GOOGLE_CREDENTIALS_FILE}")

    token_path = Path(config.GOOGLE_TOKEN_FILE)
    if token_path.exists():
        print(f"  ✓ Token already exists: {config.GOOGLE_TOKEN_FILE}")
        print("    (delete this file to re-authenticate)")
    else:
        print("  → Opening browser for Google consent flow...")
        try:
            import gcal_client
            service = gcal_client.get_service()
            # Quick test: list calendars
            cals = service.calendarList().list().execute()
            names = [c.get("summary", "?") for c in cals.get("items", [])]
            print(f"  ✓ Authenticated! Available calendars: {', '.join(names)}")
        except Exception as e:
            print(f"  ✗ Authentication failed: {e}")


def check_optional_deps():
    print("\n[4/4] Checking optional dependencies...")

    # Tesseract
    try:
        result = subprocess.run(["tesseract", "--version"], capture_output=True, text=True)
        print(f"  ✓ Tesseract OCR installed: {result.stdout.splitlines()[0]}")
    except FileNotFoundError:
        print("  ⓘ Tesseract not installed (optional — for OCR fallback on images)")
        print("    Install: sudo apt install tesseract-ocr && pip install pytesseract")

    # Poppler (for pdf2image)
    try:
        result = subprocess.run(["pdfinfo", "-v"], capture_output=True, text=True, stderr=subprocess.STDOUT)
        print(f"  ✓ Poppler installed (needed for PDF→image conversion)")
    except FileNotFoundError:
        print("  ⓘ Poppler not installed (optional — for PDF vision fallback)")
        print("    Install: sudo apt install poppler-utils && pip install pdf2image")


def main():
    print("=" * 55)
    print("  Document-to-Calendar Sync — First-Time Setup")
    print("=" * 55)

    check_ollama()
    check_directories()
    check_google_auth()
    check_optional_deps()

    print("\n" + "=" * 55)
    print("  Setup complete!")
    print()
    print("  Next steps:")
    print(f"    1. Fix any ✗ issues above")
    print(f"    2. Test: python3 pipeline.py")
    print(f"    3. Add cron job:")
    print(f"       crontab -e")
    print(f"       0 * * * * cd /home/wesley/doc-calendar-sync && /usr/bin/python3 pipeline.py")
    print("=" * 55)


if __name__ == "__main__":
    main()
