"""Quick-connect SSH command parser tests without importing the GUI stack."""
import ast
import os
import shlex
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src" / "agent_code" / "agent.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
NODE = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "parse_ssh_command")
NS = {"os": os, "shlex": shlex}
exec(compile(ast.Module(body=[NODE], type_ignores=[]), str(SOURCE), "exec"), NS)
parse_ssh_command = NS["parse_ssh_command"]


def test_parse_user_host_command():
    assert parse_ssh_command("ssh root@ubuntu-server.com") == {
        "host": "ubuntu-server.com", "username": "root", "port": 22,
        "key_filename": "", "config_file": os.path.expanduser("~/.ssh/config")
    }


def test_parse_port_identity_and_username_options():
    parsed = parse_ssh_command("ssh -p 2202 -i ~/.ssh/vm_key -l deploy vm.example")
    assert parsed["host"] == "vm.example"
    assert parsed["username"] == "deploy"
    assert parsed["port"] == 2202
    assert parsed["key_filename"] == os.path.expanduser("~/.ssh/vm_key")


def test_parse_custom_config_and_alias():
    parsed = parse_ssh_command("ssh -F ~/.ssh/other_config my-vm")
    assert parsed["host"] == "my-vm"
    assert parsed["config_file"] == os.path.expanduser("~/.ssh/other_config")


def test_reject_remote_command_and_unsafe_custom_options():
    import pytest
    with pytest.raises(ValueError, match="remote command"):
        parse_ssh_command("ssh root@host.example 'rm -rf /'")
    with pytest.raises(ValueError, match="ProxyCommand"):
        parse_ssh_command("ssh -o ProxyCommand=anything root@host.example")


def test_reject_bad_ports_and_non_ssh_input():
    import pytest
    with pytest.raises(ValueError, match="port"):
        parse_ssh_command("ssh -p 70000 root@host.example")
    with pytest.raises(ValueError, match="beginning with `ssh`"):
        parse_ssh_command("scp file host:/tmp")


def test_quick_connect_prompts_for_unknown_host_and_authentication():
    source = SOURCE.read_text(encoding="utf-8")
    assert "PromptHostKeyPolicy" in source
    assert "Verify SSH host" in source
    assert "SSH authentication" in source
    assert "Trust Once" in source
    assert "client.set_missing_host_key_policy(PromptHostKeyPolicy())" in source


def test_parser_uses_windows_quoting_rules_for_windows_paths():
    source = SOURCE.read_text(encoding="utf-8")
    assert 'posix=(os.name != "nt")' in source
    # shlex must preserve backslashes in a Windows identity-file path.
    parsed = shlex.split(r'ssh -i C:\Users\Alice\.ssh\id_ed25519 deploy@example.com', posix=False)
    assert parsed[2] == r'C:\Users\Alice\.ssh\id_ed25519'


def test_ssh_worker_uses_initialized_session_password_closure():
    source = SOURCE.read_text(encoding="utf-8")
    assert "session_password = self.ssh_password_entry.get() or None" in source
    assert "nonlocal session_password" in source
    assert "password=session_password, passphrase=session_password" in source
    assert "session_password = self._ssh_ui_prompt" in source



def test_remote_shell_uses_the_selected_permission_profile():
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    central = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_central_tool_permission")
    remote = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_remote_shell")
    central_text = ast.get_source_segment(source, central)
    remote_text = ast.get_source_segment(source, remote)
    # SSH is a core stateful tool: the central guard must not prompt before
    # _remote_shell applies the same permission profile as local commands.
    assert '"remote_shell"' in central_text
    assert 'self.permission != PERMISSION_AUTO' in remote_text
    assert 'getattr(self, "permission_mode", "ask")' not in remote_text
