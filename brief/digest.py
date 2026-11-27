"""Turn fetched items into a bilingual digest with one LLM call, then validate it."""
import json

from . import gnews, llm

PREFIX = {"douyin": "d", "weibo": "w", "zhihu": "z", "bilibili": "b", "x": "x", "youtube": "y", "news": "n"}
PLATFORM_LABEL = {
    "douyin": ("抖音热榜", "Douyin"), "weibo": ("微博热搜", "Weibo"), "zhihu": ("知乎热榜", "Zhihu"),
    "bilibili": ("B站热搜", "Bilibili"), "x": ("X 趋势", "X Trends"),
}
HOT_CN = ("douyin", "weibo", "zhihu", "bilibili")
# When picking links for a story, reported sources come before raw hot-list entries.
LINK_PRIORITY = {"news": 0, "youtube": 1, "zhihu": 2, "douyin": 3, "weibo": 3, "bilibili": 3, "x": 4}

SYSTEM = """You are the editor of a short bilingual (Simplified Chinese + English) daily news brief for one busy reader.
You receive numbered items from the last ~24 hours:
- Chinese platform hot lists: Douyin (抖音, ids d*), Weibo (微博, w*), Zhihu (知乎, z*), Bilibili (B站, b*)
- X (Twitter) US trending topics (x*) — often just a name or hashtag
  For hot lists and X trends the number in the id is the rank: d1 is #1 on Douyin.
- Recent videos from selected YouTube news channels
- Google News search results (Chinese edition and US English edition)

Write the brief as JSON only. Rules:
1. Topics: only use the topic ids given. For each topic pick up to {per_topic} of the most important real-world stories, most important first.
   Skip celebrity gossip, ads, pure entertainment, sports scores and vague items unless the topic description says otherwise.
   A topic may have fewer stories (or none) if nothing relevant happened.
2. A story is ONE event or development. Merge every item about the same event into one story, across platforms and languages,
   and list all their ids. Never put the same event in two topics.
3. Use only facts stated in the items. Don't guess numbers, dates or motives. If items give only a headline, keep the summary short and plain.
   Never invent ids.
4. Lengths: title_zh <= 22 Chinese characters; title_en <= 12 words; summary_zh 1-2 sentences, <= 80 Chinese characters;
   summary_en 1-2 sentences, <= 45 words. Neutral tone. Chinese must be Simplified Chinese.
5. must_know: the {must_know} most important stories of the day across all topics, each as one plain sentence in both languages,
   pointing at a story by topic id and its 0-based index in that topic.
6. hot_cn: the {hot_top} hottest entries across the Chinese hot lists (d/w/z/b ids). Merge the same topic across platforms;
   rank entries on more platforms first, then by best rank; at most 2 from any single platform.
   hot_us: the top {hot_top} X trends (x ids). For each give a short Chinese and English label; for X trends add a short note
   (<= 15 words / 20 characters) saying what it is about, only if clear from the items or well known — otherwise empty strings.

JSON shape:
{{"topics": {{"<topic_id>": [{{"ids": ["n3","d1"], "title_zh": "", "title_en": "", "summary_zh": "", "summary_en": ""}}]}},
 "must_know": [{{"topic": "<topic_id>", "index": 0, "zh": "", "en": ""}}],
 "hot_cn": [{{"ids": ["w1","d4"], "zh": "", "en": ""}}],
 "hot_us": [{{"ids": ["x1"], "zh": "", "en": "", "note_zh": "", "note_en": ""}}]}}"""


def number_items(items):
    """Give every item a short id like d1, n12. Returns {id: item}."""
    counters, by_id = {}, {}
    for it in items:
        p = PREFIX[it["platform"]]
        counters[p] = counters.get(p, 0) + 1
        iid = f"{p}{counters[p]}"
        it["id"] = iid
        by_id[iid] = it
    return by_id


EXTRA_CHARS = 60  # snippet length per item; the biggest lever on prompt size


