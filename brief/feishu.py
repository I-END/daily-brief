"""Push the digest to a Feishu group through a custom bot webhook (飞书自定义机器人)."""
import base64
import hashlib
import hmac
import json
import time

from . import net

TOPIC_ICON = {"ai_tech": "🤖", "finance": "📈", "us_china_world": "🌏", "china": "🇨🇳", "us": "🇺🇸"}
MAX_BYTES = 19000  # Feishu rejects request bodies over 20 KB


def sign(secret, timestamp):
    """Feishu signature: HMAC-SHA256 keyed by "timestamp\\nsecret" over an empty message, base64."""
    key = f"{timestamp}\n{secret}".encode("utf-8")
    return base64.b64encode(hmac.new(key, b"", hashlib.sha256).digest()).decode("utf-8")


def _md_text(s):
    return s.replace("[", "［").replace("]", "］")


def build_card(d, site, site_url, lang="zh", per_topic=3):
    """Interactive card (schema 2.0): must-knows, the top story titles per topic, trending, buttons to the site."""
    zh = lang == "zh"
    title = f"{site['title_zh'] if zh else site['title_en']} · {d['date']}"
    parts = []
    if d["must_know"]:
        lines = [f"**{'📌 今日必知' if zh else '📌 Must-knows'}**"]
        for i, m in enumerate(d["must_know"], 1):
            text = _md_text(m["zh"] if zh else m["en"])
            lines.append(f"{i}. [{text}]({m['url']})" if m.get("url") else f"{i}. {text}")
        parts.append("\n".join(lines))
    for t in d["topics"]:
        if not t["stories"]:
            continue
        lines = [f"**{TOPIC_ICON.get(t['id'], '•')} {t['zh'] if zh else t['en']}**"]
        for s in t["stories"][:per_topic]:
            text = _md_text(s["title_zh"] if zh else s["title_en"])
            url = s["links"][0]["url"] if s["links"] else None
            lines.append(f"• [{text}]({url})" if url else f"• {text}")
        parts.append("\n".join(lines))
    hot_cn = "、".join(_md_text(h["zh"] if zh else h["en"]) for h in d["hot"]["cn"])
    hot_us = "、".join(_md_text(h["zh"] if zh else h["en"]) for h in d["hot"]["us"])
    if hot_cn or hot_us:
        head = "**🔥 热搜**" if zh else "**🔥 Trending**"
        parts.append("\n".join([head] + ([f"中国：{hot_cn}" if zh else f"China: {hot_cn}"] if hot_cn else [])
                               + ([f"美国 X：{hot_us}" if zh else f"US on X: {hot_us}"] if hot_us else [])))

    elements = [{"tag": "markdown", "content": "\n\n".join(parts)}]
    if site_url:
        base = site_url.rstrip("/") + "/"
        elements.append({"tag": "column_set", "columns": [
            {"tag": "column", "width": "auto", "elements": [_button("查看完整日报" if zh else "Open full brief",
                                                                    base + ("" if zh else "?lang=en"), "primary")]},
            {"tag": "column", "width": "auto", "elements": [_button("English" if zh else "中文版",
                                                                    base + ("?lang=en" if zh else "?lang=zh"), "default")]},
        ]})
    card = {"schema": "2.0",
            "header": {"title": {"tag": "plain_text", "content": title}, "template": "red"},
            "body": {"elements": elements}}
    return {"msg_type": "interactive", "card": card}


def _button(text, url, kind):
    return {"tag": "button", "text": {"tag": "plain_text", "content": text}, "type": kind,
            "behaviors": [{"type": "open_url", "default_url": url}]}


def _fit(payload):
    """Trim story lines from the bottom until the body is under Feishu's size limit."""
    md = payload["card"]["body"]["elements"][0]
    while len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_BYTES:
        lines = md["content"].split("\n")
        idx = max((i for i, l in enumerate(lines) if l.startswith("• ")), default=None)
        if idx is None:
            break
        del lines[idx]
        md["content"] = "\n".join(lines)
    return payload


def send(webhook, secret, payload):
    body = dict(_fit(payload))
    if secret:
        ts = str(int(time.time()))
        body.update({"timestamp": ts, "sign": sign(secret, ts)})
    r = net.post(webhook, json=body)
    try:
        data = r.json()
    except ValueError:
        data = {"code": r.status_code, "msg": r.text[:200]}
    code = data.get("code", data.get("StatusCode", -1))
    if r.status_code != 200 or code != 0:
        raise RuntimeError(f"飞书推送失败: HTTP {r.status_code} {data}")
    return data
