import json
import zipfile
from pathlib import Path
import pytest
from agent_code.addons import install_addon_archive, remove_addon


def test_install_valid_addon_zip(tmp_path):
    archive = tmp_path / "addon.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("sample/addon.json", json.dumps({"name": "sample", "version": "1.0"}))
        z.writestr("sample/addon.py", "def register(api): pass\n")
    target = install_addon_archive(archive, tmp_path / "addons")
    assert (target / "addon.py").exists()
    assert remove_addon("sample", tmp_path / "addons")


def test_rejects_zip_path_traversal(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../outside.txt", "bad")
    with pytest.raises(ValueError, match="Unsafe path"):
        install_addon_archive(archive, tmp_path / "addons")
    assert not (tmp_path / "outside.txt").exists()
