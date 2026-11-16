# Workspace IDE

The authenticated Agent Code Server WebUI now includes a lightweight workspace IDE. Open **Workspace** to browse the active project, select a text file, edit it, and save it. Use **New file** to create a relative path inside the workspace.

Safety boundaries: file operations are confined to the active workspace; absolute paths, `..` traversal, symbolic links, credential-like paths (`.env`, `.ssh`, `.aws`, credentials, secrets, SSH private keys), and files over 500 KB are rejected. Files are saved as UTF-8 using an atomic temporary-file replacement. This is a lightweight editor, not a full language server or debugger.
