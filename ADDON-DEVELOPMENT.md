# Agent Code Add-on Development API

Add-ons are trusted Python extensions stored in the per-user `addons/<id>/` directory. Each add-on contains `addon.json` and `addon.py`; helper modules and packages may live beside them.

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "api_version": 1,
  "description": "Adds a custom workspace and alternate Skill Store client",
  "author": "Developer",
  "permissions": ["network"]
}
```

```python
class AlternateSkillStore:
    base_url = "https://my-store.example/api"

    def list_skills(self):
        ...


def build_classic_sidebar_button(parent, app):
    import customtkinter as ctk
    return ctk.CTkButton(parent, text="My workspace",
        command=lambda: app.log_line("Workspace opened", "dim"))


def register(api):
    # Classic CustomTkinter widget contribution.
    api.register_ui("my-workspace", build_classic_sidebar_button,
                    location="sidebar", label="My workspace", backend="tk")

    # WebUI contribution.
    api.register_web_component("workspace-card", location="addons",
        label="My workspace", html="<p>Workspace extension is active.</p>")


    # Replace a named service when the relevant core integration opts in.
    api.register_service("skill_store", AlternateSkillStore(),
                         replaces=True, priority=50)

    # Add custom agent tools, slash commands, actions and lifecycle hooks too.
    api.on("tools_loaded", lambda **ctx: None)
```

## Agent tool namespacing

Add-on tool authors should register a short, local function name such as
`search` or `write_file`. Agent Code automatically registers it as
`<addon-name>_<tool-name>` (for example `my_extension_search`). Do not add the
add-on prefix yourself. Core, Native Skill, MCP, Add-on, and future system tool
sources all pass through the global Unified Tool Namespace before their
schemas are sent to an AI provider. Duplicate local names across different
add-ons are therefore supported and remain bound to their own handlers.

## UI extension points

`register_ui(name, builder, location=..., label=..., description=...)` supports `sidebar`, `addons`, `settings`, `toolbar`, and `workspace`. The builder receives `(parent, app)` and should return a widget for its backend. Use `backend="tk"` for CustomTkinter widgets. The authenticated WebUI uses the declarative `register_web_component(...)` API for HTML/CSS/JavaScript components. Web components are rendered by the server WebUI Add-ons panel; Tk widget contributions remain available in the CustomTkinter desktop. Keep builders fast and do not block the UI thread.

## Service extensions

`register_service(name, implementation, replaces=False, priority=0, description="")` registers a named service implementation. `AddonManager.resolve_service(name, default, app=...)` returns the highest-priority registered implementation, or the supplied default. Factories can set `addon_service_factory = True` and accept `app`.

Service names are explicit extension points, not arbitrary monkey-patching of core globals. Core integrations must call `resolve_service` for a service before an add-on can replace it. Add-ons should document the interface they implement. Existing services remain the default when no add-on replacement is registered.

## Trust and safety

Python add-ons execute with the user's operating-system permissions. They are not sandboxed. Install only code you trust. The catalogue publishes SHA-256 hashes and the client verifies them when supplied. Publisher signatures are not implemented yet, and the server does not AI-review add-on code. Disabling an add-on prevents its code from being imported on the next load; it does not reverse changes an already-loaded add-on made outside the API. Declare requested capabilities in `addon.json` under `permissions`; this is informational metadata, not an OS sandbox or automatic permission enforcement.

## Add-on installation and store

Add-ons may be imported from a directory or installed from a ZIP containing `addon.json` and `addon.py` (at the archive root or in one enclosing directory). The desktop validates names, archive paths, file count, and expanded size before installation. Python add-ons are trusted executable code and are **not sandboxed**.

The Add-on Store client uses the same configurable HTTPS server as the Skills Store. Agent Code 2.3.0's `server/skill-server.py` implements `GET /addons?search=...`, `GET /addons/{name}`, `GET /addons/{name}/download`, admin-only `POST /addons`, and admin-only `DELETE /addons/{name}`. Update the deployed Skills Store server to this version to enable the catalogue. Publishing requires the server admin token; downloads include a SHA-256 value that the client verifies when supplied.


## Authenticated WebUI contributions

```python
def register(api):
    api.register_web_component(
        "status-card",
        label="Status card",
        description="A small status panel",
        location="addons",
        html='<div class="my-addon-status">Extension is active</div>',
        css='.my-addon-status { padding: 12px; border-radius: 10px; }',
        javascript='console.info("Example add-on component mounted")',
    )
```

Web components are trusted extension code and can run JavaScript inside the authenticated browser session. Only install add-ons you trust. The agent's Python tools, commands and hooks remain shared across the authenticated WebUI, CustomTkinter and terminal interfaces.
