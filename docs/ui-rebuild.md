# Agent Code 2.3.0 — Workspace UI

The authenticated `agent-code server` serves the standalone WebUI using the shared HTML, CSS, JavaScript, and `AgentWebAPI` implementation. The desktop app is CustomTkinter and does not embed this WebUI.

## Pages

- **Chat:** task-first conversation, file/image attachments, Plan/Build/Max mode, Stop/Continue, chat export/search/clear, meaningful activity preview.
- **Tasks & plans:** current todo checklist, saved task history, resume/rerun, and checkpoint previews.
- **Project blueprint:** edit the persistent `.agent-code/blueprint.json` project intent document.
- **Workspace:** bounded directory browsing and safe text-file previews. Hidden directories, sensitive paths, symbolic links, binary files, and oversized files are excluded.
- **Skills, Add-ons, Extension Store, MCP:** existing Agent Code extension management through the shared engine.
- **Settings:** provider/model endpoint, saved provider profiles, execution mode, permission policy, Core Mode, Podman sandbox preference, activity detail preference, chat sync, repair attempts, desktop UI, and extension store endpoint.

## Keyboard shortcuts

- `Ctrl+K`: focus the task composer.
- `Ctrl+1`: return to Chat.
- `Enter`: send a task.
- `Shift+Enter`: add a newline.
- `Escape`: close an open dialog.

## Activity filtering

Streaming fragments (`stream_chunk`, `stream_end`, token deltas) are excluded from the visible Activity timeline. Task lifecycle events, tool operations, approvals, and meaningful progress messages remain visible.

## Security boundaries

Workspace previews resolve requested paths under the active workspace, reject symbolic links and path escapes, omit hidden/sensitive files, and cap preview size. Provider profile listings expose metadata and key counts only, never raw API keys. The remote server continues to require its authenticated session for every API call and asset.

## Terminal interface reliability

The Textual TUI now routes Ask User prompts through a modal and returns answers to the waiting agent worker. It also maps Add-ons navigation to the actual tab ID and clears the busy state in a `finally` path. The legacy curses TUI now treats terminal resize/closed-screen and input-timeout errors as recoverable, and guards terminal writes against Unicode/encoding failures.
