#!/usr/bin/env python3
"""Check a repository against docs/STYLE_GUIDE.md.

The style guide is 500 lines of prose and nothing enforced it. This script turns
the mechanically checkable parts into exit codes, so a pull request that breaks
them fails instead of relying on a reviewer remembering section 7.

Checks come from the guide, not from invention:

  section 2   marketing words, filler openings, emoji in headings
  section 4   language suffixes
  section 5   content that stays out of public repositories
  section 6   internal note paths
  section 7   file naming
  section 13  the grep list the guide already tells reviewers to run

Usage:
    python scripts/check_style.py [--root PATH] [--phase {1,2}]

Phases exist because 26 repositories already carry violations. Turning all of
them into blocking failures on day one means every open pull request goes red
and the check gets deleted. Phase 1 blocks only the defects that leak private
data or break a reader's navigation; naming and README structure are reported
but do not fail. Phase 2 blocks everything, and should be switched on once the
naming cleanup is done.

Exit code 0 when nothing in the blocking set is found.
"""

from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import html
import ipaddress
import posixpath
import re
import struct
import subprocess
import sys
import unicodedata
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

# Section 7: these keep their uppercase spelling because tools and readers
# expect them.
CONVENTIONAL_UPPER = {
    "README", "CHANGELOG", "SECURITY", "CONTRIBUTING", "CODE_OF_CONDUCT",
    "LICENSE", "SUPPORT", "GOVERNANCE", "AUTHORS", "NOTICE", "AGENTS",
    "CLAUDE", "THIRD_PARTY_NOTICES", "TRADEMARK", "ARCHITECTURE",
    "CONFIGURATION", "GLOSSARY", "STYLE_GUIDE", "PULL_REQUEST_TEMPLATE",
    "ISSUE_TEMPLATE", "FUNDING", "SKILL", "INDEX",
}

DATE_IN_NAME = re.compile(r"(?<!\d)20\d{2}[-_]?\d{2}[-_]?\d{2}(?!\d)")

# The block `tools/sync_agents.py` writes into AGENTS.md. A rule stated only in
# the guide is read by whoever opens the guide; this one is read by every agent
# that opens the repository, which is the only point early enough to matter.
CONTENT_BOUNDARY = "<!-- content-boundary:begin -->"

# A date in the name is a defect when the file describes something that keeps
# changing, because the date goes stale while the name stays. It is the
# identity of the record when the file is a snapshot of one date: two analyses
# of the same subject from different months are different documents, and
# dropping the date leaves them fighting over one name.
#
# Section 7 therefore exempts the two places that hold records. ADRs carry a
# sequence number rather than a date, but they are the same kind of thing.
DATE_BEARING_PATHS = ("docs/adr/", "docs/research/")

# Section 3 outline. The guide calls it "a default, not a required template",
# so a missing section is never blocking.
README_OUTLINE = [
    "status", "what this is", "what this is not", "quick start",
    "configuration", "architecture", "repository layout", "contributing",
    "security", "license",
]

# Section 2, "Habits to avoid".
#
# `robust` and `powerful` are deliberately absent. Both are technical terms in
# this corpus — a robust estimator, statistical power — and a rule that flags
# them reported twelve non-defects in the research docs and one quotation of
# Hansen's SPA test. A word that is marketing in a landing page and a term of
# art in a research note cannot be decided by a word list, so the list keeps
# only the words that have no technical sense here.
MARKETING_WORDS = [
    "seamless", "cutting-edge", "comprehensive",
    "world-class", "next-generation", "state-of-the-art", "best-in-class",
]
FILLER_PHRASES = [
    "it is worth noting", "it's worth noting", "in summary", "let's dive in",
    "needless to say", "at the end of the day",
]

# Section 13 says "non-placeholder buckets" and section 7 line 104 says the
# placeholder form is `<bucket>`, `<project-id>`, `$PROJECTS_ROOT`. So a
# `gs://` URI whose bucket segment is a placeholder is the correct form, not a
# finding. `synthetic-` is on the list because the organisation's fixtures are
# named that way; without it every fixture a doc quotes becomes a finding the
# day the doc is written.
PLACEHOLDER_BUCKET = re.compile(
    r"^[<{$]|[<>{}]|\.\.\."
    r"|^(?:your|my|example|sample|placeholder|shared|synthetic)[-_]"
    r"|^bucket(?:-|$)"
)

# Section 13 asks for a placeholder wherever a deployed subdomain would appear,
# so `YOUR_SUBDOMAIN.workers.dev` is the correct form, not a finding. Matching
# the domain shape alone reports the guide's own advice as a leak, which is how
# a check earns the reputation that lets the real leak through.
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
    prose: str  # the text with fenced blocks blanked out, offsets preserved
    masked: str  # `prose` with inline code blanked out too


def phrase_is_prose(text: str, match: re.Match, ctx: FileContext) -> bool:
    """A rule about phrasing describes prose; backticks name the phrase.

    The style guide writes `this round` when it means the words, and a value
    rule such as `gs://` is the opposite case: a bucket inside backticks is
    still a bucket. That is why this is a per-rule predicate and not a blanket
    skip on code spans.
    """
    return bool(ctx.masked[match.start():match.end()].strip())


def bucket_is_real(text: str, match: re.Match, ctx: FileContext) -> bool:
    bucket = match.group(0)[len("gs://"):].split("/", 1)[0].lower()
    # A sentence-final period is punctuation, not part of the name. An ellipsis
    # is the placeholder, so it must survive this.
    if bucket.endswith(".") and not bucket.endswith("..."):
        bucket = bucket[:-1]
    return bool(bucket) and not PLACEHOLDER_BUCKET.search(bucket)


def subdomain_is_real(text: str, match: re.Match, ctx: FileContext) -> bool:
    """A placeholder subdomain is the form section 13 asks for, not a leak.

    What survives this predicate is a subdomain that was actually deployed,
    including inside fenced command or config examples.
    """
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
    """Reject workstation home paths in prose and fenced examples while allowing placeholders."""
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
    """Section 5 forbids 40-character hex *in prose* — CI head SHAs pasted in.

    A revision reference is a different thing and the guide asks for it: line
    377 writes `<40-char sha>` and the cross-repo links pin `blob/<sha>/`. So
    the three forms that carry a revision are exempt, and what is left is the
    case the rule was written for.
    """
    if ctx.prose[match.start()] == " ":
        return False  # inside a fenced block: a contract example, not prose
    for start, end in ctx.url_spans:
        if start <= match.start() < end:
            return False  # a link target
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    line = text[line_start: line_end if line_end != -1 else len(text)]
    column = match.start() - line_start
    if line[:column].count("`") % 2 == 1:
        return False  # a quoted identifier
    if text[match.end(): match.end() + 2] == "](":
        return False  # the label of a link whose target carries the same sha
    return len(set(match.group(0))) != 1  # 000...0 and friends, a placeholder


# Section 13 grep list plus section 5 categories that are recognisable.
# The lookbehind keeps URL paths such as https://example.com/home/legal/ out of
# the results; "/home/" inside a URL is not a local path.
#
# Two categories, because they carry different weight. A real home path is
# evidence that something leaked from a workstation. The rest are the guide's
# own "prompt to check, not a certain failure" greps.
#
# The last column is a predicate deciding whether a match is a finding at all.
# Both heuristics in this list match far more than they mean: `gs://` matches
# `gs://<bucket>/...`, which is the form section 13 asks for, and a 40-character
# hex string matches every commit SHA, which is how a cross-repository reference
# is supposed to be pinned. Without the predicates the two rules reported 522
# findings across the organisation and not one of them was a defect, which is
# the same as having no rule: the report gets scrolled past.
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
    # `| PR |` is a table header; `| PR #12 |` and `| #12 |` are the rows this
    # rule is about. Matching the header too reported the guide's own row
    # describing the rule.
    (re.compile(r"\|\s*(?:PR\s*#?\d+|#\d+)"),
     "content", "PR-number status table (section 5)", None),
    (re.compile(r"\b(this round|this task|in this task)\b", re.IGNORECASE),
     "content", "task-scope wording (section 5)", phrase_is_prose),
    (re.compile(r"\b(the owner approved|approved by)\b", re.IGNORECASE),
     "content", "owner approval note (section 5)", phrase_is_prose),
]


# Section 6: paths for notes that must never be committed. The four wildcard
# entries are spelled with [Aa] character classes because .gitignore is
# case-sensitive on some platforms and `*audit*.md` alone lets `Audit.md` past.
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

# Directories whose contents are working material, never reader-facing docs.
INTERNAL_NOTE_DIRS = re.compile(
    r"(^|/)(docs/plans|docs/handoffs|docs/superpowers|docs/audits|docs/changes)/"
)

DATED_TITLE = re.compile(r"(audit|acceptance).*20\d{2}-\d{2}-\d{2}", re.IGNORECASE)

# Blocking categories per phase.
#
# Phase 1 blocks only what is unambiguous: a leaked local path, a link a reader
# cannot follow, a missing rules file, a .gitignore that has stopped keeping
# working notes out. Everything else is reported as NOTE. Phase 2 blocks the
# rest once the naming cleanup is done. README structure never blocks, because
# section 3 is a default and section 4 says so.
PHASE_BLOCKING = {
    1: {"paths", "links", "agents", "hygiene", "publish"},
    2: {"paths", "links", "agents", "hygiene", "publish", "content", "naming", "language", "docs"},
}

# Rules whose purpose is to stop an identifier being published.
#
# The style guide governs published documentation. In a private repository
# nothing is published, and a deployment document may need the real host name to
# be usable at all — an OAuth callback URL with a placeholder in it cannot be
# configured. So these report as notes there and block in public repositories,
# which is the case the rule was written for. The default stays "public", so
# forgetting the flag cannot switch a leak rule off by accident.
PUBLICATION_CATEGORIES = {"paths", "publish"}


class Report:
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
    rel_parts = path.relative_to(root).parts
    if ".git" in rel_parts:
        return True
    # Pages publishes the entire site/ directory, including site/dist or site/build.
    if rel_parts and rel_parts[0] == "site":
        return False
    return any(part in SKIP_DIRS for part in rel_parts)


def iter_files(root: Path):
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


def has_emoji(text: str) -> bool:
    for char in text:
        if ord(char) < 0x2000:
            continue
        if unicodedata.category(char) == "So":
            return True
    return False


