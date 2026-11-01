from pathlib import Path


def test_stop_button_uses_three_click_escalation_and_preserves_browser():
    source = Path('src/agent_code/agent.py').read_text(encoding='utf-8')
    assert 'self._stop_click_count >= 3' in source
    assert 'three times quickly to force cancellation' in source
    force_handler = source.split('def _on_force_stop(self, _event=None):', 1)[1].split('\n    def ', 1)[0]
    assert 'self._stop_event.set()' in force_handler
    assert 'browser.stop' not in force_handler
    assert 'browser.close' not in force_handler
    assert 'browser.quit' not in force_handler


def test_tool_dispatch_checks_stop_event_before_execution():
    source = Path('src/agent_code/agent.py').read_text(encoding='utf-8')
    assert 'Stopped by user before tool execution.' in source
    assert 'if self._stop_event.is_set():' in source
