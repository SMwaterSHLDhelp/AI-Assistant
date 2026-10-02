"""Real OAuth device-code and PKCE flows for providers that publish them.

OpenAI: device authorization and token endpoints documented by OpenAI's auth
server (the same endpoints their open-source CLI calls). PKCE uses the
authorization-code endpoints published for registered clients. This plugin does
not embed another application's client ID.

Google: the OAuth 2.0 device flow and the installed-app PKCE flow. The user
creates their own OAuth client in Google Cloud. API keys remain the simpler path.
"""

from __future__ import annotations

import base64
import hashlib
import html
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from .http_util import HttpError, request_json

OPENAI_ISSUER = "https://auth.openai.com"
GOOGLE_DEVICE_URL = "https://oauth2.googleapis.com/device/code"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
# Google's Gemini OAuth quickstart requests cloud-platform because generateContent
# has no narrower public scope. The README tells users to prefer an API key.
GOOGLE_SCOPES = " ".join(
    (
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/generative-language.retriever",
    )
)
OPENAI_PKCE_SCOPES = "openid profile email offline_access"
# Public Grok CLI client. xAI's OpenID discovery document
# (https://auth.x.ai/.well-known/openid-configuration) advertises the device-code
# grant and token auth method "none", so a public client does not use a secret.
# Hermes Agent, OpenCode, and others call this same client. It is not Hermes's
# private credential. See https://github.com/NousResearch/hermes-agent
XAI_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
XAI_SCOPES = "openid profile email offline_access grok-cli:access api:access"
XAI_DEVICE_URL = "https://auth.x.ai/oauth2/device/code"
XAI_TOKEN_URL = "https://auth.x.ai/oauth2/token"
XAI_DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
PKCE_PORT_OPENAI = 8137
PKCE_PORT_GOOGLE = 8138
_LOGIN_TIMEOUT = 15 * 60


class OAuthError(Exception):
    pass


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def openai_device_start(client_id: str) -> dict[str, Any]:
    if not client_id:
        raise OAuthError("Paste an OpenAI OAuth client ID first. An API key does not need one.")
    payload = request_json(
        "POST",
        f"{OPENAI_ISSUER}/api/accounts/deviceauth/usercode",
        payload={"client_id": client_id},
        timeout=20,
    )
    if not isinstance(payload, dict) or not payload.get("user_code") or not payload.get("device_auth_id"):
        raise OAuthError("OpenAI did not return a device code. This client ID may not be enabled for device login.")
    interval = payload.get("interval") or 5
    try:
        interval_s = max(int(str(interval).strip()), 1)
    except ValueError:
        interval_s = 5
    return {
        "device_auth_id": str(payload["device_auth_id"]),
        "user_code": str(payload["user_code"]),
        "interval": interval_s,
        "verification_url": f"{OPENAI_ISSUER}/codex/device",
    }


def openai_device_poll(client_id: str, device_auth_id: str, user_code: str) -> dict[str, Any] | None:
    """Return token fields when approved, or None while the user has not finished."""
    try:
        payload = request_json(
            "POST",
            f"{OPENAI_ISSUER}/api/accounts/deviceauth/token",
            payload={"device_auth_id": device_auth_id, "user_code": user_code},
            timeout=20,
        )
    except HttpError as exc:
        if exc.status in {403, 404}:
            return None
        raise OAuthError(str(exc)) from exc
    if not isinstance(payload, dict) or not payload.get("authorization_code"):
        return None
    return exchange_openai_code(
        client_id=client_id,
        code=str(payload["authorization_code"]),
        code_verifier=str(payload.get("code_verifier") or ""),
        redirect_uri=f"{OPENAI_ISSUER}/deviceauth/callback",
    )


def openai_authorize_url(client_id: str, redirect_uri: str, challenge: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": OPENAI_PKCE_SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "resource": "https://api.openai.com/v1",
        }
    )
    return f"{OPENAI_ISSUER}/api/accounts/authorize?{query}"


