import json

import pytest

from brief import llm

CFG = {"base_url": "https://api.example.com", "model": "m", "api_key_env": "TEST_KEY",
       "extra": {"thinking": {"type": "disabled"}}}


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.text = json.dumps(body) if not isinstance(body, str) else body

    def json(self):
        return self._body


def ok(content):
    return Resp(200, {"choices": [{"message": {"content": content}}]})


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "k")
    monkeypatch.delenv("LLM_REPLAY_DIR", raising=False)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)


def test_drops_unknown_extra_params_after_400(monkeypatch):
    sent = []

    def post(url, json, headers, timeout):
        sent.append(dict(json))
        return Resp(400, "unknown field thinking") if "thinking" in json else ok('{"a": 1}')

    monkeypatch.setattr(llm.net, "post", post)
    assert llm.chat_json(CFG, "sys json", "user") == {"a": 1}
    assert "thinking" in sent[0] and "thinking" not in sent[1]
    assert sent[1]["response_format"] == {"type": "json_object"}


def test_bad_key_fails_fast(monkeypatch):
    calls = []
    monkeypatch.setattr(llm.net, "post", lambda *a, **k: calls.append(1) or Resp(401, "bad key"))
    with pytest.raises(llm.LLMError, match="401"):
        llm.chat_json(CFG, "s", "u")
    assert len(calls) == 1


def test_fenced_and_empty_replies(monkeypatch):
    replies = iter([ok(None), ok("```json\n{\"b\": 2}\n```")])
    monkeypatch.setattr(llm.net, "post", lambda *a, **k: next(replies))
    assert llm.chat_json(CFG, "s", "u") == {"b": 2}


def test_missing_key(monkeypatch):
    monkeypatch.delenv("TEST_KEY")
    assert not llm.have_key(CFG)
    with pytest.raises(llm.LLMError):
        llm.chat_json(CFG, "s", "u")