def _line(it):
    """Compact one-line form. Hot-list ids carry the rank (d3 = Douyin #3), so no rank/heat text."""
    text = it["title"]
    if it["platform"] in ("youtube", "news"):
        text = f"{it['source'].removeprefix('YouTube · ')}: {text}"
    extra = " ".join(it.get("extra", "").split())[:EXTRA_CHARS]
    return f"{it['id']} {text}" + (f" — {extra}" if extra else "")


GROUPS = [("Douyin hot list", lambda i: i["platform"] == "douyin"),
          ("Weibo hot search", lambda i: i["platform"] == "weibo"),
          ("Zhihu hot list", lambda i: i["platform"] == "zhihu"),
          ("Bilibili hot search", lambda i: i["platform"] == "bilibili"),
          ("X US trends", lambda i: i["platform"] == "x"),
          ("YouTube videos (channel: title)", lambda i: i["platform"] == "youtube"),
          ("Google News, Chinese edition (outlet: headline)", lambda i: i["platform"] == "news" and i["side"] == "cn"),
          ("Google News, US edition (outlet: headline)", lambda i: i["platform"] == "news" and i["side"] == "us")]


def build_prompt(items, topics, dcfg):
    system = SYSTEM.format(per_topic=dcfg["per_topic"], must_know=dcfg["must_know"], hot_top=dcfg["hot_top"])
    topic_lines = "\n".join(f"- {t['id']}: {t['zh']} / {t['en']} — {t.get('about', '')}" for t in topics)
    blocks = []
    for name, pred in GROUPS:
        lines = [_line(i) for i in items if pred(i)]
        if lines:
            blocks.append(f"## {name}\n" + "\n".join(lines))
    user = f"TOPICS:\n{topic_lines}\n\nITEMS:\n\n" + "\n\n".join(blocks) + "\n\nReturn the JSON now."
    return system, user


def _links(ids, by_id, limit):
    """Pick up to `limit` links, best sources first, mixing China-side and US-side when both exist."""
    its = sorted((by_id[i] for i in ids), key=lambda i: LINK_PRIORITY.get(i["platform"], 9))
    picked, seen = [], set()  # seen holds urls and labels: two "知乎热榜" pills look like a bug
    for want_side in ("cn", "us", None):  # one from each side first, then the rest in order
        for it in its:
            if len(picked) >= limit:
                break
            label = link_of(it)["label_zh"]
            if it["url"] in seen or label in seen or (want_side and it["side"] != want_side):
                continue
            seen.update((it["url"], label))
            picked.append(it)
            if want_side:
                break
    picked.sort(key=lambda i: LINK_PRIORITY.get(i["platform"], 9))
    return [link_of(it) for it in picked]


def link_of(it):
    zh, en = PLATFORM_LABEL.get(it["platform"], (it["source"], it["source"]))
    return {"url": it["url"], "label_zh": zh, "label_en": en, "side": it["side"]}


def _s(v):
    return v.strip() if isinstance(v, str) else ""