def strip_fenced_blocks(text: str) -> str:
    """Drop ``` fenced blocks.

    Documentation about documentation contains example links such as
    `[简体中文](README.zh-CN.md)`. Those are illustrations, not links, and
    checking them reports failures the author cannot fix.
    """
    return re.sub(r"^```.*?^```", "", text, flags=re.DOTALL | re.MULTILINE)


# GitHub recognises these two template names with underscores only. Renaming
# them to hyphens silently disables the template, so they are exempt from the
# underscore rule while the lowercase rule still applies.
GITHUB_TEMPLATE_NAMES = {"pull_request_template", "issue_template"}


def check_naming(root: Path, report: Report) -> None:
    for path in iter_files(root):
        if not is_markdown(path):
            continue
        name = path.name
        rel = path.relative_to(root).as_posix()
        core = name[:-3]

        if " " in name:
            report.add("naming", f"{rel}: file name contains a space")

        if core.endswith(".zh-CN"):
            core = core[: -len(".zh-CN")]
        elif core.endswith(".zh-cn"):
            report.add("naming", f"{rel}: language suffix must be .zh-CN.md, not .zh-cn.md")
            core = core[: -len(".zh-cn")]
        elif core.endswith(".en"):
            report.add(
                "naming",
                f"{rel}: English is the base name (section 4); .en.md is not a suffix",
            )

        if rel != "PROPOSAL.md" and core not in CONVENTIONAL_UPPER and core not in GITHUB_TEMPLATE_NAMES:
            if core != core.lower():
                report.add("naming", f"{rel}: file name must be lowercase (section 7)")
            if "_" in core:
                report.add("naming", f"{rel}: use hyphens, not underscores (section 7)")

        if DATE_IN_NAME.search(core) and not rel.startswith(DATE_BEARING_PATHS):
            report.add("naming", f"{rel}: dates belong in history, not file names (section 7)")


RE_PATCH_PROSE = re.compile(
    r"\b(this change|this pr|in this pr|this policy pr|remains? unchanged)\b",
    re.IGNORECASE,
)
RE_PHASE_HEADING = re.compile(r"^#{1,4}\s+.*\bP0[–-]P\d+\b", re.MULTILINE)
RE_LICENSE_HEADING = re.compile(r"^##\s+(?:License|许可证)\s*$")
RE_H2_HEADING = re.compile(r"^##\s+\S+")
MAX_AGENTS_LINES = 120


def check_readme(root: Path, report: Report) -> None:
    readme = root / "README.md"
    if not readme.exists():
        report.add("readme", "README.md is missing")
    else:
        text = readme.read_text(encoding="utf-8", errors="ignore")
        headings = [h.strip().lower() for h in re.findall(r"^#{2,3}\s+(.+)$", text, re.MULTILINE)]
        missing = [
            section for section in README_OUTLINE
            if not any(section in heading for heading in headings)
        ]
        if missing:
            report.add(
                "readme",
                "README.md: section 3 outline not followed — missing "
                + ", ".join(missing)
                + " (a default, not a requirement)",
            )

    for name in ("README.md", "README.zh-CN.md"):
        path = root / name
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8", errors="ignore")
        prose = blank_fenced_blocks(raw)
        masked = blank_code_spans(prose)
        seen_license = False
        for lineno, (prose_line, masked_line) in enumerate(
            zip(prose.splitlines(), masked.splitlines()), 1
        ):
            match = RE_PATCH_PROSE.search(masked_line)
            if match:
                report.add(
                    "content",
                    f"{name}:{lineno}: PR-diff narration '{match.group(0)}' belongs in PR description, not README (section 2)",
                )
            if RE_PHASE_HEADING.match(prose_line):
                report.add(
                    "content",
                    f"{name}:{lineno}: phase code heading belongs outside reader-facing README (section 5)",
                )
            if RE_LICENSE_HEADING.match(prose_line):
                seen_license = True
            elif seen_license and RE_H2_HEADING.match(prose_line):
                report.add(
                    "content",
                    f"{name}:{lineno}: top-level section after License belongs above License (section 3)",
                )


def check_links(root: Path, report: Report) -> None:
    for path in iter_files(root):
        if not is_markdown(path):
            continue
        # A link written inside backticks is an example of how to write a link,
        # not a link. `pr-attachments.md` documents `![alt](./shot.png)` so the
        # reader can copy it; reporting that as a broken target makes the
        # documentation of the feature impossible to pass the check.
        text = blank_code_spans(
            strip_fenced_blocks(path.read_text(encoding="utf-8", errors="ignore"))
        )
        for match in re.finditer(r"\[[^\]]*\]\(([^)\s]+)\)", text):
            target = match.group(1)
            if target.startswith(("http://", "https://", "mailto:", "#", "<")):
                continue
            resolved = (path.parent / urllib.parse.unquote(target.split("#")[0])).resolve()
            # A link that climbs out of the repository points at a sibling
            # checkout. CI only has this repository, so the target cannot exist
            # there — that is not a broken link, it is a reference this check
            # cannot verify. Reporting it as broken makes the check unusable in
            # CI while passing locally, which is the worst of both.
            if not resolved.is_relative_to(root):
                # `xref` is not in PHASE_BLOCKING, so this stays a note in
                # both phases. `tools/check_cross_repo_links.py` resolves these
                # against the sibling's default branch on a schedule; a check
                # that says "not checked" has no standing to block.
                report.add(
                    "xref",
                    f"{path.relative_to(root).as_posix()}: cross-repository reference, not checked -> {target}",
                )
                continue
            if not resolved.exists():
                report.add(
                    "links",
                    f"{path.relative_to(root).as_posix()}: broken relative link -> {target}",
                )


def check_agent_files(root: Path, report: Report) -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "--cached", "-z", "--", "AGENTS.md", "CLAUDE.md"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    names = set(tracked.stdout.split("\0")) if tracked.returncode == 0 else set()

    for name in ("AGENTS.md", "CLAUDE.md"):
        path = root / name
        if not path.exists():
            report.add("agents", f"{name} is missing")
        elif name not in names:
            report.add("agents", f"{name} is not tracked by Git; a local copy is not a committed rule")

    claude = root / "CLAUDE.md"
    if claude.exists():
        content = claude.read_text(encoding="utf-8", errors="ignore").strip()
        if content != "@AGENTS.md":
            report.add("agents", "CLAUDE.md must contain the single line @AGENTS.md")

    if (root / ".github" / "engineering.md").exists() and not is_untracked_gitignored(
        root, ".github/engineering.md"
    ):
        report.add(
            "agents",
            ".github/engineering.md is retired; consolidate rules in AGENTS.md",
        )

    agents = root / "AGENTS.md"
    if agents.exists():
        text = agents.read_text(encoding="utf-8", errors="ignore")
        if len(text.splitlines()) > MAX_AGENTS_LINES:
            report.add(
                "agents",
                f"AGENTS.md exceeds {MAX_AGENTS_LINES} lines; keep agent rules concise",
            )
        if CONTENT_BOUNDARY not in text:
            report.add(
                "agents",
                "AGENTS.md is missing the content-boundary block, see section 5",
            )


def check_docs_baseline(root: Path, report: Report) -> None:
    """The file set a reader expects, split by what the repository is.

    A LICENSE is the signal: a repository that grants rights to outside readers
    owes them a contribution path, a way to report a vulnerability, and a
    conduct policy. A repository that does not grant them is internal, and an
    internal repository needs one thing from this list — where credentials live
    and what to do when one leaks — not a public disclosure process it will
    never run.
    """
    if (root / "LICENSE").exists():
        required = ["CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md"]
        kind = "public"
    else:
        required = ["SECURITY.md"]
        kind = "private"
    missing = [name for name in required if not (root / name).exists()]
    if missing:
        report.add(
            "docs",
            f"{kind} repository is missing {', '.join(missing)} (section 14)",
        )


QUOTE_MARKS = "\"'\u201c\u201d\u2018\u2019"
QUOTED_TERM = re.compile(r"[\"\'\u201c\u2018][^\"\'\u201c\u201d\u2018\u2019]{1,40}[\"\'\u201d\u2019]")


def quoted_term_list(line: str, match: re.Match) -> bool:
    """True when a banned word sits inside a list of quoted terms.

    Section 2 forbids marketing words in prose. A guide that writes
    "Elevate", "Seamless", "Unleash" is naming the words it forbids, and
    reporting it makes the rule unusable exactly where it is most needed --
    the same shape as the placeholder-subdomain and template-underscore
    exemptions.

    The condition is two or more quoted terms on the line, so one quoted word
    used as a claim ("our 'seamless' onboarding") is still reported. That
    keeps the exemption about lists, not about quotation marks.
    """
    before = line[match.start() - 1] if match.start() else ""
    after = line[match.end()] if match.end() < len(line) else ""
    if before not in QUOTE_MARKS or after not in QUOTE_MARKS:
        return False
    return len(QUOTED_TERM.findall(line)) >= 2


def check_language(root: Path, report: Report) -> None:
    marketing = re.compile(
        r"\b(" + "|".join(re.escape(w) for w in MARKETING_WORDS) + r")\b", re.IGNORECASE
    )
    filler = re.compile(
        r"\b(" + "|".join(re.escape(p) for p in FILLER_PHRASES) + r")\b", re.IGNORECASE
    )
    for path in iter_files(root):
        if not is_markdown(path):
            continue
        rel = path.relative_to(root).as_posix()
        # A word inside a fenced block or a code span is being named, not used.
        # The guide lists the words it forbids, and without this the guide is
        # the largest offender in the organisation.
        text = blank_code_spans(blank_fenced_blocks(path.read_text(encoding="utf-8", errors="ignore")))
        first_heading = True
        for number, line in enumerate(text.splitlines(), 1):
            for match in marketing.finditer(line):
                if quoted_term_list(line, match):
                    continue
                report.add("language", f"{rel}:{number}: marketing word '{match.group(0)}' (section 2)")
            for match in filler.finditer(line):
                report.add("language", f"{rel}:{number}: filler phrase '{match.group(0)}' (section 2)")
            if line.startswith("#") and has_emoji(line):
                report.add("language", f"{rel}:{number}: emoji in heading (section 2)")
            if line.startswith("#"):
                # Section 5 is about the title a reader sees in a list of
                # documents. A dated section inside a research log is a
                # chronology, not a title.
                if first_heading and DATED_TITLE.search(line):
                    report.add("language", f"{rel}:{number}: dated title in a reader-facing doc (section 5)")
                first_heading = False


