#!/usr/bin/env python3
"""Check QuantStrategyLab website assets, links, and identifier leaks.

Usage:
    python scripts/check_site.py [--root PATH] [--phase {1,2}] [--advisory] [--visibility {public,private}]
"""

from __future__ import annotations

import argparse
import base64
import fnmatch
import html
import ipaddress
import json
import posixpath
import re
import struct
import subprocess
import sys
import urllib.parse
import zlib
from html.parser import HTMLParser
from pathlib import Path
from typing import NamedTuple

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "build", "dist",
    ".gradle", ".mypy_cache", ".pytest_cache", ".ruff_cache", "site-packages",
    ".idea", ".vscode",
}

# Section 13 says "non-placeholder buckets" and section 7 says the placeholder
# form is `<bucket>`, `<project-id>`, `$PROJECTS_ROOT`. A `gs://` URI whose
# bucket segment is a placeholder is the correct form, not a finding.
PLACEHOLDER_BUCKET = re.compile(
    r"^[<{$]|[<>{}]|\.\.\."
    r"|^(?:your|my|example|sample|placeholder|shared|synthetic)[-_]"
    r"|^bucket(?:-|$)"
)

PLACEHOLDER_SUBDOMAIN = re.compile(
    r"^[<{$]|[<>{}]"
    r"|^(?:your|my|example|sample|placeholder)[-_]"
    r"|^subdomain(?:-|$)"
    r"|^x{2,}$"
)

URL_TOKEN = re.compile(r"https?://[^\s)\]\"'<>`]+", re.IGNORECASE)
FENCED_BLOCK = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)


class FileContext(NamedTuple):
    """Per-file material the leak predicates need to judge a match."""

    url_spans: list[tuple[int, int]]
    prose: str  # text with fenced blocks blanked out, offsets preserved
    masked: str  # `prose` with inline code blanked out too


def phrase_is_prose(text: str, match: re.Match, ctx: FileContext) -> bool:
    """Return True when a prose-only rule matched outside code spans and fences."""
    return bool(ctx.masked[match.start():match.end()].strip())


def bucket_is_real(text: str, match: re.Match, ctx: FileContext) -> bool:
    """Return True when a `gs://` URI names a non-placeholder bucket."""
    bucket = match.group(0)[len("gs://"):].split("/", 1)[0].lower()
    if bucket.endswith(".") and not bucket.endswith("..."):
        bucket = bucket[:-1]
    return bool(bucket) and not PLACEHOLDER_BUCKET.search(bucket)


def subdomain_is_real(text: str, match: re.Match, ctx: FileContext) -> bool:
    """Return True when a `*.workers.dev` host is not a documented placeholder."""
    subdomain = match.group(0)[: -len(".workers.dev")]
    return not PLACEHOLDER_SUBDOMAIN.search(subdomain.lower())


PLACEHOLDER_HOME_USER = re.compile(
    r"^/(?:Users|home)/(?:<[^>]+>|\{[^}]+\}|\$[A-Za-z_]\w*|(?:your|my|example|sample|placeholder)(?:[-_]\w+)?)(?:/|$)",
    re.IGNORECASE,
)
PLACEHOLDER_PATH_SEG = re.compile(
    r"^(?:<[^>]+>|\{[^}]+\}|\$[A-Za-z_]\w*|%[A-Za-z_]\w*%|\.\.\."
    r"|(?:your|my|example|sample|placeholder)(?:[-_.]\w+)?)$",
    re.IGNORECASE,
)


def home_path_is_real(text: str, match: re.Match, ctx: FileContext) -> bool:
    """Reject workstation home paths while allowing placeholders and URL `/home/` segments."""
    if any(start <= match.start() < end for start, end in ctx.url_spans):
        return False
    return not PLACEHOLDER_HOME_USER.search(match.group(0))


def windows_path_is_real(text: str, match: re.Match, ctx: FileContext) -> bool:
    """Reject Windows drive-letter and UNC paths while allowing explicit placeholders."""
    raw = match.group(0).rstrip(".,;:")
    if "\\" not in raw and any(start <= match.start() < end for start, end in ctx.url_spans):
        return False
    if raw.startswith(("\\\\", "//")):
        parts = [p for p in re.split(r"[\\/]+", raw) if p]
        if not parts:
            return False
        return not PLACEHOLDER_PATH_SEG.match(parts[0])
    rest = re.sub(r"^[A-Za-z]:[\\/]+", "", raw)
    segs = [s for s in re.split(r"[\\/]+", rest) if s]
    if not segs:
        return False
    if segs[0].lower() == "users":
        if len(segs) < 2:
            return not bool(re.match(r"^(?:<[^>]+>|\{[^}]+\})", text[match.end():]))
        return not PLACEHOLDER_PATH_SEG.match(segs[1])
    return not PLACEHOLDER_PATH_SEG.match(segs[0])


def hex_is_prose(text: str, match: re.Match, ctx: FileContext) -> bool:
    """Reject bare 40-char hex SHAs in prose while exempting links, code, and placeholders."""
    if ctx.prose[match.start()] == " ":
        return False
    for start, end in ctx.url_spans:
        if start <= match.start() < end:
            return False
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    line = text[line_start: line_end if line_end != -1 else len(text)]
    column = match.start() - line_start
    if line[:column].count("`") % 2 == 1:
        return False
    if text[match.end(): match.end() + 2] == "](":
        return False
    return len(set(match.group(0))) != 1


LEAK_PATTERNS = [
    (re.compile(r"(?<![\w.])/(?i:users|home)/[^\s`)\]\"'<>|]{2,}"),
     "paths", "absolute home path (section 13)", home_path_is_real),
    (re.compile(
        r"(?:(?<![A-Za-z0-9_])[A-Za-z]:(?:\\+|/)[^\s`)\]\"'<>|]{2,}"
        r"|(?<![:/\\A-Za-z0-9_])(?:\\\\(?:<[^>]+>|\{[^}]+\}|[A-Za-z0-9.$%_-]+)\\+(?:<[^>]+>|\{[^}]+\}|[A-Za-z0-9$.%_-]+)(?:\\+[^\s`)\]\"'<>|]*)*"
        r"|//(?:<[^>]+>|\{[^}]+\}|[A-Za-z0-9$%_-]+)/(?:<[^>]+>|\{[^}]+\}|[A-Za-z0-9$.%_-]+)(?:/[^\s`)\]\"'<>|]*)*))"
     ),
     "paths", "Windows deployment path (section 13)", windows_path_is_real),
    (re.compile(r"\bgs://[^\s`)\]\"'<>]+", re.IGNORECASE),
     "content", "non-placeholder bucket (section 13)", bucket_is_real),
    (re.compile(r"\b[\w-]+\.workers\.dev\b", re.IGNORECASE),
     "publish", "personal subdomain (section 13)", subdomain_is_real),
    (re.compile(r"\b[0-9a-f]{40}\b"),
     "content", "40-character hex string in prose (section 5)", hex_is_prose),
    (re.compile(r"\|\s*(?:PR\s*#?\d+|#\d+)"),
     "content", "PR-number status table (section 5)", None),
    (re.compile(r"\b(this round|this task|in this task)\b", re.IGNORECASE),
     "content", "task-scope wording (section 5)", phrase_is_prose),
    (re.compile(r"\b(the owner approved|approved by)\b", re.IGNORECASE),
     "content", "owner approval note (section 5)", phrase_is_prose),
]


