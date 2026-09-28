"""
Image utilities for SmartGov — OCR-based geo-tag validation.

Uses Tesseract OCR to read text from the image.
A photo is accepted ONLY if it contains ALL of:
  - A location / address (place name, lat/lng, or street)
  - A date  (day name OR date pattern)
  - A time  (HH:MM pattern)

This works with GPS Map Camera watermarks regardless of whether EXIF is
present (WhatsApp strips EXIF but the visual watermark survives).
"""
import io
import re
import pytesseract
from PIL import Image, ImageFilter, ImageEnhance
from PIL.ExifTags import TAGS, GPSTAGS

# Tesseract path on Windows (default install location)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

ALLOWED_EXTENSIONS = {"jpg", "jpeg"}

# ── Pattern matchers ─────────────────────────────────────────────────────────

# Day names
_DAYS = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"mon|tue|wed|thu|fri|sat|sun)\b",
    re.IGNORECASE
)

# Date patterns: 21/07/2026  |  2026-07-21  |  21 Jul 2026  |  July 21, 2026
_DATE = re.compile(
    r"\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}"       # 21/07/2026
    r"|\d{4}[\/\-]\d{2}[\/\-]\d{2}"                    # 2026-07-21
    r"|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{4}"  # 21 Jul 2026
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2},?\s+\d{4})\b",  # July 21, 2026
    re.IGNORECASE
)

# Time patterns: 13:45  |  1:45 PM  |  01:11 PM GMT
_TIME = re.compile(
    r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]m)?(?:\s*gmt)?\b",
    re.IGNORECASE
)

# Location: lat/lng decimal degrees
_LATLONG = re.compile(
    r"\b\d{1,3}\.\d{3,}[°o]?\b"   # e.g. 11.018199° or 76.966169
)

# Location keywords — place names, address words
_LOCATION_KW = re.compile(
    r"\b(lat|long|lng|gps|india|street|road|st\.|rd\.|nagar|puram|pur|"
    r"district|city|town|village|ward|block|state|tamil|kerala|karnataka|"
    r"andhra|telangana|maharashtra|gujarat|rajasthan|punjab|haryana|"
    r"coimbatore|chennai|bangalore|mumbai|delhi|hyderabad|kolkata|"
    r"google|map|camera)\b",
    re.IGNORECASE
)


def allowed_file(filename: str) -> bool:
    parts = filename.rsplit(".", 1)
    return len(parts) == 2 and parts[1].lower() in ALLOWED_EXTENSIONS


def _dms_to_decimal(dms, ref) -> float:
    vals = []
    for v in dms:
        try:
            vals.append(float(v.numerator) / float(v.denominator))
        except AttributeError:
            try:
                vals.append(float(v))
            except Exception:
                vals.append(0.0)
    d, m, s = (vals + [0, 0, 0])[:3]
    decimal = d + m / 60.0 + s / 3600.0
    if str(ref).upper() in ("S", "W"):
        decimal = -decimal
    return round(decimal, 6)


def _ocr_text_from_image(data: bytes) -> str:
    """
    Run Tesseract OCR on the full image AND a cropped bottom strip
    (where GPS Camera apps place watermarks).
    Returns combined text.
    """
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return ""

    w, h = img.size

    # ── Enhance image for better OCR accuracy ────────────────────────────────
    def enhance(region):
        region = region.resize((region.width * 2, region.height * 2), Image.LANCZOS)
        region = ImageEnhance.Contrast(region).enhance(2.0)
        region = ImageEnhance.Sharpness(region).enhance(2.0)
        return region

    texts = []

    # Full image OCR
    try:
        full = enhance(img.copy())
        texts.append(pytesseract.image_to_string(full, config="--psm 3"))
    except Exception:
        pass

    # Bottom 30% strip (where GPS Map Camera puts its watermark)
    try:
        bottom = img.crop((0, int(h * 0.70), w, h))
        bottom = enhance(bottom)
        texts.append(pytesseract.image_to_string(bottom, config="--psm 6"))
    except Exception:
        pass

    # Bottom 20% strip (tighter crop)
    try:
        strip = img.crop((0, int(h * 0.80), w, h))
        strip = enhance(strip)
        texts.append(pytesseract.image_to_string(strip, config="--psm 6"))
    except Exception:
        pass

    combined = " ".join(texts)
    # OCR text is used only for photo validation; do not print it in the server console.
    return combined


