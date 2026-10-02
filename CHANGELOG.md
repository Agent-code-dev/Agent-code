# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] — 2026-10-02

### Added
- Markdown rendering in the chat log — headers, bold, italic, inline code, fenced blocks, lists, links
- Claude Code-inspired workflow: `todo_write` for planning, read before edit, verify after
- New file tools: `edit_file`, `glob_files`, `grep_files`, `read_file` with line ranges
- New web tool: `web_fetch(url)` — URL to readable text
- Subagent tool (`task`) for isolated research with a fresh context
- Todo list (`todo_write` / `todo_read`) for multi-step tasks
- Permission modes: `readonly`, `ask`, `auto`
- New buttons: Clear, Copy last, Export, Todo
- Project context auto-loaded from `AGENT.md` / `CLAUDE.md` / `README.md`

### Changed
- Windows config moves to `%LOCALAPPDATA%\agent-code\`
- Polished dark UI — deeper background, framed log, layered panels
- Turn limit raised from 30 to 40
- Dual-mode `agent.py` — runs standalone or as an installed package

### Fixed
- `NameError` in Tkinter error callbacks during network failures
- `AttributeError: 'tkapp' object has no attribute 'flagged_only'` in the skill store
- Path resolution on NixOS, containers, and headless environments
- Cloud sync response handling across the HTTPS + IP fallback chain
- Browser self-test result now shown in the header

## [1.0.0] — 2026-09-29

### Added
- First public release on PyPI as `agent-code`
- Headless Chromium browser via DrissionPage
- Sandboxed shell with allowlist and workspace jail
- Stop / Continue buttons
- Local chat save + optional cloud sync
- Multi-key LLM rotation with custom base URL
- Settings, Skills, and two-pane Help dialogs
- Skill registry client (`agent-code manage`)
- Bundled skills: `filesystem`, `public_api`, `temp_mail`
- Developer guide: `docs/skills.html`
- Cross-platform: Windows, macOS, Linux