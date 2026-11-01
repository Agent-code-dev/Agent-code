---
name: browser
description: Headless Chromium via DrissionPage or Firefox via Selenium: navigate, read, click, type, scroll.
version: 1.0.0
author: agent-code
---

# browser

Headless Chromium wrapped as a skill. Cookies and history survive between
calls in the same agent session.

## Tools

| Tool | Arguments | What it does |
|---|---|---|
| `browser_navigate` | `url` | Open a URL. `https://` added if missing. |
| `browser_snapshot` | `max_chars` (default 6000) | Return visible body text. |
| `browser_click` | `selector` | Click an element by CSS selector. |
| `browser_type` | `selector`, `text` | Clear and type into an input. |
| `browser_links` | `limit` (default 30) | List anchor text and hrefs. |
| `browser_scroll` | `pixels` (default 800) | Scroll down. |

## Slash command

- `/browser-close` - shut down the headless Chromium process.

## Requirements

    pip install DrissionPage


## Firefox support

Automatic browser priority is Chrome/Chromium first, Firefox second, and WebDriver setup guidance as the final fallback. If both Chrome and Firefox are installed, Chrome is selected. Set `AGENT_CODE_BROWSER=chrome` or `AGENT_CODE_BROWSER=firefox` to override detection. Before first WebDriver startup, the user should approve installation of the optional WebDriver toolkit. Install the Python integration with `pip install agent-code`; Selenium Manager may fetch `geckodriver` on first use. The machine needs network access for that first-time download.
