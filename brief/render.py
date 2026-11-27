"""Render every saved digest into a static site: site/index.html (latest) + site/archive/<date>.html."""
import json
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import prefs as P

WD_ZH = "一二三四五六日"
WD_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WD_EN_LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

_env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                   autoescape=select_autoescape(["html"]), trim_blocks=False, lstrip_blocks=False)


def day_info(d):
    dt = date.fromisoformat(d["date"])
    wd = dt.weekday()
    gen = datetime.fromisoformat(d["generated_at"])
    return {
        "num": dt.day,
        "wd_zh": "周" + WD_ZH[wd], "wd_en": WD_EN[wd],
        "long_zh": f"{dt.month}月{dt.day}日 星期{WD_ZH[wd]}",
        "long_en": f"{WD_EN_LONG[wd]}, {MONTHS[dt.month - 1][:3]} {dt.day}",
        "generated": gen.strftime("%Y-%m-%d %H:%M") + f" (UTC{gen.strftime('%z')[:3]})",
    }


def load_digests(data_dir):
    files = sorted(Path(data_dir).glob("*.json"))
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def render_page(d, site, archive, root):
    return _env.get_template("page.html").render(d=d, site=site, archive=archive, root=root, day=day_info(d))


def render_settings(site, prefs, topics, repo):
    cfg = {"repo": repo, "prefs": prefs, "defaults": P.DEFAULTS, "limits": P.LIMITS,
           "topics": [{"id": t["id"], "zh": t["zh"], "en": t["en"]} for t in topics],
           "sources": [{"id": i, "zh": zh, "en": en} for i, zh, en in P.SOURCES]}
    return _env.get_template("settings.html").render(site=site, cfg=cfg)


def build_site(data_dir, out_dir, site, settings_page=None):
    """settings_page: {"prefs", "topics" (built-in), "repo"} to also write settings.html."""
    digests = load_digests(data_dir)
    if not digests:
        return None
    out = Path(out_dir)
    (out / "archive").mkdir(parents=True, exist_ok=True)
    recent = digests[-site.get("archive_days", 30):]
    archive = [{"date": d["date"], "href": f"archive/{d['date']}.html"} for d in reversed(recent)]
    for d in digests:
        (out / "archive" / f"{d['date']}.html").write_text(render_page(d, site, archive, "../"), encoding="utf-8")
    latest = digests[-1]
    (out / "index.html").write_text(render_page(latest, site, archive, ""), encoding="utf-8")
    if settings_page:
        (out / "settings.html").write_text(render_settings(site, **settings_page), encoding="utf-8")
    return out / "index.html"
