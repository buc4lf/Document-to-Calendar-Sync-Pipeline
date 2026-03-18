"""
Google Calendar integration — OAuth2 auth, duplicate checking, event creation.
"""

import logging
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import config

logger = logging.getLogger(__name__)

_service = None


def get_service():
    """Return an authenticated Google Calendar API service, caching it."""
    global _service
    if _service is not None:
        return _service

    creds = None

    # Load saved token
    try:
        creds = Credentials.from_authorized_user_file(
            config.GOOGLE_TOKEN_FILE, config.GOOGLE_SCOPES
        )
    except Exception:
        pass

    # Refresh or run auth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Google token")
            creds.refresh(Request())
        else:
            logger.info("Running Google OAuth consent flow (first time setup)")
            flow = InstalledAppFlow.from_client_secrets_file(
                config.GOOGLE_CREDENTIALS_FILE, config.GOOGLE_SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save for next run
        with open(config.GOOGLE_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    _service = build("calendar", "v3", credentials=creds)
    return _service


def find_duplicate(event_data: dict) -> str | None:
    """
    Check if a similar event already exists on the calendar.
    Returns the event ID if a duplicate is found, otherwise None.

    Matching logic:
      - Same date (or overlapping date range)
      - Title similarity (case-insensitive substring match)
    """
    service = get_service()

    # Determine search window around the event's start date
    start_str = event_data.get("start_date", "")
    if not start_str:
        return None

    try:
        if "T" in start_str:
            event_start = datetime.fromisoformat(start_str)
        else:
            event_start = datetime.strptime(start_str, "%Y-%m-%d")
    except ValueError:
        logger.warning("Could not parse start_date: %s", start_str)
        return None

    # Ensure timezone-aware for API query
    if event_start.tzinfo is None:
        event_start = event_start.replace(tzinfo=timezone.utc)

    # Search window: 1 day before to 1 day after
    time_min = (event_start - timedelta(days=1)).isoformat()
    time_max = (event_start + timedelta(days=2)).isoformat()

    try:
        result = service.events().list(
            calendarId=config.CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            maxResults=50,
        ).execute()
    except Exception as e:
        logger.error("Google Calendar query failed: %s", e)
        return None

    title = event_data.get("title", "").lower().strip()
    if not title:
        return None

    for existing in result.get("items", []):
        existing_title = existing.get("summary", "").lower().strip()
        # Check for substring match in either direction
        if title in existing_title or existing_title in title:
            logger.info(
                "Duplicate found: '%s' matches existing '%s' (id: %s)",
                title, existing.get("summary"), existing["id"],
            )
            return existing["id"]

    return None


def create_event(event_data: dict) -> str | None:
    """
    Create a Google Calendar event from the extracted event data.
    Returns the event ID on success, or None on failure.
    """
    service = get_service()

    body = _build_event_body(event_data)
    if body is None:
        return None

    try:
        created = service.events().insert(
            calendarId=config.CALENDAR_ID, body=body
        ).execute()
        logger.info("Created event: %s (id: %s)", created.get("summary"), created["id"])
        return created["id"]
    except Exception as e:
        logger.error("Failed to create event: %s", e)
        return None


def update_event(event_id: str, event_data: dict) -> bool:
    """
    Update an existing Google Calendar event with new data.
    Returns True on success.
    """
    service = get_service()

    body = _build_event_body(event_data)
    if body is None:
        return False

    try:
        service.events().update(
            calendarId=config.CALENDAR_ID, eventId=event_id, body=body
        ).execute()
        logger.info("Updated event %s: %s", event_id, event_data.get("title"))
        return True
    except Exception as e:
        logger.error("Failed to update event %s: %s", event_id, e)
        return False


def _build_event_body(event_data: dict) -> dict | None:
    """Convert our event dict into a Google Calendar API event body."""
    title = event_data.get("title")
    start_str = event_data.get("start_date")

    if not title or not start_str:
        logger.warning("Event missing title or start_date, skipping: %s", event_data)
        return None

    all_day = event_data.get("all_day", False)

    # Parse start
    if all_day or "T" not in start_str:
        # All-day event
        start_date = start_str[:10]  # YYYY-MM-DD
        end_str = event_data.get("end_date")
        if end_str:
            end_date = end_str[:10]
        else:
            # All-day events: end is exclusive, so next day
            try:
                d = datetime.strptime(start_date, "%Y-%m-%d")
                end_date = (d + timedelta(days=1)).strftime("%Y-%m-%d")
            except ValueError:
                end_date = start_date

        start_body = {"date": start_date}
        end_body = {"date": end_date}
    else:
        # Timed event
        start_body = {"dateTime": start_str, "timeZone": "America/Los_Angeles"}
        end_str = event_data.get("end_date")
        if not end_str:
            # Default to 1 hour duration
            try:
                s = datetime.fromisoformat(start_str)
                end_str = (s + timedelta(hours=1)).isoformat()
            except ValueError:
                end_str = start_str
        end_body = {"dateTime": end_str, "timeZone": "America/Los_Angeles"}

    body = {
        "summary": title,
        "start": start_body,
        "end": end_body,
    }

    if event_data.get("description"):
        body["description"] = event_data["description"]
    if event_data.get("location"):
        body["location"] = event_data["location"]

    return body
