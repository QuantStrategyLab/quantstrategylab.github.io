"""Regression tests for the documentation checker.

This checker runs against every repository that adopts the rule set, from one
copy or many, so a rule that silently stops working fails everywhere at once
and nobody notices. Each test here pins one decision that was easy to get
wrong:

  * the leak heuristics must not report the placeholder forms the guide asks
    for, or the report fills with non-defects and gets ignored
  * the .gitignore block must be required, not suggested, or the layer that
    stops a note being committed disappears without a trace
  * phase 1 must stay quiet about naming, or every open pull request goes red
    the day the checker lands

Run with `python scripts/test_style.py`.
"""

from __future__ import annotations

import importlib.util
import io
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_style", Path(__file__).with_name("check_style.py")
)
check_style = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_style)

GITIGNORE_BLOCK = "\n".join(check_style.INTERNAL_NOTE_GITIGNORE) + "\n"
SHA = "8e8ec51884bf8abb0a7ca699fc2da39fad134f89"


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

    def report(self, phase: int = 2) -> check_style.Report:
        return check_style.Report(check_style.PHASE_BLOCKING[phase])

    def messages(self, report: check_style.Report, category: str) -> list[str]:
        return [m for c, m in report.findings if c == category]

    def run_main(self, *extra: str) -> tuple[int, str]:
        with redirect_stdout(io.StringIO()) as captured:
            code = check_style.main(["--root", str(self.root), "--phase", "2", *extra])
        return code, captured.getvalue()


class NamingTest(CheckerTestCase):
    def test_underscore_is_flagged(self):
        self.write("docs/hk_equity_runtime.md", "# x\n")
        report = self.report()
        check_style.check_naming(self.root, report)
        self.assertTrue(any("underscores" in m for m in self.messages(report, "naming")))

    def test_github_templates_keep_their_underscore(self):
        # GitHub only reads pull_request_template.md / issue_template.md with the
        # underscore; renaming them to hyphens disables the template.
        self.write(".github/pull_request_template.md", "## Summary\n")
        self.write(".github/issue_template.md", "---\nname: bug\n---\n")
        report = self.report()
        check_style.check_naming(self.root, report)
        self.assertEqual(self.messages(report, "naming"), [])

    def test_date_is_flagged_outside_record_paths(self):
        self.write("docs/2026-10-30-release.md", "# x\n")
        report = self.report()
        check_style.check_naming(self.root, report)
        self.assertTrue(any("dates belong" in m for m in self.messages(report, "naming")))

    def test_date_is_allowed_in_record_paths(self):
        self.write("docs/research/2026-10-30-revision.md", "# x\n")
        report = self.report()
        check_style.check_naming(self.root, report)
        self.assertFalse(any("dates belong" in m for m in self.messages(report, "naming")))

    def test_en_suffix_is_flagged(self):
        self.write("docs/runtime-baseline.en.md", "# x\n")
        report = self.report()
        check_style.check_naming(self.root, report)
        self.assertTrue(any(".en.md is not a suffix" in m for m in self.messages(report, "naming")))

    def test_root_proposal_has_its_owner_requested_name(self):
        self.write("PROPOSAL.md", "# Proposed governance change\n")
        report = self.report()
        check_style.check_naming(self.root, report)
        self.assertEqual(self.messages(report, "naming"), [])

    def test_nested_proposal_still_requires_lowercase(self):
        self.write("docs/PROPOSAL.md", "# x\n")
        report = self.report()
        check_style.check_naming(self.root, report)
        self.assertTrue(any("lowercase" in m for m in self.messages(report, "naming")))

    def test_uppercase_convention_is_allowed(self):
        self.write("SECURITY.md", "# x\n")
        report = self.report()
        check_style.check_naming(self.root, report)
        self.assertEqual(self.messages(report, "naming"), [])


