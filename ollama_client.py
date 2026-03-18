"""
Ollama client — model management and LLM interaction.
"""

import base64
import json
import logging
import requests
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def _api(method: str, endpoint: str, **kwargs) -> requests.Response:
    """Low-level Ollama API call."""
    url = f"{config.OLLAMA_HOST}{endpoint}"
    resp = getattr(requests, method)(url, timeout=600, **kwargs)
    resp.raise_for_status()
    return resp


# ------------------------------------------------------------------
# Model management
# ------------------------------------------------------------------

def get_loaded_models() -> list[str]:
    """Return list of model names currently loaded in VRAM."""
    try:
        data = _api("get", "/api/ps").json()
        return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        logger.warning("Could not query loaded models: %s", e)
        return []


def unload_model(model: str) -> None:
    """Unload a model from VRAM by sending a generate request with keep_alive=0."""
    logger.info("Unloading model: %s", model)
    try:
        _api("post", "/api/generate", json={
            "model": model,
            "prompt": "",
            "keep_alive": 0,
        })
    except Exception as e:
        logger.warning("Failed to unload %s: %s", model, e)


def unload_all_models() -> None:
    """Unload every model currently in VRAM."""
    for model in get_loaded_models():
        unload_model(model)


def preload_model(model: str) -> None:
    """Load a model into VRAM (warm it up) without generating output."""
    logger.info("Preloading model: %s", model)
    try:
        _api("post", "/api/generate", json={
            "model": model,
            "prompt": "",
            "keep_alive": "1h",
        })
    except Exception as e:
        logger.warning("Failed to preload %s: %s", model, e)


def swap_to_processing_model() -> None:
    """Unload everything, then load the processing model."""
    unload_all_models()
    preload_model(config.PROCESSING_MODEL)


def restore_default_model() -> None:
    """Unload processing model, reload the default model."""
    unload_all_models()
    preload_model(config.DEFAULT_MODEL)


# ------------------------------------------------------------------
# LLM queries
# ------------------------------------------------------------------

EVENT_EXTRACTION_PROMPT = """You are an event extraction assistant. Analyze the following document text and extract ALL events, appointments, meetings, deadlines, or scheduled activities mentioned.

For EACH event found, return a JSON object with these fields:
- "title": string — short descriptive title for the event
- "description": string — fuller description including relevant details
- "start_date": string — ISO 8601 format (YYYY-MM-DDTHH:MM:SS) or just YYYY-MM-DD for all-day events
- "end_date": string — ISO 8601 format, or null if not specified (will default to 1 hour after start)
- "all_day": boolean — true if no specific time is mentioned
- "location": string or null — venue/location if mentioned
- "recurrence": string or null — e.g. "weekly", "monthly", "every Tuesday", or null

Return ONLY a JSON array of event objects. If no events are found, return an empty array: []
Do NOT include any explanation, markdown formatting, or text outside the JSON array.

DOCUMENT TEXT:
{text}"""

EVENT_EXTRACTION_PROMPT_VISION = """You are an event extraction assistant. Look at this document image and extract ALL events, appointments, meetings, deadlines, or scheduled activities mentioned.

For EACH event found, return a JSON object with these fields:
- "title": string — short descriptive title for the event
- "description": string — fuller description including relevant details
- "start_date": string — ISO 8601 format (YYYY-MM-DDTHH:MM:SS) or just YYYY-MM-DD for all-day events
- "end_date": string — ISO 8601 format, or null if not specified (will default to 1 hour after start)
- "all_day": boolean — true if no specific time is mentioned
- "location": string or null — venue/location if mentioned
- "recurrence": string or null — e.g. "weekly", "monthly", "every Tuesday", or null

Return ONLY a JSON array of event objects. If no events are found, return an empty array: []
Do NOT include any explanation, markdown formatting, or text outside the JSON array."""


def extract_events_from_text(text: str) -> list[dict]:
    """Send document text to the LLM and parse out structured event data."""
    prompt = EVENT_EXTRACTION_PROMPT.format(text=text)
    return _query_llm(prompt)


def extract_events_from_image(image_path: str) -> list[dict]:
    """Send a document image to the LLM using vision/multimodal capability."""
    image_bytes = Path(image_path).read_bytes()
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    logger.info("Sending image to LLM for vision-based extraction: %s", image_path)
    try:
        resp = _api("post", "/api/chat", json={
            "model": config.PROCESSING_MODEL,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": EVENT_EXTRACTION_PROMPT_VISION,
                    "images": [b64],
                }
            ],
        })
        raw = resp.json().get("message", {}).get("content", "")
        return _parse_event_json(raw)
    except Exception as e:
        logger.error("Vision-based extraction failed: %s", e)
        return []


def _query_llm(prompt: str) -> list[dict]:
    """Send a text prompt to the Ollama generate endpoint."""
    try:
        resp = _api("post", "/api/generate", json={
            "model": config.PROCESSING_MODEL,
            "prompt": prompt,
            "stream": False,
        })
        raw = resp.json().get("response", "")
        return _parse_event_json(raw)
    except Exception as e:
        logger.error("LLM query failed: %s", e)
        return []


def _parse_event_json(raw: str) -> list[dict]:
    """Robustly extract a JSON array from the LLM response."""
    raw = raw.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    # Try to find array bounds
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        raw = raw[start:end + 1]

    try:
        events = json.loads(raw)
        if isinstance(events, list):
            return events
        logger.warning("LLM returned JSON but not a list: %s", type(events))
        return []
    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM JSON response: %s\nRaw: %.500s", e, raw)
        return []