CODE_SPAN = re.compile(r"`[^`\n]+`")


def blank_code_spans(text: str) -> str:
    """Replace inline code with spaces, keeping offsets.

    A word in backticks is a mention: the style guide writes `robust` when it
    means the word, and a research note writes a commit id as a value. Neither
    is prose, and both were reported as prose.
    """
    return CODE_SPAN.sub(lambda m: " " * len(m.group(0)), text)


def blank_fenced_blocks(text: str) -> str:
    """Replace fenced blocks with spaces, keeping every offset in place.

    `hex_is_prose` needs to know whether a match sits in a contract example or
    in running text, and it needs the character offsets to stay usable for the
    line and backtick lookups that follow.
    """
    def blank(match: re.Match) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    return FENCED_BLOCK.sub(blank, text)


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PNG_EXTRA_IMAGE_CHUNKS = {
    b"PLTE", b"tRNS", b"gAMA", b"cHRM", b"sRGB",
    b"sBIT", b"bKGD", b"hIST", b"pHYs", b"tIME",
}
PNG_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}

APPROVED_SITE_RASTERS: dict[str, list[tuple[int, int, int, int, int, str]]] = {
    "site/favicon.ico": [
        (16, 16, 8, 6, 0, "fba8bde649a5423b2934c86a8705d476694fb712fb8da98a80496ccb715889a7"),
        (32, 32, 8, 6, 0, "9e27f396de07f6e3052d6a197ae10408596f79dba02a70e67c929e080e8df292"),
        (48, 48, 8, 6, 0, "1786525e5efbafbd75de650f5a2a53cfdc3fe39ff2d388eba49f87cb892908c2"),
    ],
    "site/landing-light-192.png": [
        (192, 192, 8, 6, 0, "26aa89b6369a45ace2c47db94d2eee28ed812caa92bc591fd59782e1aedf6124"),
    ],
    "site/landing-light-512.png": [
        (512, 512, 8, 6, 0, "bdaabe227116fc88c75bde2110a00e1e6a64448a853137cdc512c4d2ebc1251a"),
    ],
    "site/landing-light-apple-touch-180.png": [
        (180, 180, 8, 6, 0, "2db31b1e3ce7507ed4e9323d948d2bbc714d4033c6fd40c8cefbf995a6f053d5"),
    ],
    "site/landing-light-maskable-512.png": [
        (512, 512, 8, 6, 0, "61aa86a2070e1187bd23e501a7df0fb8152dbba1024e36db63d4f50806cde018"),
    ],
}

SITE_SCRIPT_SUFFIXES = {".js", ".mjs", ".cjs"}
APPROVED_SITE_SCRIPT_FILES: dict[str, str] = {
    "site/assets/app.js": "a38c89a342115396fc79960771a77eb63e314dc6874fdcad46529dead36a6408",
    "site/assets/i18n.js": "0e6946cbdaf887fb790cae6c05992dff0575e99328dd02968374d4a09b35dda5",
}
APPROVED_SITE_INLINE_SCRIPTS: set[str] = {
    "df216a14d05020b1d67c017b9252c0390dcfd70f727e188f42d8b92ac557637f",
}


def resolve_site_asset_href(page_rel: str, href: str) -> str | None:
    """Resolve a site/-local HTML href against page_rel; return None for external or escaping targets."""
    raw = href.strip()
    if not raw or raw.startswith("//") or "\\" in raw:
        return None
    clean = raw.split("#", 1)[0].split("?", 1)[0].strip()
    if not clean or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", clean):
        return None
    sub_page = page_rel[len("site/"):] if page_rel.startswith("site/") else page_rel
    if clean.startswith("/"):
        rel_in_site = posixpath.normpath(clean.lstrip("/"))
    else:
        base_dir = posixpath.dirname(sub_page)
        joined = posixpath.join(base_dir, clean) if base_dir else clean
        rel_in_site = posixpath.normpath(joined)
    if rel_in_site in ("", ".", "..") or rel_in_site.startswith("../"):
        return None
    return "site/" + rel_in_site


def unfilter_png_scanlines(
    decomp: bytes, width: int, height: int, bit_depth: int, color_type: int
) -> bytes | None:
    """Reconstruct unfiltered raw pixel bytes for non-interlaced 8/16-bit PNGs."""
    channels = PNG_CHANNELS.get(color_type)
    if channels is None or bit_depth not in (8, 16) or width < 1 or height < 1:
        return None
    bpp = channels * (bit_depth // 8)
    stride = width * bpp
    if len(decomp) != (stride + 1) * height:
        return None
    out = bytearray(stride * height)
    for y in range(height):
        row_start = y * (stride + 1)
        ftype = decomp[row_start]
        row = decomp[row_start + 1:row_start + 1 + stride]
        base = y * stride
        if ftype == 0:
            out[base:base + stride] = row
        elif ftype == 1:
            for i in range(stride):
                a = out[base + i - bpp] if i >= bpp else 0
                out[base + i] = (row[i] + a) & 0xFF
        elif ftype == 2:
            prev = base - stride
            for i in range(stride):
                b = out[prev + i] if y > 0 else 0
                out[base + i] = (row[i] + b) & 0xFF
        elif ftype == 3:
            prev = base - stride
            for i in range(stride):
                a = out[base + i - bpp] if i >= bpp else 0
                b = out[prev + i] if y > 0 else 0
                out[base + i] = (row[i] + ((a + b) >> 1)) & 0xFF
        elif ftype == 4:
            prev = base - stride
            for i in range(stride):
                a = out[base + i - bpp] if i >= bpp else 0
                b = out[prev + i] if y > 0 else 0
                c = out[prev + i - bpp] if (y > 0 and i >= bpp) else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                out[base + i] = (row[i] + pr) & 0xFF
        else:
            return None
    return bytes(out)


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


def inspect_png_asset(
    raw: bytes,
) -> tuple[str, tuple[int, int, int, int, int, str], bool] | None:
    """Validate PNG structure/CRCs/scanlines and return (metadata_text, sig, clean_chunks)."""
    if not raw.startswith(PNG_MAGIC):
        return None
    pos = len(PNG_MAGIC)
    ihdr: tuple[int, int, int, int, int] | None = None
    seen_iend = False
    extra_image_chunks = False
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
            if width < 1 or height < 1 or comp != 0 or flt != 0 or interlace != 0:
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
        if ctype in PNG_EXTRA_IMAGE_CHUNKS:
            extra_image_chunks = True
            continue
        if ctype == b"tEXt":
            if b"\x00" not in cdata:
                return None
            parts.append(cdata.replace(b"\x00", b"\n").decode("latin-1"))
        elif ctype == b"zTXt":
            sep = cdata.find(b"\x00")
            if sep == -1 or sep + 2 > len(cdata) or cdata[sep + 1] != 0:
                return None
            parts.append(cdata[:sep].decode("latin-1"))
            zraw = _zlib_decompress_exact(cdata[sep + 2:])
            if zraw is None:
                return None
            parts.append(zraw.decode("latin-1"))
        elif ctype == b"iTXt":
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
                parts.append(cdata[:sep1].decode("utf-8"))
                parts.append(text_bytes.decode("utf-8"))
            except UnicodeDecodeError:
                return None
        else:
            return None
    if ihdr is None or not seen_iend or pos != len(raw) or not idat_parts:
        return None
    decomp = _zlib_decompress_exact(b"".join(idat_parts))
    if decomp is None:
        return None
    width, height, bit_depth, color_type, interlace = ihdr
    pixels = unfilter_png_scanlines(decomp, width, height, bit_depth, color_type)
    if pixels is None:
        return None
    sig = (width, height, bit_depth, color_type, interlace, hashlib.sha256(pixels).hexdigest())
    clean_chunks = not extra_image_chunks and not parts
    return "\n".join(parts), sig, clean_chunks


def inspect_ico_asset(
    raw: bytes,
) -> tuple[str, list[tuple[int, int, int, int, int, str]], bool] | None:
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
    sigs: list[tuple[int, int, int, int, int, str]] = []
    clean_all = True
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
        png_txt, sig, png_clean = png_info
        sigs.append(sig)
        clean_all = clean_all and png_clean
        if png_txt:
            parts.append(png_txt)
    if cursor != len(raw):
        return None
    return "\n".join(parts), sigs, clean_all


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
    """Return ('text', str), ('unapproved_raster', str), ('unapproved_script', str), ('skip', None), or ('unscanned_binary', None)."""
    rel = path.relative_to(root).as_posix()
    if not rel.startswith("site/"):
        return "skip", None
    suffix = path.suffix.lower()
    raw = path.read_bytes()
    if suffix == ".png":
        inspected = inspect_png_asset(raw)
        if inspected is None:
            return "unscanned_binary", None
        text, sig, clean_chunks = inspected
        if clean_chunks and [sig] == APPROVED_SITE_RASTERS.get(rel):
            return "text", text
        return "unapproved_raster", text
    if suffix == ".ico":
        inspected = inspect_ico_asset(raw)
        if inspected is None:
            return "unscanned_binary", None
        text, sigs, clean_chunks = inspected
        if clean_chunks and sigs == APPROVED_SITE_RASTERS.get(rel):
            return "text", text
        return "unapproved_raster", text
    if suffix == ".pdf":
        return "unscanned_binary", None
    text_status, text = _decode_site_text(raw)
    if text_status != "text" or text is None:
        return "unscanned_binary", None
    if suffix in SITE_SCRIPT_SUFFIXES:
        if hashlib.sha256(raw).hexdigest() == APPROVED_SITE_SCRIPT_FILES.get(rel):
            return "text", text
        return "unapproved_script", text
    return "text", text


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
INLINE_DISPLAY_RE = re.compile(r"(?i)\bdisplay\s*:\s*(?:inline(?:-[a-z-]+)?|contents)\b")
HTML_BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "body", "br", "caption", "dd",
    "details", "dialog", "div", "dl", "dt", "fieldset", "figcaption", "figure",
    "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header",
    "hgroup", "hr", "html", "li", "link", "main", "menu", "meta", "nav",
    "noscript", "ol", "option", "p", "pre", "script", "section", "style",
    "summary", "table", "tbody", "td", "template", "tfoot", "th", "thead",
    "title", "tr", "ul", "text",
}
HTML_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
SIMPLE_COMPOUND_RE = re.compile(
    r"^(?:[a-zA-Z][a-zA-Z0-9-]*)?(?:(?:#[a-zA-Z0-9_-]+)|(?:\.[a-zA-Z0-9_-]+)|(?:\[[a-zA-Z0-9_-]+(?:=[a-zA-Z0-9_\"'-]+)?\]))*$"
)
DISALLOWED_SITE_CSS_RE = [
    (re.compile(r"(?i)@import\b"), "CSS @import external stylesheet"),
    (re.compile(r"(?i)url\(\s*[\"']?(?:https?:|//)"), "CSS remote resource URL"),
    (re.compile(r"(?i)\bflex-direction\s*:\s*(?:row|column)-reverse\b"), "reverse flex visual ordering"),
    (re.compile(r"(?i)\bflex-wrap\s*:\s*wrap-reverse\b"), "reverse flex-wrap visual ordering"),
    (re.compile(r"(?i)(?<![a-z-])direction\s*:\s*rtl\b"), "RTL CSS text direction"),
    (re.compile(r"(?i)\bunicode-bidi\s*:\s*(?!normal\b)[a-z-]+"), "CSS unicode-bidi override"),
    (re.compile(r"(?i)\bwriting-mode\s*:\s*(?!horizontal-tb\b)[a-z-]+"), "non-horizontal CSS writing-mode"),
    (re.compile(r"(?i)(?<![a-z-])float\s*:\s*(?!none\b)[a-z-]+"), "CSS float visual reordering"),
    (re.compile(r"(?i)(?<![a-z-])(?:left|right|top|bottom|inset(?:-[a-z-]+)?)\s*:\s*(?!auto\b)[^;}]+"), "CSS coordinate offset positioning"),
    (re.compile(r"(?i)(?<![a-z-])(?:transform|translate)\s*:\s*(?!none\b)[^;}]+"), "CSS transform visual positioning"),
    (re.compile(r"(?i)\bgrid-(?:template-areas|area)\s*:"), "CSS named grid-area placement"),
    (re.compile(r"(?i)\bgrid-auto-flow\s*:[^;}]*\bdense\b"), "CSS dense grid auto-placement"),
    (re.compile(r"(?i)@(?:-[a-z]+-)?keyframes\b"), "CSS @keyframes animation"),
]
DISALLOWED_SITE_HTML_RE = [
    (re.compile(r"(?i)<\s*(?:bdo|bdi)\b"), "HTML bidirectional override element"),
    (re.compile(r"(?i)\bdir\s*=\s*[\"']?\s*(?:rtl|auto)\b"), "HTML non-LTR dir attribute"),
    (re.compile(r"(?i)<\s*(?:text|tspan|textPath|foreignObject)\b"), "SVG positioned text or foreignObject element"),
    (re.compile(r"(?i)<\s*(?:iframe|object|embed)\b"), "embedded browsing context in site/"),
    (re.compile(r"(?i)<\s*base\b"), "HTML base href element in site/"),
    (re.compile(r"(?i)<\s*meta\b[^>]*\bhttp-equiv\b"), "HTML meta http-equiv element in site/"),
    (
        re.compile(
            r"(?i)<\s*(?:link\b[^>]*rel\s*=\s*[\"']?[^>]*\bstylesheet\b[^>]*\bhref|script\b[^>]*\bsrc)"
            r"\s*=\s*[\"']?(?:https?:|//|data:|javascript:|vbscript:)"
        ),
        "remote or inline-scheme stylesheet or script in site/",
    ),
    (
        re.compile(r"(?i)<\s*(?:details|dialog|select|option|textarea|input|canvas|audio|video|marquee|math)\b"),
        "unmodeled interactive or collapsible element in site/",
    ),
    (
        re.compile(
            r"(?i)<\s*(?:animate|animateMotion|animateTransform|set|discard|use|switch|clipPath|mask|filter|pattern|marker)\b"
        ),
        "SVG animation, reference, or masking element in site/",
    ),
    (re.compile(r"(?i)<\s*(?:script|style)\b[^>]*/>"), "self-closing script or style tag in site/"),
]


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
    """Decode CSS hex codepoint escapes for identifier scanning."""
    def _repl(match: re.Match) -> str:
        cp = int(match.group(1), 16)
        if 0 < cp <= 0x10FFFF and not (0xD800 <= cp <= 0xDFFF):
            return chr(cp)
        return match.group(0)

    return CSS_ESCAPE_RE.sub(_repl, LINE_CONTINUATION_RE.sub("", text))


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