class LeakTest(CheckerTestCase):
    def findings(self, text: str) -> list[str]:
        self.write("docs/page.md", text)
        report = self.report()
        check_style.check_leaks(self.root, report)
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
        # Section 13 asks for a placeholder where a deployed subdomain would
        # appear. Reporting the guide's own recommended form is how a check
        # teaches people to ignore it.
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
        import pathlib
        import struct
        import zlib

        repo_root = pathlib.Path(check_style.__file__).resolve().parent.parent

        def png_chunk(ctype: bytes, data: bytes) -> bytes:
            return struct.pack(">I4s", len(data), ctype) + data + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)

        def make_png(*extra_chunks: bytes) -> bytes:
            ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
            idat = zlib.compress(b"\x00\xff\x00\x00")
            return b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr) + b"".join(extra_chunks) + png_chunk(b"IDAT", idat) + png_chunk(b"IEND", b"")

        def make_ico(png_bytes: bytes) -> bytes:
            header = struct.pack("<HHH", 0, 1, 1)
            entry = struct.pack("<BBBBHHII", 1, 1, 0, 0, 1, 32, len(png_bytes), 22)
            return header + entry + png_bytes

        clean_png = make_png()
        self.write(
            "site/index.html",
            '<link rel="stylesheet" href="assets/styles.css">\n'
            '<script src="assets/i18n.js" defer></script>\n'
            '<script src="assets/app.js" defer></script>\n'
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
        (self.root / "site/favicon.ico").write_bytes((repo_root / "site/favicon.ico").read_bytes())
        (self.root / "site/assets").mkdir(parents=True, exist_ok=True)
        (self.root / "site/assets/app.js").write_bytes((repo_root / "site/assets/app.js").read_bytes())
        (self.root / "site/assets/i18n.js").write_bytes((repo_root / "site/assets/i18n.js").read_bytes())
        self.write("site/unused.css", "p { display: none; }\n")
        clean_report = self.report()
        check_style.check_leaks(self.root, clean_report)
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
            '<p>&#47;home&#47;<strong>operator</strong>&#47;prod&#47;config and '
            'db-primary&#46;<span>ops</span>&#46;internal</p>'
            '<a href="https:&#47;&#47;actual-private-app&#46;workers&#46;dev">x</a>\n',
        )
        self.write(
            "site/css-inline-leak.html",
            '<style>.join{display:inline}</style>'
            '<span>/home/</span><div class="join">operator</div><span>/prod/config</span>\n',
        )
        self.write(
            "site/css-flex-leak.html",
            '<style>.row{display:flex}</style><div class="row">\n'
            '  <div>db-primary.</div>\n'
            '  <div>ops.internal</div>\n'
            '</div>\n',
        )
        self.write(
            "site/css-order-leak.html",
            '<style>.row{display:flex}.a{order:2}.b{order:1}.c{order:3}</style>'
            '<div class="row"><span class="a">operator</span>'
            '<span class="b">/home/</span><span class="c">/prod/config</span></div>\n',
        )
        self.write(
            "site/css-grid-leak.html",
            '<div style="display:grid;grid-template-columns:1fr">'
            '<span style="grid-row:2;grid-column:1">operator</span>'
            '<span>/home/</span><span>/prod/config</span></div>\n',
        )
        self.write(
            "site/css-hidden-sep.html",
            '<style>.h{display:none}</style>'
            '<span>/home/</span><span class="h">SAFE</span><span>operator/prod/config</span>\n',
        )
        self.write(
            "site/css-reverse.html",
            '<div style="display:flex;flex-direction:row-reverse"><span>a</span><span>b</span></div>\n',
        )
        self.write(
            "site/escaped-leak.js",
            'const p = "\\u002fhome\\u002foperator\\u002fprod\\u002fconfig";\n',
        )
        self.write(
            "site/data-uri.html",
            '<img src="data:image/png;base64,iVBORw0KGgo=">\n',
        )
        self.write("site/actual-private-app.workers.dev/index.html", "<p>benign page content</p>\n")
        self.write("site/db-primary.ops.internal/cfg.html", "<p>benign internal path</p>\n")
        self.write(
            "site/assets/app.js.map",
            '{"sourceRoot":"gs://actual-prod-bucket/maps"}\n',
        )
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
        (self.root / "site/unapproved-pixel.png").write_bytes(clean_png)
        (self.root / "site/unapproved.ico").write_bytes(make_ico(clean_png))
        (self.root / "site/landing-light-192.png").write_bytes(clean_png)
        # Re-compress/append trailing payload inside IDAT of an otherwise approved PNG.
        approved_bytes = (repo_root / "site/landing-light-512.png").read_bytes()
        pos = 8
        tampered = bytearray(b"\x89PNG\r\n\x1a\n")
        while pos < len(approved_bytes):
            clen, ctype = struct.unpack(">I4s", approved_bytes[pos:pos + 8])
            cdata = approved_bytes[pos + 8:pos + 8 + clen]
            if ctype == b"IDAT":
                cdata = cdata + b"/home/operator/prod/config db-primary.ops.internal"
            tampered.extend(png_chunk(ctype, cdata))
            pos += 12 + clen
        (self.root / "site/landing-light-512.png").write_bytes(bytes(tampered))
        iend_src = (repo_root / "site/landing-light-apple-touch-180.png").read_bytes()
        iend_out = bytearray(b"\x89PNG\r\n\x1a\n")
        ipos = 8
        while ipos < len(iend_src):
            clen, ctype = struct.unpack(">I4s", iend_src[ipos:ipos + 8])
            cdata = iend_src[ipos + 8:ipos + 8 + clen]
            if ctype == b"IEND":
                cdata = b"/home/operator/prod/config actual-private-app.workers.dev"
            iend_out.extend(png_chunk(ctype, cdata))
            ipos += 12 + clen
        (self.root / "site/landing-light-apple-touch-180.png").write_bytes(bytes(iend_out))
        (self.root / "site/leak-meta.png").write_bytes(
            make_png(
                png_chunk(b"tEXt", b"Comment\x00deploy /home/operator/prod/config http://10.23.45.67"),
                png_chunk(b"zTXt", b"Host\x00\x00" + zlib.compress(b"https://actual-private-app.workers.dev")),
            )
        )
        (self.root / "site/release.pdf").write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n")
        (self.root / "site/bundle.zip").write_bytes(b"PK\x03\x04\x00\x00payload")
        (self.root / "site/corrupt.png").write_bytes(b"not a real png\x00")
        dirty_report = self.report()
        check_style.check_leaks(self.root, dirty_report)
        check_style.check_internal_paths(self.root, dirty_report)
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
        self.assertTrue(any("site/leak-meta.png" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/leak-meta.png" in m and "private IPv4 address" in m for m in msgs))
        self.assertTrue(any("site/leak-meta.png" in m and "personal subdomain" in m for m in msgs))
        self.assertTrue(any("site/leak-meta.png" in m and "unapproved or uninspected raster asset" in m for m in msgs))
        self.assertTrue(any("site/unapproved-pixel.png" in m and "unapproved or uninspected raster asset" in m for m in msgs))
        self.assertTrue(any("site/unapproved.ico" in m and "unapproved or uninspected raster asset" in m for m in msgs))
        self.assertTrue(any("site/landing-light-192.png" in m and "unapproved or uninspected raster asset" in m for m in msgs))
        self.assertTrue(any("site/landing-light-512.png" in m and "unscanned binary or encrypted asset" in m for m in msgs))
        self.assertTrue(any("site/landing-light-apple-touch-180.png" in m and "unscanned binary or encrypted asset" in m for m in msgs))
        self.assertEqual(sum(1 for m in msgs if "site/runtime-config.yaml" in m and "Windows deployment path" in m), 2)
        self.assertTrue(any("site/release.pdf" in m and "unscanned binary or encrypted asset" in m for m in msgs))
        self.assertTrue(any("site/bundle.zip" in m and "unscanned binary or encrypted asset" in m for m in msgs))
        self.assertTrue(any("site/corrupt.png" in m and "unscanned binary or encrypted asset" in m for m in msgs))
        self.assertTrue(any("site/runtime-config.yaml" in m and "internal hostname" in m for m in msgs))
        self.assertEqual(sum(1 for m in msgs if "site/runtime-config.yaml" in m and "account identifier" in m), 3)
        self.assertEqual(sum(1 for m in msgs if "site/runtime-config.json" in m and "account identifier" in m), 2)
        self.assertTrue(any("site/rendered-leak.html" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/rendered-leak.html" in m and "internal hostname" in m for m in msgs))
        self.assertTrue(any("site/rendered-leak.html" in m and "personal subdomain" in m for m in msgs))
        self.assertTrue(any("site/css-inline-leak.html" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/css-flex-leak.html" in m and "internal hostname" in m for m in msgs))
        self.assertTrue(any("site/css-order-leak.html" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/css-grid-leak.html" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/css-hidden-sep.html" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/css-reverse.html" in m and "reverse flex visual ordering" in m for m in msgs))
        self.assertTrue(any("site/escaped-leak.js" in m and "absolute home path" in m for m in msgs))
        self.assertTrue(any("site/data-uri.html" in m and "embedded data URI asset" in m for m in msgs))
        self.assertTrue(any("site/actual-private-app.workers.dev/index.html" in m and "personal subdomain" in m for m in msgs))
        self.assertTrue(any("site/db-primary.ops.internal/cfg.html" in m and "internal hostname" in m for m in msgs))

        self.write(
            "site/mixed-case.json",
            '{"url": "HTTPS://REAL-LEAK.WORKERS.DEV", "bucket": "GS://CORP-QUANT-BUCKET", '
            '"arn": "ARN:AWS:IAM::123456789012:ROLE/OPS", '
            '"sa": "DEPLOY@CORP-QUANT-PROD.IAM.GSERVICEACCOUNT.COM"}\n',
        )
        self.write("site/a.css", ".vis-box { display: flex; } .f1 { order: 2; } .f2 { order: 1; }\n")
        self.write("site/z.css", ".vis-box { display: none; }\n")
        self.write(
            "site/linked-css.html",
            '<link rel="stylesheet" href="a.css">\n'
            '<div class="vis-box"><span class="f1">/alice/secret</span><span class="f2">/Users</span></div>\n',
        )
        self.write("site/indirect.js", 'const p = ["/U", "sers/", "bob"].join("");\n')
        self.write("site/inline-js.html", '<script>const p = ["/U", "sers/", "bob"].join("");</script>\n')
        self.write(
            "site/media-order.html",
            "<style>\n"
            ".mwrap { display: flex; }\n"
            "@media (max-width: 600px) { .ma { order: 2; } .mb { order: 1; } }\n"
            "@media (min-width: 601px) { .ma { order: 1; } .mb { order: 2; } }\n"
            "</style>\n"
            '<div class="mwrap"><span class="ma">/alice/mobile</span><span class="mb">/Users</span></div>\n',
        )
        self.write("site/nonpixel-media.css", "@media (prefers-color-scheme: dark) { .hid { display: none; } }\n")
        self.write("site/bad-handler.html", '<img src="landing-light-192.png" onclick="evil()"><a href="javascript:evil()">x</a>\n')
        self.write(
            "site/sr-only-sentinel.html",
            "<style>.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}</style>\n"
            '<p>actual-private-app.work<span class="sr-only">SAFE</span>ers.dev</p>\n',
        )
        self.write(
            "site/clip-path-hide.html",
            "<style>.hidden{position:absolute;clip-path:inset(100%)}</style>\n"
            '<p>actual-private-app.work<span class="hidden">SAFE</span>ers.dev</p>\n',
        )
        self.write("site/zero-width-hide.html", "<style>.z{width:0;overflow:hidden}</style>\n<p>x</p>\n")

        extra_report = self.report()
        check_style.check_leaks(self.root, extra_report)
        extra_msgs = [f"{cat}: {detail}" for cat, detail in extra_report.findings]
        self.assertTrue(any("site/mixed-case.json" in m and "personal subdomain" in m for m in extra_msgs), extra_msgs)
        self.assertTrue(any("site/mixed-case.json" in m and "non-placeholder bucket" in m for m in extra_msgs), extra_msgs)
        self.assertTrue(any("site/mixed-case.json" in m and "account identifier" in m and "ARN:AWS:" in m for m in extra_msgs), extra_msgs)
        self.assertTrue(any("site/mixed-case.json" in m and "account identifier" in m and "DEPLOY@CORP-QUANT-PROD" in m for m in extra_msgs), extra_msgs)
        self.assertTrue(any("site/linked-css.html" in m and "absolute home path" in m for m in extra_msgs), extra_msgs)
        self.assertTrue(any("site/indirect.js" in m and "unapproved or uninspected executable script" in m for m in extra_msgs), extra_msgs)
        self.assertTrue(any("site/inline-js.html" in m and "unapproved executable inline script" in m for m in extra_msgs), extra_msgs)
        self.assertTrue(any("site/media-order.html" in m and "absolute home path" in m for m in extra_msgs), extra_msgs)
        self.assertTrue(any("site/nonpixel-media.css" in m and "non-pixel conditional layout rule" in m for m in extra_msgs), extra_msgs)
        self.assertTrue(any("site/bad-handler.html" in m and "inline event handler attribute" in m for m in extra_msgs), extra_msgs)
        self.assertTrue(any("site/bad-handler.html" in m and "javascript: or vbscript: URI" in m for m in extra_msgs), extra_msgs)
        self.assertTrue(any("site/sr-only-sentinel.html" in m and "personal subdomain" in m for m in extra_msgs), extra_msgs)
        self.assertTrue(any("site/clip-path-hide.html" in m and "unmodeled CSS property (clip-path)" in m for m in extra_msgs), extra_msgs)
        self.assertTrue(any("site/zero-width-hide.html" in m and "sub-2px box dimension hiding" in m for m in extra_msgs), extra_msgs)

    def test_public_markdown_scans_account_and_internal_host_identifiers(self):
        self.write(
            "README.md",
            '```json\n{"account_id": "000000000000", "host": "your-host.internal", '
            '"arn": "arn:aws:iam::000000000000:role/example", "sa": "your-sa@example.iam.gserviceaccount.com"}\n```\n',
        )
        clean = self.report()
        check_style.check_leaks(self.root, clean)
        self.assertEqual(clean.findings, [])

        self.write(
            "README.md",
            '```json\n{"account_id": "123456789012", "host": "db-primary.ops.internal", "ip": "10.23.45.67"}\n```\n',
        )
        dirty = self.report()
        check_style.check_leaks(self.root, dirty)
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
        check_style.check_internal_paths(self.root, report)
        found = self.messages(report, "hygiene")
        self.assertEqual(len(found), 1)
        self.assertIn("docs/audits/", found[0])

    def test_complete_gitignore_passes(self):
        self.write(".gitignore", GITIGNORE_BLOCK)
        report = self.report()
        check_style.check_internal_paths(self.root, report)
        self.assertEqual(self.messages(report, "hygiene"), [])

    def test_hygiene_blocks_in_phase_one(self):
        report = self.report(phase=1)
        check_style.check_internal_paths(self.root, report)
        self.assertEqual(len(report.blocking_findings()), 1)

    def test_audit_directory_is_reported(self):
        self.write(".gitignore", GITIGNORE_BLOCK)
        self.write("docs/audits/2026-10-30-review.md", "# x\n")
        report = self.report()
        check_style.check_internal_paths(self.root, report)
        self.assertTrue(any("plan/handoff directory" in m for m in self.messages(report, "content")))

    def test_changes_directory_and_obsolete_engineering_rule_are_reported(self):
        self.write(".gitignore", GITIGNORE_BLOCK + "!.github/engineering.md\n")
        self.write("docs/changes/task/change-card.md", "# x\n")
        report = self.report()
        check_style.check_internal_paths(self.root, report)
        self.assertTrue(any("engineering.md" in m for m in self.messages(report, "hygiene")))
        self.assertTrue(any("plan/handoff directory" in m for m in self.messages(report, "content")))

    def test_acceptance_policy_blocks_public_only(self):
        self.write(".gitignore", GITIGNORE_BLOCK)
        self.write("docs/acceptance-policy.md", "# policy\n")
        pub = self.report(phase=2)
        check_style.check_internal_paths(self.root, pub)
        self.assertTrue(any(cat == "publish" for cat, _ in pub.blocking_findings()))
        _, output = self.run_main("--visibility", "private")
        self.assertTrue(
            any(line.startswith("NOTE") and "acceptance-policy.md" in line for line in output.splitlines())
        )


class AgentFileTest(CheckerTestCase):
    def test_missing_agents_md_is_reported(self):
        report = self.report()
        check_style.check_agent_files(self.root, report)
        self.assertTrue(any("AGENTS.md is missing" in m for m in self.messages(report, "agents")))

    def test_untracked_agents_md_is_reported(self):
        self.write("AGENTS.md", "# rules\n")
        self.write("CLAUDE.md", "@AGENTS.md\n")
        self.git("init", "--quiet")
        report = self.report()
        check_style.check_agent_files(self.root, report)
        found = self.messages(report, "agents")
        self.assertTrue(any("not tracked by Git" in m for m in found))

    def test_tracked_agents_md_passes(self):
        self.write("AGENTS.md", "# rules\n\n" + check_style.CONTENT_BOUNDARY + "\n")
        self.write("CLAUDE.md", "@AGENTS.md\n")
        self.git("init", "--quiet")
        self.git("add", "AGENTS.md", "CLAUDE.md")
        report = self.report()
        check_style.check_agent_files(self.root, report)
        self.assertEqual(self.messages(report, "agents"), [])

    def test_content_boundary_block_is_required(self):
        # A rule that lives only in the guide is read by whoever opens the
        # guide. The block is the copy that reaches an agent before it writes,
        # so its absence is a finding rather than a preference.
        self.write("AGENTS.md", "# rules\n")
        self.write("CLAUDE.md", "@AGENTS.md\n")
        self.git("init", "--quiet")
        self.git("add", "AGENTS.md", "CLAUDE.md")
        report = self.report()
        check_style.check_agent_files(self.root, report)
        self.assertTrue(
            any("content-boundary" in m for m in self.messages(report, "agents"))
        )

    def test_claude_must_be_the_single_line(self):
        self.write("AGENTS.md", "# rules\n")
        self.write("CLAUDE.md", "# rules\n\ncopied body\n")
        self.git("init", "--quiet")
        self.git("add", "AGENTS.md", "CLAUDE.md")
        report = self.report()
        check_style.check_agent_files(self.root, report)
        self.assertTrue(any("@AGENTS.md" in m for m in self.messages(report, "agents")))

    def test_retired_engineering_doc_and_long_agents_are_reported(self):
        long_body = "# rules\n" + "\n".join(f"line {i}" for i in range(125)) + "\n" + check_style.CONTENT_BOUNDARY + "\n"
        self.write("AGENTS.md", long_body)
        self.write("CLAUDE.md", "@AGENTS.md\n")
        self.write(".github/engineering.md", "# legacy\n")
        self.git("init", "--quiet")
        self.git("add", "AGENTS.md", "CLAUDE.md")
        report = self.report()
        check_style.check_agent_files(self.root, report)
        found = self.messages(report, "agents")
        self.assertTrue(any("engineering.md is retired" in m for m in found))
        self.assertTrue(any("exceeds 120 lines" in m for m in found))


class LanguageTest(CheckerTestCase):
    """Section 2 — the word list reports usage, not mention."""

    def test_marketing_word_in_prose_is_reported(self):
        self.write("docs/note.md", "# Note\n\nA seamless handover.\n")
        report = self.report()
        check_style.check_language(self.root, report)
        self.assertTrue(any("seamless" in m for m in self.messages(report, "language")))

    def test_marketing_word_in_a_code_span_is_a_mention(self):
        # The guide writes the words it forbids. Reporting them there makes the
        # guide the largest offender in the organisation.
        self.write("docs/note.md", "# Note\n\nAvoid `seamless` and `world-class`.\n")
        report = self.report()
        check_style.check_language(self.root, report)
        self.assertEqual(self.messages(report, "language"), [])

    def test_marketing_word_in_a_fenced_block_is_a_mention(self):
        self.write("docs/note.md", "# Note\n\n```markdown\nA seamless handover.\n```\n")
        report = self.report()
        check_style.check_language(self.root, report)
        self.assertEqual(self.messages(report, "language"), [])

    def test_technical_terms_are_not_marketing(self):
        # A robust estimator and statistical power are terms of art; the list
        # that flagged them reported twelve non-defects in the research docs.
        self.write(
            "docs/note.md",
            "# Note\n\nThe robust plateau holds, and the test is more powerful "
            "than the Reality Check.\n",
        )
        report = self.report()
        check_style.check_language(self.root, report)
        self.assertEqual(self.messages(report, "language"), [])

    def test_dated_section_heading_is_not_a_dated_title(self):
        self.write(
            "docs/note.md",
            "# Contract acceptance\n\n## Bounded run acceptance (2026-10-05)\n",
        )
        report = self.report()
        check_style.check_language(self.root, report)
        self.assertEqual(self.messages(report, "language"), [])

    def test_dated_document_title_is_reported(self):
        self.write("docs/note.md", "# Console audit, 2026-10-15\n")
        report = self.report()
        check_style.check_language(self.root, report)
        self.assertTrue(any("dated title" in m for m in self.messages(report, "language")))


class CrossRepositoryTest(CheckerTestCase):
    def test_cross_repository_reference_never_blocks(self):
        # The scheduled link job resolves these against the sibling's default
        # branch. A finding that says "not checked" cannot block a merge.
        # Two levels up: one level stays inside the repository, and on macOS
        # `/tmp` resolves through a symlink, so a one-level fixture passed here
        # and failed on the Linux runner.
        self.write("docs/note.md", "# Note\n\n[peer](../../Sibling/docs/x.md)\n")
        report = self.report(phase=2)
        check_style.check_links(self.root, report)
        self.assertTrue(any(c == "xref" for c, _ in report.findings))
        self.assertEqual(report.blocking_findings(), [])


class DocsBaselineTest(CheckerTestCase):
    def test_public_repository_needs_the_reader_file_set(self):
        self.write("LICENSE", "MIT\n")
        report = self.report()
        check_style.check_docs_baseline(self.root, report)
        found = self.messages(report, "docs")
        self.assertTrue(any("CONTRIBUTING.md" in m for m in found))
        self.assertTrue(any("CODE_OF_CONDUCT.md" in m for m in found))

    def test_public_repository_with_the_file_set_passes(self):
        self.write("LICENSE", "MIT\n")
        for name in ("CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md"):
            self.write(name, "# " + name + "\n")
        report = self.report()
        check_style.check_docs_baseline(self.root, report)
        self.assertEqual(self.messages(report, "docs"), [])

    def test_private_repository_needs_only_the_credential_doc(self):
        # No LICENSE means the repository grants nothing to outside readers, so
        # a public disclosure process would be a document nobody runs.
        self.write("SECURITY.md", "# Credentials\n")
        report = self.report()
        check_style.check_docs_baseline(self.root, report)
        self.assertEqual(self.messages(report, "docs"), [])

    def test_private_repository_without_the_credential_doc_is_reported(self):
        report = self.report()
        check_style.check_docs_baseline(self.root, report)
        self.assertTrue(any("SECURITY.md" in m for m in self.messages(report, "docs")))


class PhaseTest(CheckerTestCase):
    def test_phase_one_does_not_block_naming(self):
        self.write("docs/hk_equity_runtime.md", "# x\n")
        report = self.report(phase=1)
        check_style.check_naming(self.root, report)
        self.assertTrue(report.findings)
        self.assertEqual(report.blocking_findings(), [])

    def test_phase_two_blocks_naming(self):
        self.write("docs/hk_equity_runtime.md", "# x\n")
        report = self.report(phase=2)
        check_style.check_naming(self.root, report)
        self.assertTrue(report.blocking_findings())


class AdvisoryModeTest(CheckerTestCase):
    """Adoption has to be possible before compliance.

    A repository adds the check while it still has findings. If that pull
    request goes red, the check is removed instead of the findings fixed, and
    the repository ends up with neither.
    """

    def test_advisory_reports_the_findings_it_would_have_blocked_on(self):
        self.write("docs/hk_equity_runtime.md", "# x\n")
        code, output = self.run_main("--advisory")
        self.assertEqual(code, 0)
        self.assertIn("underscores", output)
        self.assertIn("advisory run", output)

    def test_without_advisory_the_same_findings_still_fail(self):
        self.write("docs/hk_equity_runtime.md", "# x\n")
        code, _ = self.run_main()
        self.assertEqual(code, 1)


class VisibilityTest(CheckerTestCase):
    """The publication rules govern publishing, not existence.

    A private repository publishes nothing, and a deployment document may need
    the real host name to be usable — an OAuth callback URL with a placeholder
    in it cannot be configured. Blocking there would force a document to be
    wrong in order to pass.
    """

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
        # Forgetting the flag must not switch a leak rule off.
        self.deploy_doc()
        _, output = self.run_main()
        self.assertIn("(public)", output)
        self.assertTrue(
            any(line.startswith("ERROR") and "personal subdomain" in line
                for line in output.splitlines())
        )

    def test_private_still_blocks_a_missing_security_policy(self):
        # Visibility narrows the publication rules only; it is not a blanket
        # exemption for everything the checker knows.
        _, output = self.run_main("--visibility", "private")
        self.assertTrue(
            any(line.startswith("ERROR") and "SECURITY.md" in line
                for line in output.splitlines())
        )




class ReadmeHygieneTest(CheckerTestCase):
    def test_readme_patch_prose_phase_heading_and_post_license_block(self):
        self.write(
            "README.md",
            "# Demo\n\n## P0-P6 Runtime Authority\n\nIn this PR the gate remains unchanged.\n\n## License\n\nMIT\n\n## Weekly secret scan\n\nExtra\n",
        )
        self.write(
            "README.zh-CN.md",
            "# 示例\n\n## 许可证\n\nMIT\n\n## 每周密钥扫描\n\nExtra\n",
        )
        report = self.report(phase=2)
        check_style.check_readme(self.root, report)
        blocking = [m for c, m in report.blocking_findings() if c == "content"]
        self.assertTrue(any("phase code heading" in m for m in blocking))
        self.assertTrue(any("In this PR" in m for m in blocking))
        self.assertTrue(any("after License" in m and "README.md" in m for m in blocking))
        self.assertTrue(any("after License" in m and "README.zh-CN.md" in m for m in blocking))

    def test_clean_readme_and_fenced_examples_pass(self):
        self.write(
            "README.md",
            "# Demo\n\nUses `remains unchanged` in code.\n\n```markdown\nIn this PR\n```\n\n## Weekly secret scan\n\nRuns weekly.\n\n## License\n\nMIT\n",
        )
        report = self.report(phase=2)
        check_style.check_readme(self.root, report)
        self.assertEqual(report.blocking_findings(), [])


class ExampleMentionTest(CheckerTestCase):
    """Rules must not fire on text that is showing what not to do.

    Both cases below came from real repositories: a reference page documenting
    how to attach an image, and a design guide listing the filler words it
    forbids. Each was blocked by the rule it was teaching the reader to obey.
    """

    def test_a_link_inside_inline_code_is_an_example(self):
        self.write(
            "docs/pr-attachments.md",
            "# t\n\nReference it as `![alt](./settings-after.png)` to place it inline.\n",
        )
        report = self.report()
        # The temporary directory is not resolved; check_links resolves the
        # target, so an unresolved root would look like a sibling checkout.
        check_style.check_links(self.root.resolve(), report)
        self.assertEqual(self.messages(report, "links"), [])

    def test_a_real_broken_link_is_still_reported(self):
        self.write("docs/page.md", "# t\n\nSee [the settings](./settings-after.png).\n")
        report = self.report()
        check_style.check_links(self.root.resolve(), report)
        self.assertEqual(len(self.messages(report, "links")), 1)

    def test_a_quoted_word_list_is_not_marketing_language(self):
        self.write(
            "docs/design.md",
            '# t\n\n* **NO filler verbs.** "Elevate", "Seamless", "Unleash"'
            " \u2192 concrete verbs only.\n",
        )
        report = self.report()
        check_style.check_language(self.root, report)
        self.assertEqual(self.messages(report, "language"), [])

    def test_one_quoted_word_is_still_a_claim(self):
        # The exemption is about lists. A single quoted word is a word used.
        self.write("docs/page.md", "# t\n\nOur 'Seamless' onboarding flow.\n")
        report = self.report()
        check_style.check_language(self.root, report)
        self.assertEqual(len(self.messages(report, "language")), 1)


class GitVisibilityTest(CheckerTestCase):
    def test_gitignored_notes_do_not_block_while_staged_notes_do(self):
        self.write(".gitignore", GITIGNORE_BLOCK)
        self.write("AGENTS.md", "# rules\n\n" + check_style.CONTENT_BOUNDARY + "\n")
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
