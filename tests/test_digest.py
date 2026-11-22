import json

from brief import digest, feishu, render

TOPICS = [{"id": "ai_tech", "zh": "AI与科技", "en": "AI & Tech"},
          {"id": "us", "zh": "美国要闻", "en": "United States"}]
DCFG = {"per_topic": 5, "must_know": 3, "hot_top": 5, "links_per_story": 3}
SITE = {"title_zh": "每日简报", "title_en": "Daily Brief", "archive_days": 30}


def items():
    mk = lambda p, side, t, u, src: {"platform": p, "side": side, "title": t, "url": u, "source": src,
                                     "extra": "", "heat": None, "published": None}
    return [mk("douyin", "cn", "某AI发布", "https://d/1", "抖音热榜"),
            mk("weibo", "cn", "某AI发布了", "https://w/1", "微博热搜"),
            mk("x", "us", "#AI", "https://x/1", "X Trends"),
            mk("news", "us", "AI launch", "https://n/1", "Reuters"),
            mk("news", "cn", "AI 发布会", "https://n/2", "新华网")]


def raw_reply():
    return {"topics": {"ai_tech": [
                {"ids": ["ghost"], "title_zh": "幽灵", "title_en": "ghost"},  # unknown id -> dropped
                {"ids": ["d1", "w1", "n1", "n2"], "title_zh": "AI发布", "title_en": "AI launch",
                 "summary_zh": "摘要", "summary_en": "Summary"}],
            "nope": [{"ids": ["d1"], "title_zh": "x", "title_en": "x"}]},  # unknown topic -> ignored
            "must_know": [{"topic": "ai_tech", "index": 1, "zh": "AI发布", "en": "AI launch"}],
            "hot_cn": [{"ids": ["d1", "w1"], "zh": "某AI发布", "en": "An AI launch"}],
            "hot_us": [{"ids": ["x1"], "zh": "AI", "en": "AI", "note_zh": "", "note_en": ""}]}


def test_validate_drops_bad_ids_and_remaps_must_know():
    its = items()
    by_id = digest.number_items(its)
    out = digest.validate(raw_reply(), by_id, TOPICS, DCFG)
    ai = out["topics"][0]["stories"]
    assert len(ai) == 1 and ai[0]["title_en"] == "AI launch"
    # must_know pointed at model index 1, which is kept index 0 after the ghost story was dropped
    assert out["must_know"][0]["index"] == 0
    assert out["must_know"][0]["url"] == ai[0]["links"][0]["url"]
    assert out["topics"][1]["stories"] == []
    assert out["hot"]["cn"][0]["platforms_zh"] == "抖音热榜、微博热搜"


def test_links_prefer_news_and_mix_sides():
    by_id = digest.number_items(items())
    links = digest._links(["d1", "w1", "n1", "n2"], by_id, 3)
    sides = {l["side"] for l in links}
    assert len(links) == 3 and sides == {"cn", "us"}
    assert links[0]["url"].startswith("https://n/")  # reported news first


def test_hot_falls_back_to_raw_ranks():
    by_id = digest.number_items(items())
    out = digest.validate({"topics": {}}, by_id, TOPICS, DCFG)
    assert [h["url"] for h in out["hot"]["cn"]] == ["https://d/1", "https://w/1"]


def test_prompt_mentions_json_and_all_items():
    its = items()
    digest.number_items(its)
    system, user = digest.build_prompt(its, TOPICS, DCFG)
    assert "JSON" in system
    for it in its:
        assert "\n" + it["id"] + " " in user


def _digest():
    its = items()
    by_id = digest.number_items(its)
    body = digest.validate(raw_reply(), by_id, TOPICS, DCFG)
    return {"date": "2026-11-22", "generated_at": "2026-11-22T06:31:00-05:00", **body,
            "stats": {"model": "test", "item_count": 5, "sources": {}, "failed_zh": [], "failed_en": []}}


def test_render_has_both_languages(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "2026-11-22.json").write_text(json.dumps(_digest(), ensure_ascii=False), encoding="utf-8")
    index = render.build_site(data, tmp_path / "site", SITE)
    html = index.read_text(encoding="utf-8")
    assert "AI发布" in html and "AI launch" in html
    assert 'data-set="en"' in html and "周日" in html
    assert (tmp_path / "site" / "archive" / "2026-11-22.html").exists()


def test_feishu_card_has_buttons_and_fits():
    payload = feishu.build_card(_digest(), SITE, "https://example.github.io/daily-brief/")
    text = json.dumps(payload, ensure_ascii=False)
    assert payload["msg_type"] == "interactive"
    assert "https://example.github.io/daily-brief/?lang=en" in text
    assert len(text.encode("utf-8")) < feishu.MAX_BYTES


def test_feishu_card_trims_when_too_big():
    d = _digest()
    d["topics"][0]["stories"] = d["topics"][0]["stories"] * 400
    payload = feishu._fit(feishu.build_card(d, SITE, ""))
    assert len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) <= feishu.MAX_BYTES


def test_feishu_sign_matches_reference():
    # Reference: Feishu docs' algorithm (HMAC-SHA256 keyed with "timestamp\nsecret", empty body, base64).
    import base64, hashlib, hmac
    ts, secret = "1599360473", "demo"
    want = base64.b64encode(hmac.new(f"{ts}\n{secret}".encode(), digestmod=hashlib.sha256).digest()).decode()
    assert feishu.sign(secret, ts) == want


def test_links_skip_repeated_labels():
    its = items() + [{"platform": "douyin", "side": "cn", "title": "另一条", "url": "https://d/2", "source": "抖音热榜",
                      "extra": "", "heat": None, "published": None}]
    by_id = digest.number_items(its)
    labels = [l["label_zh"] for l in digest._links(["d1", "d2"], by_id, 3)]
    assert labels == ["抖音热榜"]
