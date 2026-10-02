#!/usr/bin/env python3
"""LAN bridge that runs Claude Code on a PC and streams it to the Steam Deck plugin.

The Deck sends a shared secret and a prompt. This process runs the official
``claude -p --output-format stream-json`` CLI and forwards each JSON line.
Sign in on this computer with ``claude login`` or ``claude setup-token``
before starting the bridge. The bridge does not see or store that token.

Usage:
    export CLAUDE_BRIDGE_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
    python3 bridge/claude_bridge.py --host 0.0.0.0 --port 8765

Then set the plugin's bridge URL to http://<this-pc-lan-ip>:8765 and paste the
same secret into the provider. Use is subject to Anthropic's terms for Claude Code.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 1_000_000


def find_claude(explicit: str) -> str:
    if explicit:
        return explicit
    found = shutil.which("claude")
    if found:
        return found
    home = os.path.expanduser("~")
    for candidate in (
        os.path.join(home, ".local", "bin", "claude"),
        os.path.join(home, ".claude", "local", "claude"),
        "/usr/local/bin/claude",
        "/usr/bin/claude",
    ):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return ""


def claude_command(binary: str, model: str, system: str, resume: str) -> list[str]:
    command = [
        binary,
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--model",
        model or "sonnet",
        "--tools",
        "",
        "--permission-mode",
        "dontAsk",
    ]
    if resume:
        command.extend(["--resume", resume])
    if system.strip():
        command.extend(["--append-system-prompt", system])
    return command


def child_env() -> dict[str, str]:
    """Prefer the Claude subscription if an API key is also set in the shell."""
    env = dict(os.environ)
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
    ):
        env.pop(name, None)
    return env


def _authorized(header: str, supplied_header: str, secret: str) -> bool:
    supplied = ""
    if header.lower().startswith("bearer "):
        supplied = header[7:].strip()
    if not supplied:
        supplied = supplied_header.strip()
    if not supplied or not secret:
        return False
    return hmac.compare_digest(supplied, secret)


def make_handler(secret: str, binary: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0].rstrip("/") != "/health":
                self._json(404, {"error": "Not found"})
                return
            if not self._check_auth():
                return
            self._json(200, {"ok": True, "claude": bool(binary), "models": ["sonnet", "opus", "haiku"]})

        def do_POST(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0].rstrip("/") != "/v1/chat":
                self._json(404, {"error": "Not found"})
                return
            if not self._check_auth():
                return
            if not binary:
                self._json(503, {"error": "claude was not found on this computer"})
                return
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                self._json(400, {"error": "Bad Content-Length"})
                return
            if length <= 0 or length > MAX_BODY:
                self._json(400, {"error": "Request body is missing or too large"})
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                self._json(400, {"error": "Body must be JSON"})
                return
            if not isinstance(payload, dict):
                self._json(400, {"error": "Body must be a JSON object"})
                return
            prompt = str(payload.get("prompt") or "")
            if not prompt.strip():
                self._json(400, {"error": "Prompt is empty"})
                return
            model = str(payload.get("model") or "sonnet")
            system = str(payload.get("system") or "")
            resume = str(payload.get("session_id") or "")
            self._stream(prompt, model, system, resume)

        def log_message(self, fmt: str, *args: object) -> None:
            sys.stderr.write("bridge %s\n" % (fmt % args))

        def _check_auth(self) -> bool:
            ok = _authorized(
                self.headers.get("Authorization") or "",
                self.headers.get("X-AI-Assistant-Secret") or "",
                secret,
            )
            if not ok:
                self._json(401, {"error": "Shared secret was rejected"})
            return ok

        def _json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _stream(self, prompt: str, model: str, system: str, resume: str) -> None:
            proc = subprocess.Popen(
                claude_command(binary, model, system, resume),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                start_new_session=True,
                env=child_env(),
            )
            try:
                assert proc.stdin is not None and proc.stdout is not None

                def _write() -> None:
                    try:
                        if proc.stdin is not None:
                            proc.stdin.write(prompt)
                            proc.stdin.close()
                    except Exception:
                        return

                threading.Thread(target=_write, daemon=True).start()
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for line in proc.stdout:
                    if not line.endswith("\n"):
                        line += "\n"
                    data = line.encode("utf-8")
                    self.wfile.write(b"%x\r\n" % len(data))
                    self.wfile.write(data)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                if proc.poll() is None:
                    try:
                        os.killpg(proc.pid, 15)
                    except OSError:
                        proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(proc.pid, 9)
                        except OSError:
                            proc.kill()

    return Handler


def serve(host: str, port: int, secret: str, binary: str) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(secret, binary))
    print(f"Claude Code bridge listening on http://{host}:{port}", file=sys.stderr)
    if host in {"0.0.0.0", "::"}:
        print("Bound to every interface. Prefer your LAN address and a firewall rule.", file=sys.stderr)
    server.serve_forever()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Stream Claude Code to the AI Assistant Decky plugin.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--secret", default="", help="Shared secret. Prefer CLAUDE_BRIDGE_SECRET so it is not in the process list.")
    parser.add_argument("--claude", default="", help="Path to the claude binary. Defaults to PATH.")
    args = parser.parse_args(argv)
    secret = os.environ.get("CLAUDE_BRIDGE_SECRET") or args.secret
    if not secret or len(secret) < 16:
        raise SystemExit("Set CLAUDE_BRIDGE_SECRET or --secret to a random string of at least 16 characters.")
    binary = find_claude(args.claude)
    if not binary:
        print("warning: claude was not found. /health will report claude: false until it is installed.", file=sys.stderr)
    serve(args.host, args.port, secret, binary)


if __name__ == "__main__":
    main()