def _read_gps_from_bytes(data: bytes):
    """Try all Pillow methods to extract GPS EXIF. Returns gps_dict or {}."""
    gps_info = {}
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        return gps_info

    try:
        exif = img.getexif()
        if exif:
            gps_tag_id = next((k for k, v in TAGS.items() if v == "GPSInfo"), None)
            if gps_tag_id:
                ifd = exif.get_ifd(gps_tag_id)
                if ifd:
                    gps_info = {GPSTAGS.get(k, str(k)): v for k, v in ifd.items()}
    except Exception:
        pass

    if not gps_info:
        try:
            raw = img._getexif() or {}
            for tag_id, value in raw.items():
                if TAGS.get(tag_id) == "GPSInfo" and value:
                    try:
                        gps_info = {GPSTAGS.get(k, str(k)): v for k, v in value.items()}
                    except Exception:
                        pass
        except Exception:
            pass

    return gps_info


def validate_image_exif(file_storage):
    """
    OCR-based validation:
    Accept image only if it contains location + (date OR time) in visible text.
    Also tries EXIF GPS as a bonus for auto-filling coordinates.

    Returns (True, None, lat_or_None, lng_or_None) or (False, reason, None, None).
    """
    try:
        file_storage.stream.seek(0)
        data = file_storage.stream.read()
        file_storage.stream.seek(0)
    except Exception:
        return False, "Could not read the uploaded file. Please try again.", None, None

    if not data:
        return False, "The uploaded file is empty.", None, None

    # ── OCR: read all visible text from the image ────────────────────────────
    text = _ocr_text_from_image(data)

    has_location = bool(
        _LATLONG.search(text) or
        _LOCATION_KW.search(text)
    )
    has_date = bool(_DATE.search(text) or _DAYS.search(text))
    has_time = bool(_TIME.search(text))

    # Keep validation details internal so submitted-image OCR does not confuse the complaint log.

    if not has_location:
        return (
            False,
            "Photo rejected: No location information found in the image. "
            "Please use GPS Map Camera app and ensure location is visible on the photo.",
            None, None
        )

    if not has_date and not has_time:
        return (
            False,
            "Photo rejected: No date or time found in the image. "
            "Please use GPS Map Camera app — the photo must show the date and time.",
            None, None
        )

    # ── Try EXIF GPS for auto-fill ───────────────────────────────────────────
    lat, lng = None, None
    gps_info = _read_gps_from_bytes(data)
    if "GPSLatitude" in gps_info and "GPSLongitude" in gps_info:
        try:
            lat = _dms_to_decimal(gps_info["GPSLatitude"], gps_info.get("GPSLatitudeRef", "N"))
            lng = _dms_to_decimal(gps_info["GPSLongitude"], gps_info.get("GPSLongitudeRef", "E"))
        except Exception:
            pass

    # Try to parse lat/lng from OCR text if EXIF unavailable
    if lat is None:
        matches = _LATLONG.findall(text)
        if len(matches) >= 2:
            try:
                lat = float(matches[0].replace("°", "").replace("o", ""))
                lng = float(matches[1].replace("°", "").replace("o", ""))
            except Exception:
                pass

    return True, None, lat, lng


def has_gps_data(file_storage) -> bool:
    try:
        file_storage.stream.seek(0)
        data = file_storage.stream.read()
        file_storage.stream.seek(0)
        gps_info = _read_gps_from_bytes(data)
        return bool(gps_info and "GPSLatitude" in gps_info)
    except Exception:
        return False


def extract_gps(file_storage):
    try:
        file_storage.stream.seek(0)
        data = file_storage.stream.read()
        file_storage.stream.seek(0)
        gps_info = _read_gps_from_bytes(data)
        if not gps_info or "GPSLatitude" not in gps_info:
            return None, None
        lat = _dms_to_decimal(gps_info["GPSLatitude"], gps_info.get("GPSLatitudeRef", "N"))
        lng = _dms_to_decimal(gps_info["GPSLongitude"], gps_info.get("GPSLongitudeRef", "E"))
        return lat, lng
    except Exception:
        return None, None
