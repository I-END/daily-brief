"""Fetchers. Each returns a list of items:

    {"platform", "side", "title", "url", "source", "extra", "heat", "published"}

side is "cn" (Chinese-language / China side) or "us" (English / US side).
Every fetcher has fallbacks, because these unofficial endpoints break often.
"""
import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import feedparser
from bs4 import BeautifulSoup

from . import net

NEWSNOW = "https://newsnow.busiyi.world/api/s?id={}&latest"


def _item(platform, side, title, url, source, extra="", heat=None, published=None):
    return {"platform": platform, "side": side, "title": title.strip(), "url": url,
            "source": source, "extra": (extra or "").strip(), "heat": heat, "published": published}


def _first_working(*attempts):
    """Run fetch attempts in order; return the first non-empty result."""
    errors = []
    for fn in attempts:
        try:
            items = fn()
            if items:
                return items
            errors.append(f"{fn.__name__}: empty")
        except Exception as e:  # noqa: BLE001 - any failure means "try the next one"
            errors.append(f"{fn.__name__}: {e}")
    raise RuntimeError("; ".join(errors))


def _newsnow(sid, platform, source, limit):
    def newsnow():
        data = net.get(NEWSNOW.format(sid)).json()
        return [_item(platform, "cn", it["title"], it.get("url") or it.get("mobileUrl"), source,
                      extra=(it.get("extra") or {}).get("hover", "")[:150],
                      heat=(it.get("extra") or {}).get("info"))
                for it in data.get("items", [])[:limit] if it.get("title")]
    return newsnow


# ---------- China hot lists ----------

def douyin(limit=30):
    def direct():
        r = net.get("https://www.douyin.com/aweme/v1/web/hot/search/list/",
                     params={"device_platform": "webapp", "aid": "6383",
                             "channel": "channel_pc_web", "detail_list": "1"},
                     headers={"Referer": "https://www.douyin.com/"})
        words = r.json()["data"]["word_list"]
        return [_item("douyin", "cn", w["word"], f"https://www.douyin.com/hot/{w['sentence_id']}",
                      "抖音热榜", heat=w.get("hot_value")) for w in words[:limit]]

    def billboard():
        r = net.get("https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/")
        return [_item("douyin", "cn", w["word"], f"https://www.douyin.com/search/{quote(w['word'])}",
                      "抖音热榜", heat=w.get("hot_value")) for w in r.json()["word_list"][:limit]]

    return _first_working(direct, billboard, _newsnow("douyin", "douyin", "抖音热榜", limit))


def weibo(limit=30):
    return _first_working(_newsnow("weibo", "weibo", "微博热搜", limit))


def zhihu(limit=20):
    def api():
        r = net.get("https://api.zhihu.com/topstory/hot-lists/total", params={"limit": limit})
        out = []
        for d in r.json()["data"][:limit]:
            t = d["target"]
            out.append(_item("zhihu", "cn", t["title"], f"https://www.zhihu.com/question/{t['id']}",
                             "知乎热榜", extra=t.get("excerpt", "")[:150], heat=d.get("detail_text")))
        return out

    return _first_working(api, _newsnow("zhihu", "zhihu", "知乎热榜", limit))


def bilibili(limit=20):
    def square():
        r = net.get("https://api.bilibili.com/x/web-interface/wbi/search/square", params={"limit": limit})
        lst = r.json()["data"]["trending"]["list"]
        return [_item("bilibili", "cn", w["show_name"] or w["keyword"],
                      f"https://search.bilibili.com/all?keyword={quote(w['keyword'])}",
                      "B站热搜", heat=w.get("heat_score")) for w in lst[:limit]]

    def hotword():
        lst = net.get("https://s.search.bilibili.com/main/hotword").json()["list"]
        return [_item("bilibili", "cn", w["show_name"] or w["keyword"],
                      f"https://search.bilibili.com/all?keyword={quote(w['keyword'])}",
                      "B站热搜", heat=w.get("heat_score")) for w in lst[:limit]]

    return _first_working(square, hotword, _newsnow("bilibili-hot-search", "bilibili", "B站热搜", limit))


# ---------- US ----------

