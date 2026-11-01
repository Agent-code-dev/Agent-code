from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src" / "agent_code" / "agent.py"


def test_saved_profiles_detect_matching_custom_endpoints_and_prompt_to_merge_keys():
    source = SOURCE.read_text(encoding="utf-8")
    assert "def _normalize_profile_endpoint(endpoint):" in source
    assert "Endpoint already saved" in source
    assert "Do you want to add the new API key(s) to that endpoint" in source
    assert "existing_profile[\"openai_api_keys\"] = merged" in source


def test_endpoint_normalization_ignores_trailing_slash_and_default_port():
    source = SOURCE.read_text(encoding="utf-8")
    assert "parsed.path or \"\").rstrip(\"/\")" in source
    assert "port == 443" in source and "port == 80" in source