def validate(raw, by_id, topics, dcfg):
    """Keep only well-formed stories with real ids; build links. Never trusts the model blindly."""
    out_topics, kept_index = [], {}  # kept_index[(topic, model's index)] = index after dropping bad stories
    for t in topics:
        stories = []
        for orig_i, s in enumerate((raw.get("topics") or {}).get(t["id"], []) or []):
            if not isinstance(s, dict):
                continue
            ids = [i for i in s.get("ids", []) if isinstance(i, str) and i in by_id]
            if not ids or not (_s(s.get("title_zh")) or _s(s.get("title_en"))):
                continue
            kept_index[(t["id"], orig_i)] = len(stories)
            stories.append({
                "title_zh": _s(s.get("title_zh")) or _s(s.get("title_en")),
                "title_en": _s(s.get("title_en")) or _s(s.get("title_zh")),
                "summary_zh": _s(s.get("summary_zh")),
                "summary_en": _s(s.get("summary_en")),
                "links": _links(ids, by_id, dcfg["links_per_story"]),
            })
            if len(stories) >= dcfg["per_topic"]:
                break
        out_topics.append({"id": t["id"], "zh": t["zh"], "en": t["en"], "stories": stories})

    tmap = {t["id"]: t for t in out_topics}
    must = []
    for m in raw.get("must_know") or []:
        if not isinstance(m, dict) or not (_s(m.get("zh")) or _s(m.get("en"))):
            continue
        t = tmap.get(m.get("topic"))
        idx = kept_index.get((m.get("topic"), m.get("index")))
        story = t["stories"][idx] if t and idx is not None else None
        must.append({"zh": _s(m.get("zh")) or _s(m.get("en")), "en": _s(m.get("en")) or _s(m.get("zh")),
                     "topic": m.get("topic") if story else None, "index": idx if story else None,
                     "url": story["links"][0]["url"] if story and story["links"] else None})
        if len(must) >= dcfg["must_know"]:
            break

    def hot(key, platforms):
        rows = []
        for h in raw.get(key) or []:
            if not isinstance(h, dict):
                continue
            ids = [i for i in h.get("ids", []) if isinstance(i, str) and i in by_id
                   and by_id[i]["platform"] in platforms]
            if not ids:
                continue
            first = by_id[ids[0]]
            plats = []
            for i in ids:
                lab = PLATFORM_LABEL[by_id[i]["platform"]]
                if lab not in plats:
                    plats.append(lab)
            rows.append({"zh": _s(h.get("zh")) or first["title"], "en": _s(h.get("en")) or first["title"],
                         "note_zh": _s(h.get("note_zh")), "note_en": _s(h.get("note_en")),
                         "url": first["url"],
                         "platforms_zh": "、".join(p[0] for p in plats),
                         "platforms_en": ", ".join(p[1] for p in plats)})
            if len(rows) >= dcfg["hot_top"]:
                break
        if not rows:  # model skipped it (or no AI today): take #1 of each platform, then #2, ...
            per = [[i for i in by_id.values() if i["platform"] == p] for p in platforms]
            ranked = [lst[r] for r in range(max(map(len, per), default=0)) for lst in per if r < len(lst)]
            for it in ranked[: dcfg["hot_top"]]:
                lab = PLATFORM_LABEL[it["platform"]]
                rows.append({"zh": it["title"], "en": it["title"], "note_zh": "", "note_en": "",
                             "url": it["url"], "platforms_zh": lab[0], "platforms_en": lab[1]})
        return rows

    return {"must_know": must, "topics": out_topics,
            "hot": {"cn": hot("hot_cn", HOT_CN), "us": hot("hot_us", ("x",))}}


def make_digest(items, topics, dcfg, llm_cfg):
    by_id = number_items(items)
    system, user = build_prompt(items, topics, dcfg)
    raw = llm.chat_json(llm_cfg, system, user, name="digest")
    result = validate(raw, by_id, topics, dcfg)
    if not any(t["stories"] for t in result["topics"]):
        raise llm.LLMError("模型没有返回任何有效新闻: " + json.dumps(raw, ensure_ascii=False)[:300])
    resolve_links(result)
    return result


def explain_error(e):
    """LLM error -> short (zh, en) reason for the page and the Feishu card."""
    s = str(e)
    if "401" in s or "没有设置" in s:
        return "DeepSeek key 无效或没有设置，需要换一个新 key", "the DeepSeek key is invalid or missing"
    if "402" in s:
        return "DeepSeek 账户余额不足", "the DeepSeek account is out of balance"
    if "429" in s:
        return "DeepSeek 请求太频繁，被限流了", "DeepSeek rate-limited the request"
    return "AI 接口出错：" + s[:80], "the AI service returned an error: " + s[:80]