def x_trends(limit=30):
    def trends24():
        soup = BeautifulSoup(net.get("https://trends24.in/united-states/").text, "html.parser")
        card = soup.select_one("ol.trend-card__list")  # first card = latest hour
        out = []
        for li in card.select("li")[:limit]:
            a = li.select_one("a.trend-link")
            count = li.select_one(".tweet-count")
            name = a.get_text(strip=True)
            heat = int(count["data-count"]) if count and count.get("data-count", "").isdigit() else None
            out.append(_item("x", "us", name, f"https://x.com/search?q={quote(name)}", "X Trends", heat=heat))
        return out

    def getdaytrends():
        soup = BeautifulSoup(net.get("https://getdaytrends.com/united-states/").text, "html.parser")
        out, seen = [], set()
        for a in soup.select('a[href*="/united-states/trend/"]'):
            name = a.get_text(strip=True)
            if name and name not in seen:
                seen.add(name)
                out.append(_item("x", "us", name, f"https://x.com/search?q={quote(name)}", "X Trends"))
            if len(out) >= limit:
                break
        return out

    return _first_working(trends24, getdaytrends)


def youtube(channels, max_age_hours=30, per_channel=3):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    def one(ch):
        try:
            r = net.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['id']}", tries=2)
        except Exception:  # noqa: BLE001 - one dead channel shouldn't sink the rest
            return []
        out = []
        for e in feedparser.parse(r.text).entries:
            pub = datetime(*e.published_parsed[:6], tzinfo=timezone.utc) if e.get("published_parsed") else None
            if pub and pub < cutoff:
                continue
            desc = e.get("summary", "") or ""
            out.append(_item("youtube", ch.get("side", "us"), e.title, e.link, f"YouTube · {ch['name']}",
                             extra=desc[:150], published=pub.isoformat() if pub else None))
            if len(out) >= per_channel:
                break
        return out

    with ThreadPoolExecutor(8) as ex:
        return [it for chunk in ex.map(one, channels) for it in chunk]


def google_news(query, lang, per_query=12):
    """lang: 'zh' (China edition) or 'en' (US edition). Only the last 24 hours."""
    ed = ({"hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"} if lang == "zh"
          else {"hl": "en-US", "gl": "US", "ceid": "US:en"})
    r = net.get("https://news.google.com/rss/search", params={"q": f"{query} when:1d", **ed})
    out = []
    for e in feedparser.parse(r.text).entries[:per_query]:
        src = (e.get("source") or {}).get("title", "")
        title = e.title
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        out.append(_item("news", "cn" if lang == "zh" else "us", html.unescape(title), e.link,
                         src or "Google News", published=e.get("published")))
    return out


# ---------- run everything ----------

def fetch_all(sources_cfg, topics):
    """Returns (items, stats). stats maps source name -> count or error string."""
    jobs = {}
    hl = sources_cfg.get("hot_lists", {})
    for name, fn in (("douyin", douyin), ("weibo", weibo), ("zhihu", zhihu), ("bilibili", bilibili)):
        c = hl.get(name, {})
        if c.get("enabled", True):
            jobs[name] = (fn, (c.get("limit", 20),))
    xc = sources_cfg.get("x_trends", {})
    if xc.get("enabled", True):
        jobs["x_trends"] = (x_trends, (xc.get("limit", 30),))
    yc = sources_cfg.get("youtube", {})
    if yc.get("enabled", True) and yc.get("channels"):
        jobs["youtube"] = (youtube, (yc["channels"], yc.get("max_age_hours", 30), yc.get("per_channel", 3)))
    gc = sources_cfg.get("google_news", {})
    if gc.get("enabled", True):
        for t in topics:
            for lang in ("zh", "en"):
                q = t.get(f"news_{lang}")
                if q:
                    jobs[f"news:{t['id']}:{lang}"] = (google_news, (q, lang, gc.get("per_query", 12)))

    items, stats = [], {}
    with ThreadPoolExecutor(10) as ex:
        futures = {name: ex.submit(fn, *args) for name, (fn, args) in jobs.items()}
        for name, fut in futures.items():
            try:
                got = fut.result()
                items.extend(got)
                stats[name] = len(got)
            except Exception as e:  # noqa: BLE001
                stats[name] = f"error: {str(e)[:200]}"
    return _dedupe(items), stats


def _dedupe(items):
    seen, out = set(), []
    for it in items:
        key = it["url"] or (it["platform"], re.sub(r"\s+", "", it["title"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out
