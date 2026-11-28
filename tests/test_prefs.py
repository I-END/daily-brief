import json

import run
from brief import prefs

SETTINGS = {"site": {"title_zh": "每日简报", "title_en": "Daily Brief"}, "timezone": "America/New_York",
            "digest": {"per_topic": 5, "must_know": 3, "hot_top": 5, "links_per_story": 3, "card_per_topic": 3}}
TOPICS = [{"id": "ai_tech", "zh": "AI与科技", "en": "AI & Tech"}, {"id": "us", "zh": "美国要闻", "en": "US"}]
SOURCES = {"hot_lists": {"douyin": {"enabled": True, "limit": 30}}, "youtube": {"enabled": True}}


def test_missing_or_broken_file_means_defaults(tmp_path):
    assert prefs.load(tmp_path / "nope.json") == prefs.DEFAULTS
    bad = tmp_path / "p.json"
    bad.write_text("{oops", encoding="utf-8")
    assert prefs.load(bad)["push_hour"] == 7


def test_numbers_are_clamped_and_junk_ignored(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"push_hour": 99, "digest": {"per_topic": "3", "must_know": -2, "bogus": 1},
                             "github": {"trending": "x"}, "default_lang": "fr"}), encoding="utf-8")
    p = prefs.load(f)
    assert p["push_hour"] == 23 and p["digest"]["per_topic"] == 3 and p["digest"]["must_know"] == 0
    assert "bogus" not in p["digest"] and p["github"]["trending"] == 8 and p["default_lang"] == "zh"


def test_apply_switches_topics_and_sources_and_adds_custom(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({
        "topics": {"us": False},
        "sources": {"douyin": False, "github": False},
        "digest": {"per_topic": 2},
        "custom_topics": [{"id": "c1", "zh": "体育", "en": "", "keywords_zh": "NBA，中超", "keywords_en": "NBA, Premier League"},
                          {"id": "c2", "zh": "空的", "en": "Empty"}],  # no keywords -> dropped
    }), encoding="utf-8")
    s, topics, src = prefs.apply(prefs.load(f), SETTINGS, TOPICS, SOURCES)
    assert [t["id"] for t in topics] == ["ai_tech", "c1"]
    sport = topics[1]
    assert sport["en"] == "体育" and sport["news_zh"] == "NBA OR 中超" and sport["news_en"] == "NBA OR Premier League"
    assert src["hot_lists"]["douyin"]["enabled"] is False and src["youtube"]["enabled"] is True
    assert s["github"]["enabled"] is False and s["digest"]["per_topic"] == 2 and s["push_hour"] == 7
    assert SETTINGS["digest"]["per_topic"] == 5  # inputs untouched


def test_decide():
    assert run.decide(None, 3, 7, scheduled=True, force=False) == "early"
    assert run.decide(None, 3, 7, scheduled=False, force=False) == "run"  # manual runs ignore the clock
    assert run.decide(None, 8, 7, scheduled=True, force=False) == "run"
    assert run.decide({"date": "x"}, 8, 7, scheduled=True, force=False) == "done"
    assert run.decide({"degraded": True}, 9, 7, scheduled=True, force=False) == "retry"
    assert run.decide({"date": "x"}, 3, 7, scheduled=True, force=True) == "run"
    early = {"generated_at": "2026-11-28T02:09:50-05:00"}  # made by hand at 2 AM
    assert run.decide(early, 8, 7, scheduled=True, force=False) == "refresh"
    assert run.decide(early, 8, 7, scheduled=False, force=False) == "done"
    assert run.decide(early, 5, 7, scheduled=True, force=False) == "early"
    assert run.decide({"generated_at": "2026-11-28T07:30:00-05:00"}, 9, 7, scheduled=True, force=False) == "done"
