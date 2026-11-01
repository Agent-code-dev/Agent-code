import importlib.util
import io
import zipfile
from pathlib import Path

SERVER = Path(__file__).parents[1] / "server" / "skill-server.py"
spec = importlib.util.spec_from_file_location("agent_code_skill_server", SERVER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def make_zip(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return out.getvalue()

def test_valid_skill_zip_is_read():
    sources, error = mod.extract_python_sources(make_zip({"skill.py": "print(1)"}))
    assert error is None
    assert sources["skill.py"] == "print(1)"

def test_missing_skill_py_is_rejected():
    sources, error = mod.extract_python_sources(make_zip({"other.py": "pass"}))
    assert sources == {}
    assert "missing skill.py" in error

def test_path_traversal_is_rejected():
    sources, error = mod.extract_python_sources(make_zip({"skill.py": "pass", "../evil.py": "pass"}))
    assert sources == {}
    assert "unsafe entry" in error

def test_too_many_zip_entries_are_rejected():
    files = {f"x{i}.txt": "x" for i in range(501)}
    sources, error = mod.extract_python_sources(make_zip(files))
    assert sources == {}
    assert "too many entries" in error
