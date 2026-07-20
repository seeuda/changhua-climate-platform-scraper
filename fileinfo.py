"""Shared helpers for inferring file metadata from HTTP responses.

Real cca.gov.tw download URLs (service.cca.gov.tw/File/Get/...) carry no
file extension, so format/filename must come from response headers.
"""

import re
from pathlib import Path
from urllib.parse import unquote

EXTENSION_FORMATS = {
    '.pdf': 'PDF', '.doc': 'Word', '.docx': 'Word',
    '.xls': 'Excel', '.xlsx': 'Excel', '.ods': 'ODF Excel', '.odt': 'ODF Word',
    '.ppt': 'PowerPoint', '.pptx': 'PowerPoint', '.zip': 'ZIP',
}

CONTENT_TYPE_FORMATS = {
    'application/pdf': 'PDF',
    'application/msword': 'Word',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word',
    'application/vnd.ms-excel': 'Excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'Excel',
    'application/vnd.ms-powerpoint': 'PowerPoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'PowerPoint',
    'application/zip': 'ZIP',
    'application/x-zip-compressed': 'ZIP',
    'application/vnd.oasis.opendocument.text': 'ODF Word',
    'application/vnd.oasis.opendocument.spreadsheet': 'ODF Excel',
}

CONTENT_TYPE_EXTENSIONS = {v: k for k, v in EXTENSION_FORMATS.items()}


def filename_from_disposition(disposition: str) -> str:
    """Parse filename from a Content-Disposition header (RFC 5987 aware).

    cca.gov.tw sends percent-encoded names in the plain filename= form
    (not filename*=), so those are unquoted too."""
    if not disposition:
        return ''
    m = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", disposition, re.IGNORECASE)
    if m:
        return unquote(m.group(1).strip().strip('"'))
    m = re.search(r'filename="?([^";]+)"?', disposition, re.IGNORECASE)
    if not m:
        return ''
    name = m.group(1).strip()
    if '%' in name:
        decoded = unquote(name)
        if '�' not in decoded:
            return decoded
    return name


def format_from_headers(headers) -> str:
    """Infer document format from response headers; '' if unknown."""
    filename = filename_from_disposition(headers.get('Content-Disposition', ''))
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in EXTENSION_FORMATS:
            return EXTENSION_FORMATS[ext]
    ctype = (headers.get('Content-Type') or '').split(';')[0].strip()
    return CONTENT_TYPE_FORMATS.get(ctype, '')


def extension_for_format(file_format: str) -> str:
    """Best-effort extension for a format label; '.bin' if unknown."""
    return CONTENT_TYPE_EXTENSIONS.get(file_format, '.bin')


def human_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
