# Desktop and WebUI interfaces

The local desktop application uses CustomTkinter and launches with:

```bash
agent-code
```

The browser-based interface is a separate authenticated server. Start it with:

```bash
agent-code server
```

The server serves the shared HTML, CSS, and JavaScript assets to remote browsers. It does not embed a browser window in the desktop application and does not require pywebview. See [Server mode](server-mode.md) for authentication and network security guidance.
