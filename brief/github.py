"""GitHub section: today's trending repos, this week's new repos, and trending agent skills.

Each entry: {"name", "repo", "url", "desc", "lang", "stars", "gain", "source"}
  gain = stars today (trending) or installs this week (skills.sh); stars = total stars.
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from . import net

SKILL_TOPICS = ("agent-skills", "claude-skills")


def _num(s):
    """'1,597' / '29.6K' / '1.2M' -> int."""
    m = re.search(r"([\d.,]+)\s*([KkMm]?)", s or "")
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return int(v * {"": 1, "k": 1_000, "m": 1_000_000}[m.group(2).lower()])


def _entry(name, repo, url, desc="", lang="", stars=None, gain=None, source="GitHub"):
    return {"name": name, "repo": repo.lower(), "url": url, "desc": " ".join((desc or "").split())[:300],
            "lang": lang or "", "stars": stars, "gain": gain, "source": source}


def _api(params):
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):  # set in Actions; without it the search API allows 10 calls a minute
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    return net.get("https://api.github.com/search/repositories", params=params, headers=headers).json()["items"]


def _since(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def parse_trending(html):
    out = []
    for row in BeautifulSoup(html, "html.parser").select("article.Box-row"):
        a = row.select_one("h2 a")
        if not a:
            continue
        repo = a["href"].strip("/")
        desc, lang = row.select_one("p"), row.select_one('[itemprop="programmingLanguage"]')
        stars, today = row.select_one('a[href$="/stargazers"]'), row.select_one("span.float-sm-right")
        out.append(_entry(repo, repo, f"https://github.com/{repo}",
                          desc.get_text(" ", strip=True) if desc else "",
                          lang.get_text(strip=True) if lang else "",
                          _num(stars.get_text()) if stars else None,
                          _num(today.get_text()) if today else None, "GitHub Trending"))
    return out


def parse_skills_sh(html):
    out, seen = [], set()
    for a in BeautifulSoup(html, "html.parser").select("a[href]"):
        h3, p = a.select_one("h3"), a.select_one("p")
        nums = a.select("span.font-mono")
        if not (h3 and p and nums) or not a["href"].startswith("/"):
            continue
        repo = p.get_text(strip=True)
        if repo.lower() in seen:  # one skill per repo, so a big skill pack doesn't fill the list
            continue
        seen.add(repo.lower())
        out.append(_entry(h3.get_text(strip=True), repo, "https://www.skills.sh" + a["href"],
                          gain=_num(nums[-1].get_text()), source="skills.sh"))
    return out


def trending(limit):
    return parse_trending(net.get("https://github.com/trending", params={"since": "daily"}).text)[:limit]


def new_repos(limit, days=7):
    items = _api({"q": f"created:>{_since(days)}", "sort": "stars", "order": "desc", "per_page": 30})
    return [_entry(r["full_name"], r["full_name"], r["html_url"], r.get("description"), r.get("language"),
                   r.get("stargazers_count")) for r in items][: limit * 3]  # extra, in case of overlap


def _skill_page_desc(url):
    try:
        soup = BeautifulSoup(net.get(url, tries=1, timeout=10).text, "html.parser")
        m = soup.select_one('meta[name="description"]')
        return (m.get("content") or "").rstrip("…").strip() if m else ""
    except Exception:  # noqa: BLE001 - a missing description is fine
        return ""


def skills(limit):
    """skills.sh's weekly trending list, interleaved with new GitHub repos tagged as agent skills."""
    lists, errors = [], []
    try:
        lists.append(parse_skills_sh(net.get("https://www.skills.sh/trending").text))
    except Exception as e:  # noqa: BLE001
        errors.append(f"skills.sh: {e}")
    for topic in SKILL_TOPICS:
        try:
            items = _api({"q": f"topic:{topic} created:>{_since(30)}", "sort": "stars", "order": "desc",
                          "per_page": 10})
            lists.append([_entry(r["full_name"], r["full_name"], r["html_url"], r.get("description"),
                                 r.get("language"), r.get("stargazers_count")) for r in items])
        except Exception as e:  # noqa: BLE001
            errors.append(f"{topic}: {e}")
    if not any(lists):
        raise RuntimeError("; ".join(errors) or "empty")
    merged = [e for group in _interleave(lists) for e in group]
    return merged[: limit * 3]


def _interleave(lists):
    """[[a1,a2],[b1]] -> [[a1,b1],[a2]]"""
    for i in range(max(len(x) for x in lists)):
        yield [x[i] for x in lists if i < len(x)]


def fetch(cfg):
    """cfg: {"enabled", "trending", "new", "skills"} counts. Returns (sections, stats)."""
    jobs = {k: fn for k, fn in (("trending", trending), ("new", new_repos), ("skills", skills))
            if cfg.get("enabled", True) and cfg.get(k, 0) > 0}
    raw, stats = {}, {}
    with ThreadPoolExecutor(3) as ex:
        futures = {k: ex.submit(fn, cfg[k]) for k, fn in jobs.items()}
        for k, fut in futures.items():
            try:
                raw[k] = fut.result()
            except Exception as e:  # noqa: BLE001
                raw[k] = []
                stats[f"github:{k}"] = f"error: {str(e)[:200]}"

    # The same repo shows up once, in the first section that has it.
    sections, seen = {}, set()
    for k in ("trending", "new", "skills"):
        picked = []
        for e in raw.get(k, []):
            if e["repo"] in seen:
                continue
            seen.add(e["repo"])
            picked.append(e)
            if len(picked) >= cfg[k]:
                break
        sections[k] = picked
        if k in jobs and f"github:{k}" not in stats:
            stats[f"github:{k}"] = len(picked)

    need = [e for e in sections.get("skills", []) if e["source"] == "skills.sh" and not e["desc"]]
    with ThreadPoolExecutor(5) as ex:
        for e, desc in zip(need, ex.map(_skill_page_desc, [e["url"] for e in need])):
            e["desc"] = desc
    return sections, stats