def count_grid_columns(val: str) -> int | None:
    """Count static tracks in a CSS grid-template-columns declaration, or -1 if dynamic."""
    v = val.strip().lower()
    if v in ("none", "auto"):
        return None
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in v:
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            cur.append(ch)
        elif ch.isspace() and depth == 0:
            if cur:
                parts.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur))
    total = 0
    for tok in parts:
        if tok.startswith("[") and tok.endswith("]"):
            continue
        m = re.match(r"^repeat\(\s*(\d+)\s*,\s*(.+)\)$", tok)
        if m:
            sub = count_grid_columns(m.group(2))
            if not sub or sub < 1:
                return -1
            total += int(m.group(1)) * sub
        elif tok.startswith("repeat(") or "subgrid" in tok:
            return -1
        else:
            total += 1
    return total if total >= 1 else -1


ALLOWED_SITE_CSS_PROPS = {
    "-webkit-font-smoothing",
    "align-items", "align-self", "animation",
    "background", "background-color",
    "border", "border-bottom", "border-color", "border-left", "border-radius", "border-right", "border-top",
    "box-sizing", "clip", "color", "content", "counter-increment", "counter-reset", "cursor",
    "display", "fill", "flex", "flex-direction", "flex-grow", "flex-shrink", "flex-wrap",
    "font", "font-family", "font-size", "font-style", "font-weight",
    "gap", "row-gap", "column-gap",
    "grid-column", "grid-column-start", "grid-row", "grid-row-start", "grid-template-columns",
    "height", "justify-content", "letter-spacing", "line-height", "list-style",
    "margin", "margin-bottom", "margin-left", "margin-right", "margin-top",
    "max-height", "max-width", "min-height", "min-width",
    "opacity", "order", "outline", "outline-offset", "overflow",
    "padding", "padding-bottom", "padding-left", "padding-right", "padding-top",
    "position", "stroke", "stroke-linecap", "stroke-linejoin", "stroke-width",
    "text-align", "text-decoration", "text-decoration-thickness", "text-rendering",
    "text-transform", "text-underline-offset", "transition", "visibility", "white-space", "width",
}
TRANSPARENT_COLOR_RE = re.compile(
    r"(?i)\btransparent\b|color-mix\("
    r"|rgba?\([^)]*[,/]\s*0(?:\.0+)?%?\s*\)"
    r"|hsla?\([^)]*[,/]\s*0(?:\.0+)?%?\s*\)"
    r"|#(?:[0-9a-f]{3}0|[0-9a-f]{6}00)\b"
)
CSS_DYNAMIC_FUNC_RE = re.compile(r"(?i)\b(?:var|calc|min|max|clamp)\(")