def google_device_start(client_id: str) -> dict[str, Any]:
    if not client_id:
        raise OAuthError("Paste a Google OAuth client ID first. An AI Studio API key does not need one.")
    payload = request_json(
        "POST",
        GOOGLE_DEVICE_URL,
        form={"client_id": client_id, "scope": GOOGLE_SCOPES},
        timeout=20,
    )
    if not isinstance(payload, dict) or not payload.get("device_code"):
        raise OAuthError("Google did not start a device login. Use a TV and Limited Input OAuth client.")
    return {
        "device_code": str(payload["device_code"]),
        "user_code": str(payload.get("user_code") or ""),
        "verification_url": str(payload.get("verification_url") or "https://www.google.com/device"),
        "interval": max(int(payload.get("interval") or 5), 1),
    }


def google_device_poll(client_id: str, client_secret: str, device_code: str) -> dict[str, Any] | None:
    if not client_secret:
        raise OAuthError("Google's device flow needs the client secret from your OAuth client.")
    try:
        payload = request_json(
            "POST",
            GOOGLE_TOKEN_URL,
            form={
                "client_id": client_id,
                "client_secret": client_secret,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=20,
        )
    except HttpError as exc:
        message = str(exc)
        if "authorization_pending" in message:
            return None
        if "slow_down" in message:
            raise OAuthError("slow_down") from exc
        raise OAuthError(message) from exc
    return _token_fields(payload)


def google_authorize_url(client_id: str, redirect_uri: str, challenge: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": GOOGLE_SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    return f"{GOOGLE_AUTH_URL}?{query}"


def exchange_google_code(
    client_id: str,
    client_secret: str,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> dict[str, Any]:
    form = {
        "client_id": client_id,
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    if client_secret:
        form["client_secret"] = client_secret
    try:
        payload = request_json("POST", GOOGLE_TOKEN_URL, form=form, timeout=20)
    except HttpError as exc:
        raise OAuthError(str(exc)) from exc
    return _token_fields(payload)


def refresh_access_token(provider: dict[str, Any]) -> dict[str, Any] | None:
    """Return new token fields when a refresh token is present and the access token is expiring."""
    refresh = str(provider.get("oauth_refresh_token") or "")
    if not refresh:
        return None
    expires_at = int(provider.get("oauth_expires_at") or 0)
    if expires_at and expires_at > time.time() + 60:
        return None
    kind = provider.get("kind")
    client_id = str(provider.get("oauth_client_id") or "")
    client_secret = str(provider.get("oauth_client_secret") or "")
    try:
        if kind == "google":
            form = {
                "client_id": client_id,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            }
            if client_secret:
                form["client_secret"] = client_secret
            payload = request_json("POST", GOOGLE_TOKEN_URL, form=form, timeout=20)
        elif kind == "openai":
            payload = request_json(
                "POST",
                f"{OPENAI_ISSUER}/oauth/token",
                form={
                    "client_id": client_id,
                    "refresh_token": refresh,
                    "grant_type": "refresh_token",
                },
                timeout=20,
            )
        elif kind == "xai":
            payload = request_json(
                "POST",
                XAI_TOKEN_URL,
                form={
                    "client_id": XAI_CLIENT_ID,
                    "refresh_token": refresh,
                    "grant_type": "refresh_token",
                },
                timeout=20,
            )
        else:
            return None
    except HttpError as exc:
        raise OAuthError(str(exc)) from exc
    fields = _token_fields(payload)
    if not fields.get("refresh_token"):
        fields["refresh_token"] = refresh
    return fields


def wait_for_redirect(
    port: int,
    expected_state: str,
    cancel: threading.Event,
    timeout: float = _LOGIN_TIMEOUT,
) -> str:
    """Listen on 127.0.0.1 only until the provider redirects back with a code."""
    result: dict[str, str] = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib name
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path.rstrip("/") == "/cancel":
                cancel.set()
                done.set()
                self._reply(200, "Login cancelled. You can close this window.")
                return
            query = urllib.parse.parse_qs(parsed.query)
            state = (query.get("state") or [""])[0]
            if state != expected_state:
                self._reply(400, "This login link does not match the one AI Assistant started.")
                return
            error = (query.get("error") or [""])[0]
            if error:
                result["error"] = error
                done.set()
                self._reply(400, "Sign-in was not completed. You can close this window.")
                return
            code = (query.get("code") or [""])[0]
            if not code:
                self._reply(400, "The provider did not include a code. You can close this window.")
                return
            result["code"] = code
            done.set()
            self._reply(200, "Signed in. You can close this window and return to your Steam Deck.")

        def log_message(self, fmt: str, *args: Any) -> None:
            # The query string contains the authorization code. Never log it.
            return

        def _reply(self, status: int, text: str) -> None:
            body = (
                "<!doctype html><meta charset=utf-8><title>AI Assistant</title><p>"
                + html.escape(text)
                + "</p>"
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    try:
        server = HTTPServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        raise OAuthError(
            f"Port {port} is already in use. Close the other login window and try again."
        ) from exc
    server.timeout = 0.5
    try:
        deadline = time.time() + timeout
        while not done.is_set() and not cancel.is_set() and time.time() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    if cancel.is_set():
        raise OAuthError("Login cancelled")
    if result.get("error"):
        raise OAuthError(f"Sign-in failed: {result['error']}")
    if not result.get("code"):
        raise OAuthError("Login timed out before the browser redirected back")
    return result["code"]


def exchange_openai_code(*, client_id: str, code: str, code_verifier: str, redirect_uri: str) -> dict[str, Any]:
    form = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": redirect_uri,
    }
    if code_verifier:
        form["code_verifier"] = code_verifier
    try:
        payload = request_json("POST", f"{OPENAI_ISSUER}/oauth/token", form=form, timeout=20)
    except HttpError as first_error:
        # Fall back only when that token URL is not the one this client uses.
        # Any other status may mean the one-time code was already consumed.
        if first_error.status != 404:
            raise OAuthError(str(first_error)) from first_error
        try:
            payload = request_json(
                "POST",
                f"{OPENAI_ISSUER}/api/accounts/oauth/token",
                form=form,
                timeout=20,
            )
        except HttpError as exc:
            raise OAuthError(str(exc)) from exc
    return _token_fields(payload)


def xai_device_start() -> dict[str, Any]:
    """Start xAI's published device-code grant. No client secret is sent."""
    try:
        payload = request_json(
            "POST",
            XAI_DEVICE_URL,
            form={"client_id": XAI_CLIENT_ID, "scope": XAI_SCOPES},
            timeout=20,
        )
    except HttpError as exc:
        raise OAuthError(str(exc)) from exc
    if not isinstance(payload, dict) or not payload.get("device_code") or not payload.get("user_code"):
        raise OAuthError("xAI did not return a device code.")
    url = str(payload.get("verification_uri_complete") or payload.get("verification_uri") or "")
    if not url:
        raise OAuthError("xAI did not return a verification page.")
    try:
        interval = int(payload.get("interval") or 5)
    except (TypeError, ValueError):
        interval = 5
    try:
        expires_in = int(payload.get("expires_in") or 900)
    except (TypeError, ValueError):
        expires_in = 900
    return {
        "device_code": str(payload["device_code"]),
        "user_code": str(payload["user_code"]),
        "verification_url": url,
        "interval": max(interval, 1),
        "expires_in": max(expires_in, 30),
        "message": "Open the verification page and enter the code. This signs in with your xAI account.",
    }


def xai_device_poll(device_code: str) -> dict[str, Any] | None:
    try:
        payload = request_json(
            "POST",
            XAI_TOKEN_URL,
            form={
                "client_id": XAI_CLIENT_ID,
                "device_code": device_code,
                "grant_type": XAI_DEVICE_GRANT,
            },
            timeout=20,
        )
    except HttpError as exc:
        message = str(exc)
        if "authorization_pending" in message:
            return None
        if "slow_down" in message:
            raise OAuthError("slow_down") from exc
        if "access_denied" in message or "authorization_denied" in message:
            raise OAuthError("xAI denied the sign-in.") from exc
        if "expired_token" in message:
            raise OAuthError("That xAI code expired. Start sign-in again.") from exc
        raise OAuthError(message) from exc
    return _token_fields(payload)


def _token_fields(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise OAuthError("The provider did not return an access token")
    expires_in = int(payload.get("expires_in") or 3600)
    return {
        "access_token": str(payload["access_token"]),
        "refresh_token": str(payload.get("refresh_token") or ""),
        "expires_at": int(time.time()) + max(expires_in, 0),
    }
