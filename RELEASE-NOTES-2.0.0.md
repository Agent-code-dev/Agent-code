# Agent Code 2.0.0 — Release Notes

This release consolidates the Agent Code desktop application, native Skills, MCP integration, Add-ons framework, task experience improvements, token/context handling, SSH permission fixes, browser selection, and HTML documentation.

## Architecture
- **Add-ons** extend the Agent Code application (Core, UI, and supported services).
- **Native Skills** provide tools and commands for the AI agent.
- **MCP** connects the agent to external tool servers.
- These systems remain separate and interoperable.

## User experience and reliability
- Collapsed activity details with concise working status.
- Cleaner conversation history and message composer.
- Task summaries and file-diff review support.
- Checkpoint and recovery improvements.
- Three-click force-stop behavior that interrupts agent communication/work without intentionally closing the browser application.
- SSH permission handling aligned with the selected permission mode.

## Efficiency and provider handling
- Reduced main-agent prompt and context overhead.
- Compact tool-result handling for provider/service errors.
- Bounded retry handling for transient provider failures.

## Documentation
See `docs/index.html`, `docs/skills.html`, and `docs/addons.html`.

## Licensing
The Agent Code application is MIT licensed. The standalone `server/` component is separately licensed under AGPL-3.0-only; its license is included in `server/LICENSE`. Do not treat the server component as MIT licensed.

## Validation notes
The release was checked for Python syntax, archive integrity, and the available automated regression tests. Two test modules could not be collected in the packaging environment because `customtkinter` was not installed; the remaining collected suite passed. Live GUI and real provider/SSH integration tests were not performed as part of this packaging run.
