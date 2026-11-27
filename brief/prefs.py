"""User preferences from config/preferences.json (written by the website's settings page).

They sit on top of the YAML files: the YAML holds the full definitions (topics, channels, model),
preferences only switch things on/off and set a few numbers.
"""
import copy
import json
import re

SOURCES = [  # id, 中文, English — the order shown on the settings page
    ("douyin", "抖音热榜", "Douyin"), ("weibo", "微博热搜", "Weibo"), ("zhihu", "知乎热榜", "Zhihu"),
    ("bilibili", "B站热搜", "Bilibili"), ("x_trends", "X 美国趋势", "X US trends"),
    ("youtube", "YouTube 新闻频道", "YouTube news channels"), ("google_news", "Google News", "Google News"),
    ("github", "GitHub 热门", "GitHub trending"),
]
HOT_LISTS = ("douyin", "weibo", "zhihu", "bilibili")

DEFAULTS = {
    "push_hour": 7, "feishu": True, "default_lang": "zh",
    "topics": {}, "custom_topics": [],
    "sources": {s[0]: True for s in SOURCES},
    "digest": {"per_topic": 5, "must_know": 3, "card_per_topic": 3},
    "github": {"trending": 8, "new": 5, "skills": 5},
}
# allowed ranges for numbers, so a typo on the settings page can't break a run
LIMITS = {"push_hour": (0, 23), "per_topic": (1, 8), "must_know": (0, 5), "card_per_topic": (1, 5),
          "trending": (0, 15), "new": (0, 15), "skills": (0, 15)}


def _int(v, key, default):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    lo, hi = LIMITS[key]
    return max(lo, min(hi, v))


def load(path):
    """Read preferences, fill in defaults, clamp numbers. A missing or broken file means all defaults."""
    raw = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            print(f"⚠ {path.name} 不是合法 JSON，先用默认设置")
    p = copy.deepcopy(DEFAULTS)
    if not isinstance(raw, dict):
        return p
    p["push_hour"] = _int(raw.get("push_hour"), "push_hour", p["push_hour"])
    p["feishu"] = bool(raw.get("feishu", True))
    p["default_lang"] = "en" if raw.get("default_lang") == "en" else "zh"
    for key in ("topics", "sources"):
        if isinstance(raw.get(key), dict):
            p[key].update({k: bool(v) for k, v in raw[key].items()})
    for key in ("digest", "github"):
        if isinstance(raw.get(key), dict):
            for k, default in p[key].items():
                p[key][k] = _int(raw[key].get(k), k, default)
    p["custom_topics"] = [t for t in (_custom(t) for t in raw.get("custom_topics") or []) if t]
    return p


def _keywords(s):
    return [w.strip() for w in re.split(r"[,，、;；\n]", s or "") if w.strip()]


def _custom(t):
    """A topic added on the settings page: names + keywords -> a full topic definition."""
    if not isinstance(t, dict):
        return None
    tid = re.sub(r"[^a-z0-9_]", "", str(t.get("id", "")).lower())
    zh, en = str(t.get("zh", "")).strip(), str(t.get("en", "")).strip()
    kw_zh, kw_en = _keywords(t.get("keywords_zh")), _keywords(t.get("keywords_en"))
    if not tid or not (zh or en) or not (kw_zh or kw_en):
        return None
    zh, en = zh or en, en or zh
    return {"id": tid, "zh": zh, "en": en, "custom": True,
            "keywords_zh": "，".join(kw_zh), "keywords_en": ", ".join(kw_en),
            "about": f"{zh} / {en}: " + ", ".join(kw_zh + kw_en),
            "news_zh": " OR ".join(kw_zh), "news_en": " OR ".join(kw_en)}


def apply(p, settings, topics, sources_cfg):
    """Return (settings, topics, sources_cfg) with the preferences applied. Inputs are not modified."""
    settings, sources_cfg = copy.deepcopy(settings), copy.deepcopy(sources_cfg)
    settings["digest"].update(p["digest"])
    settings["push_hour"] = p["push_hour"]
    settings["feishu"] = p["feishu"]
    settings["site"]["default_lang"] = p["default_lang"]
    settings["github"] = {**p["github"], "enabled": p["sources"].get("github", True)}

    on = p["sources"]
    for name in HOT_LISTS:
        sources_cfg.setdefault("hot_lists", {}).setdefault(name, {})["enabled"] = on.get(name, True)
    for name in ("x_trends", "youtube", "google_news"):
        sources_cfg.setdefault(name, {})["enabled"] = on.get(name, True)

    builtin_ids = {t["id"] for t in topics}
    picked = [t for t in topics if p["topics"].get(t["id"], True)]
    picked += [t for t in p["custom_topics"] if t["id"] not in builtin_ids and p["topics"].get(t["id"], True)]
    return settings, picked, sources_cfg
