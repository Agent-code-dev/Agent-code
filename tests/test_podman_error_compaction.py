import ast
from pathlib import Path
import re

ROOT = Path(__file__).parents[1]
AGENT = ROOT / "src" / "agent_code" / "agent.py"
TREE = ast.parse(AGENT.read_text(encoding="utf-8"))
NODES = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_compact_podman_error"]
NS = {"re": re}
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(AGENT), "exec"), NS)


def test_hides_signed_cloudfront_download_url():
    msg = 'Error: Get "https://production.cloudfront.docker.com/registry-v2/blobs/sha256/abc/data?Expires=123&Signature=secret&Key-Pair-Id=key": dial tcp timeout'
    result = NS["_compact_podman_error"](msg)
    assert "signed download URL was hidden" in result
    assert "secret" not in result
    assert len(result) < 400


def test_network_error_is_actionable_and_short():
    result = NS["_compact_podman_error"]('dial tcp: lookup registry-1.docker.io: no such host')
    assert "DNS" in result
    assert len(result) < 300


def test_repetitive_or_long_output_is_bounded():
    result = NS["_compact_podman_error"]("ordinary diagnostic line\n" * 1000)
    assert len(result) <= 701


def test_podman_pull_uses_portable_cli_and_python_retry():
    source = AGENT.read_text(encoding="utf-8")
    assert '["pull", image]' in source
    assert 'for attempt in range(2)' in source
    assert '"--retry=1"' not in source
    assert '"--pull=never", image' in source
