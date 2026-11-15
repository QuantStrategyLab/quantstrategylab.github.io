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
import fnmatch
import hashlib
import html
import ipaddress
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

URL_TOKEN = re.compile(r"https?://[^\s)\]\"'<>`]+")
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
    bucket = match.group(0)[len("gs://"):].split("/", 1)[0]
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
    (re.compile(r"(?<![\w.])/(?:Users|home)/[^\s`)\]\"'<>|]{2,}"),
     "paths", "absolute home path (section 13)", home_path_is_real),
    (re.compile(
        r"(?:(?<![A-Za-z0-9_])[A-Za-z]:(?:\\+|/)[^\s`)\]\"'<>|]{2,}"
        r"|(?<![:/\\A-Za-z0-9_])(?:\\\\(?:<[^>]+>|\{[^}]+\}|[A-Za-z0-9.$%_-]+)\\+(?:<[^>]+>|\{[^}]+\}|[A-Za-z0-9$.%_-]+)(?:\\+[^\s`)\]\"'<>|]*)*"
        r"|//(?:<[^>]+>|\{[^}]+\}|[A-Za-z0-9$%_-]+)/(?:<[^>]+>|\{[^}]+\}|[A-Za-z0-9$.%_-]+)(?:/[^\s`)\]\"'<>|]*)*))"
     ),
     "paths", "Windows deployment path (section 13)", windows_path_is_real),
    (re.compile(r"\bgs://[^\s`)\]\"'<>]+"),
     "content", "non-placeholder bucket (section 13)", bucket_is_real),
    (re.compile(r"\b[\w-]+\.workers\.dev\b"),
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


def read_deployed_site_asset(root: Path, path: Path) -> tuple[str, str | None]:
    """Return ('text', str), ('unapproved_raster', str), ('skip', None), or ('unscanned_binary', None)."""
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


class _RenderedHTMLNormalizer(HTMLParser):
    def __init__(self, depth: int = 0) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = depth
        self.inline_parts: list[str] = []
        self.fused_parts: list[str] = []
        self.compact_parts: list[str] = []
        self.attr_lines: list[str] = []
        self.comment_lines: list[str] = []
        self.subtrees: list[str] = []
        self._tag_stack: list[tuple[str, bool]] = []
        self._raw_tag: str | None = None
        self._raw_chunks: list[str] = []

    @staticmethod
    def _has_inline_display(attrs: list[tuple[str, str | None]]) -> bool:
        for k, v in attrs:
            if k.lower() == "style" and v and INLINE_DISPLAY_RE.search(v):
                return True
        return False

    def _handle_attrs(self, attrs: list[tuple[str, str | None]]) -> None:
        for k, v in attrs:
            if not v:
                continue
            self.attr_lines.append(f"{k}={v}")
            if "%" in v:
                self.attr_lines.append(f"{k}={urllib.parse.unquote(v)}")
            if k.lower() == "srcdoc" and self.depth < 3:
                self.subtrees.append(normalize_html_text(v, self.depth + 1))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        is_block = (t in HTML_BLOCK_TAGS) and not self._has_inline_display(attrs)
        self._tag_stack.append((t, is_block))
        if is_block:
            self.inline_parts.append("\n")
        self._handle_attrs(attrs)
        if t in ("script", "style"):
            self._raw_tag = t
            self._raw_chunks = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if (t in HTML_BLOCK_TAGS) and not self._has_inline_display(attrs):
            self.inline_parts.append("\n")
        self._handle_attrs(attrs)

    def _flush_raw_tag(self, tag_name: str) -> None:
        raw_body = "".join(self._raw_chunks)
        if tag_name == "script":
            dec = unescape_js_literals(raw_body)
            self.subtrees.append(dec)
            if ("<" in dec or "&" in dec) and self.depth < 3:
                self.subtrees.append(normalize_html_text(dec, self.depth + 1))
        elif tag_name == "style":
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

    def handle_comment(self, data: str) -> None:
        self.comment_lines.append(html.unescape(data))


def normalize_html_text(text: str, depth: int = 0) -> str:
    """Canonicalize rendered HTML/SVG text, attributes, comments, and scripts."""
    parser = _RenderedHTMLNormalizer(depth=depth)
    parser.feed(text)
    parser.close()
    if parser._raw_tag is not None:
        parser._flush_raw_tag(parser._raw_tag)
    combined = "\n".join([
        "".join(parser.inline_parts),
        "".join(parser.fused_parts),
        "".join(parser.compact_parts),
        "\n".join(parser.attr_lines),
        "\n".join(parser.comment_lines),
        *parser.subtrees,
    ])
    return INVISIBLE_FORMAT_RE.sub("", combined)


def normalized_site_views(path: Path, text: str) -> list[str]:
    """Build raw and decoded/rendered views of a deployed site/ text asset."""
    views: list[str] = []

    def _add(candidate: str) -> None:
        if candidate and candidate not in views:
            views.append(candidate)

    _add(text)
    stripped = INVISIBLE_FORMAT_RE.sub("", text)
    _add(stripped)
    js_dec = INVISIBLE_FORMAT_RE.sub("", unescape_js_literals(text))
    _add(js_dec)
    suffix = path.suffix.lower()
    if suffix in (".css", ".html", ".htm", ".xhtml", ".svg"):
        _add(INVISIBLE_FORMAT_RE.sub("", unescape_css_literals(text)))
    if suffix in (".html", ".htm", ".xhtml", ".svg", ".xml") or "<" in js_dec or "&" in js_dec:
        _add(normalize_html_text(text))
        if js_dec != text:
            _add(normalize_html_text(js_dec))
    return views


def always_report(text: str, match: re.Match, ctx: FileContext) -> bool:
    return True


SITE_LEAK_PATTERNS = [
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
        re.compile(r"\barn:aws(?:-[a-z-]+)?:[a-z0-9-]+:[a-z0-9-]*:(\d{12}):[^\s`)\]\"'<>]+"),
        "publish",
        "account identifier (section 13)",
        arn_is_real,
    ),
    (
        re.compile(r"\b([a-z0-9][a-z0-9-]*)@([a-z0-9][a-z0-9-]*)\.iam\.gserviceaccount\.com\b"),
        "publish",
        "account identifier (section 13)",
        service_account_is_real,
    ),
    (
        re.compile(
            r"""(?i)\b(?:aws[-_]?account[-_]?id|account[-_]?id|tenant[-_]?id|subscription[-_]?id)\b"""
            r"""(?:\\?["'])?\s*[:=]\s*(?:\\?["'])?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d{12})(?:\\?["'])?(?![0-9a-f-])"""
        ),
        "publish",
        "account identifier (section 13)",
        account_field_is_real,
    ),
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
    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        markdown = is_markdown(path)
        if rel.startswith("site/"):
            seen_for_file: set[tuple[str, str]] = set()
            site_rel_path = "/" + rel[len("site/"):]
            path_views = [site_rel_path]
            if "%" in site_rel_path:
                decoded_rel_path = urllib.parse.unquote(site_rel_path)
                if decoded_rel_path != site_rel_path:
                    path_views.append(decoded_rel_path)
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
            elif status != "text" or site_text is None:
                continue
            patterns = list(LEAK_PATTERNS) if markdown else list(LEAK_PATTERNS[:4])
            patterns.extend(SITE_LEAK_PATTERNS)
            for view in normalized_site_views(path, site_text):
                prose = blank_fenced_blocks(view) if markdown else view
                masked = blank_code_spans(prose) if markdown else view
                ctx = FileContext(
                    url_spans=[(m.start(), m.end()) for m in URL_TOKEN.finditer(view)],
                    prose=prose,
                    masked=masked,
                )
                _scan_leak_patterns(rel, view, patterns, ctx, report, seen_for_file)
            continue
        elif markdown:
            text = path.read_text(encoding="utf-8", errors="ignore")
        else:
            continue
        prose = blank_fenced_blocks(text)
        masked = blank_code_spans(prose)
        ctx = FileContext(
            url_spans=[(m.start(), m.end()) for m in URL_TOKEN.finditer(text)],
            prose=prose,
            masked=masked,
        )
        _scan_leak_patterns(rel, text, list(LEAK_PATTERNS), ctx, report)


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