def fallback(items, topics, dcfg, error):
    """The no-AI edition: news headlines per topic (original language), raw hot-list ranks."""
    by_id = number_items(items)
    result = validate({}, by_id, topics, dcfg)
    for t in result["topics"]:
        news = [i for i in items if i["platform"] == "news" and i.get("topic") == t["id"]]
        cn, us = [i for i in news if i["side"] == "cn"], [i for i in news if i["side"] == "us"]
        mixed = [lst[r] for r in range(max(len(cn), len(us))) for lst in (cn, us) if r < len(lst)]
        t["stories"] = [{"title_zh": it["title"], "title_en": it["title"], "summary_zh": "", "summary_en": "",
                         "links": [link_of(it)]}  # news links are labelled with the outlet name
                        for it in mixed[: dcfg["per_topic"]]]
    resolve_links(result)
    zh, en = explain_error(error)
    result.update(degraded=True, error_zh=zh, error_en=en)
    return result


GH_SYSTEM = """You write one-line descriptions of GitHub projects and AI agent skills for a bilingual daily brief.
For each numbered entry say, in plain words, what it is or what it does, using only the name and description given.
zh: Simplified Chinese, at most 30 characters. en: at most 15 words. No hype, no star counts, no "this project".
If the description is empty or too vague to tell, return empty strings for that id.
JSON only: {"g1": {"zh": "", "en": ""}, "g2": {"zh": "", "en": ""}}"""


def describe_github(sections, llm_cfg):
    """Add desc_zh / desc_en to every GitHub entry: AI one-liners, falling back to the repo's own text."""
    entries = [e for k in ("trending", "new", "skills") for e in sections.get(k, [])]
    for e in entries:  # fallback: the repo's own text, cut short
        e["desc_zh"] = e["desc_en"] = e["desc"] if len(e["desc"]) <= 140 else e["desc"][:138].rstrip() + "…"
    if not entries or llm_cfg is None:
        return sections
    lines = [f"g{n} {e['name']}" + (f" ({e['repo']})" if e["repo"] != e["name"].lower() else "")
             + (f" [{e['lang']}]" if e["lang"] else "") + (f" — {e['desc'][:200]}" if e["desc"] else "")
             for n, e in enumerate(entries, 1)]
    try:
        raw = llm.chat_json(llm_cfg, GH_SYSTEM, "\n".join(lines) + "\n\nReturn the JSON now.", name="github")
    except llm.LLMError as err:
        print(f"⚠ GitHub 简介没写成，用项目自己的介绍：{err}")
        return sections
    for n, e in enumerate(entries, 1):
        d = raw.get(f"g{n}") if isinstance(raw, dict) else None
        if isinstance(d, dict):
            e["desc_zh"] = _s(d.get("zh")) or e["desc"]
            e["desc_en"] = _s(d.get("en")) or e["desc"]
    return sections


def github_view(sections):
    """Entries -> what the page and card show (metric text per section)."""
    def metric(kind, e):
        if kind == "trending" and e["gain"]:
            return f"今天 +{e['gain']:,} 星", f"+{e['gain']:,} stars today"
        if e["source"] == "skills.sh" and e["gain"]:
            return f"本周 {e['gain']:,} 次安装", f"{e['gain']:,} installs this week"
        if e["stars"]:
            return f"{e['stars']:,} 星", f"{e['stars']:,} stars"
        return "", ""

    out = {}
    for kind in ("trending", "new", "skills"):
        rows = []
        for e in sections.get(kind, []):
            mz, me = metric(kind, e)
            rows.append({"name": e["name"], "repo": e["repo"] if e["repo"] != e["name"].lower() else "",
                         "url": e["url"], "lang": e["lang"], "desc_zh": e.get("desc_zh", e["desc"]),
                         "desc_en": e.get("desc_en", e["desc"]), "metric_zh": mz, "metric_en": me})
        out[kind] = rows
    return out


def resolve_links(result):
    """Swap Google News redirects for original article URLs where possible (best effort)."""
    links = [l for t in result["topics"] for s in t["stories"] for l in s["links"]]
    real = gnews.resolve_all([l["url"] for l in links])
    for l in links:
        l["url"] = real.get(l["url"], l["url"])
    for m in result["must_know"]:
        if m.get("url"):
            m["url"] = real.get(m["url"], m["url"])
