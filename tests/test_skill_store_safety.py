import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from agent_code.skill_manager import ApiError, extract_zip_safe, parse_skill_md


class SkillStoreSafetyTests(unittest.TestCase):
    def test_parse_skill_metadata(self):
        meta = parse_skill_md(
            "---\nname: demo\ndescription: Example skill\nversion: 1.2.0\n---\n"
        )
        self.assertEqual(meta["name"], "demo")
        self.assertEqual(meta["version"], "1.2.0")

    def test_safe_archive_extracts_skill(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("demo/skill.py", "SKILL = {'name': 'demo'}\n")
            archive.writestr("demo/skill.md", "---\nname: demo\n---\n")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "stage"
            extract_zip_safe(buf.getvalue(), target)
            self.assertTrue((target / "demo" / "skill.py").is_file())

    def test_rejects_parent_traversal(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("../outside.txt", "nope")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ApiError):
                extract_zip_safe(buf.getvalue(), Path(tmp) / "stage")
            self.assertFalse((Path(tmp).parent / "outside.txt").exists())


    def test_rejects_windows_parent_traversal(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr(r"..\outside.txt", "nope")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ApiError):
                extract_zip_safe(buf.getvalue(), Path(tmp) / "stage")

    def test_rejects_symlink_entries(self):
        import stat
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            info = zipfile.ZipInfo("demo/link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "../../outside")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ApiError):
                extract_zip_safe(buf.getvalue(), Path(tmp) / "stage")

    def test_rejects_oversized_unpacked_archive(self):
        from agent_code.skill_manager import MAX_SKILL_UNPACKED_BYTES
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("large.txt", b"0" * (MAX_SKILL_UNPACKED_BYTES + 1))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ApiError):
                extract_zip_safe(buf.getvalue(), Path(tmp) / "stage")


    def test_rejects_symlink_extraction_target(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            outside = base / "outside"
            outside.mkdir()
            target = base / "stage-link"
            try:
                target.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are not available on this platform")
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as archive:
                archive.writestr("skill.py", "SKILL = {}\n")
            with self.assertRaises(ApiError):
                extract_zip_safe(buf.getvalue(), target)
            self.assertEqual(list(outside.iterdir()), [])

    def test_rejects_invalid_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(zipfile.BadZipFile):
                extract_zip_safe(b"not a zip archive", Path(tmp) / "stage")


if __name__ == "__main__":
    unittest.main()