def parse_style_decls(
    decl_text: str, allow_zero_scrollbar: bool = False
) -> tuple[dict[str, tuple[object, bool]], list[str]]:
    """Parse CSS declarations relevant to visual layout, ordering, and visibility."""
    props: dict[str, tuple[object, bool]] = {}
    invalid: list[str] = []
    raw_decls: dict[str, str] = {}
    raw_imp: dict[str, bool] = {}
    small_box_dims: list[str] = []

    def _set_prop(key: str, val: object, is_imp: bool) -> None:
        prev = props.get(key)
        if prev is not None and prev[1] and not is_imp:
            return
        props[key] = (val, is_imp)

    clean = CSS_COMMENT_RE.sub("", unescape_css_literals(decl_text))
    if "{" in clean or "}" in clean:
        invalid.append("nested CSS block inside declarations")
        return props, invalid
    for part in clean.split(";"):
        if ":" not in part:
            continue
        k, raw_v = part.split(":", 1)
        k = k.strip().lower()
        imp = bool(re.search(r"(?i)!important\s*$", raw_v))
        v = re.sub(r"(?i)\s*!important\s*$", "", raw_v.strip()).strip()
        vl = v.lower()
        if not k.startswith("--") and k not in ALLOWED_SITE_CSS_PROPS:
            invalid.append(f"unmodeled CSS property ({k})")
            continue
        if (k.startswith("--") or k in ("color", "fill")) and TRANSPARENT_COLOR_RE.search(v):
            invalid.append(f"transparent color hiding ({k})")
        if imp or not raw_imp.get(k, False):
            raw_decls[k] = v
            raw_imp[k] = imp
        if k == "display":
            if vl in {
                "none", "contents", "block", "inline", "inline-block", "flex",
                "inline-flex", "grid", "inline-grid", "list-item", "table", "table-row", "table-cell",
            }:
                _set_prop("display", vl, imp)
            else:
                invalid.append(f"display:{v[:24]}")
        elif k == "visibility":
            if vl in {"visible", "hidden", "collapse"}:
                _set_prop("visibility", vl, imp)
            else:
                invalid.append(f"visibility:{v[:24]}")
        elif k == "opacity":
            if re.match(r"^(?:0(?:\.0+)?|\.0+|1(?:\.0+)?|0?\.[2-9]\d*)$", vl):
                _set_prop("opacity", "0" if float(vl) == 0.0 else vl, imp)
            else:
                invalid.append(f"opacity:{v[:24]}")
        elif k == "position":
            if vl in {"static", "relative", "absolute"}:
                _set_prop("position", vl, imp)
            else:
                invalid.append(f"position:{v[:24]}")
        elif k == "clip":
            if vl == "auto":
                _set_prop("clip", "auto", imp)
            elif re.match(
                r"^rect\(\s*0(?:px)?(?:\s*,\s*|\s+)0(?:px)?(?:\s*,\s*|\s+)0(?:px)?(?:\s*,\s*|\s+)0(?:px)?\s*\)$",
                vl,
            ):
                _set_prop("clip", "zero", imp)
            else:
                invalid.append(f"clip:{v[:24]}")
        elif k in ("animation", "transition"):
            if vl != "none":
                invalid.append(f"{k}:{v[:24]}")
        elif k == "flex-direction":
            if vl not in {"row", "column"}:
                invalid.append(f"flex-direction:{v[:24]}")
        elif k == "flex-wrap":
            if vl not in {"nowrap", "wrap"}:
                invalid.append(f"flex-wrap:{v[:24]}")
        elif k == "font-size":
            if CSS_DYNAMIC_FUNC_RE.search(vl):
                invalid.append(f"font-size:{v[:24]}")
            else:
                m_fs = re.match(r"^([+-]?\d+(?:\.\d+)?)([a-z%]+)?$", vl)
                if m_fs:
                    fs_num = float(m_fs.group(1))
                    fs_unit = m_fs.group(2) or "px"
                    min_fs = 0.25 if fs_unit in ("em", "rem", "ch") else 4.0
                    if fs_num == 0.0:
                        _set_prop("font-size", "0", imp)
                    elif fs_num < 0.0 or fs_num < min_fs:
                        invalid.append(f"font-size:{v[:24]}")
                    else:
                        _set_prop("font-size", vl, imp)
                else:
                    _set_prop("font-size", vl, imp)
        elif k == "line-height":
            if CSS_DYNAMIC_FUNC_RE.search(vl):
                invalid.append(f"line-height:{v[:24]}")
            else:
                m_lh = re.match(r"^([+-]?\d+(?:\.\d+)?)$", vl)
                if m_lh and float(m_lh.group(1)) < 0.5:
                    invalid.append(f"line-height:{v[:24]}")
        elif k == "font":
            if vl != "inherit":
                stripped_v = re.sub(r"\bvar\(--[a-zA-Z0-9_-]+\)", "", vl)
                if CSS_DYNAMIC_FUNC_RE.search(stripped_v) or re.search(
                    r"(?<![\d.])0(?:\.0+)?(?:px|em|rem|%|pt|ch|vw|vh)?(?:\s*/|\s|$)",
                    stripped_v,
                ):
                    invalid.append(f"font:{v[:24]}")
                else:
                    _set_prop("font-size", "16px", imp)
        elif k == "letter-spacing":
            if CSS_DYNAMIC_FUNC_RE.search(vl):
                invalid.append(f"letter-spacing:{v[:24]}")
            elif "-" in vl:
                m_ls = re.match(r"^-(\d*(?:\.\d+)?)([a-z%]+)?$", vl)
                if not m_ls:
                    invalid.append(f"letter-spacing:{v[:24]}")
                else:
                    ls_num = float(m_ls.group(1))
                    ls_unit = m_ls.group(2) or "px"
                    max_neg = 0.05 if ls_unit in ("em", "rem") else (1.0 if ls_unit == "px" else 0.0)
                    if ls_num > max_neg:
                        invalid.append(f"letter-spacing:{v[:24]}")
        elif k in ("margin", "margin-top", "margin-right", "margin-bottom", "margin-left"):
            if CSS_DYNAMIC_FUNC_RE.search(vl):
                invalid.append(f"{k}:{v[:24]}")
            else:
                for m_neg in re.finditer(r"-(\d+(?:\.\d+)?)([a-z%]*)", vl):
                    if m_neg.group(2) != "px" or float(m_neg.group(1)) > 32.0:
                        invalid.append(f"{k}:{v[:24]}")
                        break
        elif k in ("width", "height", "max-width", "max-height"):
            if CSS_DYNAMIC_FUNC_RE.search(vl):
                invalid.append(f"{k}:{v[:24]}")
            else:
                m_dim = re.match(r"^([+-]?\d+(?:\.\d+)?)([a-z%]+)?$", vl)
                if m_dim:
                    dim_num = float(m_dim.group(1))
                    dim_unit = m_dim.group(2) or "px"
                    min_dim = 0.25 if dim_unit in ("em", "rem", "ch") else 2.0
                    if dim_num < min_dim:
                        small_box_dims.append(f"{k}:{v[:24]}")
        elif k == "order":
            m = re.match(r"^[+-]?\d+$", v)
            if m:
                _set_prop("order", int(m.group(0)), imp)
            else:
                invalid.append(f"order:{v[:24]}")
        elif k in ("grid-row", "grid-row-start", "grid-column", "grid-column-start"):
            prop_key = "grid-row" if k.startswith("grid-row") else "grid-column"
            if vl == "auto":
                _set_prop(prop_key, None, imp)
            else:
                m = re.match(r"^(\d+)(?:\s*/\s*(\d+))?$", v)
                if m and int(m.group(1)) >= 1 and (m.group(2) is None or int(m.group(2)) > int(m.group(1))):
                    _set_prop(prop_key, int(m.group(1)), imp)
                else:
                    invalid.append(f"{k}:{v[:24]}")
        elif k == "grid-template-columns":
            cols = count_grid_columns(v)
            if cols == -1:
                invalid.append(f"grid-template-columns:{v[:24]}")
            elif cols is not None:
                _set_prop("grid-cols", cols, imp)
    has_zero_clip = props.get("clip", (None, False))[0] == "zero"
    if props.get("position", (None, False))[0] == "absolute" and not has_zero_clip:
        invalid.append("position:absolute without clip:rect(0,0,0,0)")
    if small_box_dims and not (has_zero_clip or allow_zero_scrollbar):
        invalid.append(f"sub-2px box dimension hiding ({small_box_dims[0]})")
    if "color" in raw_decls:
        c_val = raw_decls["color"].strip().lower()
        bg_val = (raw_decls.get("background-color") or raw_decls.get("background") or "").strip().lower()
        if (bg_val and c_val == bg_val) or (c_val == "var(--bg)" and not bg_val):
            invalid.append("foreground color matching background hiding")
    return props, invalid


def _check_css_safety(clean_css: str) -> list[str]:
    """Flag CSS constructs capable of unanalyzable visual reordering or text injection."""
    issues: list[str] = []
    for rx, label in DISALLOWED_SITE_CSS_RE:
        m = rx.search(clean_css)
        if m:
            issues.append(f"{label} ({m.group(0).strip()[:36]})")
    for m in re.finditer(r"(?i)(?<![a-z-])content\s*:\s*([^;}]+)", clean_css):
        val = m.group(1).strip()
        rem = re.sub(r"(?i)\bcounter\([^)]*\)", "", val)
        rem = re.sub(r"(?i)\b(?:none|normal|open-quote|close-quote)\b", "", rem)
        rem = re.sub(r"[\"\'\s.]", "", rem)
        if rem:
            issues.append(f"CSS content text injection ({val[:36]})")
    return issues


def parse_simple_selector(sel: str):
    """Parse descendant/child CSS selectors of tags, ids, classes, and attributes."""
    tokens = [t for t in re.split(r"(\s*>\s*|\s+)", sel.strip()) if t]
    chain = []
    comb: str | None = None
    spec_ids = spec_cls = spec_tags = 0
    for tok in tokens:
        if ">" in tok:
            comb = ">"
            continue
        if tok.isspace():
            if comb is None:
                comb = " "
            continue
        if not SIMPLE_COMPOUND_RE.match(tok) or tok == "":
            return None, (0, 0, 0)
        tag_m = re.match(r"^([a-zA-Z][a-zA-Z0-9-]*)", tok)
        tag = tag_m.group(1).lower() if tag_m else None
        if tag:
            spec_tags += 1
        ids = re.findall(r"#([a-zA-Z0-9_-]+)", tok)
        spec_ids += len(ids)
        classes = re.findall(r"\.([a-zA-Z0-9_-]+)", tok)
        attrs: list[tuple[str, str | None]] = []
        for am in re.finditer(r"\[([a-zA-Z0-9_-]+)(?:=([a-zA-Z0-9_\"'-]+))?\]", tok):
            ak = am.group(1).lower()
            av = am.group(2).strip("\"'") if am.group(2) is not None else None
            attrs.append((ak, av))
        spec_cls += len(classes) + len(attrs)
        chain.append((comb, tag, ids, classes, attrs))
        comb = None
    return (chain if chain else None), (spec_ids, spec_cls, spec_tags)


def parse_media_interval(prelude: str) -> tuple[float, float, bool]:
    """Parse @media pixel-width bounds; mark non-pixel/complex queries unresolvable."""
    q = prelude.strip()
    if q.lower().startswith("@media"):
        q = q[6:].strip()
    if not q or "," in q or " or " in f" {q.lower()} ":
        return 0.0, float("inf"), True
    parts = [p.strip() for p in re.split(r"(?i)\band\b", q) if p.strip()]
    lo, hi = 0.0, float("inf")
    unres = False
    for part in parts:
        pl = part.lower()
        if pl in ("all", "screen", "only screen", "only all"):
            continue
        m = re.match(
            r"^\(\s*(min-width|max-width|width)\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*px\s*\)$",
            pl,
        )
        if m:
            kind, val = m.group(1), float(m.group(2))
            if kind == "min-width":
                lo = max(lo, val)
            elif kind == "max-width":
                hi = min(hi, val)
            else:
                lo = max(lo, val)
                hi = min(hi, val)
            continue
        m_cmp = re.match(
            r"^\(\s*width\s*(<=|>=|<|>|=)\s*([0-9]+(?:\.[0-9]+)?)\s*px\s*\)$",
            pl,
        )
        if m_cmp:
            op, val = m_cmp.group(1), float(m_cmp.group(2))
            if op == "<=":
                hi = min(hi, val)
            elif op == "<":
                hi = min(hi, max(0.0, val - 0.1))
            elif op == ">=":
                lo = max(lo, val)
            elif op == ">":
                lo = max(lo, val + 0.1)
            else:
                lo = max(lo, val)
                hi = min(hi, val)
            continue
        unres = True
    return lo, hi, unres


