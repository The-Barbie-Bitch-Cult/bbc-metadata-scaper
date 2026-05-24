from __future__ import annotations

import argparse
import csv
import html
import html.parser
import http.client
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import __version__


DEFAULT_USER_AGENT = f"site-exif/{__version__} (+https://localhost/metadata-audit)"
HTML_TYPES = {"text/html", "application/xhtml+xml"}
CSS_TYPES = {"text/css"}
SITEMAP_TYPES = {"application/xml", "text/xml"}
TEXT_TYPES = {
    "application/javascript",
    "application/json",
    "application/ld+json",
    "application/x-javascript",
    "text/javascript",
    "text/plain",
}
MAX_DEFAULT_BYTES = 50 * 1024 * 1024
MEDIA_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".jpe",
    ".tif",
    ".tiff",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".ico",
    ".heic",
    ".heif",
    ".avif",
    ".svg",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".odt",
    ".ods",
    ".odp",
    ".mp3",
    ".mp4",
    ".m4a",
    ".m4v",
    ".mov",
    ".avi",
    ".wav",
    ".zip",
}
PAGE_EXTENSIONS = {"", ".html", ".htm", ".php", ".asp", ".aspx", ".jsp"}
DEFAULT_MAX_PAGES = 1000
DEFAULT_MAX_DEPTH = 4
CYBERPUNK_HEADER = (
    "\033[38;5;213m"
    "==============================================================\n"
    "██████╗  █████╗ ██████╗ ██████╗ ██╗███████╗\n"
    "██╔══██╗██╔══██╗██╔══██╗██╔══██╗██║██╔════╝\n"
    "██████╔╝███████║██████╔╝██████╔╝██║█████╗  \n"
    "██╔══██╗██╔══██║██╔══██╗██╔══██╗██║██╔══╝  \n"
    "██████╔╝██║  ██║██║  ██║██████╔╝██║███████╗\n"
    "╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝╚══════╝\n"
    "\033[38;5;141m"
    "██████╗ ██╗████████╗ ██████╗██╗  ██╗\n"
    "██╔══██╗██║╚══██╔══╝██╔════╝██║  ██║\n"
    "██████╔╝██║   ██║   ██║     ███████║\n"
    "██╔══██╗██║   ██║   ██║     ██╔══██║\n"
    "██████╔╝██║   ██║   ╚██████╗██║  ██║\n"
    "╚═════╝ ╚═╝   ╚═╝    ╚═════╝╚═╝  ╚═╝\n"
    "\033[38;5;51m"
    " ██████╗██╗   ██╗██╗  ████████╗\n"
    "██╔════╝██║   ██║██║  ╚══██╔══╝\n"
    "██║     ██║   ██║██║     ██║   \n"
    "██║     ██║   ██║██║     ██║   \n"
    "╚██████╗╚██████╔╝███████╗██║   \n"
    " ╚═════╝ ╚═════╝ ╚══════╝╚═╝   \n"
    "\033[38;5;250m"
    "              Barbie Bitch Cult - The Exif Website Data Extractor\n"
    "\033[38;5;213m"
    "==============================================================\n"
    "\033[0m"
)

EXIF_TAGS = {
    0x010E: "ImageDescription",
    0x010F: "Make",
    0x0110: "Model",
    0x0112: "Orientation",
    0x011A: "XResolution",
    0x011B: "YResolution",
    0x0128: "ResolutionUnit",
    0x0131: "Software",
    0x0132: "DateTime",
    0x013B: "Artist",
    0x8298: "Copyright",
    0x829A: "ExposureTime",
    0x829D: "FNumber",
    0x8769: "ExifIFDPointer",
    0x8825: "GPSInfoIFDPointer",
    0x8827: "ISOSpeedRatings",
    0x9000: "ExifVersion",
    0x9003: "DateTimeOriginal",
    0x9004: "DateTimeDigitized",
    0x9201: "ShutterSpeedValue",
    0x9202: "ApertureValue",
    0x9204: "ExposureBiasValue",
    0x9207: "MeteringMode",
    0x9209: "Flash",
    0x920A: "FocalLength",
    0x927C: "MakerNote",
    0x9286: "UserComment",
    0xA002: "PixelXDimension",
    0xA003: "PixelYDimension",
    0xA405: "FocalLengthIn35mmFilm",
}

GPS_TAGS = {
    0x0000: "GPSVersionID",
    0x0001: "GPSLatitudeRef",
    0x0002: "GPSLatitude",
    0x0003: "GPSLongitudeRef",
    0x0004: "GPSLongitude",
    0x0005: "GPSAltitudeRef",
    0x0006: "GPSAltitude",
    0x0007: "GPSTimeStamp",
    0x001D: "GPSDateStamp",
}

