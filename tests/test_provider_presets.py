import ast
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src" / "agent_code" / "agent.py"


def test_google_ai_studio_and_anthropic_presets_exist():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "PROVIDER_PRESETS" for t in n.targets))
    presets = ast.literal_eval(node.value)
    assert presets["Google AI Studio"]["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert presets["Anthropic"]["base_url"] == "https://api.anthropic.com/v1/"
    assert presets["Custom OpenAI-compatible"]["base_url"] == ""


def test_provider_preset_is_persisted():
    source = SOURCE.read_text(encoding="utf-8")
    assert '"provider_name": self.provider_var.get()' in source
    assert 'self.provider_name = cfg.get("provider_name", "OpenAI")' in source
