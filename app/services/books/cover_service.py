"""
cover_service.py — Book Cover & Metadata Fetching Service

Tries sources in order:
1. OpenLibrary (covers.openlibrary.org)
2. Google Books API (books.googleapis.com)
3. Gradient placeholder SVG as data URI

Enhancements (BookTale):
- Extracts dominant_color from cover image (5×5 grid median-cut, no Pillow)
- Extracts page_count, categories/genres from Google Books API
- Returns a richer result dict

All functions return a consistent dict:
{
  "cover_url": str,
  "description": str,
  "cover_source": str | None,
  "dominant_color": str,
  "page_count": int | None,
  "genres": list[str]
}
"""

import hashlib
import json
import re
import struct
import urllib.error
import urllib.parse
import urllib.request


def _fetch_url(url: str, timeout: int = 5) -> bytes | None:
    """Fetch a URL and return raw bytes, or None on failure."""
    # Restrict to http(s) only — never follow file:// or custom schemes (B310).
    if not url.lower().startswith(("http://", "https://")):
        return None
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "BookTale/1.0 (library management system; book metadata fetch)"},
        )
        # nosec B310: scheme restricted to http(s) by the guard above.
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None


def _head_url(url: str, timeout: int = 5) -> bool:
    """Check if a URL returns a valid (non-1x1) image via HEAD request."""
    # Restrict to http(s) only — never follow file:// or custom schemes (B310).
    if not url.lower().startswith(("http://", "https://")):
        return False
    try:
        req = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "BookTale/1.0 (library management system; cover check)"},
        )
        # nosec B310: scheme restricted to http(s) by the guard above.
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            content_length = resp.headers.get("Content-Length", "0")
            if status == 200 and "image" in content_type:
                length = int(content_length) if content_length.isdigit() else 0
                return length > 1000
            return False
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


# DOMINANT COLOR EXTRACTION (no Pillow dependency)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB values (0-255) to hex string like '#rrggbb'."""
    return f"#{r:02x}{g:02x}{b:02x}"


def _is_near_white(r: int, g: int, b: int, threshold: int = 230) -> bool:
    """Check if a color is near-white (to skip backgrounds)."""
    return r > threshold and g > threshold and b > threshold


def _is_near_black(r: int, g: int, b: int, threshold: int = 25) -> bool:
    """Check if a color is near-black (to skip dark borders)."""
    return r < threshold and g < threshold and b < threshold


