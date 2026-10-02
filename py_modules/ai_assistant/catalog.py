"""Provider kinds. Add a new entry here and a stream implementation to support another backend."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProviderKind:
    kind: str
    label: str
    description: str
    default_base_url: str
    default_model: str
    # required: an API key or OAuth token is needed. optional: a key may be set. none: no key.
    auth: str
    # none, openai, or google. OAuth is only set when the provider publishes a real flow.
    oauth: str


KINDS: dict[str, ProviderKind] = {
    item.kind: item
    for item in (
        ProviderKind(
            kind="openai",
            label="OpenAI / ChatGPT",
            description=(
                "Platform API key is the supported way for third-party apps to call models. "
                "Device-code and PKCE sign-in are also implemented against OpenAI's published "
                "auth endpoints when you supply an OAuth client ID."
            ),
            default_base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            auth="required",
            oauth="openai",
        ),
        ProviderKind(
            kind="anthropic",
            label="Anthropic Claude",
            description=(
                "API key from the Anthropic console. Anthropic does not offer OAuth for "
                "third-party apps to call the Claude API."
            ),
            default_base_url="https://api.anthropic.com",
            default_model="claude-sonnet-4-5",
            auth="required",
            oauth="none",
        ),
        ProviderKind(
            kind="gemini",
            label="Google Gemini",
            description=(
                "AI Studio API key, or Google OAuth (device code or PKCE) with your own "
                "OAuth client from Google Cloud."
            ),
            default_base_url="https://generativelanguage.googleapis.com/v1beta",
            default_model="gemini-2.5-flash",
            auth="required",
            oauth="google",
        ),
        ProviderKind(
            kind="hermes",
            label="Nous Hermes",
            description=(
                "OpenAI-compatible chat. Defaults to OpenRouter. Point the base URL at any "
                "other OpenAI-compatible Hermes endpoint if you prefer."
            ),
            default_base_url="https://openrouter.ai/api/v1",
            default_model="nousresearch/hermes-4-70b",
            auth="required",
            oauth="none",
        ),
        ProviderKind(
            kind="ollama",
            label="Ollama",
            description="Local or LAN Ollama server. Models are read from /api/tags.",
            default_base_url="http://127.0.0.1:11434",
            default_model="",
            auth="optional",
            oauth="none",
        ),
        ProviderKind(
            kind="llamacpp",
            label="llama.cpp server",
            description="llama.cpp's OpenAI-compatible server (typically port 8080, path /v1).",
            default_base_url="http://127.0.0.1:8080/v1",
            default_model="",
            auth="optional",
            oauth="none",
        ),
        ProviderKind(
            kind="custom",
            label="Custom OpenAI-compatible",
            description="Any server that implements POST /chat/completions and GET /models.",
            default_base_url="",
            default_model="",
            auth="optional",
            oauth="none",
        ),
    )
}


def catalog_payload() -> list[dict[str, str]]:
    return [asdict(kind) for kind in KINDS.values()]


def get_kind(kind: str) -> ProviderKind:
    try:
        return KINDS[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown provider type: {kind}") from exc
