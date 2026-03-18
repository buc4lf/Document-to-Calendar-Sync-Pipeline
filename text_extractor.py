"""
Document text extraction — PDF text, OCR fallback, image handling.
"""

import logging
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def extract_text(filepath: str) -> str:
    """
    Extract text from a document file.
    Returns the extracted text, or empty string if extraction fails.
    """
    path = Path(filepath)
    ext = path.suffix.lower()

    if ext == ".pdf":
        return _extract_pdf_text(filepath)
    elif ext in {".png", ".jpg", ".jpeg", ".tiff", ".tif"}:
        return _extract_image_text(filepath)
    else:
        logger.warning("Unsupported file type: %s", ext)
        return ""


def _extract_pdf_text(filepath: str) -> str:
    """Extract text from a PDF using pypdf (fast, no OCR)."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n\n".join(text_parts)
    except Exception as e:
        logger.error("PDF text extraction failed for %s: %s", filepath, e)
        return ""


def _extract_image_text(filepath: str) -> str:
    """
    Try OCR on an image file using pytesseract.
    Returns empty string if tesseract is not available — caller should
    fall back to vision-based LLM extraction.
    """
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(filepath)
        return pytesseract.image_to_string(img)
    except ImportError:
        logger.info("pytesseract not installed — will use LLM vision fallback")
        return ""
    except Exception as e:
        logger.error("OCR failed for %s: %s", filepath, e)
        return ""


def is_text_sufficient(text: str) -> bool:
    """Check whether extracted text meets the minimum quality threshold."""
    cleaned = text.strip()
    return len(cleaned) >= config.MIN_TEXT_LENGTH
