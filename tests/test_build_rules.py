import contextlib
import io
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import build_rules as build


def rule_lines(text):
    return [line.strip() for line in text.splitlines() if build.is_rule(line.strip())]


class ConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outputs = build.build_outputs(build.ROOT)

    def test_all_source_rules_survive_conversion(self):
        reverse_qx = {
            "host": "DOMAIN", "host-suffix": "DOMAIN-SUFFIX",
            "host-keyword": "DOMAIN-KEYWORD", "host-wildcard": "DOMAIN-WILDCARD",
        }
        for name, policy in build.RULESETS:
            expected = rule_lines((build.ROOT / "source" / f"{name}.list").read_text(encoding="utf-8"))
            with self.subTest(name=name):
                self.assertEqual(rule_lines(self.outputs[Path(f"rules/surge/{name}.list")]), expected)
                stash = self.outputs[Path(f"rules/stash/{name}.yaml")]
                # The serializer emits quoted JSON strings, a strict YAML subset.
                self.assertIn("\npayload:\n", stash)
                self.assertEqual([json.loads(line[4:]) for line in stash.splitlines() if line.startswith("  - ")], expected)
                qx = rule_lines(self.outputs[Path(f"rules/quantumult-x/{name}.list")])
                converted = []
                for line in qx:
                    kind, value, actual_policy = line.split(",")
                    converted.append(f"{reverse_qx[kind]},{value}")
                    self.assertEqual(actual_policy, policy.lower() if policy in ("DIRECT", "REJECT") else policy)
                self.assertEqual(converted, expected)

    def test_loon_loses_only_the_documented_wildcard(self):
        for name, _ in build.RULESETS:
            expected = rule_lines((build.ROOT / "source" / f"{name}.list").read_text(encoding="utf-8"))
            actual = rule_lines(self.outputs[Path(f"rules/loon/{name}.list")])
            self.assertEqual(actual, [line for line in expected if line != "DOMAIN-WILDCARD,ads-*.xhscdn.com"])
        reject = self.outputs[Path("rules/loon/RednoteReject.list")]
        self.assertIn("未知广告域名不在此覆盖范围", reject)
        self.assertNotIn("DOMAIN-SUFFIX,xhscdn.com", rule_lines(reject))
        for host in ("ads-img-al", "ads-img-qc", "ads-video-al", "ads-video-qc", "ads-vp5"):
            self.assertIn(f"DOMAIN,{host}.xhscdn.com", rule_lines(reject))

    def test_unhandled_loon_wildcard_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "Loon 无法转换通配符"):
            build.render_rules("loon", "RednoteReject", "REJECT", ["DOMAIN-WILDCARD,*.example.com"])

    def test_partial_loon_fallback_requires_all_known_hosts(self):
        with self.assertRaisesRegex(ValueError, "精确广告域名不完整"):
            build.render_rules("loon", "RednoteReject", "REJECT", [build.LOON_XHS_RULE, "DOMAIN,ads-img-al.xhscdn.com"])

    def test_every_subscription_url_resolves_to_a_generated_file(self):
        expected_order = [
            "RednoteReject", "CustomDirect", "CustomAd", "CustomDownload",
            "CustomJapan", "CustomUS3", "CustomProxy",
        ]
        for client in build.CLIENTS:
            extension = "yaml" if client == "stash" else "conf"
            config = self.outputs[Path(f"config/{client}.{extension}")]
            urls = re.findall(r"https://[^\s,]+", config)
            targets = [Path(url.removeprefix(build.BASE_URL + "/")) for url in urls]
            self.assertEqual([path.stem for path in targets], expected_order)
            for path in targets:
                self.assertIn(path, self.outputs)
                self.assertEqual(path.parts[:2], ("rules", client))
            self.assertFalse(any(line.startswith(("FINAL,", "final,", "MATCH,")) for line in rule_lines(config)))

    def test_qx_force_policies_match_exported_rule_policies(self):
        config = self.outputs[Path("config/quantumult-x.conf")]
        for line in config.splitlines():
            if not line.startswith("https://"):
                continue
            fields = [field.strip() for field in line.split(",")]
            params = dict(field.split("=", 1) for field in fields[1:])
            path = Path(fields[0].removeprefix(build.BASE_URL + "/"))
            self.assertEqual(params["opt-parser"], "false")
            self.assertEqual({rule.split(",")[2] for rule in rule_lines(self.outputs[path])}, {params["force-policy"]})

    def test_stash_providers_and_references_stay_paired(self):
        config = self.outputs[Path("config/stash.yaml")]
        providers = re.findall(r"^  ((?:Custom|Rednote)\w+):$", config, re.MULTILINE)
        refs = [json.loads(line[4:]).split(",") for line in config.splitlines() if line.startswith("  - ")]
        self.assertEqual(providers, [name for kind, name, policy in refs if kind == "RULE-SET"])
        self.assertEqual(config.count("behavior: classical"), len(refs))
        self.assertEqual(config.count("format: yaml"), len(refs))

    def test_custom_base_url_updates_all_clients(self):
        base = "https://example.org/my-rules/testing"
        outputs = build.build_outputs(build.ROOT, base + "/")
        for path, content in outputs.items():
            if path.parts[0] == "config":
                self.assertNotIn(build.BASE_URL, content)
                self.assertEqual(content.count(base + "/rules/"), 7)

    def test_base_url_cannot_inject_configuration(self):
        for url in ("http://example.org", "https://u:p@example.org", "https://example.org?q=x", "https://example.org/#x", "https://example.org/,policy=DIRECT", "https://example.org/\n[Rule]"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                build.build_outputs(build.ROOT, url)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(build.ROOT / "source", self.root / "source")

    def run_build(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return build.main(list(args), root=self.root)

    def test_invalid_rules_report_file_and_line(self):
        invalid = (
            "IP-CIDR,192.0.2.0/24", "DOMAIN,example.com,DIRECT", "DOMAIN,",
            "DOMAIN,https://example.com", "DOMAIN,*.example.com", "DOMAIN,.example.com",
            "DOMAIN-SUFFIX,example..com", "DOMAIN-WILDCARD,example.com",
            "DOMAIN,example.com\nDOMAIN,example.com",
        )
        path = self.root / "bad.list"
        for text in invalid:
            with self.subTest(text=text):
                path.write_text(text + "\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, r"bad\.list:\d+:"):
                    build.read_source(path)

    def test_empty_rule_set_is_an_error(self):
        path = self.root / "empty.list"
        path.write_text("# no rules\n\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "规则集为空"):
            build.read_source(path)

    def test_comment_formats_and_whitespace_are_handled(self):
        path = self.root / "comments.list"
        path.write_text("# first\n; second\n// third\n DOMAIN , example.com \n", encoding="utf-8")
        lines = build.read_source(path)
        self.assertEqual(lines[-1], "DOMAIN,example.com")
        stash = build.render_rules("stash", "comments", "DIRECT", lines)
        self.assertIn("# second\n# third\n", stash)

    def test_check_detects_missing_stale_and_obsolete_files_without_writing(self):
        self.assertEqual(self.run_build("--check"), 1)
        self.assertFalse((self.root / "rules").exists())
        self.assertEqual(self.run_build(), 0)
        self.assertEqual(self.run_build("--check"), 0)
        path = self.root / "rules/surge/CustomDirect.list"
        path.write_text("# stale\n", encoding="utf-8")
        self.assertEqual(self.run_build("--check"), 1)
        self.assertEqual(path.read_text(encoding="utf-8"), "# stale\n")
        self.assertEqual(self.run_build(), 0)
        extra = self.root / "rules/surge/Obsolete.list"
        extra.write_text("DOMAIN,example.com\n", encoding="utf-8")
        self.assertEqual(self.run_build("--check"), 1)
        self.assertEqual(self.run_build(), 1)
        self.assertTrue(extra.exists())

    def test_invalid_new_rule_fails_before_modifying_outputs(self):
        self.assertEqual(self.run_build(), 0)
        before = {path: (self.root / path).read_bytes() for path in build.build_outputs(self.root)}
        with (self.root / "source/CustomProxy.list").open("a", encoding="utf-8") as file:
            file.write("\nDOMAIN-WILDCARD,*.example.com\n")
        self.assertEqual(self.run_build(), 1)
        self.assertEqual({path: (self.root / path).read_bytes() for path in before}, before)

    def test_unregistered_and_missing_sources_fail(self):
        extra = self.root / "source/Other.list"
        extra.write_text("DOMAIN,example.com\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "未登记.*Other.list"):
            build.build_outputs(self.root)
        extra.unlink()
        (self.root / "source/CustomAd.list").unlink()
        with self.assertRaisesRegex(ValueError, "缺少.*CustomAd.list"):
            build.build_outputs(self.root)


if __name__ == "__main__":
    unittest.main()
