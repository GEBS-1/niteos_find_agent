from __future__ import annotations

from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def ssh_connect(env: dict[str, str]) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        env["SSH_HOST"],
        port=int(env.get("SSH_PORT") or 22),
        username=env["SSH_USER"],
        password=env["SSH_PASSWORD"],
        timeout=30,
        banner_timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    transport = client.get_transport()
    if transport is not None:
        transport.set_keepalive(15)
    return client


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 120) -> tuple[int, str]:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    channel = stdout.channel
    channel.settimeout(timeout)
    out_chunks: list[str] = []
    err_chunks: list[str] = []
    deadline = __import__("time").time() + timeout
    while True:
        if channel.recv_ready():
            out_chunks.append(channel.recv(65535).decode("utf-8", "replace"))
            continue
        if channel.recv_stderr_ready():
            err_chunks.append(channel.recv_stderr(65535).decode("utf-8", "replace"))
            continue
        if channel.exit_status_ready():
            while channel.recv_ready():
                out_chunks.append(channel.recv(65535).decode("utf-8", "replace"))
            while channel.recv_stderr_ready():
                err_chunks.append(channel.recv_stderr(65535).decode("utf-8", "replace"))
            break
        if __import__("time").time() > deadline:
            channel.close()
            raise TimeoutError(f"command timed out after {timeout}s: {cmd[:80]}")
        __import__("time").sleep(0.2)
    code = channel.recv_exit_status()
    return code, ("".join(out_chunks) + "".join(err_chunks))
