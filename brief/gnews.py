"""Turn Google News redirect links (news.google.com/rss/articles/...) into the original article URLs.

Best effort: any failure keeps the redirect link, which still opens the article.
"""
import json
import re
import time
from urllib.parse import urlparse

from . import net

BATCH = "https://news.google.com/_/DotsSplashUi/data/batchexecute"


def decode(url):
    aid = urlparse(url).path.rstrip("/").split("/")[-1]
    page = net.get(f"https://news.google.com/rss/articles/{aid}", tries=1).text
    sg = re.search(r'data-n-a-sg="([^"]+)"', page)
    ts = re.search(r'data-n-a-ts="([^"]+)"', page)
    if not (sg and ts):
        raise ValueError("signature not found")
    inner = (f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
             f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{aid}",{ts.group(1)},"{sg.group(1)}"]')
    r = net._session.post(BATCH, data={"f.req": json.dumps([[["Fbv4je", inner, None, "generic"]]])},
                          headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}, timeout=15)
    r.raise_for_status()
    parsed = json.loads(r.text.split("\n\n")[1])[:-2]
    real = json.loads(parsed[0][2])[1]
    if not real.startswith("http"):
        raise ValueError("unexpected answer")
    return real


def resolve_all(urls, limit=80, pause=0.3):
    """Returns {google_url: real_url} for the ones that decoded."""
    out, failures = {}, 0
    for u in list(dict.fromkeys(u for u in urls if "news.google.com" in u))[:limit]:
        try:
            out[u] = decode(u)
        except Exception:  # noqa: BLE001
            failures += 1
            if failures >= 5 and not out:
                break  # Google is refusing us today; stop wasting time
        time.sleep(pause)
    return out