INTERNAL_NOTE_GITIGNORE = [
    "*[Aa][Uu][Dd][Ii][Tt]*.md",
    "*[Hh][Aa][Nn][Dd][Oo][Ff][Ff]*.md",
    "*-[Rr][Ee][Vv][Ii][Ee][Ww]-*.md",
    "*_[Rr][Ee][Vv][Ii][Ee][Ww]_*.md",
    "docs/audits/",
    "docs/plans/",
    "docs/handoffs/",
    "docs/superpowers/",
    "docs/changes/",
    "docs/acceptance-policy.md",
    ".claude/",
    ".codex/",
    ".local/",
    "ops-notes/",
    "*.local.md",
    "*.internal.md",
]

INTERNAL_NOTE_DIRS = re.compile(
    r"(^|/)(docs/plans|docs/handoffs|docs/superpowers|docs/audits|docs/changes)/"
)

PHASE_BLOCKING = {
    1: {"paths", "links", "agents", "hygiene", "publish"},
    2: {"paths", "links", "agents", "hygiene", "publish", "content", "naming", "language", "docs"},
}

PUBLICATION_CATEGORIES = {"paths", "publish"}


class Report:
    """Collect categorized findings and separate blocking vs advisory items."""

    def __init__(self, blocking: set[str]) -> None:
        self.blocking = blocking
        self.findings: list[tuple[str, str]] = []

    def add(self, category: str, message: str) -> None:
        self.findings.append((category, message))

    def blocking_findings(self) -> list[tuple[str, str]]:
        return [f for f in self.findings if f[0] in self.blocking]

    def advisory_findings(self) -> list[tuple[str, str]]:
        return [f for f in self.findings if f[0] not in self.blocking]


def git_visible_files(root: Path) -> set[Path] | None:
    """Return tracked and unignored working-tree files when root is a Git checkout."""
    if not (root / ".git").exists():
        return None
    res = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if res.returncode != 0:
        return None
    visible: set[Path] = set()
    for raw in res.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="surrogateescape")
        candidate = root / rel
        if candidate.is_file():
            visible.add(candidate)
    return visible


def is_untracked_gitignored(root: Path, rel_path: str) -> bool:
    """Return True only when rel_path has no tracked/unignored files and is gitignored."""
    if not (root / ".git").exists():
        return False
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", rel_path],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if listed.returncode == 0 and listed.stdout.strip(b"\0"):
        return False
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--", rel_path],
        cwd=root,
        check=False,
    )
    return ignored.returncode == 0


def should_skip_path(root: Path, path: Path) -> bool:
    """Skip tooling directories outside site/; Pages publishes the entire site/ tree."""
    rel_parts = path.relative_to(root).parts
    if ".git" in rel_parts:
        return True
    if rel_parts and rel_parts[0] == "site":
        return False
    return any(part in SKIP_DIRS for part in rel_parts)


def iter_files(root: Path):
    """Yield repository files subject to scanning."""
    visible = git_visible_files(root)
    if visible is not None:
        for path in sorted(visible):
            if should_skip_path(root, path):
                continue
            yield path
        return
    for path in sorted(root.rglob("*")):
        if should_skip_path(root, path):
            continue
        if path.is_file():
            yield path


def is_markdown(path: Path) -> bool:
    return path.suffix.lower() in {".md", ".markdown"}


CODE_SPAN = re.compile(r"`[^`\n]+`")


def blank_code_spans(text: str) -> str:
    """Replace inline code with spaces while preserving character offsets."""
    return CODE_SPAN.sub(lambda m: " " * len(m.group(0)), text)


def blank_fenced_blocks(text: str) -> str:
    """Replace fenced code blocks with spaces while preserving character offsets."""
    def blank(match: re.Match) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    return FENCED_BLOCK.sub(blank, text)


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PNG_ALLOWED_ANCILLARY_CHUNKS = {
    b"PLTE", b"tRNS", b"gAMA", b"cHRM", b"sRGB",
    b"sBIT", b"bKGD", b"hIST", b"pHYs",
}
PNG_TEXT_CHUNKS = {b"tEXt", b"zTXt", b"iTXt"}
PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
PNG_VALID_BIT_DEPTHS = {
    0: {1, 2, 4, 8, 16},
    2: {8, 16},
    3: {1, 2, 4, 8},
    4: {8, 16},
    6: {8, 16},
}
_ADAM7_PASSES = (
    (0, 8, 0, 8),
    (4, 8, 0, 8),
    (0, 4, 4, 8),
    (2, 4, 0, 4),
    (0, 2, 2, 4),
    (1, 2, 0, 2),
    (0, 1, 1, 2),
)

ALLOWED_SITE_TEXT_SUFFIXES: set[str] = {
    ".html", ".htm", ".xhtml", ".css", ".js", ".mjs", ".cjs", ".svg", ".xml",
    ".json", ".webmanifest", ".yaml", ".yml", ".toml", ".txt", ".md", ".map",
}


def _parse_srcset_urls(srcset: str) -> list[str]:
    """Extract candidate URLs from an HTML srcset attribute per spec."""
    urls: list[str] = []
    i, n = 0, len(srcset)
    while i < n:
        while i < n and srcset[i] in " \t\n\r\f,":
            i += 1
        if i >= n:
            break
        start = i
        while i < n and srcset[i] not in " \t\n\r\f":
            i += 1
        url = srcset[start:i]
        if url.endswith(","):
            urls.append(url.rstrip(","))
            continue
        urls.append(url)
        while i < n and srcset[i] in " \t\n\r\f":
            i += 1
        while i < n and srcset[i] != ",":
            i += 1
        if i < n and srcset[i] == ",":
            i += 1
    return urls


def resolve_site_asset_href(page_rel: str, href: str, allow_root: bool = False) -> str | None:
    """Resolve a site/-local HTML/CSS href against page_rel; return None for external or escaping targets."""
    raw = href.strip()
    if not raw or raw.startswith("//") or "\\" in raw:
        return None
    clean = raw.split("#", 1)[0].split("?", 1)[0].strip()
    if not clean or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", clean):
        return None
    clean = urllib.parse.unquote(clean)
    if not clean or "\\" in clean or "\x00" in clean or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", clean):
        return None
    sub_page = page_rel[len("site/"):] if page_rel.startswith("site/") else page_rel
    if clean.startswith("/"):
        rel_in_site = posixpath.normpath(clean.lstrip("/"))
    else:
        base_dir = posixpath.dirname(sub_page)
        joined = posixpath.join(base_dir, clean) if base_dir else clean
        rel_in_site = posixpath.normpath(joined)
    if rel_in_site == ".":
        return "site" if allow_root else None
    if rel_in_site in ("", "..") or rel_in_site.startswith("../"):
        return None
    return "site/" + rel_in_site


def _zlib_decompress_exact(data: bytes) -> bytes | None:
    """Decompress a zlib stream and fail closed on truncation or trailing bytes."""
    zobj = zlib.decompressobj()
    try:
        out = zobj.decompress(data) + zobj.flush()
    except zlib.error:
        return None
    if not zobj.eof or zobj.unused_data or zobj.unconsumed_tail:
        return None
    return out


