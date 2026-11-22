"""每日简报：抓取 → AI 整理 → 生成网站 → 飞书推送。

    python run.py                正常运行（今天已经生成过就跳过）
    python run.py --force        重新生成今天的日报
    python run.py --fetch-only   只测试抓取，打印每个来源抓到几条
    python run.py --no-push      不推送飞书
    python run.py --push-latest  把最新一期推送到飞书（云端在网站部署完后用它）
    python run.py --render-only  只用已有数据重新生成网站
    python run.py --use-cache    不重新抓取，用今天抓过的缓存（调试用）

本地运行时，密钥放在同目录的 .env 文件里（参考 .env.example）。
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from brief import digest, feishu, llm, render, sources

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "digests"
SITE = ROOT / "site"
CACHE = ROOT / ".cache"

SOURCE_NAMES = {"douyin": ("抖音", "Douyin"), "weibo": ("微博", "Weibo"), "zhihu": ("知乎", "Zhihu"),
                "bilibili": ("B站", "Bilibili"), "x_trends": ("X 趋势", "X trends"),
                "youtube": ("YouTube", "YouTube"), "news": ("Google News", "Google News")}


def load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_yaml(name):
    return yaml.safe_load((ROOT / "config" / name).read_text(encoding="utf-8"))


def set_output(key, value):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def site_url(settings):
    return settings["site"].get("url") or os.environ.get("SITE_URL", "")


def push_latest(settings):
    hooks = [h.strip() for h in os.environ.get("FEISHU_WEBHOOK", "").split(",") if h.strip()]
    if not hooks:
        print("飞书：没有设置 FEISHU_WEBHOOK，跳过推送")
        return
    secrets = [s.strip() for s in os.environ.get("FEISHU_SECRET", "").split(",")]
    latest = render.load_digests(DATA)[-1]
    payload = feishu.build_card(latest, settings["site"], site_url(settings),
                                per_topic=settings["digest"].get("card_per_topic", 3))
    for i, hook in enumerate(hooks):
        feishu.send(hook, secrets[i] if i < len(secrets) else "", payload)
        print(f"飞书：已推送 {latest['date']}（第 {i + 1} 个机器人）")


def failed_names(stats):
    bad = []
    for name, v in stats.items():
        if isinstance(v, str):
            key = "news" if name.startswith("news:") else name
            if SOURCE_NAMES[key] not in bad:
                bad.append(SOURCE_NAMES[key])
    return [b[0] for b in bad], [b[1] for b in bad]


def main():
    ap = argparse.ArgumentParser(description="每日简报")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--fetch-only", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--push-latest", action="store_true")
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--use-cache", action="store_true")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252 and choke on Chinese
        stream.reconfigure(encoding="utf-8", errors="replace")

    load_env(ROOT / ".env")
    settings, topics = load_yaml("settings.yaml"), load_yaml("topics.yaml")["topics"]
    src_cfg = load_yaml("sources.yaml")
    tz = ZoneInfo(settings["timezone"])
    now = datetime.now(tz)
    today = now.date().isoformat()
    out_path = DATA / f"{today}.json"
    set_output("changed", "false")

    if args.render_only:
        print("网站：", render.build_site(DATA, SITE, settings["site"]))
        return 0
    if args.push_latest:
        push_latest(settings)
        return 0
    if out_path.exists() and not (args.force or args.fetch_only):
        print(f"{today} 的日报已经生成过了，跳过（要重新生成请加 --force）")
        return 0
    if (os.environ.get("GITHUB_EVENT_NAME") == "schedule" and now.hour < settings.get("run_after_hour", 0)
            and not args.force):
        print(f"现在是当地 {now:%H:%M}，还没到 {settings['run_after_hour']} 点，跳过")
        return 0

    cache = CACHE / f"raw-{today}.json"
    if args.use_cache and cache.exists():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        items, stats = cached["items"], cached["stats"]
        print("用缓存：", cache.relative_to(ROOT))
    else:
        print(f"抓取中…（{now:%Y-%m-%d %H:%M %Z}）")
        items, stats = sources.fetch_all(src_cfg, topics)
    for name, v in stats.items():
        print(f"  {name:28} {v}")
    print(f"  共 {len(items)} 条（去重后）")
    CACHE.mkdir(exist_ok=True)
    cache.write_text(json.dumps({"items": items, "stats": stats}, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.fetch_only:
        return 0 if items else 1

    llm_cfg = settings["llm"]
    if not llm.have_key(llm_cfg):
        print(f"⚠ 没有设置 {llm_cfg['api_key_env']}，无法生成摘要。请按 README 把 key 存好。")
        # A manual cloud run still publishes what we already have, so the site and Feishu can be tested.
        if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch" and render.build_site(DATA, SITE, settings["site"]):
            print("已用现有数据重新发布网站")
            set_output("changed", "true")
        return 0
    if len(items) < 20:
        print("⚠ 抓到的内容太少，今天不生成")
        return 1

    print(f"AI 整理中…（{llm.model_label(llm_cfg)}）")
    try:
        body = digest.make_digest(items, topics, settings["digest"], llm_cfg)
    except llm.LLMError as e:
        print(f"❌ AI 整理失败：{e}")
        return 1
    failed_zh, failed_en = failed_names(stats)
    d = {"date": today, "generated_at": datetime.now(tz).isoformat(timespec="seconds"), **body,
         "stats": {"model": llm.model_label(llm_cfg), "item_count": len(items), "sources": stats,
                   "failed_zh": failed_zh, "failed_en": failed_en}}
    DATA.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print("已保存：", out_path.relative_to(ROOT))
    print("网站：", render.build_site(DATA, SITE, settings["site"]))
    set_output("changed", "true")

    if not args.no_push:
        push_latest(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
