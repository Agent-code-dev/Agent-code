from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src" / "agent_code" / "agent.py"
TEXT = SOURCE.read_text(encoding="utf-8")


def test_composer_uses_full_width_editor_and_separate_footer():
    assert 'self.entry.grid(row=0, column=0, columnspan=3, sticky="ew"' in TEXT
    assert 'footer.grid(row=1, column=0, columnspan=3, sticky="ew"' in TEXT
    assert 'text="＋ Attach"' in TEXT
    assert 'Enter to send  ·  Shift + Enter for a new line' in TEXT


def test_continue_control_uses_same_grid_manager_as_composer_footer():
    assert 'self.continue_btn.grid_remove()' in TEXT
    assert 'self.continue_btn.grid()' in TEXT
    assert 'self.continue_btn.pack()' not in TEXT


def test_quiet_activity_mode_shows_only_project_working_status():
    assert '"Working in project" if not self._show_activity_details else "Working…"' in TEXT