def _decode_png_text_chunk(ctype: bytes, cdata: bytes) -> list[str] | None:
    """Decode a PNG tEXt/zTXt/iTXt chunk into text parts, or None if malformed."""
    if ctype == b"tEXt":
        if b"\x00" not in cdata:
            return None
        return [cdata.replace(b"\x00", b"\n").decode("latin-1")]
    if ctype == b"zTXt":
        sep = cdata.find(b"\x00")
        if sep == -1 or sep + 2 > len(cdata) or cdata[sep + 1] != 0:
            return None
        zraw = _zlib_decompress_exact(cdata[sep + 2:])
        if zraw is None:
            return None
        return [cdata[:sep].decode("latin-1"), zraw.decode("latin-1")]
    sep1 = cdata.find(b"\x00")
    if sep1 == -1 or sep1 + 3 > len(cdata):
        return None
    comp_flag, comp_method = cdata[sep1 + 1], cdata[sep1 + 2]
    rest_parts = cdata[sep1 + 3:].split(b"\x00", 2)
    if len(rest_parts) < 3:
        return None
    text_bytes = rest_parts[2]
    if comp_flag == 1:
        if comp_method != 0:
            return None
        text_bytes = _zlib_decompress_exact(text_bytes)
        if text_bytes is None:
            return None
    elif comp_flag != 0:
        return None
    try:
        return [cdata[:sep1].decode("utf-8"), text_bytes.decode("utf-8")]
    except UnicodeDecodeError:
        return None


def _valid_png_scanlines(
    decomp: bytes, width: int, height: int, bit_depth: int, color_type: int, interlace: int
) -> bool:
    """Verify PNG decompressed scanline lengths and filter-type bytes for non-interlaced and Adam7 PNGs."""
    bits_per_pixel = PNG_CHANNELS[color_type] * bit_depth
    passes = _ADAM7_PASSES if interlace == 1 else ((0, 1, 0, 1),)
    offset = 0
    for xs, xstep, ys, ystep in passes:
        if width <= xs or height <= ys:
            continue
        pass_w = (width - xs + xstep - 1) // xstep
        pass_h = (height - ys + ystep - 1) // ystep
        stride = (pass_w * bits_per_pixel + 7) // 8
        for _ in range(pass_h):
            if offset + 1 + stride > len(decomp) or decomp[offset] > 4:
                return False
            offset += 1 + stride
    return offset == len(decomp)


def _valid_ancillary_png_chunk(
    ctype: bytes, cdata: bytes, bit_depth: int, color_type: int, plte_entries: int
) -> bool:
    """Validate structure and spec-mandated byte sizes of allowed ancillary PNG chunks."""
    if ctype == b"sRGB":
        return len(cdata) == 1 and cdata[0] <= 3
    if ctype == b"gAMA":
        return len(cdata) == 4 and struct.unpack(">I", cdata)[0] > 0
    if ctype == b"cHRM":
        return len(cdata) == 32
    if ctype == b"pHYs":
        return len(cdata) == 9 and cdata[8] in (0, 1)
    if ctype == b"sBIT":
        expected = 3 if color_type == 3 else PNG_CHANNELS[color_type]
        max_bits = 8 if color_type == 3 else bit_depth
        return len(cdata) == expected and all(1 <= b <= max_bits for b in cdata)
    if ctype == b"bKGD":
        if color_type == 3:
            return plte_entries > 0 and len(cdata) == 1 and cdata[0] < plte_entries
        return len(cdata) == (2 if color_type in (0, 4) else 6)
    if ctype == b"tRNS":
        if color_type == 0:
            return len(cdata) == 2
        if color_type == 2:
            return len(cdata) == 6
        if color_type == 3:
            return plte_entries > 0 and 1 <= len(cdata) <= plte_entries
        return False
    if ctype == b"hIST":
        return plte_entries > 0 and len(cdata) == 2 * plte_entries
    return False


def inspect_png_asset(raw: bytes) -> tuple[str, bool] | None:
    """Validate PNG magic, chunk CRCs, IHDR, IDAT zlib stream, IEND, and ancillary text chunks.

    Returns (extracted_metadata_text, has_text_metadata), or None if malformed.
    """
    if not raw.startswith(PNG_MAGIC):
        return None
    pos = len(PNG_MAGIC)
    ihdr: tuple[int, int, int, int, int] | None = None
    seen_iend = False
    has_text_meta = False
    seen_ancillary: set[bytes] = set()
    plte_entries = 0
    idat_parts: list[bytes] = []
    parts: list[str] = []
    while pos + 8 <= len(raw):
        clen, ctype = struct.unpack(">I4s", raw[pos:pos + 8])
        data_start = pos + 8
        data_end = data_start + clen
        if data_end + 4 > len(raw):
            return None
        cdata = raw[data_start:data_end]
        expected_crc = struct.unpack(">I", raw[data_end:data_end + 4])[0]
        if (zlib.crc32(ctype + cdata) & 0xFFFFFFFF) != expected_crc:
            return None
        pos = data_end + 4
        if ihdr is None:
            if ctype != b"IHDR" or len(cdata) != 13:
                return None
            width, height, bit_depth, color_type, comp, flt, interlace = struct.unpack(">IIBBBBB", cdata)
            valid_depths = PNG_VALID_BIT_DEPTHS.get(color_type)
            if (
                width < 1
                or height < 1
                or valid_depths is None
                or bit_depth not in valid_depths
                or comp != 0
                or flt != 0
                or interlace not in (0, 1)
            ):
                return None
            ihdr = (width, height, bit_depth, color_type, interlace)
            continue
        if ctype == b"IHDR":
            return None
        if ctype == b"IEND":
            if clen != 0:
                return None
            seen_iend = True
            break
        if ctype == b"IDAT":
            idat_parts.append(cdata)
            continue
        if ctype == b"PLTE":
            if (
                ihdr[3] != 3
                or idat_parts
                or ctype in seen_ancillary
                or not (3 <= len(cdata) <= 3 * (1 << ihdr[2]))
                or len(cdata) % 3 != 0
            ):
                return None
            seen_ancillary.add(ctype)
            plte_entries = len(cdata) // 3
            continue
        if ctype in PNG_ALLOWED_ANCILLARY_CHUNKS:
            if idat_parts or ctype in seen_ancillary:
                return None
            if not _valid_ancillary_png_chunk(ctype, cdata, ihdr[2], ihdr[3], plte_entries):
                return None
            seen_ancillary.add(ctype)
            continue
        if ctype in PNG_TEXT_CHUNKS:
            has_text_meta = True
            decoded = _decode_png_text_chunk(ctype, cdata)
            if decoded is None:
                return None
            parts.extend(decoded)
            continue
        return None
    if ihdr is None or not seen_iend or pos != len(raw) or not idat_parts:
        return None
    if ihdr[3] == 3 and plte_entries == 0:
        return None
    decomp = _zlib_decompress_exact(b"".join(idat_parts))
    if decomp is None:
        return None
    width, height, bit_depth, color_type, interlace = ihdr
    if not _valid_png_scanlines(decomp, width, height, bit_depth, color_type, interlace):
        return None
    return "\n".join(parts), has_text_meta


