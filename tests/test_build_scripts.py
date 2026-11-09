import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import branding
from scripts.build_windows import filename_slug, pyinstaller_command, validate_app_name


class TestBranding(unittest.TestCase):
    def test_missing_manifest_uses_default_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            with patch("modules.branding.bundled_path", return_value=str(missing)):
                result = branding.load_branding()

        self.assertEqual(result.app_name, "NTE Auto-Fish")

    def test_manifest_can_set_explicit_display_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "build_brand.json"
            manifest.write_text(
                json.dumps({"app_name": "Fishing Tools"}),
                encoding="utf-8",
            )
            with patch("modules.branding.bundled_path", return_value=str(manifest)):
                result = branding.load_branding()

        self.assertEqual(result.app_name, "Fishing Tools")


class TestWindowsBuildScript(unittest.TestCase):
    def test_app_name_validation_rejects_control_characters(self):
        with self.assertRaises(ValueError):
            validate_app_name("Bad\nName")

    def test_app_name_validation_rejects_non_ascii_native_titles(self):
        with self.assertRaises(ValueError):
            validate_app_name("釣りツール")

    def test_filename_slug_is_stable_and_safe(self):
        self.assertEqual(filename_slug("Fishing Tools 2026"), "Fishing-Tools-2026")

    def test_pyinstaller_command_contains_branding_resources(self):
        command = pyinstaller_command(
            "Fishing Tools",
            Path("icon.ico"),
            Path("build_brand.json"),
            Path("build_icon.ico"),
            Path("dist"),
        )
        joined = "\n".join(command)

        self.assertIn("--name=Fishing-Tools", command)
        self.assertIn("build_brand.json", joined)
        self.assertIn("build_icon.ico", joined)
        self.assertIn("--collect-data=rapidocr", command)
        self.assertIn("--uac-admin", command)


if __name__ == "__main__":
    unittest.main()