def parse_css_stylesheet(
    css_text: str,
    media_iv: tuple[float, float] = (0.0, float("inf")),
    unresolvable_cond: bool = False,
    start_idx: int = 0,
    in_at_rule: bool = False,
) -> tuple[list, list[str], int]:
    """Parse stylesheet rules for visual-order reconstruction and flag unsafe layout rules."""
    clean = CSS_COMMENT_RE.sub("", unescape_css_literals(css_text))
    rules: list = []
    issues: list[str] = [] if in_at_rule else _check_css_safety(clean)
    idx = start_idx
    layout_keys = {
        "display", "order", "grid-row", "grid-column", "grid-cols",
        "visibility", "opacity", "position", "clip",
    }
    i, n = 0, len(clean)
    while i < n:
        semi = clean.find(";", i)
        brace = clean.find("{", i)
        if semi != -1 and (brace == -1 or semi < brace):
            stmt = clean[i:semi].strip()
            if stmt and not re.match(r'(?i)^@charset\s+"utf-8"$', stmt):
                issues.append(f"unmodeled CSS statement ({stmt[:36]})")
            i = semi + 1
            continue
        if brace == -1:
            rem = clean[i:].strip()
            if rem:
                issues.append(f"unmodeled trailing CSS text ({rem[:36]})")
            break
        prelude = clean[i:brace].strip()
        depth = 1
        j = brace + 1
        while j < n and depth > 0:
            if clean[j] == "{":
                depth += 1
            elif clean[j] == "}":
                depth -= 1
            j += 1
        body = clean[brace + 1:j - 1]
        i = j
        if not prelude:
            continue
        if prelude.startswith("@"):
            pl_low = prelude.lower()
            if pl_low.startswith("@media"):
                c_lo, c_hi, c_unres = parse_media_interval(prelude)
                sub_iv = (max(media_iv[0], c_lo), min(media_iv[1], c_hi))
                sub_rules, sub_issues, idx = parse_css_stylesheet(
                    body,
                    media_iv=sub_iv,
                    unresolvable_cond=unresolvable_cond or c_unres,
                    start_idx=idx,
                    in_at_rule=True,
                )
                rules.extend(sub_rules)
                issues.extend(sub_issues)
            elif pl_low.startswith(("@supports", "@layer", "@container", "@scope", "@starting-style")):
                sub_rules, sub_issues, idx = parse_css_stylesheet(
                    body,
                    media_iv=media_iv,
                    unresolvable_cond=True,
                    start_idx=idx,
                    in_at_rule=True,
                )
                rules.extend(sub_rules)
                issues.extend(sub_issues)
            else:
                issues.append(f"unmodeled CSS at-rule ({prelude[:36]})")
            continue
        props, bad_vals = parse_style_decls(
            body,
            allow_zero_scrollbar=(prelude.strip().lower() == "::-webkit-scrollbar"),
        )
        issues.extend(f"non-literal CSS visual-order value ({bv})" for bv in bad_vals)
        fs_val = props.get("font-size", ("", False))[0]
        has_zero_font = isinstance(fs_val, str) and bool(re.match(r"^0(?:\.0+)?(?:[a-z%]+)?$", fs_val))
        has_layout_prop = has_zero_font or any(k in props for k in layout_keys)
        if has_layout_prop and unresolvable_cond:
            issues.append(f"non-pixel conditional layout rule ({prelude[:36]})")
        for sel in prelude.split(","):
            sel = sel.strip()
            if not sel:
                continue
            chain, spec = parse_simple_selector(sel)
            if chain is None:
                if has_layout_prop:
                    issues.append(f"complex CSS visual-order selector ({sel[:36]})")
            else:
                idx += 1
                rules.append((chain, spec, idx, props, media_iv))
    return rules, issues, idx


class _DOMNode:
    def __init__(self, tag: str, attrs: dict[str, str], parent: "_DOMNode | None" = None) -> None:
        self.tag = tag
        self.attrs = attrs
        self.parent = parent
        self.children: list[str | _DOMNode] = []
        self.classes = set(attrs.get("class", "").split())
        self.id = attrs.get("id", "")


def _matches_compound(node: _DOMNode, tag, ids, classes, attrs) -> bool:
    if tag and node.tag != tag:
        return False
    if any(i != node.id for i in ids):
        return False
    if any(c not in node.classes for c in classes):
        return False
    for ak, av in attrs:
        if ak not in node.attrs:
            return False
        if av is not None and node.attrs[ak] != av:
            return False
    return True


def _matches_chain(node: _DOMNode, chain) -> bool:
    if not _matches_compound(node, *chain[-1][1:]):
        return False
    cur = node
    for idx in range(len(chain) - 1, 0, -1):
        comb = chain[idx][0]
        target = chain[idx - 1][1:]
        if comb == ">":
            if cur.parent is None or cur.parent.tag == "__root__" or not _matches_compound(cur.parent, *target):
                return False
            cur = cur.parent
        else:
            anc = cur.parent
            while anc is not None and anc.tag != "__root__":
                if _matches_compound(anc, *target):
                    break
                anc = anc.parent
            else:
                return False
            cur = anc
    return True


def compute_node_style(
    node: _DOMNode, rules: list | tuple, viewport_w: float | None = None
) -> dict[str, object]:
    """Compute cascaded CSS properties on a DOM node using selector specificity and viewport width."""
    resolved: dict[str, tuple[tuple[int, int, int, int, int, int], object]] = {}
    for chain, spec, r_idx, props, (lo, hi) in rules:
        if viewport_w is None:
            if lo > 0.0 or hi < float("inf"):
                continue
        elif not (lo <= viewport_w <= hi):
            continue
        if _matches_chain(node, chain):
            for prop, (val, imp) in props.items():
                rank = (1 if imp else 0, 0, spec[0], spec[1], spec[2], r_idx)
                if prop not in resolved or rank >= resolved[prop][0]:
                    resolved[prop] = (rank, val)
    inline_s = node.attrs.get("style", "")
    if inline_s:
        iprops, _ = parse_style_decls(inline_s)
        for prop, (val, imp) in iprops.items():
            rank = (1 if imp else 0, 1, 0, 0, 0, 10**9)
            if prop not in resolved or rank >= resolved[prop][0]:
                resolved[prop] = (rank, val)
    return {k: v[1] for k, v in resolved.items()}


def _is_hidden_node(node: _DOMNode, st: dict[str, object]) -> bool:
    if (
        node.tag in ("template", "script", "style", "noscript", "svg", "defs", "symbol", "desc", "metadata")
        or "hidden" in node.attrs
    ):
        return True
    if st.get("display") == "none" or st.get("visibility") in ("hidden", "collapse"):
        return True
    if st.get("clip") == "zero" or st.get("position") == "absolute":
        return True
    if st.get("opacity") in ("0", "0.0", ".0"):
        return True
    fs = st.get("font-size")
    if isinstance(fs, str) and re.match(r"^0(?:\.0+)?(?:[a-z%]+)?$", fs):
        return True
    return False


_TABLE_SECTION_ORDER = {
    "caption": 0,
    "colgroup": 1,
    "col": 1,
    "thead": 2,
    "tbody": 3,
    "tr": 3,
    "tfoot": 4,
}