def inspect_ico_asset(raw: bytes) -> tuple[str, bool] | None:
    """Validate ICO directory structure and embedded PNG frames."""
    if len(raw) < 6:
        return None
    reserved, itype, count = struct.unpack("<HHH", raw[:6])
    if reserved != 0 or itype not in (1, 2) or count < 1:
        return None
    dir_end = 6 + 16 * count
    if dir_end > len(raw):
        return None
    spans: list[tuple[int, int]] = []
    for i in range(count):
        base = 6 + 16 * i
        size, offset = struct.unpack("<II", raw[base + 8:base + 16])
        if size < 8 or offset < dir_end or offset + size > len(raw):
            return None
        spans.append((offset, offset + size))
    spans.sort()
    cursor = dir_end
    parts: list[str] = []
    has_text_meta = False
    for start, end in spans:
        if start != cursor:
            return None
        cursor = end
        entry = raw[start:end]
        if not entry.startswith(PNG_MAGIC):
            return None
        png_info = inspect_png_asset(entry)
        if png_info is None:
            return None
        png_txt, png_meta = png_info
        has_text_meta = has_text_meta or png_meta
        if png_txt:
            parts.append(png_txt)
    if cursor != len(raw):
        return None
    return "\n".join(parts), has_text_meta


def _decode_site_text(raw: bytes) -> tuple[str, str | None]:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return "text", raw.decode("utf-16")
        except UnicodeDecodeError:
            return "unscanned_binary", None
    if b"\x00" in raw:
        return "unscanned_binary", None
    try:
        return "text", raw.decode("utf-8")
    except UnicodeDecodeError:
        return "unscanned_binary", None


def read_deployed_site_asset(root: Path, path: Path) -> tuple[str, str | None]:
    """Return ('text', str), ('png_metadata', str), ('skip', None), or ('unscanned_binary', None)."""
    rel = path.relative_to(root).as_posix()
    if not rel.startswith("site/"):
        return "skip", None
    suffix = path.suffix.lower()
    raw = path.read_bytes()
    if suffix == ".png":
        inspected = inspect_png_asset(raw)
        if inspected is None:
            return "unscanned_binary", None
        text, has_text_meta = inspected
        return ("png_metadata", text) if has_text_meta else ("text", text)
    if suffix == ".ico":
        inspected = inspect_ico_asset(raw)
        if inspected is None:
            return "unscanned_binary", None
        text, has_text_meta = inspected
        return ("png_metadata", text) if has_text_meta else ("text", text)
    if suffix in ALLOWED_SITE_TEXT_SUFFIXES:
        return _decode_site_text(raw)
    return "unscanned_binary", None


INTERNAL_IPV4_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
)

INTERNAL_IPV6_NETWORKS = (
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::1/128"),
)


def is_internal_ipv4(addr: ipaddress.IPv4Address) -> bool:
    return any(addr in net for net in INTERNAL_IPV4_NETWORKS)


def ipv4_is_private(text: str, match: re.Match, ctx: FileContext) -> bool:
    try:
        addr = ipaddress.ip_address(match.group(0))
    except ValueError:
        return False
    return isinstance(addr, ipaddress.IPv4Address) and is_internal_ipv4(addr)


def ipv6_is_private(text: str, match: re.Match, ctx: FileContext) -> bool:
    candidate = match.group(0).split("%", 1)[0]
    try:
        addr = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    if not isinstance(addr, ipaddress.IPv6Address):
        return False
    if addr.ipv4_mapped is not None and is_internal_ipv4(addr.ipv4_mapped):
        return True
    return any(addr in net for net in INTERNAL_IPV6_NETWORKS)


def internal_host_is_real(text: str, match: re.Match, ctx: FileContext) -> bool:
    host = match.group(0).lower()
    if host in {"localhost.local", "localhost.localdomain"}:
        return False
    return not any(PLACEHOLDER_SUBDOMAIN.search(label) for label in host.split("."))


def arn_is_real(text: str, match: re.Match, ctx: FileContext) -> bool:
    acct = match.group(1)
    return len(set(acct)) > 1


def service_account_is_real(text: str, match: re.Match, ctx: FileContext) -> bool:
    user, proj = match.group(1).lower(), match.group(2).lower()
    return not (PLACEHOLDER_SUBDOMAIN.search(user) or PLACEHOLDER_SUBDOMAIN.search(proj))


def account_field_is_real(text: str, match: re.Match, ctx: FileContext) -> bool:
    val = match.group(1).lower().replace("-", "")
    return len(set(val)) > 1


INVISIBLE_FORMAT_RE = re.compile(r"[\u00ad\u200b\u200c\u200d\u2060\ufeff]")
BIDI_CONTROL_RE = re.compile(r"[\u200e\u200f\u061c\u202a-\u202e\u2066-\u2069]")
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
JS_ESCAPE_RE = re.compile(
    r"\\(?:u\{([0-9a-fA-F]{1,6})\}|u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2})|([/'\"\\]))"
)
CSS_ESCAPE_RE = re.compile(r"\\([0-9a-fA-F]{1,6})(?:\r\n|[ \t\r\n\f])?")
LINE_CONTINUATION_RE = re.compile(r"\\(?:\r\n|[\r\n\f])")
HTML_BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "body", "br", "caption", "dd",
    "details", "dialog", "div", "dl", "dt", "fieldset", "figcaption", "figure",
    "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header",
    "hgroup", "hr", "html", "li", "link", "main", "menu", "meta", "nav",
    "noscript", "ol", "option", "p", "pre", "script", "section", "style",
    "summary", "table", "tbody", "td", "template", "tfoot", "th", "thead",
    "title", "tr", "ul", "text",
}


def unescape_js_literals(text: str) -> str:
    """Decode JS/JSON unicode, hex, and slash escapes for identifier scanning."""
    def _repl(match: re.Match) -> str:
        g1, g2, g3, g4 = match.groups()
        if g4 is not None:
            return g4
        cp = int(g1 or g2 or g3, 16)
        if 0 <= cp <= 0x10FFFF and not (0xD800 <= cp <= 0xDFFF):
            return chr(cp)
        return match.group(0)

    return JS_ESCAPE_RE.sub(_repl, LINE_CONTINUATION_RE.sub("", text))


def unescape_css_literals(text: str) -> str:
    """Decode CSS hex and simple escapes for identifier scanning."""
    def _repl(match: re.Match) -> str:
        cp = int(match.group(1), 16)
        if 0 < cp <= 0x10FFFF and not (0xD800 <= cp <= 0xDFFF):
            return chr(cp)
        return match.group(0)

    decoded = CSS_ESCAPE_RE.sub(_repl, LINE_CONTINUATION_RE.sub("", text))
    decoded = re.sub(r"\\([^\n\r\f0-9a-fA-F])", r"\1", decoded)
    while True:
        folded = re.sub(r'"([^"\n]*)"\s+"([^"\n]*)"', r'"\1\2"', decoded)
        folded = re.sub(r"'([^'\n]*)'\s+'([^'\n]*)'", r"'\1\2'", folded)
        if folded == decoded:
            return folded
        decoded = folded


