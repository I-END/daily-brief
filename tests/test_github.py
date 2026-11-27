from brief import digest, github, llm

TRENDING = """
<article class="Box-row">
  <h2><a href="/obra/superpowers"> obra / superpowers </a></h2>
  <p class="col-9"> An agentic skills framework. </p>
  <span itemprop="programmingLanguage">Shell</span>
  <a href="/obra/superpowers/stargazers"> 327,597 </a>
  <span class="d-inline-block float-sm-right">854 stars today</span>
</article>
<article class="Box-row"><h2><a href="/a/b">a / b</a></h2></article>
"""

SKILLS = """
<a href="/vercel-labs/agent-browser/agent-browser"><span class="font-mono">7</span><h3>agent-browser</h3>
  <p>vercel-labs/agent-browser</p><span class="font-mono text-sm">20.0K</span></a>
<a href="/vercel-labs/agent-browser/other"><span class="font-mono">8</span><h3>other</h3>
  <p>vercel-labs/agent-browser</p><span class="font-mono text-sm">1.2K</span></a>
<a href="/x/y/z"><span class="font-mono">9</span><h3>z</h3><p>x/y</p><span class="font-mono">990</span></a>
"""


def test_num():
    assert github._num("1,597 stars today") == 1597
    assert github._num("29.6K") == 29600 and github._num("1.2M") == 1_200_000 and github._num("") is None


def test_parse_trending():
    rows = github.parse_trending(TRENDING)
    assert rows[0]["repo"] == "obra/superpowers" and rows[0]["gain"] == 854 and rows[0]["stars"] == 327597
    assert rows[0]["lang"] == "Shell" and rows[0]["desc"] == "An agentic skills framework."
    assert rows[1]["gain"] is None and rows[1]["desc"] == ""


def test_parse_skills_one_per_repo():
    rows = github.parse_skills_sh(SKILLS)
    assert [r["name"] for r in rows] == ["agent-browser", "z"]
    assert rows[0]["gain"] == 20000 and rows[0]["url"] == "https://www.skills.sh/vercel-labs/agent-browser/agent-browser"


def test_fetch_dedupes_across_sections(monkeypatch):
    same = github._entry("a/b", "a/b", "https://github.com/a/b", "dup")
    monkeypatch.setattr(github, "trending", lambda n: [same])
    monkeypatch.setattr(github, "new_repos", lambda n: [same, github._entry("c/d", "c/d", "u", "new")])
    monkeypatch.setattr(github, "skills", lambda n: (_ for _ in ()).throw(RuntimeError("down")))
    sections, stats = github.fetch({"enabled": True, "trending": 5, "new": 5, "skills": 5})
    assert [e["repo"] for e in sections["new"]] == ["c/d"]
    assert stats["github:skills"].startswith("error") and stats["github:trending"] == 1


def test_describe_uses_ai_then_falls_back(monkeypatch):
    long = "x" * 200
    sections = {"trending": [github._entry("a/b", "a/b", "u", "Short.", gain=5)],
                "skills": [github._entry("tool", "o/r", "u", long, gain=1200, source="skills.sh")]}
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"g1": {"zh": "一个工具", "en": "A tool"}})
    digest.describe_github(sections, {"model": "m"})
    assert sections["trending"][0]["desc_zh"] == "一个工具"
    assert sections["skills"][0]["desc_zh"].endswith("…") and len(sections["skills"][0]["desc_zh"]) < 145
    view = digest.github_view(sections)
    assert view["trending"][0]["metric_zh"] == "今天 +5 星"
    assert view["skills"][0]["metric_en"] == "1,200 installs this week" and view["skills"][0]["repo"] == "o/r"
