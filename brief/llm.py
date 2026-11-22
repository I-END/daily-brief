"""Minimal OpenAI-compatible chat client (DeepSeek by default) that returns parsed JSON.

Replay mode (for testing without an API key): set LLM_REPLAY_DIR. Each call writes
<dir>/<name>.prompt.txt and reads <dir>/<name>.response.json instead of calling the API.
"""
import json
import os
import re
import time
from pathlib import Path

from . import net


class LLMError(RuntimeError):
    pass


def model_label(cfg):
    if os.environ.get("LLM_REPLAY_DIR"):
        return os.environ.get("LLM_REPLAY_LABEL", "replay")
    return cfg["model"]


def have_key(cfg):
    return bool(os.environ.get("LLM_REPLAY_DIR") or os.environ.get(cfg["api_key_env"]))


def chat_json(cfg, system, user, name="digest"):
    replay = os.environ.get("LLM_REPLAY_DIR")
    if replay:
        return _replay(Path(replay), name, system, user)

    key = os.environ.get(cfg["api_key_env"])
    if not key:
        raise LLMError(f"环境变量 {cfg['api_key_env']} 没有设置")
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    body = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": cfg.get("temperature", 0.3),
        "max_tokens": cfg.get("max_tokens", 16000),
        "response_format": {"type": "json_object"},
        **(cfg.get("extra") or {}),
    }
    headers = {"Authorization": f"Bearer {key}"}
    last = None
    for attempt in range(3):
        try:
            r = net.post(url, json=body, headers=headers, timeout=300)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 400 and cfg.get("extra") and any(k in body for k in cfg["extra"]):
            # The endpoint may not know our extra params: drop them and retry.
            for k in cfg["extra"]:
                body.pop(k, None)
            last = LLMError(f"HTTP 400: {r.text[:300]}")
            continue
        if r.status_code != 200:
            last = LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
            if r.status_code in (401, 402, 403):
                break  # bad key / no balance: retrying won't help
            time.sleep(5 * (attempt + 1))
            continue
        try:
            return parse_json(r.json()["choices"][0]["message"].get("content") or "")
        except (ValueError, KeyError, IndexError, TypeError) as e:
            last = LLMError(f"模型返回的不是合法 JSON: {e}")
    raise LLMError(str(last))


def parse_json(text):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object found")
    return json.loads(text[start:end + 1])


def _replay(d, name, system, user):
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.prompt.txt").write_text(f"### SYSTEM\n{system}\n\n### USER\n{user}\n", encoding="utf-8")
    resp = d / f"{name}.response.json"
    if not resp.exists():
        raise LLMError(f"replay: 请把模型回复写到 {resp}")
    return parse_json(resp.read_text(encoding="utf-8"))