def fold_js_expressions(text: str) -> str:
    """Decode common JS literal obfuscations (atob, fromCharCode, array join, string concat)."""
    out = unescape_js_literals(text)
    extras: list[str] = []
    for m in re.finditer(r"\batob\(\s*([\"'])([A-Za-z0-9+/=\s]{4,})\1\s*\)", out):
        try:
            decoded = base64.b64decode(re.sub(r"\s+", "", m.group(2))).decode("utf-8", errors="ignore")
            if decoded:
                extras.append(decoded)
        except Exception:
            pass
    for m in re.finditer(
        r"String\s*\.\s*from(?:CharCode|CodePoint)\s*(?:\.\s*apply\s*\([^,]+,\s*\[([^\]]+)\]\s*\)|\(([^)]+)\))",
        out,
    ):
        chars: list[str] = []
        arg_list = m.group(1) if m.group(1) is not None else (m.group(2) or "")
        for tok in arg_list.split(","):
            tok = tok.strip()
            try:
                cp = int(tok, 0)
                if 0 < cp <= 0x10FFFF and not (0xD800 <= cp <= 0xDFFF):
                    chars.append(chr(cp))
            except ValueError:
                pass
        if chars:
            extras.append("".join(chars))
    for m in re.finditer(
        r"\[\s*((?:(?:\"[^\"\\]*\"|'[^'\\]*')\s*,\s*)*(?:\"[^\"\\]*\"|'[^'\\]*'))\s*\]"
        r"(\s*\.\s*reverse\s*\(\s*\))?\s*\.\s*join\s*\(\s*(?:\"([^\"]*)\"|'([^']*)')?\s*\)",
        out,
    ):
        items = [im.group(1) if im.group(1) is not None else im.group(2) for im in re.finditer(r"\"([^\"]*)\"|'([^']*)'", m.group(1))]
        if m.group(2):
            items.reverse()
        sep = m.group(3) if m.group(3) is not None else (m.group(4) if m.group(4) is not None else ",")
        extras.append(sep.join(items))
    folded = out
    for _ in range(8):
        nxt = re.sub(r"\"([^\"\\]*)\"\s*\+\s*\"([^\"\\]*)\"", r'"\1\2"', folded)
        nxt = re.sub(r"'([^'\\]*)'\s*\+\s*'([^'\\]*)'", r"'\1\2'", nxt)
        if nxt == folded:
            break
        folded = nxt
    return "\n".join([folded, *extras]) if extras else folded


class _SiteHTMLParser(HTMLParser):
    """Extract text, attributes, comments, scripts, and local asset links from HTML/SVG."""

    def __init__(self, depth: int = 0, page_rel: str = "site/index.html") -> None:
        super().__init__(convert_charrefs=True)
        self.depth = depth
        self.page_rel = page_rel
        self.inline_parts: list[str] = []
        self.fused_parts: list[str] = []
        self.compact_parts: list[str] = []
        self.attr_lines: list[str] = []
        self.comment_lines: list[str] = []
        self.subtrees: list[str] = []
        self.style_blocks: list[str] = []
        self.asset_refs: list[tuple[str, str]] = []
        self.element_ids: set[str] = set()
        self.html_issues: list[tuple[str, str]] = []
        self._raw_tag: str | None = None
        self._raw_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower().rsplit(":", 1)[-1]
        if t == "base":
            self.html_issues.append(("publish", "HTML base href element in site/"))
        if t in HTML_BLOCK_TAGS:
            self.inline_parts.append("\n")
        ad: dict[str, str] = {}
        for k, v in attrs:
            kl = k.lower()
            if kl == "xml:base":
                self.html_issues.append(("publish", "XML base attribute in site/"))
            if kl in ad:
                self.html_issues.append(("publish", f"duplicate HTML attribute in site/ ({kl})"))
                continue
            ad[kl] = v if v is not None else ""
            if re.match(r"^on[a-z]{2,}$", kl):
                self.html_issues.append(("publish", f"inline event handler attribute in site/ ({kl})"))
            if not v:
                continue
            compact_val = re.sub(r"[\x00-\x20]+", "", v)
            unq_compact = re.sub(r"[\x00-\x20]+", "", urllib.parse.unquote(compact_val))
            for chk_val in (compact_val, unq_compact):
                if re.match(r"^(?:javascript|vbscript):", chk_val, re.IGNORECASE):
                    self.html_issues.append(("publish", "javascript: or vbscript: URI attribute in site/"))
                elif re.match(r"^data:", chk_val, re.IGNORECASE):
                    self.html_issues.append(("publish", "embedded data URI asset requires direct file scan"))
            self.attr_lines.append(f"{k}={v}")
            if "%" in v:
                self.attr_lines.append(f"{k}={urllib.parse.unquote(v)}")
            if kl == "style":
                self.style_blocks.append(v)
                self.subtrees.append(unescape_css_literals(v))
            elif kl in {
                "fill", "stroke", "clip-path", "mask", "filter",
                "marker-start", "marker-mid", "marker-end",
            } and "url(" in unescape_css_literals(v).lower():
                self.style_blocks.append(f"{kl}: {v}")
                self.subtrees.append(unescape_css_literals(v))
            if kl == "srcdoc":
                if self.depth < 3:
                    nested = _parse_site_html(v, depth=self.depth + 1, page_rel=self.page_rel)
                    self.html_issues.extend(nested.html_issues)
                    self.style_blocks.extend(nested.style_blocks)
                    self.asset_refs.extend(nested.asset_refs)
                    self.subtrees.append(normalize_html_text(v, self.depth + 1, page_rel=self.page_rel))
                else:
                    self.html_issues.append(("publish", "deeply nested iframe srcdoc in site/"))
        if "hidden" in ad:
            self.html_issues.append(("publish", "hidden HTML attribute in site/"))
        if ad.get("id"):
            self.element_ids.add(ad["id"])
        if t == "a" and ad.get("name"):
            self.element_ids.add(ad["name"])
        if t == "link" and "href" in ad:
            rel_tokens = {tok.lower() for tok in ad.get("rel", "").split()}
            if rel_tokens & {
                "stylesheet", "icon", "apple-touch-icon", "manifest",
                "preload", "modulepreload", "prefetch", "dns-prefetch",
                "preconnect", "prerender", "mask-icon",
            }:
                self.asset_refs.append(("link", ad["href"]))
        elif t == "script":
            script_src = ad.get("src") or ad.get("href") or ad.get("xlink:href")
            if script_src is not None:
                self.asset_refs.append(("script", script_src))
        elif t in ("img", "source"):
            if "src" in ad:
                self.asset_refs.append(("img", ad["src"]))
            if "srcset" in ad and not re.match(r"^(?:data|javascript|vbscript):", ad["srcset"].strip(), re.IGNORECASE):
                for cand_url in _parse_srcset_urls(ad["srcset"]):
                    self.asset_refs.append(("img", cand_url))
        elif t in ("iframe", "embed", "audio", "video", "input", "track"):
            if "src" in ad:
                self.asset_refs.append((t, ad["src"]))
            if t == "video" and "poster" in ad:
                self.asset_refs.append(("video", ad["poster"]))
        elif t == "object" and "data" in ad:
            self.asset_refs.append(("object", ad["data"]))
        elif t == "meta" and ad.get("http-equiv", "").strip().lower() == "refresh" and "content" in ad:
            m = re.match(
                r"^\s*\d+(?:\.\d*)?\s*[;,]\s*(?:url\s*=\s*)?(?:\"([^\"]*)\"|'([^']*)'|(.+?))\s*$",
                ad["content"],
                re.IGNORECASE,
            )
            if m:
                refresh_url = next((g for g in m.groups() if g is not None), "").strip()
                if refresh_url:
                    compact_ref = re.sub(r"[\x00-\x20]+", "", refresh_url)
                    unq_ref = re.sub(r"[\x00-\x20]+", "", urllib.parse.unquote(compact_ref))
                    for chk_val in (compact_ref, unq_ref):
                        if re.match(r"^(?:javascript|vbscript):", chk_val, re.IGNORECASE):
                            self.html_issues.append(("publish", "javascript: or vbscript: URI attribute in site/"))
                        elif re.match(r"^data:", chk_val, re.IGNORECASE):
                            self.html_issues.append(("publish", "embedded data URI asset requires direct file scan"))
                    self.asset_refs.append(("meta", refresh_url))
        elif t in ("image", "use", "feimage"):
            if t == "image" and "src" in ad:
                self.asset_refs.append(("img", ad["src"]))
            svg_href = ad.get("href") or ad.get("xlink:href")
            if svg_href and not svg_href.strip().startswith("#"):
                self.asset_refs.append(("img", svg_href))
        elif t == "a" and "href" in ad:
            self.asset_refs.append(("anchor", ad["href"]))
        if t in ("script", "style", "title"):
            if t == "title":
                self.set_cdata_mode("title")
            self._raw_tag = t
            self._raw_chunks = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower().rsplit(":", 1)[-1]
        if t in ("script", "style", "title"):
            self.html_issues.append(("publish", "self-closing script or style tag in site/"))
            self.set_cdata_mode(t)
        self.handle_starttag(tag, attrs)

    def _flush_raw_tag(self, tag_name: str) -> None:
        raw_body = "".join(self._raw_chunks)
        if tag_name == "script":
            dec = fold_js_expressions(raw_body)
            self.subtrees.append(dec)
            if ("<" in dec or "&" in dec) and self.depth < 3:
                self.subtrees.append(normalize_html_text(dec, self.depth + 1, page_rel=self.page_rel))
        elif tag_name == "style":
            self.style_blocks.append(raw_body)
            self.subtrees.append(unescape_css_literals(raw_body))
        elif tag_name == "title":
            unesc = html.unescape(raw_body)
            self.inline_parts.append(unesc)
            self.fused_parts.append(unesc)
            if unesc.strip():
                self.compact_parts.append(unesc.strip())
        self._raw_tag = None
        self._raw_chunks = []

    def handle_pi(self, data: str) -> None:
        self.html_issues.append(("publish", "HTML processing instruction in site/"))

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower().rsplit(":", 1)[-1]
        if self._raw_tag == t:
            self._flush_raw_tag(t)
        if t in HTML_BLOCK_TAGS:
            self.inline_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._raw_tag is not None:
            self._raw_chunks.append(data)
            return
        self.inline_parts.append(data)
        self.fused_parts.append(data)
        if data.strip():
            self.compact_parts.append(data.strip())

    def handle_comment(self, data: str) -> None:
        self.comment_lines.append(html.unescape(data))

    def unknown_decl(self, data: str) -> None:
        if data.startswith("CDATA["):
            self.handle_data(data[len("CDATA["):])