def serialize_visual_tree(
    root_node: _DOMNode,
    rules: list | tuple,
    viewport_w: float | None,
    respect_order: bool,
    skip_hidden: bool,
    i18n_map: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Serialize DOM text in computed visual order (flex order, grid tracks, table sections)."""
    fused: list[str] = []
    compact: list[str] = []

    def expand_children(container: _DOMNode) -> list[tuple[str, object, dict[str, object]]]:
        items: list[tuple[str, object, dict[str, object]]] = []
        for ch in container.children:
            if isinstance(ch, str):
                if ch:
                    items.append(("text", ch, {}))
            else:
                st = compute_node_style(ch, rules, viewport_w)
                if skip_hidden and _is_hidden_node(ch, st):
                    continue
                if respect_order and st.get("display") == "contents":
                    items.extend(expand_children(ch))
                else:
                    items.append(("node", ch, st))
        if not respect_order:
            return items
        if container.tag == "table":
            meaningful = [
                (idx, kind, obj, st)
                for idx, (kind, obj, st) in enumerate(items)
                if not (kind == "text" and isinstance(obj, str) and not obj.strip())
            ]
            meaningful.sort(
                key=lambda x: (
                    _TABLE_SECTION_ORDER.get(x[2].tag, 5) if isinstance(x[2], _DOMNode) else 5,
                    x[0],
                )
            )
            return [(k, o, s) for _, k, o, s in meaningful]

        parent_st = compute_node_style(container, rules, viewport_w) if container.tag != "__root__" else {}
        disp = str(parent_st.get("display", "")).lower()
        is_flex = "flex" in disp
        is_grid = "grid" in disp
        if not (is_flex or is_grid):
            return items

        meaningful_items: list[list[object]] = []
        for idx, (kind, obj, st) in enumerate(items):
            if kind == "text" and isinstance(obj, str) and not obj.strip():
                continue
            raw_ord = st.get("order", 0)
            ord_val = raw_ord if isinstance(raw_ord, int) else 0
            raw_gr = st.get("grid-row")
            gr = raw_gr if isinstance(raw_gr, int) else None
            raw_gc = st.get("grid-column")
            gc = raw_gc if isinstance(raw_gc, int) else None
            meaningful_items.append([idx, kind, obj, st, ord_val, gr, gc])

        if is_flex:
            meaningful_items.sort(key=lambda x: (int(x[4]), int(x[0])))  # type: ignore[arg-type]
            return [(m[1], m[2], m[3]) for m in meaningful_items]  # type: ignore[misc]

        explicit_cols = [m[6] for m in meaningful_items if isinstance(m[6], int)]
        parent_cols = parent_st.get("grid-cols")
        ncols = parent_cols if isinstance(parent_cols, int) and parent_cols >= 1 else max([1, *explicit_cols])
        occupied: set[tuple[int, int]] = set()
        for m in meaningful_items:
            if isinstance(m[5], int) and isinstance(m[6], int):
                r, c = m[5], m[6]
                ncols = max(ncols, c)
                occupied.add((r, c))
        for m in sorted(meaningful_items, key=lambda x: (int(x[4]), int(x[0]))):  # type: ignore[arg-type]
            if isinstance(m[5], int) and m[6] is None:
                r = m[5]
                c = 1
                while (r, c) in occupied:
                    c += 1
                m[6] = c
                ncols = max(ncols, c)
                occupied.add((r, c))
        cur_r, cur_c = 1, 1
        for m in sorted(meaningful_items, key=lambda x: (int(x[4]), int(x[0]))):  # type: ignore[arg-type]
            if m[5] is None:
                if isinstance(m[6], int):
                    c = m[6]
                    ncols = max(ncols, c)
                    r = cur_r if c >= cur_c else cur_r + 1
                    while (r, c) in occupied:
                        r += 1
                    m[5] = r
                    occupied.add((r, c))
                    cur_r, cur_c = r, c + 1
                    if cur_c > ncols:
                        cur_r += 1
                        cur_c = 1
                else:
                    while (cur_r, cur_c) in occupied:
                        cur_c += 1
                        if cur_c > ncols:
                            cur_r += 1
                            cur_c = 1
                    m[5], m[6] = cur_r, cur_c
                    occupied.add((cur_r, cur_c))
                    cur_c += 1
                    if cur_c > ncols:
                        cur_r += 1
                        cur_c = 1
        meaningful_items.sort(key=lambda x: (int(x[5]), int(x[6]), int(x[4]), int(x[0])))  # type: ignore[arg-type]
        return [(m[1], m[2], m[3]) for m in meaningful_items]  # type: ignore[misc]

    def walk(node: _DOMNode) -> None:
        if i18n_map and node.tag != "__root__":
            k_txt = node.attrs.get("data-i18n")
            k_htm = node.attrs.get("data-i18n-html")
            if k_txt and k_txt in i18n_map:
                val = i18n_map[k_txt]
                fused.append(val)
                if val.strip():
                    compact.append(val.strip())
                return
            if k_htm and k_htm in i18n_map:
                val = re.sub(r"<[^>]+>", "", i18n_map[k_htm])
                fused.append(val)
                if val.strip():
                    compact.append(val.strip())
                return
        for kind, obj, _ in expand_children(node):
            if kind == "text" and isinstance(obj, str):
                fused.append(obj)
                if obj.strip():
                    compact.append(obj.strip())
            elif isinstance(obj, _DOMNode):
                walk(obj)

    walk(root_node)
    return "".join(fused), "".join(compact)


class _RenderedHTMLNormalizer(HTMLParser):
    def __init__(self, depth: int = 0, xml_mode: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = depth
        self.xml_mode = xml_mode
        self.inline_parts: list[str] = []
        self.fused_parts: list[str] = []
        self.compact_parts: list[str] = []
        self.attr_lines: list[str] = []
        self.comment_lines: list[str] = []
        self.subtrees: list[str] = []
        self.stylesheet_entries: list[tuple[str, str, str]] = []
        self.script_tags: list[tuple[str | None, str]] = []
        self.inline_css_issues: list[str] = []
        self.html_issues: list[str] = []
        self.dom_root = _DOMNode("__root__", {})
        self._dom_stack: list[_DOMNode] = [self.dom_root]
        self._tag_stack: list[tuple[str, bool]] = []
        self._raw_tag: str | None = None
        self._raw_chunks: list[str] = []
        self._raw_media: str = ""
        self._raw_src: str | None = None

    @staticmethod
    def _has_inline_display(attrs: list[tuple[str, str | None]]) -> bool:
        for k, v in attrs:
            if k.lower() == "style" and v and INLINE_DISPLAY_RE.search(v):
                return True
        return False

    def _handle_attrs(self, attrs: list[tuple[str, str | None]]) -> None:
        for k, v in attrs:
            kl = k.lower()
            if kl in ("display", "visibility", "opacity", "clip", "clip-path", "transform", "filter", "mask"):
                self.html_issues.append(f"presentation hiding or layout attribute in site/ ({kl})")
            if re.match(r"^on[a-z]{2,}$", kl):
                self.html_issues.append(f"inline event handler attribute in site/ ({kl})")
            if not v:
                continue
            compact_val = re.sub(r"[\x00-\x20]+", "", v)
            if re.match(r"^(?:javascript|vbscript):", compact_val, re.IGNORECASE):
                self.html_issues.append("javascript: or vbscript: URI attribute in site/")
            self.attr_lines.append(f"{k}={v}")
            if "%" in v:
                self.attr_lines.append(f"{k}={urllib.parse.unquote(v)}")
            if kl == "style":
                clean_s = CSS_COMMENT_RE.sub("", unescape_css_literals(v))
                self.inline_css_issues.extend(_check_css_safety(clean_s))
                _, bad_vals = parse_style_decls(clean_s)
                self.inline_css_issues.extend(f"non-literal CSS visual-order value ({bv})" for bv in bad_vals)
            if kl == "srcdoc" and self.depth < 3:
                self.subtrees.append(normalize_html_text(v, self.depth + 1))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        ad = {k.lower(): (v or "") for k, v in attrs}
        node = _DOMNode(t, ad, parent=self._dom_stack[-1])
        self._dom_stack[-1].children.append(node)
        if t not in HTML_VOID_TAGS:
            self._dom_stack.append(node)
        is_block = (t in HTML_BLOCK_TAGS) and not self._has_inline_display(attrs)
        self._tag_stack.append((t, is_block))
        if is_block:
            self.inline_parts.append("\n")
        self._handle_attrs(attrs)
        if t == "link":
            rel_tokens = {tok.lower() for tok in ad.get("rel", "").split()}
            if "stylesheet" in rel_tokens:
                self.stylesheet_entries.append(("link", ad.get("href", "").strip(), ad.get("media", "").strip()))
        elif t == "style":
            self._raw_tag = t
            self._raw_chunks = []
            self._raw_media = ad.get("media", "").strip()
        elif t == "script":
            self._raw_tag = t
            self._raw_chunks = []
            self._raw_src = ad["src"] if "src" in ad else None

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        in_svg = self.xml_mode or any(st_tag == "svg" for st_tag, _ in self._tag_stack)
        if t in ("script", "style") or (not in_svg and t not in HTML_VOID_TAGS):
            if t in ("script", "style"):
                self.set_cdata_mode(t)
            self.handle_starttag(tag, attrs)
            return
        ad = {k.lower(): (v or "") for k, v in attrs}
        node = _DOMNode(t, ad, parent=self._dom_stack[-1])
        self._dom_stack[-1].children.append(node)
        if (t in HTML_BLOCK_TAGS) and not self._has_inline_display(attrs):
            self.inline_parts.append("\n")
        self._handle_attrs(attrs)
        if t == "link":
            rel_tokens = {tok.lower() for tok in ad.get("rel", "").split()}
            if "stylesheet" in rel_tokens:
                self.stylesheet_entries.append(("link", ad.get("href", "").strip(), ad.get("media", "").strip()))
        elif t == "script":
            self.script_tags.append((ad["src"] if "src" in ad else None, ""))

    def _flush_raw_tag(self, tag_name: str) -> None:
        raw_body = "".join(self._raw_chunks)
        if tag_name == "script":
            self.script_tags.append((self._raw_src, raw_body))
            self._raw_src = None
            dec = fold_js_expressions(raw_body)
            self.subtrees.append(dec)
            if ("<" in dec or "&" in dec) and self.depth < 3:
                self.subtrees.append(normalize_html_text(dec, self.depth + 1))
        elif tag_name == "style":
            self.stylesheet_entries.append(("inline", raw_body, self._raw_media))
            self._raw_media = ""
            self.subtrees.append(unescape_css_literals(raw_body))
        self._raw_tag = None
        self._raw_chunks = []

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if self._raw_tag == t:
            self._flush_raw_tag(t)
        is_block = t in HTML_BLOCK_TAGS
        for idx in range(len(self._tag_stack) - 1, -1, -1):
            if self._tag_stack[idx][0] == t:
                _, is_block = self._tag_stack[idx]
                del self._tag_stack[idx:]
                break
        for idx in range(len(self._dom_stack) - 1, 0, -1):
            if self._dom_stack[idx].tag == t:
                del self._dom_stack[idx:]
                break
        if is_block:
            self.inline_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._raw_tag is not None:
            self._raw_chunks.append(data)
            return
        self.inline_parts.append(data)
        self.fused_parts.append(data)
        if data.strip():
            self.compact_parts.append(data.strip())
        self._dom_stack[-1].children.append(data)

    def handle_comment(self, data: str) -> None:
        self.comment_lines.append(html.unescape(data))

    def unknown_decl(self, data: str) -> None:
        if data.startswith("CDATA["):
            self.handle_data(data[len("CDATA["):])


def _collect_page_stylesheet_rules(
    page_rel: str,
    stylesheet_entries: list[tuple[str, str, str]],
    css_by_rel: dict[str, str] | None = None,
) -> tuple[list, list[str], set[float]]:
    """Resolve linked and inline stylesheets for one page in document order."""
    rules: list = []
    issues: list[str] = []
    breakpoints: set[float] = set()
    idx_base = 0
    for kind, content, media_attr in stylesheet_entries:
        if media_attr.strip():
            m_lo, m_hi, m_unres = parse_media_interval("@media " + media_attr)
            base_iv: tuple[float, float] = (m_lo, m_hi)
        else:
            base_iv = (0.0, float("inf"))
            m_unres = False
        css_src = ""
        if kind == "link":
            resolved = resolve_site_asset_href(page_rel, content)
            if resolved is None:
                issues.append(f"external or escaping stylesheet link ({content[:36]})")
                continue
            if css_by_rel is not None:
                if resolved not in css_by_rel:
                    issues.append(f"missing local stylesheet link ({content[:36]})")
                    continue
                css_src = css_by_rel[resolved]
        else:
            css_src = content
        if css_src:
            p_rules, p_issues, idx_base = parse_css_stylesheet(
                css_src, media_iv=base_iv, unresolvable_cond=m_unres, start_idx=idx_base
            )
            rules.extend(p_rules)
            if kind == "inline":
                issues.extend(p_issues)
            elif m_unres:
                issues.extend(iss for iss in p_issues if iss.startswith("non-pixel conditional"))
            for _, _, _, _, (lo, hi) in p_rules:
                if 0.0 < lo < float("inf"):
                    breakpoints.add(lo)
                if hi < float("inf"):
                    breakpoints.add(hi)
    return rules, issues, breakpoints


def normalize_html_text(
    text: str,
    depth: int = 0,
    page_rel: str = "site/index.html",
    css_by_rel: dict[str, str] | None = None,
    i18n_maps: list[dict[str, str]] | tuple[dict[str, str], ...] = (),
) -> str:
    """Canonicalize rendered HTML/SVG text, CSS visual order, attributes, comments, and scripts."""
    parser = _RenderedHTMLNormalizer(
        depth=depth,
        xml_mode=Path(page_rel).suffix.lower() in (".svg", ".xml", ".xhtml"),
    )
    parser.feed(text)
    parser.close()
    if parser._raw_tag is not None:
        parser._flush_raw_tag(parser._raw_tag)
    all_rules, _, breakpoints = _collect_page_stylesheet_rules(
        page_rel, parser.stylesheet_entries, css_by_rel=css_by_rel
    )
    candidates = [320.0, 1440.0]
    for bp in sorted(breakpoints)[:32]:
        candidates.extend((max(0.0, bp - 0.5), bp, bp + 0.5))
    seen_sigs: set[tuple[int, ...]] = set()
    active_viewports: list[float] = []
    for vw in candidates:
        sig = tuple(r_idx for _, _, r_idx, _, (lo, hi) in all_rules if lo <= vw <= hi)
        if sig not in seen_sigs:
            seen_sigs.add(sig)
            active_viewports.append(vw)

    vis_dom_f, vis_dom_c = serialize_visual_tree(
        parser.dom_root, all_rules, viewport_w=None, respect_order=False, skip_hidden=True
    )
    rendered_views: list[str] = [vis_dom_f, vis_dom_c]
    seen_rendered: set[str] = {vis_dom_f, vis_dom_c}
    has_i18n = "data-i18n" in text and bool(i18n_maps)
    for vw in active_viewports:
        for skip_hidden in (True, False):
            vf, vc = serialize_visual_tree(
                parser.dom_root, all_rules, viewport_w=vw, respect_order=True, skip_hidden=skip_hidden
            )
            for v in (vf, vc):
                if v not in seen_rendered:
                    seen_rendered.add(v)
                    rendered_views.append(v)
            if has_i18n:
                for imap in i18n_maps:
                    if not imap:
                        continue
                    ivf, ivc = serialize_visual_tree(
                        parser.dom_root,
                        all_rules,
                        viewport_w=vw,
                        respect_order=True,
                        skip_hidden=skip_hidden,
                        i18n_map=imap,
                    )
                    for v in (ivf, ivc):
                        if v not in seen_rendered:
                            seen_rendered.add(v)
                            rendered_views.append(v)

    combined = "\n".join([
        "".join(parser.inline_parts),
        "".join(parser.fused_parts),
        "".join(parser.compact_parts),
        *rendered_views,
        "\n".join(parser.attr_lines),
        "\n".join(parser.comment_lines),
        *parser.subtrees,
    ])
    return INVISIBLE_FORMAT_RE.sub("", combined)


def check_site_visual_integrity(
    rel: str,
    path: Path,
    text: str,
    report: Report,
    seen: set[tuple[str, str]],
    css_by_rel: dict[str, str] | None = None,
    script_hashes_by_rel: dict[str, str] | None = None,
) -> None:
    """Reject bidirectional controls and CSS/HTML/script constructs that obscure visual order or bypass static scans."""
    def _emit(msg: str) -> None:
        item = ("publish", f"{rel}: {msg} (section 13)")
        if item not in seen:
            seen.add(item)
            report.add(*item)

    if BIDI_CONTROL_RE.search(text):
        _emit("bidirectional control character in published site/ asset")
    suffix = path.suffix.lower()
    if suffix == ".css":
        _, issues, _ = parse_css_stylesheet(text)
        for iss in issues:
            _emit(iss)
        return
    if suffix in (".html", ".htm", ".xhtml", ".svg", ".xml"):
        for rx, label in DISALLOWED_SITE_HTML_RE:
            m = rx.search(text)
            if m:
                _emit(f"{label}: {m.group(0).strip()[:36]}")
        parser = _RenderedHTMLNormalizer(xml_mode=suffix in (".svg", ".xml", ".xhtml"))
        parser.feed(text)
        parser.close()
        if parser._raw_tag is not None:
            parser._flush_raw_tag(parser._raw_tag)
        for iss in parser.html_issues:
            _emit(iss)
        for iss in parser.inline_css_issues:
            _emit(iss)
        _, css_issues, breakpoints = _collect_page_stylesheet_rules(
            rel, parser.stylesheet_entries, css_by_rel=css_by_rel
        )
        for iss in css_issues:
            _emit(iss)
        if len(breakpoints) > 32:
            _emit(f"too many CSS @media breakpoints ({len(breakpoints)} > 32) in site/ page")
        for src, raw_body in parser.script_tags:
            if src is not None:
                resolved_src = resolve_site_asset_href(rel, src)
                expected_sha = APPROVED_SITE_SCRIPT_FILES.get(resolved_src) if resolved_src else None
                actual_sha = (script_hashes_by_rel or {}).get(resolved_src) if resolved_src else None
                if resolved_src is None or expected_sha is None or actual_sha != expected_sha:
                    _emit(f"unapproved executable script src in site/ ({src[:36]})")
                if raw_body.strip():
                    _emit("unapproved executable inline script in site/")
            else:
                body_sha = hashlib.sha256(raw_body.encode("utf-8")).hexdigest() if raw_body.strip() else ""
                if body_sha not in APPROVED_SITE_INLINE_SCRIPTS:
                    _emit("unapproved executable inline script in site/")


def collect_site_context(root: Path) -> tuple[dict[str, str], dict[str, str], list[dict[str, str]]]:
    """Collect site/ CSS sources by relpath, script SHA-256 digests, and approved i18n dictionaries."""
    css_by_rel: dict[str, str] = {}
    script_hashes_by_rel: dict[str, str] = {}
    first_map: dict[str, str] = {}
    last_map: dict[str, str] = {}
    kv_re = re.compile(
        r"(?:([a-zA-Z_][a-zA-Z0-9_]*)|\"([^\"]+)\"|'([^']+)')\s*:\s*"
        r"(?:\"((?:[^\"\\]|\\.)*)\"|'((?:[^'\\]|\\.)*)')"
    )
    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        if not rel.startswith("site/"):
            continue
        suffix = path.suffix.lower()
        if suffix not in (".css", *SITE_SCRIPT_SUFFIXES):
            continue
        raw = path.read_bytes()
        status, text = _decode_site_text(raw)
        if suffix == ".css":
            if status == "text" and text is not None:
                css_by_rel[rel] = text
        else:
            sha = hashlib.sha256(raw).hexdigest()
            script_hashes_by_rel[rel] = sha
            if status == "text" and text is not None and sha == APPROVED_SITE_SCRIPT_FILES.get(rel):
                dec = fold_js_expressions(text)
                for m in kv_re.finditer(dec):
                    k = m.group(1) or m.group(2) or m.group(3)
                    v = m.group(4) if m.group(4) is not None else (m.group(5) or "")
                    if k not in first_map:
                        first_map[k] = v
                    last_map[k] = v
    i18n_maps = [m for m in (first_map, last_map) if m]
    return css_by_rel, script_hashes_by_rel, i18n_maps


def normalized_site_views(
    path: Path,
    text: str,
    page_rel: str = "site/index.html",
    css_by_rel: dict[str, str] | None = None,
    i18n_maps: list[dict[str, str]] | tuple[dict[str, str], ...] = (),
) -> list[str]:
    """Build raw and decoded/rendered views of a deployed site/ text asset."""
    views: list[str] = []

    def _add(candidate: str) -> None:
        if candidate and candidate not in views:
            views.append(candidate)

    _add(text)
    stripped = INVISIBLE_FORMAT_RE.sub("", text)
    _add(stripped)
    js_dec = INVISIBLE_FORMAT_RE.sub("", fold_js_expressions(text))
    _add(js_dec)
    suffix = path.suffix.lower()
    if suffix in (".css", ".html", ".htm", ".xhtml", ".svg"):
        _add(INVISIBLE_FORMAT_RE.sub("", unescape_css_literals(text)))
    if suffix in (".html", ".htm", ".xhtml", ".svg", ".xml") or "<" in js_dec or "&" in js_dec:
        _add(normalize_html_text(text, page_rel=page_rel, css_by_rel=css_by_rel, i18n_maps=i18n_maps))
        if js_dec != text:
            _add(normalize_html_text(js_dec, page_rel=page_rel, css_by_rel=css_by_rel, i18n_maps=i18n_maps))
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
            # A pattern without a predicate describes prose, and a fenced
            # block is not prose. The style guide shows each of these
            # shapes as an example of what to avoid.
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
    site_path_patterns = [*LEAK_PATTERNS[:4], *SITE_LEAK_PATTERNS]
    site_css_by_rel, site_script_hashes, site_i18n_maps = collect_site_context(root)
    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        markdown = is_markdown(path)
        if rel.startswith("site/"):
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
            if status == "unapproved_raster":
                report.add(
                    "publish",
                    f"{rel}: unapproved or uninspected raster asset in published site/ tree (section 13)",
                )
                if not site_text:
                    continue
            elif status == "unapproved_script":
                report.add(
                    "publish",
                    f"{rel}: unapproved or uninspected executable script in published site/ tree (section 13)",
                )
                if not site_text:
                    continue
            elif status != "text" or site_text is None:
                continue
            check_site_visual_integrity(
                rel,
                path,
                site_text,
                report,
                seen_for_file,
                css_by_rel=site_css_by_rel,
                script_hashes_by_rel=site_script_hashes,
            )
            patterns = list(LEAK_PATTERNS) if markdown else list(LEAK_PATTERNS[:4])
            patterns.extend(SITE_LEAK_PATTERNS)
            for view in normalized_site_views(
                path,
                site_text,
                page_rel=rel,
                css_by_rel=site_css_by_rel,
                i18n_maps=site_i18n_maps,
            ):
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
            if rel == "scripts/test_style.py":
                continue
            tx_status, decoded_txt = _decode_site_text(path.read_bytes())
            if tx_status != "text" or not decoded_txt:
                continue
            text = (
                re.sub(r'ipaddress\.ip_network\("[^"]+"\)', 'ipaddress.ip_network("")', decoded_txt)
                if rel == "scripts/check_style.py"
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
    gitignore = root / ".gitignore"
    text = gitignore.read_text(encoding="utf-8", errors="ignore") if gitignore.exists() else ""
    missing = [pattern for pattern in INTERNAL_NOTE_GITIGNORE if pattern not in text]
    if missing:
        # Blocking in both phases. This is the first of the three layers that
        # keep working notes out of a public repository, and it is the only one
        # that acts before the note is committed at all. A repository that
        # loses it stops preventing the mistake and starts detecting it, which
        # is a different and much later guarantee.
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
        help="1 blocks leaks and broken links; 2 also blocks naming (default: 1)",
    )
    parser.add_argument(
        "--advisory", action="store_true",
        help="report findings but always exit 0, for adopting a repository gradually",
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

    check_naming(root, report)
    check_readme(root, report)
    check_links(root, report)
    check_agent_files(root, report)
    check_language(root, report)
    check_docs_baseline(root, report)
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
        # A repository adopts the rule set before it can satisfy it. Failing on
        # the adoption pull request would make that pull request the first thing
        # the check blocks, and the check would be removed instead of the
        # findings fixed. The findings are still printed and still counted.
        print("advisory run: exit status forced to 0")
        return 0

    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