TIFF_TYPE_SIZES = {
    1: 1,  # BYTE
    2: 1,  # ASCII
    3: 2,  # SHORT
    4: 4,  # LONG
    5: 8,  # RATIONAL
    7: 1,  # UNDEFINED
    9: 4,  # SLONG
    10: 8,  # SRATIONAL
}


@dataclass
class QueueItem:
    url: str
    depth: int
    page_url: str


@dataclass
class FetchResult:
    url: str
    content_type: str
    body: bytes


FETCH_ERRORS = (
    urllib.error.URLError,
    TimeoutError,
    ValueError,
    OSError,
    http.client.HTTPException,
    UnicodeError,
)


def log(verbose: bool, message: str) -> None:
    if verbose:
        print(message, file=sys.stderr)


def shorten_url_for_log(url: str, limit: int = 180) -> str:
    if len(url) <= limit:
        return url
    return f"{url[: limit - 3]}..."


def canonicalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = quote_url_part(parsed.path or "/", safe="/:@!$&()*+,;=-._~%")
    query = quote_url_part(parsed.query, safe="=&?/:@!$()*+,;%-._~")
    normalized = urllib.parse.urlunsplit((scheme, netloc, path, query, ""))
    return normalized


def normalize_candidate(base_url: str, raw_url: str) -> str | None:
    if not raw_url:
        return None
    raw_url = html.unescape(raw_url).strip().rstrip(".,;")
    if not raw_url or raw_url.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    if raw_url.endswith(("?", "&", "=")):
        return None
    if contains_invalid_url_chars(raw_url):
        return None
    if is_probable_human_filename(raw_url):
        return None
    joined = urllib.parse.urljoin(base_url, raw_url)
    parsed = urllib.parse.urlsplit(joined)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    if contains_invalid_url_chars(parsed.path) or contains_invalid_url_chars(parsed.query):
        return None
    return canonicalize_url(joined)


def contains_invalid_url_chars(value: str) -> bool:
    return any(char in value for char in "<>\"'{}|\\^`") or any(ord(char) < 32 for char in value)


def quote_url_part(value: str, safe: str) -> str:
    return urllib.parse.quote(urllib.parse.unquote(value), safe=safe)


def is_probable_human_filename(value: str) -> bool:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme or value.startswith(("/", "./", "../")) or "/" in value:
        return False
    return bool(file_extension(value) in MEDIA_EXTENSIONS and re.search(r"\s", value))


def host_matches(start_host: str, candidate_host: str, include_subdomains: bool) -> bool:
    start_host = start_host.lower()
    candidate_host = candidate_host.lower()
    if candidate_host == start_host:
        return True
    if not include_subdomains:
        return False
    root = root_domain(start_host)
    return candidate_host == root or candidate_host.endswith(f".{root}")


def root_domain(host: str) -> str:
    labels = [label for label in host.split(".") if label]
    if len(labels) <= 2:
        return host
    return ".".join(labels[-2:])


def file_extension(url: str) -> str:
    path = urllib.parse.urlsplit(url).path
    return Path(path).suffix.lower()