def _parse_site_html(text: str, depth: int = 0, page_rel: str = "site/index.html") -> _SiteHTMLParser:
    parser = _SiteHTMLParser(depth=depth, page_rel=page_rel)
    parser.feed(text)
    parser.close()
    if parser._raw_tag is not None:
        parser._flush_raw_tag(parser._raw_tag)
    return parser


def normalize_html_text(
    text: str, depth: int = 0, page_rel: str = "site/index.html"
) -> str:
    """Extract rendered HTML/SVG text, attributes, comments, and decoded scripts."""
    parser = _parse_site_html(text, depth=depth, page_rel=page_rel)
    combined = "\n".join([
        "".join(parser.inline_parts),
        "".join(parser.fused_parts),
        "".join(parser.compact_parts),
        "\n".join(parser.attr_lines),
        "\n".join(parser.comment_lines),
        *parser.subtrees,
    ])
    return INVISIBLE_FORMAT_RE.sub("", combined)


def check_site_links_and_safety(
    root: Path,
    rel: str,
    path: Path,
    text: str,
    report: Report,
    seen: set[tuple[str, str]],
) -> None:
    """Validate site/ asset link integrity, local resource resolution, and URI safety."""
    def _emit(category: str, msg: str) -> None:
        item = (category, f"{rel}: {msg}")
        if item not in seen:
            seen.add(item)
            report.add(*item)

    if BIDI_CONTROL_RE.search(text):
        _emit("publish", "bidirectional control character in published site/ asset (section 13)")

    def _validate_css_target(target: str) -> None:
        if not target or target.startswith("#"):
            return
        if re.match(r"^(?:https?:|//|data:|javascript:|vbscript:)", target, re.IGNORECASE):
            _emit("publish", f"remote or inline-scheme CSS url() resource ({target[:36]}) (section 13)")
            return
        resolved = resolve_site_asset_href(rel, target)
        if resolved is None:
            _emit("publish", f"escaping CSS url() resource ({target[:36]}) (section 13)")
        elif not (root / resolved).is_file():
            _emit("links", f"broken local CSS asset link -> {target}")

    def _check_css_text(css_text: str, *, allow_hiding: bool = True) -> None:
        clean_css = CSS_COMMENT_RE.sub("", unescape_css_literals(css_text))
        if re.search(r"(?i)@import\b", clean_css):
            _emit("publish", "CSS @import external stylesheet (section 13)")
        if not allow_hiding and re.search(
            r"(?i)(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:\.0+)?(?:\s*[;}]|$))",
            clean_css,
        ):
            _emit("publish", "hidden CSS text rule in HTML site/ asset (section 13)")
        for m in re.finditer(r'(?i)\burl\s*\(\s*(?:"([^"]*)"|\'([^\']*)\'|([^)]+))\s*\)', clean_css):
            target = next((g for g in m.groups() if g is not None), "").strip()
            _validate_css_target(target)
        for m in re.finditer(r"(?i)(?:-webkit-)?image-set\s*\(((?:[^()]|\([^()]*\))*)\)", clean_css):
            inner = re.sub(r"(?i)\b(?:type|url)\s*\([^)]*\)", "", m.group(1))
            for sm in re.finditer(r'"([^"]+)"|\'([^\']+)\'', inner):
                target = (sm.group(1) if sm.group(1) is not None else sm.group(2)).strip()
                _validate_css_target(target)

    suffix = path.suffix.lower()
    if suffix == ".css":
        _check_css_text(text)
        return

    if suffix == ".webmanifest":
        try:
            manifest = json.loads(text)
        except json.JSONDecodeError:
            _emit("links", "invalid JSON in web manifest")
            return
        if isinstance(manifest, dict) and isinstance(manifest.get("icons"), list):
            for icon in manifest["icons"]:
                if not isinstance(icon, dict) or not isinstance(icon.get("src"), str):
                    continue
                src = icon["src"]
                resolved = resolve_site_asset_href(rel, src)
                if resolved is None:
                    _emit("publish", f"remote or escaping manifest icon src ({src[:36]}) (section 13)")
                elif not (root / resolved).is_file():
                    _emit("links", f"broken manifest icon link -> {src}")
        return

    if suffix not in (".html", ".htm", ".xhtml", ".svg", ".xml"):
        return

    if re.search(r"(?is)<!(?:ENTITY\b|DOCTYPE\b[^>\[]*\[)", text):
        _emit("publish", "custom XML entity or internal DTD subset in site/ asset (section 13)")

    parser = _parse_site_html(text, page_rel=rel)
    for cat, msg in parser.html_issues:
        _emit(cat, f"{msg} (section 13)")
    for css_blk in parser.style_blocks:
        _check_css_text(css_blk, allow_hiding=False)

    def _is_valid_fragment(frag: str) -> bool:
        return not frag or frag.lower() == "top" or frag in parser.element_ids

    resource_kinds = {
        "link", "script", "img", "iframe", "object", "embed",
        "audio", "video", "input", "track", "meta",
    }
    for kind, target in parser.asset_refs:
        if kind in resource_kinds:
            if re.match(r"^(?:data|javascript|vbscript):", target.strip(), re.IGNORECASE):
                continue
            resolved = resolve_site_asset_href(rel, target)
            if resolved is None:
                _emit("publish", f"remote or escaping {kind} asset in site/ ({target[:36]}) (section 13)")
            elif not (root / resolved).is_file():
                _emit("links", f"broken local {kind} link -> {target}")
        elif kind == "anchor" and suffix in (".html", ".htm", ".xhtml"):
            raw = target.strip()
            if not raw:
                continue
            unq_raw = urllib.parse.unquote(raw)
            if re.match(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//)", raw) or re.match(
                r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//)", unq_raw
            ):
                continue
            if raw.startswith("#"):
                frag = urllib.parse.unquote(raw[1:])
                if not _is_valid_fragment(frag):
                    _emit("links", f"broken fragment link -> {target}")
            elif raw.startswith("?"):
                if "#" in raw:
                    frag = urllib.parse.unquote(raw.split("#", 1)[1])
                    if not _is_valid_fragment(frag):
                        _emit("links", f"broken fragment link -> {target}")
            else:
                resolved = resolve_site_asset_href(rel, raw, allow_root=True)
                if resolved is None:
                    _emit("links", f"broken relative link -> {target}")
                else:
                    target_path = root / resolved
                    if not (target_path.is_file() or (target_path / "index.html").is_file()):
                        _emit("links", f"broken relative link -> {target}")
                    elif (resolved == rel or (resolved == "site" and rel == "site/index.html")) and "#" in raw:
                        frag = urllib.parse.unquote(raw.split("#", 1)[1])
                        if not _is_valid_fragment(frag):
                            _emit("links", f"broken fragment link -> {target}")


