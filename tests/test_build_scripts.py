import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import branding
from scripts.build_windows import (
    BUILTIN_ICONS,
    ROOT,
    filename_slug,
    new_build_id,
    pyinstaller_command,
    resolve_icon,
    validate_app_name,
    validate_build_id,
)


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
                json.dumps({"app_name": "Fishing Tools", "build_id": "abc123"}),
                encoding="utf-8",
            )
            with patch("modules.branding.bundled_path", return_value=str(manifest)):
                result = branding.load_branding()

        self.assertEqual(result.app_name, "Fishing Tools")
        self.assertEqual(result.build_id, "abc123")

    def test_runtime_names_are_scoped_by_build_without_changing_legacy_names(self):
        namespace = branding._storage_namespace(branding.Branding("Fishing Tools", "abc123"))
        self.assertEqual(namespace, "Fishing-Tools-babc123")
        self.assertEqual(
            branding.scoped_runtime_name("settings.json", namespace),
            "settings-Fishing-Tools-babc123.json",
        )
        self.assertEqual(branding.scoped_runtime_name("settings.json", ""), "settings.json")
        self.assertEqual(
            branding.scoped_runtime_name("sessions", "Fishing-Tools-babc123"),
            "sessions-Fishing-Tools-babc123",
        )


class TestWindowsBuildScript(unittest.TestCase):
    def test_app_name_validation_rejects_control_characters(self):
        with self.assertRaises(ValueError):
            validate_app_name("Bad\nName")

    def test_app_name_validation_rejects_non_ascii_native_titles(self):
        with self.assertRaises(ValueError):
            validate_app_name("釣りツール")

    def test_filename_slug_is_stable_and_safe(self):
        self.assertEqual(filename_slug("Fishing Tools 2026"), "Fishing-Tools-2026")

    def test_generated_build_ids_are_unique_and_valid(self):
        first = new_build_id()
        second = new_build_id()

        self.assertNotEqual(first, second)
        self.assertEqual(validate_build_id(first), first)
        self.assertEqual(len(first), 12)

    def test_all_builtin_icons_exist_and_are_windows_icons(self):
        self.assertEqual(
            set(BUILTIN_ICONS),
            {"classic", "bobber", "target-fish", "fisher-cat"},
        )
        for name, relative_path in BUILTIN_ICONS.items():
            with self.subTest(name=name):
                resolved = resolve_icon(name)
                self.assertEqual(resolved, (ROOT / relative_path).resolve())
                self.assertEqual(resolved.read_bytes()[:4], b"\x00\x00\x01\x00")

    def test_random_icon_uses_a_builtin_choice(self):
        with patch("scripts.build_windows.secrets.choice", return_value="fisher-cat"):
            self.assertEqual(resolve_icon("random"), resolve_icon("fisher-cat"))

    def test_pyinstaller_command_contains_branding_resources(self):
        command = pyinstaller_command(
            "Fishing Tools",
            "abc123",
            Path("icon.ico"),
            Path("build_brand.json"),
            Path("build_icon.ico"),
            Path("dist"),
        )
        joined = "\n".join(command)

        self.assertIn("--name=Fishing-Tools-babc123", command)
        self.assertIn("build_brand.json", joined)
        self.assertIn("build_icon.ico", joined)
        self.assertIn("--collect-data=rapidocr", command)
        self.assertIn("--uac-admin", command)


if __name__ == "__main__":
    unittest.main()
