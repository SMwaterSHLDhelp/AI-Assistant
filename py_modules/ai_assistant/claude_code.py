"""Claude Pro/Max chat through the official Claude Code CLI.

The plugin never talks to Anthropic's private OAuth endpoints and never sends the
subscription token itself. It runs ``claude -p`` and, for sign-in, ``claude setup-token``.
Auth is whatever Claude Code already accepts: an existing ``claude login``, a token from
``claude setup-token`` passed as ``CLAUDE_CODE_OAUTH_TOKEN``, or the same CLI on another
computer reached through the companion bridge.
"""

from __future__ import annotations

import json
import os
import pty
import re
import select
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

from .http_util import HttpError, iter_lines, join_url, request_json
from .redact import redact

MODEL_ALIASES: dict[str, str] = {
    "sonnet": "sonnet",
    "opus": "opus",
    "haiku": "haiku",
    "claude-sonnet": "sonnet",
    "claude-opus": "opus",
    "claude-haiku": "haiku",
}
MODEL_CHOICES: tuple[str, ...] = ("sonnet", "opus", "haiku")

INSTALL_HINT = (
    "Claude Code is not installed on this Deck (the claude command was not found). "
    "Install it from https://code.claude.com/docs/en/setup "
    "(the official installer, or npm install -g @anthropic-ai/claude-code). "
    "Then run claude login, or use Sign in with setup-token in provider settings. "
    "To skip Node on the Deck, run bridge/deckling_bridge.py on a PC and put that PC's URL in Bridge URL."
)

_LIMIT_MESSAGES = {
    "rate_limit": (
        "Claude Code hit a rate or usage limit on this subscription. "
        "Wait and try again, or check the plan's usage. This is not an API-key bill."
    ),
    "billing_error": (
        "Claude Code reported a billing or usage-limit error for this subscription. "
        "Check the Claude plan. The separate Anthropic provider is the one that uses an API key."
    ),
    "authentication_failed": (
        "Claude Code rejected the login. On this Deck run claude login, or Sign in with setup-token. "
        "If you use the bridge, sign in on the PC that runs it (claude login or claude setup-token)."
    ),
    "oauth_org_not_allowed": "This Claude account's organization is not allowed to use Claude Code.",
    "overloaded": "Claude is overloaded right now. Try again in a moment.",
    "model_not_found": "Claude Code does not recognize that model. Choose sonnet, opus, or haiku.",
    "max_output_tokens": "The reply hit Claude Code's output limit.",
    "invalid_request": "Claude Code rejected the request.",
    "server_error": "Claude Code could not reach Claude. Try again in a moment.",
}

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)")
_URL = re.compile(r"https://[^\s<>'\"\\)]+")
_CODE = re.compile(r"(?i)(?:user[ _-]?code|code|enter(?:\s+code)?)\s*[:#-]?\s*([A-Z0-9]{4,8}(?:-[A-Z0-9]{4,8})?)")
_TOKEN_LINE = re.compile(r"sk-ant-oat[A-Za-z0-9_-]*")
_TOKEN_PIECE = re.compile(r"[A-Za-z0-9_-]+")


class ClaudeCodeError(Exception):
    """A failure the chat panel should show as-is (already redacted)."""


def normalize_model(model: str) -> str:
    """Map the sonnet/opus/haiku aliases. Full model ids are passed through."""
    cleaned = (model or "").strip()
    mapped = MODEL_ALIASES.get(cleaned.lower())
    if mapped:
        return mapped
    return cleaned


def find_claude() -> str | None:
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
    return None


def is_remote(provider: dict[str, Any]) -> bool:
    return bool(str(provider.get("base_url") or "").strip())


