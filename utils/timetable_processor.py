import os
import io
import re
from typing import List, Dict, Tuple, Optional

import fitz  # PyMuPDF
from PIL import Image
import pytesseract
from difflib import get_close_matches

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - optional dependency
    genai = None


def _configure_tesseract() -> None:
    """
    Optional Windows-friendly override.
    If Tesseract is installed but not in PATH, set env var:
      TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
    """
    cmd = (os.getenv("TESSERACT_CMD") or "").strip()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def _extract_faculty_name(text: str) -> str | None:
    """
    Try to extract faculty name from OCR text.
    Looks for lines like: 'FACULTY: Mr. MAHESH KUMAR'
    and intentionally ignores header lines such as
    'FACULTY INDIVIDUAL TIME TABLE: 2025-26 (II TERM)'.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # First, prefer lines that explicitly start with 'FACULTY:'
    for line in lines:
        norm = re.sub(r"\s+", " ", line.upper())
        # Skip header like 'FACULTY INDIVIDUAL TIME TABLE: 2025-26 (II TERM)'
        if "TIME TABLE" in norm:
            continue
        if norm.startswith("FACULTY:"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                name = parts[1].strip()
                name = re.sub(r"\s+", " ", name)
                # Ignore if this is clearly just a year / term (mostly digits)
                if re.fullmatch(r"[0-9\s\-\(\)IVX]+", name.upper()):
                    continue
                return name

    # Fallback: any line that begins with 'FACULTY' but not 'TIME TABLE'
    for line in lines:
        norm = re.sub(r"\s+", " ", line.upper())
        if "TIME TABLE" in norm:
            continue
        if norm.startswith("FACULTY"):
            parts = re.split(r"[:\-]", line, maxsplit=1)
            if len(parts) == 2:
                name = parts[1].strip()
                name = re.sub(r"\s+", " ", name)
                if re.fullmatch(r"[0-9\s\-\(\)IVX]+", name.upper()):
                    continue
                return name
    return None


def _normalize_name(text: str) -> str:
    """
    Lightweight normalization used when matching OCR text against a list
    of known faculty names (for pages that don't have an explicit FACULTY line).
    """
    text = (text or "").upper()
    text = re.sub(r"\b(MR|MRS|MS|MISS|DR|PROF|PROFESSOR)\.?\b", "", text)
    text = re.sub(r"[^A-Z\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fallback_detect_faculty_from_page_text(
    page_text: str, known_faculty_names: List[str]
) -> Optional[str]:
    """
    When no explicit 'FACULTY:' line is present, attempt to infer the faculty
    name by matching the page OCR text against a list of known names.
    """
    if not page_text or not known_faculty_names:
        return None

    norm_page = _normalize_name(page_text)
    if not norm_page:
        return None

    # Token set of the full page text
    page_tokens = set(norm_page.split())

    best_name = None
    best_score = 0.0

    for name in known_faculty_names:
        norm_name = _normalize_name(name)
        if not norm_name:
            continue

        name_tokens = set(norm_name.split())
        if not name_tokens:
            continue

        # Overlap score (0..1) based on common tokens
        common = page_tokens & name_tokens
        if not common:
            continue

        score = len(common) / len(name_tokens)
        if score > best_score:
            best_score = score
            best_name = name

    # Require at least 60% of the name tokens to appear in the page text
    if best_score >= 0.6:
        return best_name

    # Fallback: fuzzy string similarity on normalized strings
    norm_known = [_normalize_name(n) for n in known_faculty_names]
    best = get_close_matches(norm_page, norm_known, n=1, cutoff=0.8)
    if best:
        idx = norm_known.index(best[0])
        return known_faculty_names[idx]

    return None


def extract_timetable_structure(image: Image.Image) -> Optional[Dict]:
    """
    Optional AI-powered extraction of structured timetable data from a cropped
    faculty timetable image using Google Gemini (vision model).

    Returns a dictionary like:
    {
        "faculty_name": "...",
        "total_hours": 18,
        "slots": [
            {
                "day": "MONDAY",
                "session": "I",
                "time": "9:45-10:35",
                "subject": "II BCA B Python",
                "notes": ""
            },
            ...
        ]
    }

    If the GOOGLE_API_KEY is not configured or google-generativeai is missing,
    this function returns None and the rest of the system continues to work
    without structured data.
    """
    api_key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key or genai is None:
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        img_bytes = buf.getvalue()

        prompt = """
You are reading a college faculty timetable image.
Extract the timetable into pure JSON. Return ONLY JSON, no explanation.

Use this schema:
{
  "faculty_name": "<string>",
  "total_hours": <int>,  // total teaching hours per week if shown, else 0
  "slots": [
    {
      "day": "MONDAY" | "TUESDAY" | "WEDNESDAY" | "THURSDAY" | "FRIDAY" | "SATURDAY",
      "session": "0" | "I" | "II" | "III" | "IV" | "V" | "VI" | "VII",
      "time": "<time-range as text, e.g. '8:50-9:40'>",
      "subject": "<subject / class text from the cell>",
      "notes": "<any extra text in that cell or ''>"
    }
  ]
}

Include one slot for each non-empty cell in the main timetable grid.
"""

        resp = model.generate_content(
            [
                prompt,
                {"mime_type": "image/png", "data": img_bytes},
            ]
        )

        text = (resp.text or "").strip()
        # Sometimes Gemini wraps JSON in markdown code fences
        if text.startswith("```"):
            text = text.strip("`")
            # remove possible language hint like ```json
            if "\n" in text:
                text = "\n".join(text.split("\n")[1:])

        import json as _json

        data = _json.loads(text)
        # Basic shape validation
        if not isinstance(data, dict):
            return None
        if "slots" in data and not isinstance(data["slots"], list):
            data["slots"] = []
        return data
    except Exception:
        # Fail silently – structured extraction is an enhancement only
        return None


def pdf_to_faculty_images(
    pdf_bytes: bytes,
    known_faculty_names: Optional[List[str]] = None,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Convert each page in the PDF into an image, OCR it,
    and extract the faculty name.

    Returns (pages_with_name, pages_without_name)
    where each entry is:
      {
        "page_index": int,
        "faculty_name": str | None,
        "image": PIL.Image.Image,
        "ocr_text": str,
      }
    """
    with io.BytesIO(pdf_bytes) as pdf_stream:
        doc = fitz.open(stream=pdf_stream.read(), filetype="pdf")

    pages_with_name: List[Dict] = []
    pages_without_name: List[Dict] = []

    _configure_tesseract()

    for page_index in range(len(doc)):
        page = doc.load_page(page_index)

        # Use text blocks so we can locate ALL FACULTY / PRINCIPAL sections
        # on the page, allowing multiple timetables per page.
        blocks = page.get_text("blocks") or []
        embedded_text = (page.get_text("text") or "").strip()

        page_rect = page.rect

        # First pass: find all (faculty_name, top, bottom) segments.
        segments: List[Dict] = []
        current: Dict | None = None

        for b in blocks:
            if len(b) < 5:
                continue
            x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
            if not isinstance(text, str):
                continue
            norm = re.sub(r"\s+", " ", text.upper())

            # New FACULTY header (not the 'FACULTY INDIVIDUAL TIME TABLE' title)
            if "FACULTY" in norm and "TIME TABLE" not in norm:
                name_candidate = _extract_faculty_name(text)
                if name_candidate:
                    # If a previous segment is still open without an explicit bottom,
                    # close it at this new header.
                    if current and current.get("bottom") is None:
                        current["bottom"] = y0
                        segments.append(current)

                    current = {
                        "faculty_name": name_candidate,
                        "top": y0,
                        "bottom": None,
                    }
                    continue

            # PRINCIPAL line closes the current segment (if any)
            if current and "PRINCIPAL" in norm and y0 > current.get("top", page_rect.y0):
                current["bottom"] = y0
                segments.append(current)
                current = None

        # If a segment is still open at end of page, close it at page bottom
        if current:
            current["bottom"] = page_rect.y1
            segments.append(current)

        # If we didn't detect any segments but we have known faculty names,
        # fall back to single-faculty detection from full page text.
        if not segments:
            # OCR once for the page if needed
            ocr_text = ""
            try:
                pix_full = page.get_pixmap(dpi=200)
                mode_full = "RGBA" if pix_full.alpha else "RGB"
                image_full = Image.frombytes(mode_full, (pix_full.width, pix_full.height), pix_full.samples)
                ocr_text = pytesseract.image_to_string(image_full)
            except pytesseract.TesseractNotFoundError as e:
                raise RuntimeError(
                    "Tesseract OCR is required for scanned PDFs, but it was not found. "
                    "Install Tesseract and add it to PATH, or set TESSERACT_CMD "
                    "to the full path of tesseract.exe."
                ) from e

            faculty_name = _extract_faculty_name(ocr_text) or _extract_faculty_name(embedded_text)

            if not faculty_name and known_faculty_names:
                combined_text = (embedded_text or "") + "\n" + (ocr_text or "")
                faculty_name = _fallback_detect_faculty_from_page_text(combined_text, known_faculty_names)

            entry = {
                "page_index": page_index,
                "faculty_name": faculty_name,
                "image": image_full,
                "ocr_text": ocr_text or embedded_text,
            }
            if faculty_name:
                pages_with_name.append(entry)
            else:
                pages_without_name.append(entry)
            continue

        # For each detected faculty segment on this page, render and store separately.
        for seg in segments:
            faculty_name = seg.get("faculty_name")
            top = max(page_rect.y0, seg.get("top", page_rect.y0))
            bottom = min(page_rect.y1, seg.get("bottom", page_rect.y1))

            rect = fitz.Rect(page_rect.x0, top, page_rect.x1, bottom)
            pix = page.get_pixmap(dpi=200, clip=rect)
            mode = "RGBA" if pix.alpha else "RGB"
            image = Image.frombytes(mode, (pix.width, pix.height), pix.samples)

            # For per-segment entries we can reuse embedded_text; OCR is not required
            # because we already extracted the faculty name from the FACULTY line.
            entry = {
                "page_index": page_index,
                "faculty_name": faculty_name,
                "image": image,
                "ocr_text": embedded_text,
            }
            if faculty_name:
                pages_with_name.append(entry)
            else:
                pages_without_name.append(entry)

    return pages_with_name, pages_without_name

