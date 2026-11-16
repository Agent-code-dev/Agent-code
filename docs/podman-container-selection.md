# Selecting an Agent Code Podman container

Open **Settings → Sandbox**, enable **Use Podman sandbox**, then use **Refresh containers** to discover compatible Podman containers.

Agent Code offers its workspace-specific managed Alpine container by default. Other containers appear only when their existing Podman configuration mounts the current Agent Code project directory **read-write at `/workspace`**. This restriction ensures shell commands, file tools, and background commands all operate on the same project directory rather than silently editing an unrelated filesystem.

Choose a container and click **Use selected container**. Then start it if necessary. Agent Code executes supported shell and background commands in that selected container. The container must have `bash` installed. Containers are not modified to add mounts; if a container does not have the required workspace mount, it is not selectable. Create a compatible container with the project mounted at `/workspace`, or use the managed Alpine container.

The selected container name is saved in Agent Code settings and is shared by the WebUI, desktop UI, and server because they use the same engine configuration. Selecting a container does not grant additional host access or change its Podman security settings.

**Remove selected** removes the selected container itself. It does not remove host project files stored in the mounted workspace. Use this action carefully because container-local data that is not in the mounted project directory may be lost.