def normalized_site_views(
    path: Path,
    text: str,
    page_rel: str = "site/index.html",
) -> list[str]:
    """Build raw and decoded/rendered views of a deployed site/ text asset."""
    views: list[str] = []

    def _add(candidate: str) -> None:
        if candidate and candidate not in views:
            views.append(candidate)

    _add(text)
    _add(INVISIBLE_FORMAT_RE.sub("", text))
    js_dec = INVISIBLE_FORMAT_RE.sub("", fold_js_expressions(text))
    _add(js_dec)
    suffix = path.suffix.lower()
    if suffix in (".css", ".html", ".htm", ".xhtml", ".svg"):
        _add(INVISIBLE_FORMAT_RE.sub("", unescape_css_literals(text)))
    if suffix in (".html", ".htm", ".xhtml", ".svg", ".xml") or "<" in js_dec or "&" in js_dec:
        _add(normalize_html_text(text, page_rel=page_rel))
        if js_dec != text:
            _add(normalize_html_text(js_dec, page_rel=page_rel))
    for base_view in list(views):
        cur = base_view
        for _ in range(2):
            if "%" not in cur:
                break
            unq = INVISIBLE_FORMAT_RE.sub("", urllib.parse.unquote(cur))
            if unq == cur:
                break
            _add(unq)
            cur = unq
        _add(INVISIBLE_FORMAT_RE.sub("", html.unescape(base_view)))
    return views


def always_report(text: str, match: re.Match, ctx: FileContext) -> bool:
    return True


IDENTIFIER_LEAK_PATTERNS = [
    (
        re.compile(r"(?<![0-9.])\d{1,3}(?:\.\d{1,3}){3}(?![0-9.])"),
        "publish",
        "private IPv4 address (section 13)",
        ipv4_is_private,
    ),
    (
        re.compile(
            r"(?<![0-9A-Za-z:_])"
            r"(?:[0-9A-Fa-f]{0,4}:){2,7}(?:[0-9A-Fa-f]{1,4}|\d{1,3}(?:\.\d{1,3}){3})?"
            r"(?![0-9A-Za-z:_])"
        ),
        "publish",
        "private IPv6 address (section 13)",
        ipv6_is_private,
    ),
    (
        re.compile(
            r"\b[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?(?:\.[a-zA-Z0-9-]+)*"
            r"\.(?:internal|local|corp|lan|intranet|private|home\.arpa)\b",
            re.IGNORECASE,
        ),
        "publish",
        "internal hostname (section 13)",
        internal_host_is_real,
    ),
    (
        re.compile(r"\barn:aws(?:-[a-z-]+)?:[a-z0-9-]+:[a-z0-9-]*:(\d{12}):[^\s`)\]\"'<>]+", re.IGNORECASE),
        "publish",
        "account identifier (section 13)",
        arn_is_real,
    ),
    (
        re.compile(r"\b([a-z0-9][a-z0-9-]*)@([a-z0-9][a-z0-9-]*)\.iam\.gserviceaccount\.com\b", re.IGNORECASE),
        "publish",
        "account identifier (section 13)",
        service_account_is_real,
    ),
    (
        re.compile(
            r"""(?i)\b(?:[a-z0-9]+[-_])*(?:aws[-_]?account(?:[-_]?id)?|account[-_]?id|tenant[-_]?id|subscription[-_]?id|project[-_]?number)\b"""
            r"""(?:\\?["'])?\s*[:=]\s*(?:\\?["'])?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d{12})(?:\\?["'])?(?![0-9a-f-])"""
        ),
        "publish",
        "account identifier (section 13)",
        account_field_is_real,
    ),
]
SITE_LEAK_PATTERNS = [
    *IDENTIFIER_LEAK_PATTERNS,
    (
        re.compile(
            r"(?i)\bdata:(?:image|application|audio|video|font|model|multipart|text)/"
            r"[a-z0-9.+_-]+(?:;[a-z0-9=+._-]+)*,"
        ),
        "publish",
        "embedded data URI asset requires direct file scan (section 13)",
        always_report,
    ),
]


def _scan_leak_patterns(
    rel: str,
    text: str,
    patterns,
    ctx: FileContext,
    report: Report,
    seen: set[tuple[str, str]] | None = None,
) -> None:
    for pattern, category, label, predicate in patterns:
        for match in pattern.finditer(text):
            if predicate is None and not ctx.prose[match.start():match.end()].strip():
                continue
            if predicate is not None and not predicate(text, match, ctx):
                continue
            item = (category, f"{rel}: {label}: {match.group(0)[:40]}")
            if seen is not None:
                if item in seen:
                    continue
                seen.add(item)
            report.add(*item)


