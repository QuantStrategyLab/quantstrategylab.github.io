"""Regression tests for the QuantStrategyLab site publication and leak checker.

Run with `python scripts/test_site.py`.
"""

from __future__ import annotations

import importlib.util
import io
import re
import struct
import subprocess
import tempfile
import unittest
import zlib
from contextlib import redirect_stdout
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_site", Path(__file__).with_name("check_site.py")
)
check_site = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_site)

GITIGNORE_BLOCK = "\n".join(check_site.INTERNAL_NOTE_GITIGNORE) + "\n"
SHA = "8e8ec51884bf8abb0a7ca699fc2da39fad134f89"


def _png_chunk(ctype: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(ctype + data) & 0xFFFFFFFF
    return struct.pack(">I4s", len(data), ctype) + data + struct.pack(">I", crc)


def _make_png(*extra_chunks: bytes) -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + b"".join(extra_chunks)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def _make_ico(png_bytes: bytes) -> bytes:
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 1, 1, 0, 0, 1, 32, len(png_bytes), 22)
    return header + entry + png_bytes


class CheckerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.write("README.md", "# t\n")

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def git(self, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.root), *args], check=True, capture_output=True
        )

    def report(self, phase: int = 2) -> check_site.Report:
        return check_site.Report(check_site.PHASE_BLOCKING[phase])

    def messages(self, report: check_site.Report, category: str) -> list[str]:
        return [m for c, m in report.findings if c == category]

    def run_main(self, *extra: str) -> tuple[int, str]:
        with redirect_stdout(io.StringIO()) as captured:
            code = check_site.main(["--root", str(self.root), "--phase", "2", *extra])
        return code, captured.getvalue()