def _extract_dominant_color(image_bytes: bytes, max_bytes: int = 50_000) -> str | None:
    """
    Extract dominant color from image bytes using raw pixel sampling.

    Works with:
    - BMP (no decompression needed, pixel data directly accessible)
    - JPEG/PNG via byte sniff (limited — will attempt to find RGB triples)

    Returns a hex color string like '#rrggbb' or None if extraction fails.
    """
    if not image_bytes or len(image_bytes) < 100:
        return None

    data = image_bytes[:max_bytes]
    pixels: list[tuple[int, int, int]] = []

    # Strategy 1: Try to parse as BMP (uncompressed, easy)
    if data[0:2] == b"BM" and len(data) > 54:
        try:
            # BMP header: offset to pixel data at byte 10 (4 bytes little-endian)
            pixel_offset = struct.unpack_from("<I", data, 10)[0]
            # Width at byte 18, height at byte 22 (4 bytes each, little-endian)
            width = struct.unpack_from("<i", data, 18)[0]
            height = struct.unpack_from("<i", data, 22)[0]
            # Bits per pixel at byte 28
            bpp = struct.unpack_from("<H", data, 28)[0]

            if bpp == 24 and pixel_offset + 10 < len(data):
                # Sample a 5x5 grid
                for row in range(5):
                    for col in range(5):
                        x = int(col * width / 5)
                        y = int(row * height / 5)
                        # BMP stores rows bottom-to-top, each row padded to 4 bytes
                        row_size = ((width * 3 + 3) // 4) * 4
                        px_offset = pixel_offset + (height - 1 - y) * row_size + x * 3
                        if 0 <= px_offset + 2 < len(data):
                            b, g, r = struct.unpack_from("BBB", data, px_offset)
                            if not _is_near_white(r, g, b) and not _is_near_black(r, g, b):
                                pixels.append((r, g, b))
        except (struct.error, ValueError):
            pass

    # Strategy 2: For JPEG/PNG, try raw byte scanning for RGB triple patterns
    # This is a heuristic — find common non-white/non-black byte triples
    if not pixels and len(data) > 100:
        # Scan bytes looking for potential RGB triples
        # Skip the first 100 bytes (headers) and sample every 100th triple
        step = max(3, len(data) // 100)
        for offset in range(100, len(data) - 2, step):
            r, g, b = data[offset], data[offset + 1], data[offset + 2]
            if not _is_near_white(r, g, b) and not _is_near_black(r, g, b):
                pixels.append((r, g, b))

    if not pixels:
        return None

    # Median-cut: find the most common color cluster
    # Simple approach: quantize to 8 levels per channel, find most common bucket
    buckets: dict[tuple[int, int, int], int] = {}
    for r, g, b in pixels:
        # Quantize to 32 levels per channel (5-bit)
        key = (r // 32 * 32, g // 32 * 32, b // 32 * 32)
        buckets[key] = buckets.get(key, 0) + 1

    if not buckets:
        return None

    # Find the most common bucket
    dominant = max(buckets, key=buckets.get)
    r, g, b = dominant
    # Add half the quantizer step back for a smoother color
    r = min(255, r + 16)
    g = min(255, g + 16)
    b = min(255, b + 16)

    return _rgb_to_hex(r, g, b)


def _extract_dominant_from_url(cover_url: str) -> str | None:
    """Download a cover image and extract its dominant color."""
    if not cover_url or cover_url.startswith("data:"):
        return None
    try:
        data = _fetch_url(cover_url, timeout=5)
        if data:
            return _extract_dominant_color(data)
    except (OSError, ValueError, TypeError):
        pass
    return None


# COVER FETCHING STRATEGIES


def _try_openlibrary(
    isbn: str,
) -> tuple[str | None, str | None, str | None, str | None, int | None, list]:
    """
    Try OpenLibrary cover API.
    Returns (cover_url, description, source, dominant_color, page_count, genres).
    """
    if not isbn:
        return None, None, None, None, None, []
    clean_isbn = isbn.replace("-", "").strip()
    if not clean_isbn.isdigit():
        return None, None, None, None, None, []

    ol_cover_url = f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-L.jpg"
    description = None
    page_count = None
    genres = []
    dominant_color = None

    if _head_url(ol_cover_url):
        # Try to get metadata from OpenLibrary API
        ol_api_url = f"https://openlibrary.org/isbn/{clean_isbn}.json"
        try:
            data = _fetch_url(ol_api_url)
            if data:
                info = json.loads(data)
                desc = info.get("description", {})
                if isinstance(desc, dict):
                    description = desc.get("value", "")
                elif isinstance(desc, str):
                    description = desc
                # Extract page count
                page_count = info.get("number_of_pages", None)
                if isinstance(page_count, str):
                    try:
                        page_count = int(page_count)
                    except (ValueError, TypeError):
                        page_count = None
                # Extract subjects/genres
                subjects = info.get("subjects", [])
                if subjects and isinstance(subjects, list):
                    genres = [s for s in subjects if isinstance(s, str)][:8]
        except (KeyError, TypeError, AttributeError):
            pass

        # Extract dominant color from the cover image
        dominant_color = _extract_dominant_from_url(ol_cover_url)

        return (
            ol_cover_url,
            description,
            "openlibrary",
            dominant_color,
            page_count,
            genres,
        )

    return None, None, None, None, None, []


def _try_google_books(
    isbn: str,
) -> tuple[str | None, str | None, str | None, str | None, int | None, list]:
    """
    Try Google Books API.
    Returns (cover_url, description, source, dominant_color, page_count, genres).
    """
    if not isbn:
        return None, None, None, None, None, []
    clean_isbn = isbn.replace("-", "").strip()
    if not clean_isbn.isdigit():
        return None, None, None, None, None, []

    api_url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean_isbn}&maxResults=1"
    try:
        data = _fetch_url(api_url)
        if not data:
            return None, None, None, None, None, []

        info = json.loads(data)
        items = info.get("items", [])
        if not items:
            return None, None, None, None, None, []

        vol = items[0].get("volumeInfo", {})
        image_links = vol.get("imageLinks", {})

        # Try for the largest image first
        cover_url = (
            image_links.get("extraLarge")
            or image_links.get("large")
            or image_links.get("thumbnail")
            or ""
        )

        # Upgrade thumbnail quality
        if (cover_url and "zoom=" in cover_url) or "&edge=" in cover_url:
            cover_url = cover_url.replace("zoom=1", "zoom=2").replace("&edge=curl", "")
        elif cover_url:
            cover_url = cover_url.replace("&zoom=1", "&zoom=2")

        # Make sure it's HTTPS
        if cover_url and cover_url.startswith("http://"):
            cover_url = cover_url.replace("http://", "https://")

        # Extract description
        description = vol.get("description", "")
        if description:
            description = re.sub(r"<[^>]+>", "", description)

        # Extract page count
        page_count = vol.get("pageCount", None)
        if page_count is not None:
            try:
                page_count = int(page_count)
            except (ValueError, TypeError):
                page_count = None

        # Extract categories/genres
        categories = vol.get("categories", [])
        genres = []
        if categories and isinstance(categories, list):
            for cat in categories:
                if isinstance(cat, str):
                    # Split on '/' for subcategories (e.g. "Fiction / Fantasy / Epic")
                    for sub in cat.split("/"):
                        sub = sub.strip()
                        if sub and sub not in genres:
                            genres.append(sub)

        # Extract dominant color from cover
        dominant_color = None
        if cover_url:
            dominant_color = _extract_dominant_from_url(cover_url)

        return (
            cover_url or None,
            description or None,
            "googlebooks",
            dominant_color,
            page_count,
            genres,
        )

    except (ValueError, KeyError, TypeError, OSError):
        return None, None, None, None, None, []


def _make_placeholder_svg(isbn: str, title: str, author: str) -> str:
    """
    Generate a gradient placeholder SVG as a data URI.
    Uses deterministic hue derived from hash of isbn or title.
    """
    seed = isbn or title or ""
    # Deterministic placeholder hue only — NOT used for security (B324).
    h_val = int(hashlib.md5(seed.encode(), usedforsecurity=False).hexdigest()[:6], 16) % 360
    h2 = (h_val + 30) % 360

    initials = ""
    parts = title.strip().split() if title else []
    if len(parts) >= 2:
        initials = (parts[0][0] + parts[-1][0]).upper()
    elif parts:
        initials = parts[0][:2].upper()
    else:
        initials = "BK"

    # Generate the dominant_color from the placeholder hue
    dom_r, dom_g, dom_b = _hsl_to_rgb(h_val, 60, 50)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="200" height="300" viewBox="0 0 200 300">
  <defs>
    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:hsl({h_val},60%,50%)"/>
      <stop offset="100%" style="stop-color:hsl({h2},70%,40%)"/>
    </linearGradient>
  </defs>
  <rect width="200" height="300" fill="url(#g)" rx="8"/>
  <text x="100" y="140" text-anchor="middle" fill="rgba(255,255,255,0.3)" font-size="48" font-weight="800" font-family="sans-serif">{initials}</text>
  <text x="100" y="230" text-anchor="middle" fill="rgba(255,255,255,0.6)" font-size="12" font-weight="600" font-family="sans-serif" textLength="180" lengthAdjust="spacing">{title[:40]}</text>
  <text x="100" y="250" text-anchor="middle" fill="rgba(255,255,255,0.4)" font-size="10" font-family="sans-serif">{author[:30]}</text>
</svg>"""

    encoded = urllib.parse.quote(svg)
    return f"data:image/svg+xml,{encoded}", _rgb_to_hex(dom_r, dom_g, dom_b)


def _hsl_to_rgb(h: int, s: int, l: int) -> tuple:
    """Convert HSL (hue 0-360, sat 0-100, light 0-100) to RGB tuple (0-255)."""
    h = h / 360.0
    s = s / 100.0
    l = l / 100.0

    def hue_to_rgb(p, q, t):
        if t < 0:
            t += 1
        if t > 1:
            t -= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    if s == 0:
        r = g = b = l
    else:
        q = l * (1 + s) if l < 0.5 else l + s - l * s
        p = 2 * l - q
        r = hue_to_rgb(p, q, h + 1 / 3)
        g = hue_to_rgb(p, q, h)
        b = hue_to_rgb(p, q, h - 1 / 3)

    return int(r * 255), int(g * 255), int(b * 255)


def fetch_cover(isbn: str = "", title: str = "", author: str = "") -> dict:
    """
    Fetch a book cover, description, dominant color, and metadata.

    Tries in order:
    1. OpenLibrary (covers.openlibrary.org)
    2. Google Books API
    3. Gradient placeholder SVG

    Returns:
        {
            "cover_url": str,
            "description": str,
            "cover_source": str | None,
            "dominant_color": str,
            "page_count": int | None,
            "genres": list[str]
        }
    """
    cover_url = None
    description = None
    source = None
    dominant_color = None
    page_count = None
    genres = []

    # 1. Try OpenLibrary
    if isbn:
        (cover_url, description, source, dominant_color, page_count, genres) = _try_openlibrary(
            isbn
        )

    # 2. Try Google Books
    if not cover_url and isbn:
        (cover_url, description, source, dominant_color, page_count, genres) = _try_google_books(
            isbn
        )

    # 3. Fallback: placeholder SVG
    if not cover_url:
        cover_url, dominant_color = _make_placeholder_svg(isbn, title, author)
        source = "placeholder"

    return {
        "cover_url": cover_url or "",
        "description": description or "",
        "cover_source": source or "",
        "dominant_color": dominant_color or "",
        "page_count": page_count,
        "genres": genres or [],
    }


def fetch_description(isbn: str = "", title: str = "", author: str = "") -> str | None:
    """Fetch only the description for a book. Returns None if unavailable."""
    if isbn:
        result = _try_openlibrary(isbn)
        if result[1]:
            return result[1]
        result = _try_google_books(isbn)
        if result[1]:
            return result[1]
    return None