def list_models(provider: dict[str, Any]) -> list[str]:
    if is_remote(provider):
        _check_bridge(provider)
        return list(MODEL_CHOICES)
    binary = find_claude()
    if not binary:
        raise ValueError(INSTALL_HINT)
    try:
        probe = subprocess.run(
            [binary, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
            stdin=subprocess.DEVNULL,
            env=subscription_env(None, str(provider.get("api_key") or "")),
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Claude Code did not answer claude --version. The install may be broken.") from exc
    if probe.returncode != 0:
        detail = redact((probe.stderr or probe.stdout or "").strip())[:300]
        raise ValueError(detail or "claude --version failed. Reinstall Claude Code and try again.")
    return list(MODEL_CHOICES)


def stream_text(
    provider: dict[str, Any],
    messages: list[dict[str, str]],
    model: str,
    cancel: threading.Event,
    meta: dict[str, Any] | None = None,
) -> Iterator[str]:
    chosen = normalize_model(model)
    if not chosen:
        raise ValueError("Choose sonnet, opus, or haiku")
    box = meta if meta is not None else {}
    resume = str(box.get("session_id") or "").strip()
    prompt, system = _prompt_and_system(messages, resume=bool(resume))
    if not prompt.strip():
        raise ValueError("Nothing to send")
    if is_remote(provider):
        yield from _stream_remote(provider, prompt, chosen, system, resume, cancel, box)
        return
    binary = find_claude()
    if not binary:
        raise ClaudeCodeError(INSTALL_HINT)
    yield from _stream_process(binary, prompt, chosen, system, resume, cancel, box, provider)


def run_setup_token(
    binary: str,
    cancel: threading.Event,
    on_update: Callable[[dict[str, str]], None],
    timeout: float = 15 * 60,
) -> str:
    """Run ``claude setup-token`` and return the token it prints. The token is not passed to ``on_update``."""
    if not binary:
        raise ClaudeCodeError(INSTALL_HINT)
    deadline = time.time() + timeout
    buffer = ""
    seen_url = ""
    seen_code = ""
    try:
        master, slave = pty.openpty()
    except OSError:
        master, slave = None, None
    if master is None or slave is None:
        proc = subprocess.Popen(
            [binary, "setup-token"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
    else:
        proc = subprocess.Popen(
            [binary, "setup-token"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave)
    try:
        while time.time() < deadline:
            if cancel.is_set():
                _kill(proc)
                raise ClaudeCodeError("Login cancelled")
            chunk = _read_setup_chunk(proc, master)
            if chunk:
                buffer += chunk
                url, code = login_hints(buffer)
                if url != seen_url or code != seen_code:
                    seen_url, seen_code = url, code
                    on_update(
                        {
                            "verification_url": url,
                            "user_code": code,
                            "message": _setup_message(url, code),
                        }
                    )
            if proc.poll() is not None:
                break
        else:
            _kill(proc)
            raise ClaudeCodeError("claude setup-token timed out. Start it again when you can approve it in a browser.")
        if master is not None:
            trailing = _drain_pty(master)
            if trailing:
                buffer += trailing
        elif proc.stdout is not None:
            rest = proc.stdout.read() or ""
            buffer += rest
        proc.wait(timeout=5)
    finally:
        if master is not None:
            os.close(master)
        if proc.poll() is None:
            _kill(proc)
    if cancel.is_set():
        raise ClaudeCodeError("Login cancelled")
    token = extract_setup_token(buffer)
    if token:
        return token
    if proc.returncode not in (0, None):
        raise ClaudeCodeError(
            "claude setup-token failed. "
            + (redact(_visible_tail(buffer)) or "Run it in a terminal and paste the token into the token field.")
        )
    raise ClaudeCodeError(
        "Claude Code exited without printing a token. "
        "Run claude setup-token in a terminal, then paste the token into the token field."
    )


def login_hints(text: str) -> tuple[str, str]:
    cleaned = _ANSI.sub("", text)
    urls = [item.rstrip(".,);") for item in _URL.findall(cleaned)]
    url = urls[0] if urls else ""
    code_match = _CODE.search(cleaned)
    code = code_match.group(1) if code_match else ""
    return url, code


def extract_setup_token(text: str) -> str:
    """Pull a setup-token value, including one the terminal wrapped across lines."""
    cleaned = _ANSI.sub("", text)
    match = _TOKEN_LINE.search(cleaned)
    if not match:
        return ""
    lines = cleaned[match.start() :].splitlines()
    first = _TOKEN_LINE.match(lines[0].strip())
    if not first:
        return ""
    token = first.group(0)
    for extra in lines[1:]:
        piece = extra.strip()
        if piece and _TOKEN_PIECE.fullmatch(piece):
            token += piece
            continue
        break
    if len(token) < 20:
        return ""
    return token


def explain_failure(category: str, detail: str) -> str:
    known = _LIMIT_MESSAGES.get(category)
    if known:
        return known
    lowered = f"{category} {detail}".lower()
    if any(phrase in lowered for phrase in ("rate limit", "rate_limit", "usage limit", "too many requests", "429")):
        return _LIMIT_MESSAGES["rate_limit"]
    if "usage" in lowered and "limit" in lowered:
        return _LIMIT_MESSAGES["billing_error"]
    if any(phrase in lowered for phrase in ("not logged in", "authentication", "unauthorized", "please run /login", "login expired")):
        return _LIMIT_MESSAGES["authentication_failed"]
    text = redact(detail).strip()
    if text:
        return text[:400]
    return "Claude Code failed without a message."


def subscription_env(base: dict[str, str] | None, token: str) -> dict[str, str]:
    """Child environment that prefers the Claude subscription over an API key."""
    env = dict(base or os.environ)
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
    ):
        env.pop(name, None)
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    return env


def claude_command(binary: str, model: str, system: str, resume: str) -> list[str]:
    command = [
        binary,
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--model",
        model,
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


def iter_stream_json(lines: Iterator[str], meta: dict[str, Any]) -> Iterator[str]:
    saw_delta = False
    failure = ""
    category = ""
    for raw in lines:
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        session_id = event.get("session_id")
        if isinstance(session_id, str) and session_id.strip():
            meta["claude_session_id"] = session_id.strip()
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "api_retry":
            category = str(event.get("error") or category)
            continue
        if kind == "stream_event":
            text = _text_delta(event.get("event"))
            if text:
                saw_delta = True
                yield text
            continue
        if kind != "result":
            continue
        result_text = event.get("result") if isinstance(event.get("result"), str) else ""
        errored = bool(event.get("is_error")) or str(event.get("subtype") or "") in {"error", "error_during_execution"}
        if errored:
            failure = explain_failure(category, result_text or str(event.get("error") or ""))
            continue
        if result_text and not saw_delta:
            saw_delta = True
            yield result_text
    if failure:
        raise ClaudeCodeError(failure)


def _text_delta(event: Any) -> str:
    if not isinstance(event, dict):
        return ""
    delta = event.get("delta")
    if isinstance(delta, dict) and delta.get("type") == "text_delta" and isinstance(delta.get("text"), str):
        return delta["text"]
    return ""


def _prompt_and_system(messages: list[dict[str, str]], *, resume: bool) -> tuple[str, str]:
    system_parts: list[str] = []
    conversation: list[dict[str, str]] = []
    for message in messages:
        if message.get("role") == "system":
            system_parts.append(message.get("content") or "")
        else:
            conversation.append(message)
    system = "\n\n".join(part.strip() for part in system_parts if part.strip())
    users = [item.get("content") or "" for item in conversation if item.get("role") == "user"]
    if resume:
        return (users[-1] if users else ""), system
    if len(conversation) == 1 and conversation[0].get("role") == "user":
        return conversation[0].get("content") or "", system
    lines = []
    for message in conversation:
        speaker = "Assistant" if message.get("role") == "assistant" else "User"
        lines.append(f"{speaker}: {message.get('content') or ''}")
    return "\n\n".join(lines), system


def _stream_process(
    binary: str,
    prompt: str,
    model: str,
    system: str,
    resume: str,
    cancel: threading.Event,
    meta: dict[str, Any],
    provider: dict[str, Any],
) -> Iterator[str]:
    command = claude_command(binary, model, system, resume)
    token = "" if is_remote(provider) else str(provider.get("api_key") or "")
    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env=subscription_env(None, token),
    )
    stderr: list[str] = []
    done = threading.Event()

    def _write() -> None:
        try:
            if proc.stdin is not None:
                proc.stdin.write(prompt)
                proc.stdin.close()
        except Exception:
            return

    def _stderr() -> None:
        if proc.stderr is None:
            return
        chunks: list[str] = []
        for line in proc.stderr:
            chunks.append(line)
            if sum(len(item) for item in chunks) > 4000:
                chunks = chunks[-20:]
        stderr.append("".join(chunks)[-4000:])

    def _watch() -> None:
        while not done.is_set():
            if cancel.is_set():
                _kill(proc)
                return
            done.wait(0.2)

    threading.Thread(target=_write, daemon=True).start()
    threading.Thread(target=_stderr, daemon=True).start()
    threading.Thread(target=_watch, daemon=True).start()
    assert proc.stdout is not None
    try:
        yield from iter_stream_json(proc.stdout, meta)
    finally:
        done.set()
        if cancel.is_set():
            _kill(proc)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _kill(proc)
            proc.wait(timeout=5)
    if cancel.is_set():
        return
    if proc.returncode not in (0, None) and not meta.get("claude_session_id"):
        detail = redact((stderr[0] if stderr else "").strip())
        raise ClaudeCodeError(detail or f"Claude Code exited with status {proc.returncode}.")


def _stream_remote(
    provider: dict[str, Any],
    prompt: str,
    model: str,
    system: str,
    resume: str,
    cancel: threading.Event,
    meta: dict[str, Any],
) -> Iterator[str]:
    secret = str(provider.get("api_key") or "")
    if not secret:
        raise ClaudeCodeError("Set the bridge shared secret. It is stored with the provider, mode 0600.")
    body = json.dumps(
        {"prompt": prompt, "model": model, "system": system, "session_id": resume}
    ).encode("utf-8")
    try:
        lines = iter_lines(
            "POST",
            join_url(str(provider.get("base_url")), "v1/chat"),
            headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
            body=body,
            timeout=300,
            cancel=cancel,
        )
        yield from iter_stream_json(lines, meta)
    except HttpError as exc:
        if exc.status == 401:
            raise ClaudeCodeError("The bridge rejected the shared secret.") from exc
        raise ClaudeCodeError(explain_failure("", str(exc))) from exc


def _check_bridge(provider: dict[str, Any]) -> None:
    secret = str(provider.get("api_key") or "")
    if not secret:
        raise ValueError("Set the bridge shared secret before testing the connection.")
    try:
        payload = request_json(
            "GET",
            join_url(str(provider.get("base_url")), "health"),
            headers={"Authorization": f"Bearer {secret}"},
            timeout=15,
        )
    except HttpError as exc:
        if exc.status == 401:
            raise ValueError("The bridge rejected the shared secret.") from exc
        raise
    if isinstance(payload, dict) and payload.get("claude") is False:
        raise ValueError(
            "The bridge is running, but that PC does not have the claude command. "
            "Install Claude Code there and sign in with claude login or claude setup-token."
        )


def _setup_message(url: str, code: str) -> str:
    if url and code:
        return (
            "Open the page and enter the code. Claude Code prints a token when you approve it. "
            "The token is saved on the Deck and is not shown here."
        )
    if url:
        return (
            "Open the page Claude Code printed and approve access. If it asks you to paste a code "
            "back into a terminal, paste the finished token into the token field instead."
        )
    return "Waiting for claude setup-token. If nothing appears, run it in a terminal and paste the token into the token field."


def _visible_tail(text: str) -> str:
    cleaned = _ANSI.sub("", text).strip()
    return cleaned[-300:]


def _read_setup_chunk(proc: subprocess.Popen[str], master: int | None) -> str:
    if master is None:
        if proc.stdout is None:
            return ""
        line = proc.stdout.readline()
        return line or ""
    readable, _, _ = select.select([master], [], [], 0.2)
    if not readable:
        return ""
    try:
        data = os.read(master, 4096)
    except OSError:
        return ""
    if not data:
        return ""
    return data.decode("utf-8", "replace")


def _drain_pty(master: int) -> str:
    chunks: list[str] = []
    while True:
        readable, _, _ = select.select([master], [], [], 0)
        if not readable:
            break
        try:
            data = os.read(master, 4096)
        except OSError:
            break
        if not data:
            break
        chunks.append(data.decode("utf-8", "replace"))
    return "".join(chunks)


def _kill(proc: subprocess.Popen[Any]) -> None:
    if proc.poll() is not None:
        return
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