def check_leaks(root: Path, report: Report) -> None:
    """Scan published site/ assets and repository source files for leaked identifiers."""
    site_path_patterns = [*LEAK_PATTERNS[:4], *SITE_LEAK_PATTERNS]
    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        markdown = is_markdown(path)
        if rel.startswith("site/"):
            if " " in path.name:
                report.add("naming", f"{rel}: file name contains a space")
            seen_for_file: set[tuple[str, str]] = set()
            site_rel_path = "/" + rel[len("site/"):]
            path_views = [site_rel_path]
            cur_pv = site_rel_path
            for _ in range(2):
                if "%" not in cur_pv:
                    break
                decoded_rel_path = urllib.parse.unquote(cur_pv)
                if decoded_rel_path == cur_pv:
                    break
                path_views.append(decoded_rel_path)
                cur_pv = decoded_rel_path
            for pv in path_views:
                path_ctx = FileContext(url_spans=[], prose=pv, masked=pv)
                _scan_leak_patterns(rel, pv, site_path_patterns, path_ctx, report, seen_for_file)

            status, site_text = read_deployed_site_asset(root, path)
            if status == "unscanned_binary":
                report.add(
                    "publish",
                    f"{rel}: unscanned binary or encrypted asset in published site/ tree (section 13)",
                )
                continue
            if status == "png_metadata":
                report.add(
                    "publish",
                    f"{rel}: PNG ancillary text metadata chunk (tEXt/zTXt/iTXt) not allowed in published site/ tree (section 13)",
                )
                if not site_text:
                    continue
            elif status != "text" or site_text is None:
                continue

            check_site_links_and_safety(root, rel, path, site_text, report, seen_for_file)
            patterns = list(LEAK_PATTERNS) if markdown else list(LEAK_PATTERNS[:4])
            patterns.extend(SITE_LEAK_PATTERNS)
            for view in normalized_site_views(path, site_text, page_rel=rel):
                prose = blank_fenced_blocks(view) if markdown else view
                masked = blank_code_spans(prose) if markdown else view
                ctx = FileContext(
                    url_spans=[(m.start(), m.end()) for m in URL_TOKEN.finditer(view)],
                    prose=prose,
                    masked=masked,
                )
                _scan_leak_patterns(rel, view, patterns, ctx, report, seen_for_file)
            continue

        if markdown:
            text = path.read_text(encoding="utf-8", errors="ignore")
            repo_patterns = [*LEAK_PATTERNS, *IDENTIFIER_LEAK_PATTERNS]
        else:
            if rel == "scripts/test_site.py":
                continue
            tx_status, decoded_txt = _decode_site_text(path.read_bytes())
            if tx_status != "text" or not decoded_txt:
                continue
            text = (
                re.sub(r'ipaddress\.ip_network\("[^"]+"\)', 'ipaddress.ip_network("")', decoded_txt)
                if rel == "scripts/check_site.py"
                else decoded_txt
            )
            repo_patterns = [*LEAK_PATTERNS[:4], *IDENTIFIER_LEAK_PATTERNS]

        seen_repo: set[tuple[str, str]] = set()
        repo_views: list[str] = []
        for base_cand in (text, html.unescape(text), fold_js_expressions(text)):
            cand = INVISIBLE_FORMAT_RE.sub("", base_cand)
            if cand and cand not in repo_views:
                repo_views.append(cand)
        for bv in list(repo_views):
            cur = bv
            for _ in range(2):
                if "%" not in cur:
                    break
                unq = INVISIBLE_FORMAT_RE.sub("", urllib.parse.unquote(cur))
                if unq == cur:
                    break
                if unq not in repo_views:
                    repo_views.append(unq)
                cur = unq
        for rv in repo_views:
            prose = blank_fenced_blocks(rv) if markdown else rv
            masked = blank_code_spans(prose) if markdown else rv
            ctx = FileContext(
                url_spans=[(m.start(), m.end()) for m in URL_TOKEN.finditer(rv)],
                prose=prose,
                masked=masked,
            )
            _scan_leak_patterns(rel, rv, repo_patterns, ctx, report, seen_repo)


def matching_internal_note_pattern(rel: str) -> str | None:
    """Return the matching internal-note .gitignore pattern for a Git-visible path, if any."""
    name = Path(rel).name
    for pattern in INTERNAL_NOTE_GITIGNORE:
        if pattern == "docs/acceptance-policy.md" and rel == "docs/acceptance-policy.md":
            continue
        if pattern.endswith("/"):
            if rel.startswith(pattern) or f"/{pattern}" in rel:
                return pattern
        elif "/" in pattern:
            if rel == pattern or rel.endswith("/" + pattern):
                return pattern
        elif fnmatch.fnmatchcase(name, pattern):
            return pattern
    return None


def check_internal_paths(root: Path, report: Report) -> None:
    """Verify .gitignore protections and reject tracked internal working notes."""
    gitignore = root / ".gitignore"
    text = gitignore.read_text(encoding="utf-8", errors="ignore") if gitignore.exists() else ""
    missing = [pattern for pattern in INTERNAL_NOTE_GITIGNORE if pattern not in text]
    if missing:
        report.add(
            "hygiene",
            ".gitignore: internal note paths not ignored — " + ", ".join(missing),
        )
    if "!.github/engineering.md" in text:
        report.add(
            "hygiene",
            ".gitignore: remove obsolete !.github/engineering.md unignore rule",
        )
    if (root / "docs" / "acceptance-policy.md").exists() and not is_untracked_gitignored(
        root, "docs/acceptance-policy.md"
    ):
        report.add(
            "publish",
            "docs/acceptance-policy.md: internal acceptance policy stays out of public repositories (section 5)",
        )

    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        if rel == "docs/acceptance-policy.md":
            continue
        if INTERNAL_NOTE_DIRS.search(rel):
            report.add("content", f"{rel}: plan/handoff directory in a public repo (section 5)")
        else:
            matched = matching_internal_note_pattern(rel)
            if matched is not None:
                report.add("hygiene", f"{rel}: tracked internal note matching {matched} (section 6)")
        if is_markdown(path) and re.search(r"(^|/)(out|output)/[^/]+/", rel):
            report.add("content", f"{rel}: committed output directory (section 5)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root (default: cwd)")
    parser.add_argument(
        "--phase", type=int, choices=(1, 2), default=1,
        help="1 blocks leaks and hygiene; 2 also blocks content issues (default: 1)",
    )
    parser.add_argument(
        "--advisory", action="store_true",
        help="report findings but always exit 0",
    )
    parser.add_argument(
        "--visibility", choices=("public", "private"), default="public",
        help="private demotes publication rules to notes; default treats the repository as public",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    blocking_categories = set(PHASE_BLOCKING[args.phase])
    if args.visibility == "private":
        blocking_categories -= PUBLICATION_CATEGORIES
    report = Report(blocking_categories)

    check_leaks(root, report)
    check_internal_paths(root, report)

    blocking = report.blocking_findings()
    advisory = report.advisory_findings()

    for category, message in blocking:
        print(f"ERROR  [{category}] {message}")
    for category, message in advisory:
        print(f"NOTE   [{category}] {message}")

    print()
    print(
        f"phase {args.phase} ({args.visibility}): {len(blocking)} blocking, "
        f"{len(advisory)} advisory. Advisory findings become blocking in phase 2."
    )
    if args.visibility == "private":
        print(
            "private repository: publication rules report as notes; "
            "they would block if this repository were published"
        )
    if args.advisory:
        print("advisory run: exit status forced to 0")
        return 0

    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
