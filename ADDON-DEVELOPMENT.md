# Agent Code Add-on Development API

Add-ons are trusted Python extensions stored in the per-user `addons/<id>/` directory. Each add-on contains `addon.json` and `addon.py`; helper modules and packages may live beside them.

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "description": "Adds a custom workspace and alternate Skill Store client",
  "author": "Developer"
}
```

```python
class AlternateSkillStore:
    base_url = "https://my-store.example/api"

    def list_skills(self):
        ...


def build_sidebar_button(parent, app):
    import customtkinter as ctk
    return ctk.CTkButton(parent, text="My workspace",
                         command=lambda: app.log_line("Workspace opened", "dim"))


def register(api):
    # Build arbitrary CustomTkinter widgets in supported application regions.
    api.register_ui("my-workspace", build_sidebar_button,
                    location="sidebar", label="My workspace")

    # Replace a named service when the relevant core integration opts in.
    api.register_service("skill_store", AlternateSkillStore(),
                         replaces=True, priority=50)

    # Add custom agent tools, slash commands, actions and lifecycle hooks too.
    api.on("tools_loaded", lambda **ctx: None)
```

## UI extension points

`register_ui(name, builder, location=..., label=..., description=...)` supports `sidebar`, `addons`, `settings`, `toolbar`, and `workspace`. The builder receives `(parent, app)` and should return a Tk/CustomTkinter widget. The host places the returned widget. Keep builders fast and do not block the UI thread.

## Service extensions

`register_service(name, implementation, replaces=False, priority=0, description="")` registers a named service implementation. `AddonManager.resolve_service(name, default, app=...)` returns the highest-priority registered implementation, or the supplied default. Factories can set `addon_service_factory = True` and accept `app`.

Service names are explicit extension points, not arbitrary monkey-patching of core globals. Core integrations must call `resolve_service` for a service before an add-on can replace it. Add-ons should document the interface they implement. Existing services remain the default when no add-on replacement is registered.

## Trust and safety

Python add-ons execute with the user's operating-system permissions. They are not sandboxed. Install only code you trust. A future add-on repository should support signatures, hashes, compatibility metadata, permission declarations and review before installation. Disabling an add-on prevents its code from being imported on the next load; it does not reverse changes an already-loaded add-on made outside the API.