class LeakTest(CheckerTestCase):
    def findings(self, text: str) -> list[str]:
        self.write("docs/page.md", text)
        report = self.report()
        check_site.check_leaks(self.root, report)
        return [m for _, m in report.findings]

    def test_home_path_is_reported(self):
        found = self.findings("Config lives in `/Users/someone/projects/app`.\n")
        self.assertTrue(any("absolute home path" in m for m in found))

    def test_placeholder_bucket_is_not_reported(self):
        for text in (
            "Write to `gs://<bucket>/strategy-artifacts/x.csv`.\n",
            "The default is `gs://.../universe.csv`.\n",
            "bucket 一般是 `gs://run-sources-${PROJECT_ID}-${REGION}`\n",
            "Try `gs://your-bucket/path/to/signal.json`.\n",
            "Try `gs://example-bucket/releases/current`.\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.findings(text), [])

    def test_real_bucket_is_reported(self):
        found = self.findings("Default root `gs://acme-prod-inputs/research/v2/input/`.\n")
        self.assertTrue(any("non-placeholder bucket" in m for m in found))

    def test_placeholder_subdomain_is_not_reported(self):
        for text in (
            "Open https://YOUR_SUBDOMAIN.workers.dev/admin.\n",
            "Set the host to https://your-subdomain.workers.dev.\n",
            "The example uses https://xxx.workers.dev.\n",
            "Deploy to https://<subdomain>.workers.dev.\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.findings(text), [])

    def test_real_subdomain_is_reported(self):
        found = self.findings("Open https://ops-portal.workers.dev/status.\n")
        self.assertTrue(any("personal subdomain" in m for m in found))

    def test_fenced_real_subdomain_and_home_path_are_reported_while_placeholders_pass(self):
        self.assertEqual(
            self.findings(
                "```bash\ncurl https://YOUR_SUBDOMAIN.workers.dev\ncat /home/your-user/config\n```\n"
                "```bash\ncurl https://example-portal.workers.dev\n```\n"
            ),
            [],
        )
        sub_found = self.findings("```bash\ncurl https://ops-portal.workers.dev\n```\n")
        self.assertTrue(any("personal subdomain" in m for m in sub_found))
        path_found = self.findings("```bash\ncat /home/operator/prod/config\n```\n")
        self.assertTrue(any("absolute home path" in m for m in path_found))

    def test_windows_paths_are_reported_while_placeholders_pass(self):
        for clean in (
            r"Config lives in `C:\Users\your-user\config.yaml`." + "\n",
            r"Template path `C:\Users\<user>\config.yaml`." + "\n",
            r"Env path `C:\Users\%USERNAME%\config.yaml`." + "\n",
            r"Sample dir `C:\example\config.yaml`." + "\n",
            r"Share `\\<server>\<share>\config.yaml`." + "\n",
            r"Sample share `\\example-nas\share\config.yaml`." + "\n",
        ):
            with self.subTest(clean=clean):
                self.assertEqual(self.findings(clean), [])
        for dirty in (
            r"Leaked `C:\Users\operator\prod\config.yaml`." + "\n",
            r"Leaked `D:\deploy\example\secrets.yaml`." + "\n",
            r"Share `\\corp-files\ops\config.yaml`." + "\n",
            "Posix UNC `//corp-files/ops/config.yaml`.\n",
        ):
            with self.subTest(dirty=dirty):
                found = self.findings(dirty)
                self.assertTrue(any("Windows deployment path" in m for m in found), found)

    def test_deployed_site_text_assets_are_scanned_for_identifier_leaks(self):
        repo_root = Path(check_site.__file__).resolve().parent.parent
        clean_png = _make_png()
        approved_inline_svg = re.search(
            r"<svg\b.*?</svg>",
            (repo_root / "site/index.html").read_text(encoding="utf-8"),
            re.S,
        )
        assert approved_inline_svg is not None
        self.write(
            "site/index.html",
            '<link rel="stylesheet" href="assets/styles.css">\n'
            '<script src="assets/i18n.js" defer></script>\n'
            '<script src="assets/app.js" defer></script>\n'
            f"{approved_inline_svg.group(0)}\n"
            '<a href="https://YOUR_SUBDOMAIN.workers.dev">docs</a>\n'
            "<p>Visit QuantStrategyLab.</p>\n"
            "<p>Public architecture notes.</p>\n",
        )
        self.write(
            "site/assets/styles.css",
            "a::before { content: ''; }\n"
            r"/* example 192.0.2.1 2001:db8::1 your-host.internal arn:aws:iam::000000000000:role/example your-sa@example.iam.gserviceaccount.com C:\Users\your-user\config.yaml \\example-nas\share\cfg.yaml */"
            "\n",
        )
        self.write("site/clean.json", '{"account_id": "000000000000"}\n')
        self.write("site/YOUR_SUBDOMAIN.workers.dev/index.html", "<p>placeholder path</p>\n")
        (self.root / "site/landing-light-192.png").write_bytes((repo_root / "site/landing-light-192.png").read_bytes())
        (self.root / "site/landing-light.svg").write_bytes((repo_root / "site/landing-light.svg").read_bytes())
        (self.root / "site/favicon.ico").write_bytes((repo_root / "site/favicon.ico").read_bytes())
        (self.root / "site/clean-extra.png").write_bytes(clean_png)
        (self.root / "site/clean-extra.ico").write_bytes(_make_ico(clean_png))
        (self.root / "site/assets").mkdir(parents=True, exist_ok=True)
        (self.root / "site/assets/app.js").write_bytes((repo_root / "site/assets/app.js").read_bytes())
        (self.root / "site/assets/i18n.js").write_bytes((repo_root / "site/assets/i18n.js").read_bytes())
        self.write("site/unused.css", "p { display: none; }\n")

        clean_report = self.report()
        check_site.check_leaks(self.root, clean_report)
        self.assertEqual(clean_report.findings, [])

        self.write(
            "site/runtime-config.yaml",
            "config_dir: /home/operator/prod/config\n"
            "endpoint: https://actual-private-app.workers.dev\n"
            "db_host: db-primary.ops.internal\n"
            "role: arn:aws:iam::123456789012:role/site-publisher\n"
            "sa: deployer@quant-prod-42.iam.gserviceaccount.com\n"
            "account_id: '123456789012'\n"
            r"win_cfg: 'C:\Users\operator\prod\config.yaml'" + "\n"
            r"unc_cfg: '\\corp-files\ops\config.yaml'" + "\n",
        )
        self.write(
            "site/runtime-config.json",
            '{"account_id": "123456789012", "tenantId": "12345678-1234-1234-1234-1234567890ab"}\n',
        )
        self.write(
            "site/rendered-leak.html",
            "<p>&#47;home&#47;<strong>operator</strong>&#47;prod&#47;config and "
            "db-primary&#46;<span>ops</span>&#46;internal</p>"
            '<a href="https:&#47;&#47;actual-private-app&#46;workers&#46;dev">x</a>\n',
        )
        self.write(
            "site/html-concat-leak.html",
            "<span>/home/</span><div>operator</div><span>/prod/config</span>"
            "<div>\n  db-primary.\n  ops.internal\n</div>\n",
        )
        self.write(
            "site/escaped-leak.js",
            'const p = "\\u002fhome\\u002foperator\\u002fprod\\u002fconfig";\n',
        )
        self.write("site/indirect.js", 'const p = ["/U", "sers/", "bob"].join("");\n')
        self.write("site/inline-js.html", '<script>const p = ["/U", "sers/", "bob"].join("");</script>\n')
        self.write(
            "site/self-closing-script.html",
            "<script/>const p = String.fromCharCode.apply(null, [47,104,111,109,101,47,111,112,101,114,97,116,111,114]);</script>\n",
        )
        self.write("site/data-uri.html", '<img src="data:image/png;base64,iVBORw0KGgo=">\n')
        self.write("site/actual-private-app.workers.dev/index.html", "<p>benign page content</p>\n")
        self.write("site/db-primary.ops.internal/cfg.html", "<p>benign internal path</p>\n")
        self.write("site/assets/app.js.map", '{"sourceRoot":"gs://actual-prod-bucket/maps"}\n')
        self.write(
            "site/dist/runtime-config.json",
            '{"path":"/home/operator/prod/config","url":"https://actual-private-app.workers.dev"}\n',
        )
        self.write("site/build/audit.md", "# Build audit\n")
        self.write("site/docs/acceptance-policy.md", "# Copied acceptance policy\n")
        self.write(
            "site/private-ip.html",
            "<!-- internal: http://10.23.45.67:8080, v6: http://[fd12:3456:789a::1]/api, meta: 169.254.169.254, ll: fe80::1 -->\n",
        )
        self.write(
            "site/mixed-case.json",
            '{"url": "HTTPS://REAL-LEAK.WORKERS.DEV", "bucket": "GS://CORP-QUANT-BUCKET", '
            '"arn": "ARN:AWS:IAM::123456789012:ROLE/OPS", '
            '"sa": "DEPLOY@CORP-QUANT-PROD.IAM.GSERVICEACCOUNT.COM"}\n',
        )
        self.write(
            "site/percent-config.json",
            '{"config":"%2Fhome%2Foperator%2Fprod%2Fconfig","url":"https%3A%2F%2Factual-private-app.workers.dev"}\n',
        )
        self.write("site/bad-handler.html", '<img src="landing-light-192.png" onclick="evil()"><a href="javascript:evil()">x</a>\n')
        self.write("site/dup-script-src.html", '<script src="https&#58;//evil.invalid/p.js" src="assets/app.js"></script>\n')
        (self.root / "site/release.pdf").write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n")
        (self.root / "site/bundle.zip").write_bytes(b"PK\x03\x04\x00\x00payload")

        dirty_report = self.report()
        check_site.check_leaks(self.root, dirty_report)
        check_site.check_internal_paths(self.root, dirty_report)
        msgs = [m for _, m in dirty_report.findings]
        self.assertTrue(any("site/runtime-config.yaml" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/runtime-config.yaml" in m and "personal subdomain" in m for m in msgs))
        self.assertTrue(any("site/assets/app.js.map" in m and "non-placeholder bucket" in m for m in msgs))
        self.assertTrue(any("site/dist/runtime-config.json" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/dist/runtime-config.json" in m and "personal subdomain" in m for m in msgs))
        self.assertTrue(any("site/build/audit.md" in m and "tracked internal note" in m for m in msgs))
        self.assertTrue(any("site/docs/acceptance-policy.md" in m and "tracked internal note" in m for m in msgs))
        self.assertTrue(any("site/private-ip.html" in m and "private IPv4 address" in m and "10.23.45.67" in m for m in msgs))
        self.assertTrue(any("site/private-ip.html" in m and "private IPv4 address" in m and "169.254.169.254" in m for m in msgs))
        self.assertTrue(any("site/private-ip.html" in m and "private IPv6 address" in m and "fd12:3456:789a::1" in m for m in msgs))
        self.assertTrue(any("site/private-ip.html" in m and "private IPv6 address" in m and "fe80::1" in m for m in msgs))
        self.assertEqual(sum(1 for m in msgs if "site/runtime-config.yaml" in m and "Windows deployment path" in m), 2)
        self.assertTrue(any("site/release.pdf" in m and "unscanned binary or encrypted asset" in m for m in msgs))
        self.assertTrue(any("site/bundle.zip" in m and "unscanned binary or encrypted asset" in m for m in msgs))
        self.assertTrue(any("site/runtime-config.yaml" in m and "internal hostname" in m for m in msgs))
        self.assertEqual(sum(1 for m in msgs if "site/runtime-config.yaml" in m and "account identifier" in m), 3)
        self.assertEqual(sum(1 for m in msgs if "site/runtime-config.json" in m and "account identifier" in m), 2)
        self.assertTrue(any("site/rendered-leak.html" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/rendered-leak.html" in m and "internal hostname" in m for m in msgs))
        self.assertTrue(any("site/rendered-leak.html" in m and "personal subdomain" in m for m in msgs))
        self.assertTrue(any("site/html-concat-leak.html" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/html-concat-leak.html" in m and "internal hostname" in m for m in msgs))
        self.assertTrue(any("site/escaped-leak.js" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/indirect.js" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/inline-js.html" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/self-closing-script.html" in m and "self-closing script or style tag" in m for m in msgs))
        self.assertTrue(any("site/self-closing-script.html" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/data-uri.html" in m and "embedded data URI asset" in m for m in msgs))
        self.assertTrue(any("site/actual-private-app.workers.dev/index.html" in m and "personal subdomain" in m for m in msgs))
        self.assertTrue(any("site/db-primary.ops.internal/cfg.html" in m and "internal hostname" in m for m in msgs))
        self.assertTrue(any("site/mixed-case.json" in m and "personal subdomain" in m for m in msgs))
        self.assertTrue(any("site/mixed-case.json" in m and "non-placeholder bucket" in m for m in msgs))
        self.assertTrue(any("site/mixed-case.json" in m and "account identifier" in m and "ARN:AWS:" in m for m in msgs))
        self.assertTrue(any("site/mixed-case.json" in m and "account identifier" in m and "DEPLOY@CORP-QUANT-PROD" in m for m in msgs))
        self.assertTrue(any("site/percent-config.json" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/percent-config.json" in m and "personal subdomain" in m for m in msgs))
        self.assertTrue(any("site/bad-handler.html" in m and "inline event handler attribute" in m for m in msgs))
        self.assertTrue(any("site/bad-handler.html" in m and "javascript: or vbscript: URI" in m for m in msgs))
        self.assertTrue(any("site/dup-script-src.html" in m and "duplicate HTML attribute in site/ (src)" in m for m in msgs))
        self.assertTrue(any("site/dup-script-src.html" in m and "remote or escaping script asset in site/" in m for m in msgs))

    def test_png_structure_and_metadata_chunks_are_enforced(self):
        repo_root = Path(check_site.__file__).resolve().parent.parent

        approved_bytes = (repo_root / "site/landing-light-512.png").read_bytes()
        pos = 8
        tampered = bytearray(b"\x89PNG\r\n\x1a\n")
        while pos < len(approved_bytes):
            clen, ctype = struct.unpack(">I4s", approved_bytes[pos:pos + 8])
            cdata = approved_bytes[pos + 8:pos + 8 + clen]
            if ctype == b"IDAT":
                cdata = cdata + b"/home/operator/prod/config db-primary.ops.internal"
            tampered.extend(_png_chunk(ctype, cdata))
            pos += 12 + clen
        (self.root / "site").mkdir(parents=True, exist_ok=True)
        (self.root / "site/tampered-idat.png").write_bytes(bytes(tampered))

        iend_src = (repo_root / "site/landing-light-apple-touch-180.png").read_bytes()
        iend_out = bytearray(b"\x89PNG\r\n\x1a\n")
        ipos = 8
        while ipos < len(iend_src):
            clen, ctype = struct.unpack(">I4s", iend_src[ipos:ipos + 8])
            cdata = iend_src[ipos + 8:ipos + 8 + clen]
            if ctype == b"IEND":
                cdata = b"/home/operator/prod/config actual-private-app.workers.dev"
            iend_out.extend(_png_chunk(ctype, cdata))
            ipos += 12 + clen
        (self.root / "site/nonempty-iend.png").write_bytes(bytes(iend_out))

        (self.root / "site/corrupt.png").write_bytes(b"not a real png\x00")
        (self.root / "site/leak-meta.png").write_bytes(
            _make_png(
                _png_chunk(b"tEXt", b"Comment\x00deploy /home/operator/prod/config http://10.23.45.67"),
                _png_chunk(b"zTXt", b"Host\x00\x00" + zlib.compress(b"https://actual-private-app.workers.dev")),
            )
        )
        (self.root / "site/leak-itxt.png").write_bytes(
            _make_png(
                _png_chunk(b"iTXt", b"Description\x00\x01\x00en\x00\x00" + zlib.compress(b"gs://actual-prod-bucket/img")),
            )
        )
        (self.root / "site/benign-meta.png").write_bytes(
            _make_png(_png_chunk(b"tEXt", b"Software\x00Builder"))
        )
        (self.root / "site/ico-with-meta.ico").write_bytes(
            _make_ico(_make_png(_png_chunk(b"tEXt", b"Author\x00/home/operator/secret")))
        )
        ihdr_interlaced = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 1)
        (self.root / "site/interlaced-valid.png").write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", ihdr_interlaced)
            + _png_chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
            + _png_chunk(b"IEND", b"")
        )
        (self.root / "site/interlaced-smuggled.png").write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", ihdr_interlaced)
            + _png_chunk(b"IDAT", zlib.compress(b"/home/operator/prod/config"))
            + _png_chunk(b"IEND", b"")
        )
        (self.root / "site/interlaced-bad-filter.png").write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", ihdr_interlaced)
            + _png_chunk(b"IDAT", zlib.compress(b"\x09\xff\x00\x00"))
            + _png_chunk(b"IEND", b"")
        )
        (self.root / "site/valid-ancillary.png").write_bytes(
            _make_png(
                _png_chunk(b"sRGB", b"\x00"),
                _png_chunk(b"pHYs", struct.pack(">IIB", 2835, 2835, 1)),
            )
        )
        (self.root / "site/smuggled-phys.png").write_bytes(
            _make_png(_png_chunk(b"pHYs", b"/home/operator/prod/config"))
        )

        report = self.report()
        check_site.check_leaks(self.root, report)
        msgs = [m for _, m in report.findings]
        self.assertTrue(any("site/tampered-idat.png" in m and "unscanned binary or encrypted asset" in m for m in msgs))
        self.assertTrue(any("site/nonempty-iend.png" in m and "unscanned binary or encrypted asset" in m for m in msgs))
        self.assertTrue(any("site/corrupt.png" in m and "unscanned binary or encrypted asset" in m for m in msgs))
        self.assertFalse(any("site/interlaced-valid.png" in m for m in msgs), msgs)
        self.assertTrue(any("site/interlaced-smuggled.png" in m and "unscanned binary or encrypted asset" in m for m in msgs))
        self.assertTrue(any("site/interlaced-bad-filter.png" in m and "unscanned binary or encrypted asset" in m for m in msgs))
        self.assertFalse(any("site/valid-ancillary.png" in m for m in msgs), msgs)
        self.assertTrue(any("site/smuggled-phys.png" in m and "unscanned binary or encrypted asset" in m for m in msgs))
        self.assertTrue(any("site/leak-meta.png" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/leak-meta.png" in m and "private IPv4 address" in m for m in msgs))
        self.assertTrue(any("site/leak-meta.png" in m and "personal subdomain" in m for m in msgs))
        self.assertTrue(any("site/leak-meta.png" in m and "PNG ancillary text metadata chunk" in m for m in msgs))
        self.assertTrue(any("site/leak-itxt.png" in m and "PNG ancillary text metadata chunk" in m for m in msgs))
        self.assertTrue(any("site/leak-itxt.png" in m and "non-placeholder bucket" in m for m in msgs))
        self.assertTrue(any("site/benign-meta.png" in m and "PNG ancillary text metadata chunk" in m for m in msgs))
        self.assertTrue(any("site/ico-with-meta.ico" in m and "PNG ancillary text metadata chunk" in m for m in msgs))
        self.assertTrue(any("site/ico-with-meta.ico" in m and "absolute home path" in m for m in msgs))

    def test_site_links_and_naming_are_checked(self):
        self.write(
            "site/index.html",
            '<link rel="stylesheet" href="assets/missing.css">\n'
            '<script src="assets/missing.js"></script>\n'
            '<img src="missing.png">\n'
            '<a href="#missing-id">jump</a>\n'
            '<a href="missing-page.html">page</a>\n',
        )
        self.write(
            "site/assets/styles.css",
            '@import "https://cdn.example.invalid/x.css";\n'
            'body { background: url("missing-bg.png"); }\n',
        )
        self.write(
            "site/manifest.webmanifest",
            '{"icons": [{"src": "/missing-icon.png"}]}\n',
        )
        self.write("site/bad name.txt", "hello\n")

        report = self.report()
        check_site.check_leaks(self.root, report)
        links = self.messages(report, "links")
        publish = self.messages(report, "publish")
        naming = self.messages(report, "naming")
        self.assertTrue(any("assets/missing.css" in m for m in links), links)
        self.assertTrue(any("assets/missing.js" in m for m in links), links)
        self.assertTrue(any("missing.png" in m for m in links), links)
        self.assertTrue(any("#missing-id" in m for m in links), links)
        self.assertTrue(any("missing-page.html" in m for m in links), links)
        self.assertTrue(any("missing-bg.png" in m for m in links), links)
        self.assertTrue(any("/missing-icon.png" in m for m in links), links)
        self.assertTrue(any("CSS @import external stylesheet" in m for m in publish), publish)
        self.assertTrue(any("site/bad name.txt" in m and "space" in m for m in naming), naming)

    def test_inline_style_urls_and_empty_fragments(self):
        self.write("site/product-details.html", '<h1 id="产品">Details</h1>\n')
        self.write(
            "site/nested/index.html",
            '<a href="../">Root</a><a href="?lang=en">English</a>'
            '<a href="../product%2Ddetails.html#%E4%BA%A7%E5%93%81">Details</a>\n',
        )
        self.write(
            "site/index.html",
            '<div id="产品" style="border-bottom:0">'
            '<a name="details"></a>'
            '<a href="#details">Details</a>'
            '<a href="#">Back to top</a>'
            '<a href="./">Self</a>'
            '<a href="/#">Home</a>'
            '<a href="?lang=en">English</a>'
            '<a href="#%E4%BA%A7%E5%93%81">产品</a>'
            '<a href="product%2Ddetails.html">Product</a>'
            "</div>\n",
        )
        (self.root / "site/ok.png").write_bytes(_make_png())
        self.write(
            "site/ok-imageset.css",
            'p { background-image: image-set(url("ok.png") type("image/png") 1x); }\n',
        )
        clean = self.report()
        check_site.check_leaks(self.root, clean)
        self.assertEqual(clean.findings, [])

        self.write(
            "site/inline-style-leak.html",
            '<div style="background-image:url(https://db-primary&#92;2e ops&#92;2e internal/x.png)">x</div>\n'
            '<a href="#missing-id">jump</a>\n'
            '<a href="?lang=en#missing-id">query-missing</a>\n'
            '<a href="../outside.html">escape</a>\n',
        )
        self.write(
            "site/picture-remote.html",
            '<picture><source srcset="https://cdn.example.com/hero.webp">'
            '<img src="landing-light-192.png"></picture>\n',
        )
        self.write(
            "site/base-hijack.html",
            '<base href="https://cdn.example.com/">\n'
            '<script src="assets/app.js"></script>\n',
        )
        self.write("site/assets/app.js", "console.log('ok');\n")
        (self.root / "site/landing-light-192.png").write_bytes(_make_png())
        dirty = self.report()
        check_site.check_leaks(self.root, dirty)
        publish = self.messages(dirty, "publish")
        links = self.messages(dirty, "links")
        self.assertTrue(any("remote or inline-scheme CSS url() resource" in m for m in publish), publish)
        self.assertTrue(any("internal hostname" in m for m in publish), publish)
        self.assertTrue(any("site/picture-remote.html" in m and "remote or escaping img asset" in m for m in publish), publish)
        self.assertTrue(any("site/base-hijack.html" in m and "HTML base href element in site/" in m for m in publish), publish)
        self.assertTrue(any("broken fragment link -> #missing-id" in m for m in links), links)
        self.assertTrue(any("broken fragment link -> ?lang=en#missing-id" in m for m in links), links)
        self.assertTrue(any("broken relative link -> ../outside.html" in m for m in links), links)

    def test_implicit_top_fragment_and_autoloading_resources_and_hidden_css(self):
        self.write(
            "site/index.html",
            '<a href="#top">Top</a>'
            '<a href="#TOP">TOP</a>'
            '<a href="?lang=en#Top">Query Top</a>'
            '<a href="/#top">Root Top</a>'
            '<a href="./#TOP">Dot Top</a>'
            '<a href="index.html#top">Index Top</a>'
            '<p id="details">Product details</p>'
            '<a href="#details:~:text=Product">Text Fragment</a>'
            '<a href="#:~:text=Product">Directive Only</a>'
            '<a href="#det\tails">Tab Fragment</a>'
            '<a href="in\ndex.html">Newline Path</a>'
            '<a href="sms:+15555550100">SMS</a>'
            '<a href="geo:37.786971,-122.399677">Map</a>'
            '<iframe srcdoc="&lt;p id=inner&gt;x&lt;/p&gt;&lt;a href=#inner&gt;go&lt;/a&gt;"></iframe>'
            '<img srcset="ok.png?variant=a,b 1x">\n',
        )
        (self.root / "site/ok.png").write_bytes(_make_png())
        (self.root / "site/ok(1).png").write_bytes(_make_png())
        self.write(
            "site/ok-imageset.css",
            'p { background-image: image-set(url("ok.png") type("image/png") 1x); }\n'
            'div { background-image: url("ok(1).png"); }\n',
        )
        clean = self.report()
        check_site.check_leaks(self.root, clean)
        self.assertEqual(clean.findings, [])

        self.write(
            "site/autoload-remote.html",
            '<iframe src="https://cdn.example.com/frame.html"></iframe>\n'
            '<frameset><frame src="https://collector.invalid/remote"></frameset>\n'
            '<object data="https://cdn.example.com/obj.swf"></object>\n'
            '<embed src="https://cdn.example.com/emb.swf">\n'
            '<audio src="https://cdn.example.com/a.mp3"></audio>\n'
            '<video src="https://cdn.example.com/v.mp4" poster="missing-poster.png"></video>\n'
            '<input type="image" src="missing-btn.png">\n'
            '<link rel="preload" as="script" href="https://cdn.example.com/pre.js">\n'
            '<meta http-equiv="refresh" content="0;url=https://cdn.example.com/redir">\n'
            '<meta http-equiv="refresh" content="0; https://collector.invalid/replaced">\n'
            '<image src="https://cdn.example.com/legacy.png">\n',
        )
        self.write(
            "site/autoload-js-refresh.html",
            '<meta http-equiv="refresh" content="0;url=javascript:alert(1)">\n',
        )
        self.write(
            "site/decoy-hidden.html",
            '<style>.mask{display:none}</style>\n'
            '<span style="visibility:hidden">a</span>\n'
            '<span style="opacity: 0">b</span>\n'
            '<span hidden>c</span>\n',
        )
        self.write(
            "site/srcdoc-remote.html",
            '<iframe srcdoc="&lt;script src=&quot;https://cdn.example.com/x.js&quot;&gt;&lt;/script&gt;"></iframe>\n',
        )
        self.write(
            "site/foreign-remote.svg",
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<foreignObject width="100" height="100">'
            '<img xmlns="http://www.w3.org/1999/xhtml" src="https://cdn.example.com/x.png" />'
            '</foreignObject>'
            '<image href="https://cdn.example.com/y.png" />'
            '<rect fill="url(https://collector.invalid/paint.svg#p)" />'
            '<script href="https://cdn.example.com/x.js"></script>'
            '</svg>\n',
        )
        self.write(
            "site/css-escapes-and-imageset.css",
            'p::after { content: "db-primary.ops.in\\ternal"; }\n'
            'p::before { content: "/home/" "operator/prod/config"; }\n'
            'p { background-image: image-set("https://cdn.example.com/x.png" 1x, "missing-set.png" 2x); }\n',
        )
        self.write(
            "site/entity-smuggle.svg",
            '<!DOCTYPE svg [<!ENTITY home "/home/">]><svg xmlns="http://www.w3.org/2000/svg"><text>&home;</text></svg>\n',
        )
        self.write(
            "site/ns-and-xmlbase.svg",
            '<s:svg xmlns:s="http://www.w3.org/2000/svg" xml:base="https://cdn.example.com/">'
            '<style>rect { fill: u&#114;l(https://cdn.example.com/charref.svg#p); }</style>'
            '<s:script href="https://cdn.example.com/x.js"></s:script></s:svg>\n',
        )
        dirty = self.report()
        check_site.check_leaks(self.root, dirty)
        publish = self.messages(dirty, "publish")
        links = self.messages(dirty, "links")
        for kind in ("iframe", "frame", "object", "embed", "audio", "video", "link", "meta", "script", "img"):
            self.assertTrue(
                any(f"remote or escaping {kind} asset" in m for m in publish),
                (kind, publish),
            )
        self.assertTrue(
            any("site/srcdoc-remote.html" in m and "remote or escaping script asset" in m for m in publish),
            publish,
        )
        self.assertTrue(
            any("site/foreign-remote.svg" in m and "https://cdn.example.com/x.png" in m for m in publish),
            publish,
        )
        self.assertTrue(
            any("site/foreign-remote.svg" in m and "https://cdn.example.com/y.png" in m for m in publish),
            publish,
        )
        self.assertTrue(
            any("site/foreign-remote.svg" in m and "https://cdn.example.com/x.js" in m for m in publish),
            publish,
        )
        self.assertTrue(
            any("site/foreign-remote.svg" in m and "https://collector.invalid/paint.svg#" in m for m in publish),
            publish,
        )
        self.assertTrue(
            any("site/css-escapes-and-imageset.css" in m and "internal hostname" in m for m in publish),
            publish,
        )
        self.assertTrue(
            any("site/css-escapes-and-imageset.css" in m and "absolute home path" in m for _, m in dirty.findings),
            dirty.findings,
        )
        self.assertTrue(
            any("site/entity-smuggle.svg" in m and "custom XML entity" in m for m in publish),
            publish,
        )
        self.assertTrue(
            any("site/ns-and-xmlbase.svg" in m and "XML base attribute in site/" in m for m in publish),
            publish,
        )
        self.assertTrue(
            any("site/ns-and-xmlbase.svg" in m and "remote or escaping script asset" in m for m in publish),
            publish,
        )
        self.assertTrue(
            any("site/ns-and-xmlbase.svg" in m and "https://cdn.example.com/charref.svg#" in m for m in publish),
            publish,
        )
        self.assertTrue(
            any("site/css-escapes-and-imageset.css" in m and "https://cdn.example.com/x.png" in m for m in publish),
            publish,
        )
        self.assertTrue(
            any("site/css-escapes-and-imageset.css" in m and "missing-set.png" in m for m in links),
            links,
        )
        self.assertTrue(
            any("site/autoload-remote.html" in m and "https://collector.invalid/replaced" in m for m in publish),
            publish,
        )
        self.assertTrue(
            any("site/autoload-remote.html" in m and "https://cdn.example.com/legacy.png" in m for m in publish),
            publish,
        )
        self.assertTrue(any("javascript: or vbscript: URI attribute" in m for m in publish), publish)
        self.assertTrue(any("broken local video link -> missing-poster.png" in m for m in links), links)
        self.assertTrue(any("broken local input link -> missing-btn.png" in m for m in links), links)
        self.assertTrue(any("hidden CSS text rule in HTML site/ asset" in m for m in publish), publish)
        self.assertTrue(any("hidden HTML attribute in site/" in m for m in publish), publish)

        policy_path = Path(__file__).resolve().parents[1] / ".github" / "governance" / "policy.json"
        import json
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        for pattern in (
            "site/**/*.js",
            "site/**/*.mjs",
            "site/**/*.cjs",
            "site/**/*.css",
            "site/**/*.png",
            "site/**/*.ico",
        ):
            self.assertIn(pattern, policy["r2_paths"])

    def test_tracked_workflow_and_config_files_scan_identifiers_with_placeholder_exemptions(self):
        self.write(
            ".github/workflows/ci.yml",
            "env:\n"
            "  CONFIG: /home/<user>/cfg\n"
            '  ACCOUNT_ID: "000000000000"\n'
            "  BUCKET: gs://<bucket>/artifacts\n"
            "  HOST: ${{ vars.DEPLOY_HOST }}\n",
        )
        clean = self.report()
        check_site.check_leaks(self.root, clean)
        self.assertEqual(clean.findings, [])

        self.write(
            ".github/workflows/review-check.yml",
            "env:\n"
            "  CONFIG: /home/operator/prod/config\n"
            '  ACCOUNT_ID: "123456789012"\n'
            "  BUCKET: gs://corp-quant-bucket\n"
            "  HOST: db-primary.ops.internal\n",
        )
        dirty = self.report()
        check_site.check_leaks(self.root, dirty)
        msgs = [f"{cat}: {detail}" for cat, detail in dirty.findings]
        self.assertTrue(any("review-check.yml" in m and "absolute home path" in m for m in msgs), msgs)
        self.assertTrue(any("review-check.yml" in m and "account identifier" in m for m in msgs), msgs)
        self.assertTrue(any("review-check.yml" in m and "non-placeholder bucket" in m for m in msgs), msgs)
        self.assertTrue(any("review-check.yml" in m and "internal hostname" in m for m in msgs), msgs)

    def test_public_markdown_scans_account_and_internal_host_identifiers(self):
        self.write(
            "README.md",
            '```json\n{"account_id": "000000000000", "host": "your-host.internal", '
            '"arn": "arn:aws:iam::000000000000:role/example", "sa": "your-sa@example.iam.gserviceaccount.com"}\n```\n',
        )
        clean = self.report()
        check_site.check_leaks(self.root, clean)
        self.assertEqual(clean.findings, [])

        self.write(
            "README.md",
            '```json\n{"account_id": "123456789012", "host": "db-primary.ops.internal", "ip": "10.23.45.67"}\n```\n',
        )
        dirty = self.report()
        check_site.check_leaks(self.root, dirty)
        msgs = self.messages(dirty, "publish")
        self.assertTrue(any("account identifier" in m for m in msgs), msgs)
        self.assertTrue(any("internal hostname" in m for m in msgs), msgs)
        self.assertTrue(any("private IPv4 address" in m for m in msgs), msgs)

    def test_sha_in_url_is_not_reported(self):
        text = (
            "- [Store](https://github.com/QuantStrategyLab/QuantPlatformKit/blob/"
            f"{SHA}/src/store.py)\n"
        )
        self.assertEqual(self.findings(text), [])

    def test_sha_in_code_span_is_not_reported(self):
        self.assertEqual(self.findings(f"Pinned at `{SHA}`.\n"), [])

    def test_sha_in_fenced_block_is_not_reported(self):
        text = f'```json\n{{"config_revision": "{SHA}"}}\n```\n'
        self.assertEqual(self.findings(text), [])

    def test_sha_in_link_label_is_not_reported(self):
        text = f"[{SHA}](https://github.com/QuantStrategyLab/x/commit/{SHA})\n"
        self.assertEqual(self.findings(text), [])

    def test_repeated_character_placeholder_is_not_reported(self):
        self.assertEqual(self.findings(f"`{'0' * 40}`\n"), [])

    def test_bare_sha_in_prose_is_reported(self):
        found = self.findings(f"Merged from PR #712 (head {SHA}, open).\n")
        self.assertTrue(any("40-character hex string in prose" in m for m in found))


class InternalNoteTest(CheckerTestCase):
    def test_missing_gitignore_entries_are_hygiene(self):
        report = self.report()
        check_site.check_internal_paths(self.root, report)
        found = self.messages(report, "hygiene")
        self.assertEqual(len(found), 1)
        self.assertIn("docs/audits/", found[0])

    def test_complete_gitignore_passes(self):
        self.write(".gitignore", GITIGNORE_BLOCK)
        report = self.report()
        check_site.check_internal_paths(self.root, report)
        self.assertEqual(self.messages(report, "hygiene"), [])

    def test_hygiene_blocks_in_phase_one(self):
        report = self.report(phase=1)
        check_site.check_internal_paths(self.root, report)
        self.assertEqual(len(report.blocking_findings()), 1)

    def test_audit_directory_is_reported(self):
        self.write(".gitignore", GITIGNORE_BLOCK)
        self.write("docs/audits/2026-10-30-review.md", "# x\n")
        report = self.report()
        check_site.check_internal_paths(self.root, report)
        self.assertTrue(any("plan/handoff directory" in m for m in self.messages(report, "content")))

    def test_changes_directory_and_obsolete_engineering_rule_are_reported(self):
        self.write(".gitignore", GITIGNORE_BLOCK + "!.github/engineering.md\n")
        self.write("docs/changes/task/change-card.md", "# x\n")
        report = self.report()
        check_site.check_internal_paths(self.root, report)
        self.assertTrue(any("engineering.md" in m for m in self.messages(report, "hygiene")))
        self.assertTrue(any("plan/handoff directory" in m for m in self.messages(report, "content")))

    def test_acceptance_policy_blocks_public_only(self):
        self.write(".gitignore", GITIGNORE_BLOCK)
        self.write("docs/acceptance-policy.md", "# policy\n")
        pub = self.report(phase=2)
        check_site.check_internal_paths(self.root, pub)
        self.assertTrue(any(cat == "publish" for cat, _ in pub.blocking_findings()))
        _, output = self.run_main("--visibility", "private")
        self.assertTrue(
            any(line.startswith("NOTE") and "acceptance-policy.md" in line for line in output.splitlines())
        )


class PhaseTest(CheckerTestCase):
    def test_phase_one_does_not_block_content(self):
        self.write("docs/release.md", "Default `gs://acme-prod-inputs/x.csv`.\n")
        report = self.report(phase=1)
        check_site.check_leaks(self.root, report)
        self.assertTrue(report.findings)
        self.assertEqual(report.blocking_findings(), [])

    def test_phase_two_blocks_content(self):
        self.write("docs/release.md", "Default `gs://acme-prod-inputs/x.csv`.\n")
        report = self.report(phase=2)
        check_site.check_leaks(self.root, report)
        self.assertTrue(report.blocking_findings())


class AdvisoryModeTest(CheckerTestCase):
    def test_advisory_reports_the_findings_it_would_have_blocked_on(self):
        self.write("docs/release.md", "Default `gs://acme-prod-inputs/x.csv`.\n")
        code, output = self.run_main("--advisory")
        self.assertEqual(code, 0)
        self.assertIn("non-placeholder bucket", output)
        self.assertIn("advisory run", output)

    def test_without_advisory_the_same_findings_still_fail(self):
        self.write("docs/release.md", "Default `gs://acme-prod-inputs/x.csv`.\n")
        code, _ = self.run_main()
        self.assertEqual(code, 1)


class VisibilityTest(CheckerTestCase):
    def deploy_doc(self) -> None:
        self.write(
            "docs/deployment.md",
            "Endpoint: https://billing.ops-portal.workers.dev/v1/health\n"
            "Data lives in /home/ubuntu/app/data.\n",
        )

    def test_public_repository_blocks_published_identifiers(self):
        self.deploy_doc()
        _, output = self.run_main("--visibility", "public")
        self.assertTrue(
            any(line.startswith("ERROR") and "personal subdomain" in line
                for line in output.splitlines())
        )

    def test_private_repository_reports_them_without_blocking(self):
        self.deploy_doc()
        _, output = self.run_main("--visibility", "private")
        self.assertFalse(
            any(line.startswith("ERROR") and "personal subdomain" in line
                for line in output.splitlines())
        )
        self.assertTrue(
            any(line.startswith("NOTE") and "personal subdomain" in line
                for line in output.splitlines())
        )
        self.assertIn("private repository", output)

    def test_the_default_is_public(self):
        self.deploy_doc()
        _, output = self.run_main()
        self.assertIn("(public)", output)
        self.assertTrue(
            any(line.startswith("ERROR") and "personal subdomain" in line
                for line in output.splitlines())
        )

    def test_private_still_blocks_missing_internal_gitignore_rules(self):
        _, output = self.run_main("--visibility", "private")
        self.assertTrue(
            any(line.startswith("ERROR") and "internal note paths not ignored" in line
                for line in output.splitlines())
        )


class GitVisibilityTest(CheckerTestCase):
    def test_gitignored_notes_do_not_block_while_staged_notes_do(self):
        self.write(".gitignore", GITIGNORE_BLOCK)
        self.write("AGENTS.md", "# rules\n\n\n")
        self.write("CLAUDE.md", "@AGENTS.md\n")
        self.write("SECURITY.md", "# Security\n")
        self.git("init", "--quiet")
        self.git("config", "user.name", "Test User")
        self.git("config", "user.email", "test@example.com")
        self.git("add", ".gitignore", "AGENTS.md", "CLAUDE.md", "SECURITY.md", "README.md")

        self.write("docs/changes/task/change-card.md", "# Card\n")
        self.write("docs/plans/draft.md", "# Draft\n")
        self.write("docs/acceptance-policy.md", "# Policy\n")
        self.write("deployment-audit.md", "# Audit\n")
        self.write("handoff.md", "# Handoff\n")
        self.write("ops-notes/rollout.md", "# Rollout\n")
        self.write(".codex/plan.md", "# Plan\n")
        self.write("site/release.internal.md", "# Release\n")

        code, output = self.run_main()
        self.assertEqual(code, 0, msg=output)

        self.git(
            "add", "-f",
            "docs/changes/task/change-card.md",
            "docs/acceptance-policy.md",
            "deployment-audit.md",
            "handoff.md",
            "ops-notes/rollout.md",
            ".codex/plan.md",
            "site/release.internal.md",
        )
        blocked_code, blocked_output = self.run_main()
        self.assertEqual(blocked_code, 1, msg=blocked_output)
        for blocked_path in (
            "docs/changes/task/change-card.md",
            "docs/acceptance-policy.md",
            "deployment-audit.md",
            "handoff.md",
            "ops-notes/rollout.md",
            ".codex/plan.md",
            "site/release.internal.md",
        ):
            self.assertIn(blocked_path, blocked_output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
