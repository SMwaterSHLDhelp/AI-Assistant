from ai_assistant.oauth import google_authorize_url, openai_authorize_url, pkce_pair
from ai_assistant.providers import list_models
from ai_assistant.sse import iter_json_lines, iter_sse_json


def test_sse_joins_data_and_stops_at_done() -> None:
    lines = [
        "event: content_block_delta",
        'data: {"type":"content_block_delta","delta":{"text":"Hi"}}',
        "",
        "data: [DONE]",
        "",
        'data: {"ignored":true}',
    ]
    events = list(iter_sse_json(iter(lines)))
    assert events == [{"type": "content_block_delta", "delta": {"text": "Hi"}}]


def test_ollama_json_lines() -> None:
    lines = [
        '{"message":{"content":"A"}}',
        "",
        '{"message":{"content":"B"},"done":true}',
    ]
    events = list(iter_json_lines(iter(lines)))
    assert events[0]["message"]["content"] == "A"
    assert events[1]["done"] is True


def test_pkce_challenge_matches_verifier() -> None:
    import base64
    import hashlib

    verifier, challenge = pkce_pair()
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    assert challenge == expected
    assert "=" not in challenge


def test_authorize_urls_use_real_endpoints() -> None:
    openai = openai_authorize_url("client-123", "http://127.0.0.1:8137/auth/callback", "chal", "state1")
    assert openai.startswith("https://auth.openai.com/api/accounts/authorize?")
    assert "client_id=client-123" in openai
    assert "code_challenge_method=S256" in openai
    assert "code_challenge=chal" in openai
    google = google_authorize_url("google-client", "http://127.0.0.1:8138/", "chal", "state2")
    assert google.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "cloud-platform" in google


def test_model_list_filters(monkeypatch) -> None:
    def fake_request(method, url, **kwargs):  # type: ignore[no-untyped-def]
        if "openrouter" in url:
            return {"data": [{"id": "nousresearch/hermes-4-70b"}, {"id": "openai/gpt-4o-mini"}]}
        return {
            "data": [
                {"id": "gpt-4o-mini"},
                {"id": "whisper-1"},
                {"id": "text-embedding-3-small"},
            ]
        }

    monkeypatch.setattr("ai_assistant.providers.request_json", fake_request)
    hermes = list_models(
        {
            "kind": "hermes",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-or-test-key-value",
        }
    )
    assert hermes == ["nousresearch/hermes-4-70b"]
    openai = list_models(
        {"kind": "openai", "base_url": "https://api.openai.com/v1", "api_key": "sk-test-key-value"}
    )
    assert openai == ["gpt-4o-mini"]