def media_type_for(url: str, content_type: str) -> str:
    ext = file_extension(url)
    if content_type.startswith("image/") or ext in {".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".webp", ".ico"}:
        return "image"
    if content_type == "application/pdf" or ext == ".pdf":
        return "pdf"
    if ext in {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp"}:
        return "document"
    if content_type.startswith(("audio/", "video/")) or ext in {".mp3", ".mp4", ".m4a", ".m4v", ".mov", ".avi", ".wav"}:
        return "media"
    return "asset"


def bare_content_type(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def is_xml_content_type(content_type: str) -> bool:
    return content_type in SITEMAP_TYPES or content_type.endswith("+xml")


class SiteHTMLParser(html.parser.HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        candidates: list[str] = []
        if tag == "a":
            candidates.append(attr.get("href", ""))
        if tag in {"img", "script", "source", "video", "audio", "embed", "iframe"}:
            candidates.extend([attr.get("src", ""), attr.get("poster", "")])
        if tag == "object":
            candidates.append(attr.get("data", ""))
        if tag == "link":
            candidates.append(attr.get("href", ""))
        if tag == "meta" and attr.get("property", "").lower() in {
            "og:image",
            "og:video",
            "og:audio",
        }:
            candidates.append(attr.get("content", ""))
        if tag == "meta" and attr.get("name", "").lower() in {
            "twitter:image",
            "twitter:player",
        }:
            candidates.append(attr.get("content", ""))
        if tag == "meta" and attr.get("itemprop", "").lower() in {"image", "contenturl", "thumbnailurl"}:
            candidates.append(attr.get("content", ""))
        for srcset_key in ("srcset", "imagesrcset"):
            candidates.extend(parse_srcset(attr.get(srcset_key, "")))
        for data_key in (
            "data-src",
            "data-srcset",
            "data-original",
            "data-lazy-src",
            "data-lazy-srcset",
            "data-bg",
            "data-background",
            "data-background-image",
        ):
            value = attr.get(data_key, "")
            if "srcset" in data_key:
                candidates.extend(parse_srcset(value))
            else:
                candidates.append(value)
        for key, value in attr.items():
            if key.startswith("data-") and looks_like_discoverable_url(value):
                candidates.append(value)
        candidates.extend(extract_css_urls(self.base_url, attr.get("style", "")))
        for candidate in candidates:
            normalized = normalize_candidate(self.base_url, candidate)
            if normalized:
                self.links.add(normalized)


def parse_srcset(value: str) -> list[str]:
    urls = []
    for candidate in value.split(","):
        piece = candidate.strip()
        if not piece:
            continue
        piece = re.sub(r"\s+\d+(?:\.\d+)?[wx]\s*$", "", piece).strip()
        urls.append(piece)
    return urls


CSS_URL_RE = re.compile(r"""url\(\s*(?:"([^"]+)"|'([^']+)'|([^)]*?))\s*\)""", re.IGNORECASE)
ABSOLUTE_URL_RE = re.compile(r"https?://[^\s'\"<>{}|\\^`)]+", re.IGNORECASE)
QUOTED_MEDIA_RE = re.compile(
    r"""["']([^"'<>]+?\.(?:jpe?g|png|gif|webp|tiff?|bmp|ico|heic|heif|avif|svg|pdf|docx?|xlsx?|pptx?|odt|ods|odp|mp3|mp4|m4a|m4v|mov|avi|wav|zip)(?:\?[^"'<>]*)?)["']""",
    re.IGNORECASE,
)


def extract_css_urls(base_url: str, css: str) -> set[str]:
    urls = set()
    for match in CSS_URL_RE.finditer(css):
        candidate = next(group for group in match.groups() if group is not None)
        normalized = normalize_candidate(base_url, candidate)
        if normalized:
            urls.add(normalized)
    return urls


def extract_text_urls(base_url: str, text: str) -> set[str]:
    urls = set()
    for match in ABSOLUTE_URL_RE.finditer(text):
        normalized = normalize_candidate(base_url, match.group(0).rstrip(".,;"))
        if normalized:
            urls.add(normalized)
    for match in QUOTED_MEDIA_RE.finditer(text):
        candidate = match.group(1)
        if not looks_like_embedded_media_url(candidate):
            continue
        normalized = normalize_candidate(base_url, candidate)
        if normalized:
            urls.add(normalized)
    return urls


def looks_like_embedded_media_url(value: str) -> bool:
    if re.search(r"\s", value):
        return False
    parsed = urllib.parse.urlsplit(value)
    return parsed.scheme in {"http", "https"} or value.startswith(("/", "./", "../")) or "/" in value


def looks_like_discoverable_url(value: str) -> bool:
    if not value or any(char.isspace() for char in value.strip()):
        return False
    parsed = urllib.parse.urlsplit(value)
    ext = file_extension(value)
    return parsed.scheme in {"http", "https"} or value.startswith(("/", "./", "../")) or ext in MEDIA_EXTENSIONS


def extract_sitemap_urls(base_url: str, body: bytes) -> set[str]:
    urls = set()
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        text = body.decode("utf-8", errors="replace")
        return extract_text_urls(base_url, text)
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() != "loc" or not element.text:
            continue
        normalized = normalize_candidate(base_url, element.text.strip())
        if normalized:
            urls.add(normalized)
    return urls


def extract_robots_urls(base_url: str, body: bytes) -> set[str]:
    urls = set()
    text = body.decode("utf-8", errors="replace")
    for line in text.splitlines():
        name, _, value = line.partition(":")
        if name.strip().lower() == "sitemap":
            normalized = normalize_candidate(base_url, value.strip())
            if normalized:
                urls.add(normalized)
    return urls


def sitemap_seed_urls(start_url: str) -> list[str]:
    parsed = urllib.parse.urlsplit(start_url)
    origin = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    return [f"{origin}/sitemap.xml", f"{origin}/robots.txt"]


def fetch_url(url: str, user_agent: str, timeout: float, max_bytes: int) -> FetchResult:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = bare_content_type(response.headers.get("Content-Type"))
        body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ValueError(f"response exceeds --max-bytes limit ({max_bytes})")
    return FetchResult(url=response.geturl(), content_type=content_type, body=body)


def decode_text(body: bytes, content_type: str) -> str:
    match = re.search(r"charset=([^;\s]+)", content_type or "", re.IGNORECASE)
    encoding = match.group(1) if match else "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def crawl(args: argparse.Namespace) -> int:
    start_url = canonicalize_url(args.url)
    start_host = url_host(start_url)
    include_subdomains = args.include_subdomains or not args.exact_host
    queue: deque[QueueItem] = deque([QueueItem(start_url, 0, start_url)])
    if not args.no_sitemaps:
        for sitemap_url in sitemap_seed_urls(start_url):
            queue.append(QueueItem(sitemap_url, 0, start_url))
    seen_urls: set[str] = set()
    written_assets: set[str] = set()
    rows: list[dict[str, str | int]] = []
    pages_seen = 0
    assets_seen = 0
    errors_seen = 0

    while queue:
        item = queue.popleft()
        if item.url in seen_urls:
            continue
        seen_urls.add(item.url)
        if not host_matches(start_host, url_host(item.url), include_subdomains):
            continue
        try:
            log(args.verbose, f"GET {item.url if args.verbose_all else shorten_url_for_log(item.url)}")
            fetched = fetch_url(item.url, args.user_agent, args.timeout, args.max_bytes)
        except FETCH_ERRORS as exc:
            if urllib.parse.urlsplit(item.url).path.endswith(("/sitemap.xml", "/robots.txt")):
                log(args.verbose, f"skip auxiliary discovery error for {item.url}: {exc}")
                continue
            rows.append(error_row(item.url, item.page_url, str(exc)))
            errors_seen += 1
            continue

        content_type = fetched.content_type
        ext = file_extension(item.url)
        is_html = content_type in HTML_TYPES or (not content_type and ext in PAGE_EXTENSIONS)
        is_css = content_type in CSS_TYPES or ext == ".css"
        is_xml = is_xml_content_type(content_type) or ext == ".xml"
        is_robots = urllib.parse.urlsplit(item.url).path.endswith("/robots.txt")
        is_text = content_type in TEXT_TYPES or ext in {".js", ".json", ".txt"}

        if is_html:
            if args.max_pages > 0 and pages_seen >= args.max_pages:
                continue
            pages_seen += 1
            if args.max_depth >= 0 and item.depth >= args.max_depth:
                continue
            parser = SiteHTMLParser(item.url)
            text = decode_text(fetched.body, fetched.content_type)
            parser.feed(text)
            discovered = set(parser.links)
            discovered.update(extract_text_urls(item.url, text))
            for url in sorted(discovered):
                if should_enqueue(start_host, url, include_subdomains):
                    queue.append(QueueItem(url, item.depth + 1, item.url))
            if args.delay:
                time.sleep(args.delay)
            continue

        if is_xml:
            discovered = extract_sitemap_urls(item.url, fetched.body)
            discovered.update(extract_text_urls(item.url, decode_text(fetched.body, fetched.content_type)))
            for url in sorted(discovered):
                if should_enqueue(start_host, url, include_subdomains):
                    queue.append(QueueItem(url, item.depth, item.page_url))
            continue

        if is_robots:
            for url in sorted(extract_robots_urls(item.url, fetched.body)):
                if should_enqueue(start_host, url, include_subdomains):
                    queue.append(QueueItem(url, item.depth, item.page_url))
            continue

        if is_css:
            text = decode_text(fetched.body, fetched.content_type)
            discovered = extract_css_urls(item.url, text)
            discovered.update(extract_text_urls(item.url, text))
            for url in sorted(discovered):
                if should_enqueue(start_host, url, include_subdomains):
                    queue.append(QueueItem(url, item.depth, item.page_url))
            continue

        if is_text and ext not in MEDIA_EXTENSIONS:
            for url in sorted(extract_text_urls(item.url, decode_text(fetched.body, fetched.content_type))):
                if should_enqueue(start_host, url, include_subdomains):
                    queue.append(QueueItem(url, item.depth, item.page_url))
            continue

        if item.url in written_assets:
            continue
        written_assets.add(item.url)
        asset_rows = rows_for_asset(item.url, item.page_url, fetched.content_type, fetched.body)
        rows.extend(asset_rows)
        assets_seen += 1
        if args.delay:
            time.sleep(args.delay)

    write_csv(args.output, rows)
    log(
        args.verbose,
        f"visited={len(seen_urls)} pages={pages_seen} assets={assets_seen} errors={errors_seen} wrote={len(rows)} rows to {args.output}",
    )
    return 0


def should_enqueue(start_host: str, url: str, include_subdomains: bool) -> bool:
    parsed = urllib.parse.urlsplit(url)
    return parsed.scheme in {"http", "https"} and host_matches(start_host, parsed.hostname or "", include_subdomains)


def url_host(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def error_row(source_url: str, page_url: str, error: str) -> dict[str, str | int]:
    return {
        "source_url": source_url,
        "page_url": page_url,
        "media_type": "",
        "content_type": "",
        "file_extension": file_extension(source_url),
        "bytes": 0,
        "error": error,
    }


def rows_for_asset(source_url: str, page_url: str, content_type: str, body: bytes) -> list[dict[str, str | int]]:
    media_type = media_type_for(source_url, content_type)
    metadata = extract_metadata(source_url, content_type, body)
    row: dict[str, str | int] = {
        "source_url": source_url,
        "page_url": page_url,
        "media_type": media_type,
        "content_type": content_type,
        "file_extension": file_extension(source_url),
        "bytes": len(body),
        "error": "",
    }
    for namespace, key, value in metadata:
        column = metadata_column_name(namespace, key)
        existing = row.get(column)
        row[column] = value if not existing else f"{existing}; {value}"
    return [row]


def metadata_column_name(namespace: str, key: str) -> str:
    prefix = sanitize_column_part(namespace) or "metadata"
    suffix = sanitize_column_part(key) or "value"
    return f"{prefix}_{suffix}"


def sanitize_column_part(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_")
    if cleaned and cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned


def extract_metadata(source_url: str, content_type: str, body: bytes) -> list[tuple[str, str, str]]:
    ext = file_extension(source_url)
    metadata: list[tuple[str, str, str]] = []
    if body.startswith(b"\xff\xd8") or ext in {".jpg", ".jpeg", ".jpe"}:
        metadata.extend(extract_jpeg_exif(body))
        metadata.extend(extract_xmp(body))
    elif body.startswith((b"II*\x00", b"MM\x00*")) or ext in {".tif", ".tiff"}:
        metadata.extend(extract_tiff(body, 0))
        metadata.extend(extract_xmp(body))
    elif body.startswith(b"\x89PNG\r\n\x1a\n") or ext == ".png":
        metadata.extend(extract_png_metadata(body))
        metadata.extend(extract_xmp(body))
    elif (body.startswith(b"RIFF") and body[8:12] == b"WEBP") or ext == ".webp":
        metadata.extend(extract_webp_metadata(body))
        metadata.extend(extract_xmp(body))
    elif body.startswith(b"%PDF") or content_type == "application/pdf" or ext == ".pdf":
        metadata.extend(extract_pdf_metadata(body))
        metadata.extend(extract_xmp(body))
    elif body.startswith(b"GIF") or ext == ".gif":
        metadata.extend(extract_gif_comments(body))
    else:
        metadata.extend(extract_xmp(body))
    return metadata


def extract_jpeg_exif(body: bytes) -> list[tuple[str, str, str]]:
    metadata: list[tuple[str, str, str]] = []
    index = 2
    while index + 4 <= len(body):
        if body[index] != 0xFF:
            break
        marker = body[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if marker == 0xDA:
            break
        segment_len = int.from_bytes(body[index : index + 2], "big")
        segment = body[index + 2 : index + segment_len]
        if marker == 0xE1 and segment.startswith(b"Exif\x00\x00"):
            metadata.extend(extract_tiff(segment[6:], 0))
        index += segment_len
    return metadata


def extract_tiff(data: bytes, base: int) -> list[tuple[str, str, str]]:
    if len(data) < base + 8:
        return []
    byte_order = data[base : base + 2]
    endian = "little" if byte_order == b"II" else "big" if byte_order == b"MM" else ""
    if not endian:
        return []
    if read_int(data, base + 2, 2, endian) != 42:
        return []
    first_ifd = read_int(data, base + 4, 4, endian)
    metadata: list[tuple[str, str, str]] = []
    visited: set[int] = set()
    read_ifd(data, base, first_ifd, endian, "exif", EXIF_TAGS, metadata, visited)
    return metadata


def read_ifd(
    data: bytes,
    base: int,
    offset: int,
    endian: str,
    namespace: str,
    tag_names: dict[int, str],
    metadata: list[tuple[str, str, str]],
    visited: set[int],
) -> None:
    absolute = base + offset
    if absolute in visited or absolute + 2 > len(data):
        return
    visited.add(absolute)
    count = read_int(data, absolute, 2, endian)
    entries_start = absolute + 2
    for i in range(count):
        entry = entries_start + (i * 12)
        if entry + 12 > len(data):
            break
        tag = read_int(data, entry, 2, endian)
        field_type = read_int(data, entry + 2, 2, endian)
        item_count = read_int(data, entry + 4, 4, endian)
        value_offset = data[entry + 8 : entry + 12]
        value = read_tiff_value(data, base, value_offset, field_type, item_count, endian)
        tag_name = tag_names.get(tag, f"Tag0x{tag:04X}")
        if tag == 0x8769 and isinstance(value, int):
            read_ifd(data, base, value, endian, "exif", EXIF_TAGS, metadata, visited)
            continue
        if tag == 0x8825 and isinstance(value, int):
            read_ifd(data, base, value, endian, "gps", GPS_TAGS, metadata, visited)
            continue
        if value not in (None, b""):
            metadata.append((namespace, tag_name, format_value(value)))


def read_tiff_value(
    data: bytes,
    base: int,
    value_offset: bytes,
    field_type: int,
    item_count: int,
    endian: str,
) -> object:
    size = TIFF_TYPE_SIZES.get(field_type)
    if not size:
        return None
    total = size * item_count
    raw = value_offset if total <= 4 else data[base + read_int(value_offset, 0, 4, endian) : base + read_int(value_offset, 0, 4, endian) + total]
    if len(raw) < total:
        return None
    if field_type == 2:
        return raw[:total].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    if field_type in {1, 7}:
        return raw[:total] if item_count != 1 else raw[0]
    if field_type in {3, 4, 9}:
        width = TIFF_TYPE_SIZES[field_type]
        values = [read_int(raw, idx, width, endian, signed=field_type == 9) for idx in range(0, total, width)]
        return values[0] if len(values) == 1 else values
    if field_type in {5, 10}:
        signed = field_type == 10
        values = []
        for idx in range(0, total, 8):
            numerator = read_int(raw, idx, 4, endian, signed=signed)
            denominator = read_int(raw, idx + 4, 4, endian, signed=signed)
            values.append(f"{numerator}/{denominator}" if denominator else str(numerator))
        return values[0] if len(values) == 1 else values
    return raw[:total]


def read_int(data: bytes, offset: int, width: int, endian: str, signed: bool = False) -> int:
    return int.from_bytes(data[offset : offset + width], endian, signed=signed)


def format_value(value: object) -> str:
    if isinstance(value, bytes):
        if len(value) > 64:
            return f"<{len(value)} bytes>"
        return value.decode("utf-8", errors="replace").strip("\x00")
    if isinstance(value, list):
        return ", ".join(format_value(item) for item in value)
    return str(value)


def extract_png_metadata(body: bytes) -> list[tuple[str, str, str]]:
    metadata: list[tuple[str, str, str]] = []
    index = 8
    while index + 8 <= len(body):
        length = int.from_bytes(body[index : index + 4], "big")
        chunk_type = body[index + 4 : index + 8]
        chunk_data = body[index + 8 : index + 8 + length]
        if len(chunk_data) < length:
            break
        if chunk_type == b"tEXt":
            key, _, value = chunk_data.partition(b"\x00")
            metadata.append(("png", key.decode("latin-1", errors="replace"), value.decode("utf-8", errors="replace").strip("\x00")))
        elif chunk_type == b"zTXt":
            key, _, remainder = chunk_data.partition(b"\x00")
            if len(remainder) > 1:
                try:
                    value = zlib.decompress(remainder[1:])
                except zlib.error:
                    value = remainder[1:]
                metadata.append(("png", key.decode("latin-1", errors="replace"), value.decode("utf-8", errors="replace").strip("\x00")))
        elif chunk_type == b"iTXt":
            key, _, remainder = chunk_data.partition(b"\x00")
            if len(remainder) >= 2:
                compression_flag = remainder[0]
                text_fields = remainder[2:].split(b"\x00", 2)
                text = text_fields[2] if len(text_fields) == 3 else b""
                if compression_flag == 1:
                    try:
                        text = zlib.decompress(text)
                    except zlib.error:
                        pass
                metadata.append(("png", key.decode("utf-8", errors="replace"), text.decode("utf-8", errors="replace").strip("\x00")))
        elif chunk_type == b"eXIf":
            metadata.extend(extract_tiff(chunk_data, 0))
        index += 12 + length
    return metadata


def extract_webp_metadata(body: bytes) -> list[tuple[str, str, str]]:
    metadata: list[tuple[str, str, str]] = []
    if not (body.startswith(b"RIFF") and body[8:12] == b"WEBP"):
        return metadata
    index = 12
    while index + 8 <= len(body):
        chunk_type = body[index : index + 4]
        length = int.from_bytes(body[index + 4 : index + 8], "little")
        chunk_data = body[index + 8 : index + 8 + length]
        if len(chunk_data) < length:
            break
        if chunk_type == b"EXIF":
            metadata.extend(extract_tiff(chunk_data, 0))
        elif chunk_type == b"XMP ":
            metadata.append(("xmp", "webp_packet", " ".join(chunk_data.decode("utf-8", errors="replace").split())))
        index += 8 + length + (length % 2)
    return metadata


PDF_INFO_RE = re.compile(rb"/(Title|Author|Subject|Keywords|Creator|Producer|CreationDate|ModDate)\s*(\((?:\\.|[^\\)])*\)|<[^>]*>)")


def extract_pdf_metadata(body: bytes) -> list[tuple[str, str, str]]:
    metadata = []
    sample = body[:2_000_000]
    for key, raw_value in PDF_INFO_RE.findall(sample):
        metadata.append(("pdf", key.decode("ascii"), decode_pdf_value(raw_value)))
    return metadata


def decode_pdf_value(raw: bytes) -> str:
    if raw.startswith(b"(") and raw.endswith(b")"):
        value = raw[1:-1]
        value = value.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
        return value.decode("utf-8", errors="replace")
    if raw.startswith(b"<") and raw.endswith(b">"):
        hex_value = re.sub(rb"\s+", b"", raw[1:-1])
        try:
            return bytes.fromhex(hex_value.decode("ascii")).decode("utf-16-be", errors="replace")
        except ValueError:
            return raw.decode("utf-8", errors="replace")
    return raw.decode("utf-8", errors="replace")


def extract_gif_comments(body: bytes) -> list[tuple[str, str, str]]:
    metadata = []
    index = 0
    comment_index = 0
    while True:
        marker = body.find(b"\x21\xfe", index)
        if marker == -1:
            break
        index = marker + 2
        pieces = []
        while index < len(body):
            size = body[index]
            index += 1
            if size == 0:
                break
            pieces.append(body[index : index + size])
            index += size
        comment_index += 1
        metadata.append(("gif", f"Comment{comment_index}", b"".join(pieces).decode("utf-8", errors="replace")))
    return metadata


XMP_RE = re.compile(rb"<x:xmpmeta[\s\S]*?</x:xmpmeta>|<rdf:RDF[\s\S]*?</rdf:RDF>", re.IGNORECASE)


def extract_xmp(body: bytes) -> list[tuple[str, str, str]]:
    metadata = []
    for idx, match in enumerate(XMP_RE.finditer(body[:5_000_000]), start=1):
        text = match.group(0).decode("utf-8", errors="replace")
        metadata.append(("xmp", f"packet_{idx}", " ".join(text.split())))
    return metadata


def write_csv(path: str, rows: Iterable[dict[str, str | int]]) -> None:
    rows = list(rows)
    fixed_fieldnames = [
        "source_url",
        "page_url",
        "media_type",
        "content_type",
        "file_extension",
        "bytes",
        "error",
    ]
    dynamic_fieldnames = sorted(
        {
            key
            for row in rows
            for key in row
            if key not in fixed_fieldnames
        }
    )
    fieldnames = fixed_fieldnames + dynamic_fieldnames
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def doctor(args: argparse.Namespace) -> int:
    payload = {
        "ok": True,
        "version": __version__,
        "python": sys.version.split()[0],
        "network_required_for_crawl": True,
        "auth_required": False,
        "extractors": ["jpeg_exif", "tiff_exif", "png_text", "png_exif", "webp_exif", "gif_comments", "pdf_info", "xmp"],
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"site-exif {__version__}")
        print(f"python {payload['python']}")
        print("extractors: " + ", ".join(payload["extractors"]))
    return 0


def prompt_text(label: str, default: str | None = None, required: bool = False) -> str:
    while True:
        suffix = f" [{default}]" if default is not None else ""
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        if not required:
            return ""
        print("Please enter a value.")


def prompt_int(label: str, default: int, minimum: int | None = None) -> int:
    while True:
        value = prompt_text(label, str(default))
        try:
            parsed = int(value)
        except ValueError:
            print("Please enter a whole number.")
            continue
        if minimum is not None and parsed < minimum:
            print(f"Please enter {minimum} or higher.")
            continue
        return parsed


def prompt_float(label: str, default: float, minimum: float | None = None) -> float:
    while True:
        value = prompt_text(label, str(default))
        try:
            parsed = float(value)
        except ValueError:
            print("Please enter a number.")
            continue
        if minimum is not None and parsed < minimum:
            print(f"Please enter {minimum} or higher.")
            continue
        return parsed


def prompt_yes_no(label: str, default: bool) -> bool:
    default_text = "Y/n" if default else "y/N"
    while True:
        value = input(f"{label} [{default_text}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Please answer y or n.")


def interactive(args: argparse.Namespace) -> int:
    print(CYBERPUNK_HEADER)
    print("Answer the questions below. Press Enter to accept the value in brackets.\n")

    url = prompt_text("Website URL to scan", required=True)
    output = prompt_text("CSV output file name", "site-exif.csv")
    full_crawl = prompt_yes_no("Try to crawl the whole site", False)
    if full_crawl:
        max_pages = 0
        max_depth = -1
    else:
        max_pages = prompt_int("Maximum pages to crawl (0 means unlimited)", DEFAULT_MAX_PAGES, minimum=0)
        max_depth = prompt_int("Maximum link depth (-1 means unlimited)", DEFAULT_MAX_DEPTH, minimum=-1)
    timeout = prompt_float("Seconds to wait for each request", 15.0, minimum=1.0)
    delay = prompt_float("Delay between requests in seconds", 0.0, minimum=0.0)
    max_mb = prompt_int("Largest single file to download, in MB", 50, minimum=1)
    exact_host = prompt_yes_no("Stay on the exact host only", False)
    no_sitemaps = not prompt_yes_no("Use sitemaps to find more pages", True)
    user_agent = prompt_text("User-Agent to send", DEFAULT_USER_AGENT)
    verbose = prompt_yes_no("Show progress while it runs", True)
    verbose_all = prompt_yes_no("Show full long URLs in progress output", False)

    print("\nReady to run:")
    print(f"  URL: {url}")
    print(f"  CSV: {output}")
    print(f"  Max pages: {'unlimited' if max_pages == 0 else max_pages}")
    print(f"  Max depth: {'unlimited' if max_depth < 0 else max_depth}")
    if not prompt_yes_no("Start now", True):
        print("Canceled.")
        return 1

    crawl_args = argparse.Namespace(
        url=url,
        output=output,
        max_pages=max_pages,
        max_depth=max_depth,
        max_bytes=max_mb * 1024 * 1024,
        timeout=timeout,
        delay=delay,
        include_subdomains=False,
        exact_host=exact_host,
        no_sitemaps=no_sitemaps,
        user_agent=user_agent,
        verbose=verbose,
        verbose_all=verbose_all,
    )
    return crawl(crawl_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="site-exif", description="Crawl same-site pages and export media/document metadata to CSV.")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON for commands that support it")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="show runtime and extractor support")
    doctor_parser.set_defaults(func=doctor)

    interactive_parser = subparsers.add_parser("interactive", help="ask questions and run a guided crawl")
    interactive_parser.set_defaults(func=interactive)

    crawl_parser = subparsers.add_parser("crawl", help="crawl a site and write metadata CSV")
    crawl_parser.add_argument("url", help="starting URL")
    crawl_parser.add_argument("-o", "--output", default="site-exif.csv", help="CSV output path")
    crawl_parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="maximum HTML pages to crawl; use 0 for unlimited")
    crawl_parser.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH, help="maximum link depth from starting URL; use -1 for unlimited")
    crawl_parser.add_argument("--max-bytes", type=int, default=MAX_DEFAULT_BYTES, help="maximum bytes to download for one asset")
    crawl_parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds")
    crawl_parser.add_argument("--delay", type=float, default=0.0, help="delay between requests in seconds")
    crawl_parser.add_argument("--include-subdomains", action="store_true", help="allow subdomains under the starting domain; this is the default unless --exact-host is used")
    crawl_parser.add_argument("--exact-host", action="store_true", help="only crawl the exact starting host, excluding www/assets subdomains")
    crawl_parser.add_argument("--no-sitemaps", action="store_true", help="do not seed the crawl from /sitemap.xml and sitemap entries in /robots.txt")
    crawl_parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="custom User-Agent header")
    crawl_parser.add_argument("-v", "--verbose", action="store_true", help="print requested URLs and summary to stderr")
    crawl_parser.add_argument("--verbose-all", action="store_true", help="do not shorten very long URLs in verbose output")
    crawl_parser.set_defaults(func=crawl)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
