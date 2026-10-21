#!/usr/bin/env python3
"""Launch the fixed Brocade audit with private transport inputs and output."""

import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

HOST = "192.168.0.251"


class PrerequisiteError(Exception):
    """A transport prerequisite has not been established."""


def private_path(path: Path, directory: bool = False) -> None:
    if (
        not path.is_absolute()
        or ".." in path.parts
        or any(p.is_symlink() for p in [path, *path.parents])
    ):
        raise PrerequisiteError(
            "private paths must be absolute and contain no symlinks"
        )
    try:
        info = path.stat()
    except OSError as error:
        raise PrerequisiteError("required private path is unavailable") from error
    expected = 0o700 if directory else 0o600
    correct_type = (
        stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    )
    if (
        not correct_type
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != expected
    ):
        raise PrerequisiteError(
            "private directory/file ownership or permissions are unsafe"
        )


def prepare(env: dict[str, str]) -> tuple[Path, dict[str, str]]:
    user = env.get("BROCADE_AUDIT_USER", "")
    password = env.get("BROCADE_AUDIT_PASSWORD", "")
    if (
        not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", user)
        or user.casefold() == "root"
        or not password
    ):
        raise PrerequisiteError(
            "dedicated non-root audit user and password are required"
        )
    if env.get("BROCADE_AUDIT_IDENTITY_VERIFIED") != "yes":
        raise PrerequisiteError(
            "operator verification of read-only identity is required"
        )
    if env.get("BROCADE_SERVER_KEY_VERIFIED") != "yes":
        raise PrerequisiteError(
            "operator/OOB verification of the exact server key is required"
        )
    key_path = Path(env.get("BROCADE_KNOWN_HOSTS", ""))
    runtime_parent = Path(env.get("BROCADE_RUNTIME_PRIVATE", ""))
    private_path(key_path)
    private_path(runtime_parent, directory=True)
    source = Path(__file__).resolve()
    checkout = next(
        (parent.parent for parent in source.parents if parent.name == "ansible"),
        source.parent,
    )
    if runtime_parent.is_relative_to(checkout):
        raise PrerequisiteError("runtime output must be outside the project checkout")
    # The pinned transport also reads these global files; accept no additional pins.
    for name in ["/etc/ssh/ssh_known_hosts", "/etc/openssh/ssh_known_hosts"]:
        global_keys = Path(name)
        if global_keys.exists() and global_keys.stat().st_size:
            raise PrerequisiteError(
                "execution environment contains unexpected global host keys"
            )
    from paramiko.hostkeys import HostKeyEntry, InvalidHostKey
    from paramiko.ssh_exception import SSHException

    try:
        lines = key_path.read_text().splitlines()
        if len(lines) != 1:
            raise ValueError
        entry = HostKeyEntry.from_line(lines[0])
        if entry is None or entry.hostnames != [HOST] or entry.key is None:
            raise ValueError
        if entry.key.get_name() != "ssh-rsa":
            raise ValueError
    except (OSError, UnicodeError, ValueError, SSHException, InvalidHostKey) as error:
        raise PrerequisiteError(
            "known_hosts must contain one valid exact-host RSA server pin"
        ) from error
    runtime = Path(tempfile.mkdtemp(prefix="brocade-audit-", dir=runtime_parent))
    ssh = runtime / ".ssh"
    ssh.mkdir(mode=0o700)
    (ssh / "known_hosts").write_text(lines[0] + "\n")
    (ssh / "known_hosts").chmod(0o600)
    config = runtime / "ansible.cfg"
    config.write_text(
        "[defaults]\nhost_key_checking = True\nretry_files_enabled = False\n"
        f"cliconf_plugins = {source.parent / 'cliconf_plugins'}\n"
        f"terminal_plugins = {source.parent / 'terminal_plugins'}\n"
        "[paramiko_connection]\nhost_key_auto_add = False\n"
        "[persistent_connection]\nssh_type = paramiko\nhost_key_checking = True\n"
        "log_messages = False\n"
    )
    config.chmod(0o600)
    inventory = runtime / "inventory.json"
    inventory.write_text(
        json.dumps({"all": {"hosts": {"brocade_audit": {"ansible_host": HOST}}}})
    )
    inventory.chmod(0o600)
    child = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(runtime),
        "ANSIBLE_CONFIG": str(config),
        "ANSIBLE_LOCAL_TEMP": str(runtime / "tmp"),
        "ANSIBLE_REMOTE_TEMP": str(runtime / "remote-tmp"),
        "ANSIBLE_PERSISTENT_CONTROL_PATH_DIR": str(runtime / "pc"),
        "ANSIBLE_HOST_KEY_CHECKING": "True",
        "ANSIBLE_SSH_HOST_KEY_CHECKING": "True",
        "ANSIBLE_HOST_KEY_AUTO_ADD": "False",
        "ANSIBLE_PERSISTENT_LOG_MESSAGES": "False",
        "BROCADE_AUDIT_USER": user,
        "BROCADE_AUDIT_PASSWORD": password,
        "BROCADE_AUDIT_OUTPUT": str(runtime / "audit-capture.json"),
    }
    return runtime, child


def main() -> int:
    os.umask(0o077)
    try:
        runtime, env = prepare(dict(os.environ))
    except (PrerequisiteError, ImportError):
        print(
            "Audit prerequisites failed before transport; check private identity/key/runtime inputs.",
            file=sys.stderr,
        )
        return 2
    command = [
        "ansible-playbook",
        "-i",
        str(runtime / "inventory.json"),
        str(Path(__file__).with_name("audit.yml")),
    ]
    result = subprocess.run(command, env=env, capture_output=True, check=False)
    # Never echo callback output: failures can contain device output or credentials.
    if result.returncode:
        try:
            fd = os.open(
                runtime / "audit-process-output.json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            with os.fdopen(fd, "w") as output:
                json.dump(
                    {
                        "exit_code": result.returncode,
                        "stdout": result.stdout.decode(errors="replace"),
                        "stderr": result.stderr.decode(errors="replace"),
                    },
                    output,
                )
        except OSError:
            print("Private failure diagnostics unavailable.", file=sys.stderr)
    print(f"Audit process exited {result.returncode}; private runtime: {runtime}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
