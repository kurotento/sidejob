"""X（旧Twitter）への投稿文を作り、Buffer に予約投稿として登録する.

Buffer の個人用APIキーを環境変数 BUFFER_API_KEY（GitHub の Secrets）から読む。
X の公式連携を持つ Buffer 経由で投稿するため、X のルール上の問題はない。
"""
import datetime as dt
import json
import os
import re
import unicodedata
import urllib.request
from pathlib import Path

from articles import short_name, slug_of

API = "https://api.buffer.com"
DATA = Path(__file__).resolve().parent / "data"
POSTED = DATA / "posted.json"
LOG = DATA / "social_log.txt"
JST = dt.timezone(dt.timedelta(hours=9))
SLOTS = [(12, 0), (20, 30)]  # 投稿する時刻（日本時間）
TAGS = "#楽天 #楽天市場 #PR"


def x_len(text):
    """Xの文字数（全角は2、URLは23として数える）."""
    text = re.sub(r"https?://\S+", "x" * 23, text)
    return sum(2 if unicodedata.east_asian_width(c) in "FWA" else 1 for c in text)


def fit(lines, url, limit=280):
    """収まるまで商品名（2行目以降の長い行）を削る."""
    while True:
        text = "\n".join(lines + [url, TAGS])
        if x_len(text) <= limit:
            return text
        i = max(range(len(lines)), key=lambda k: len(lines[k]))
        if len(lines[i]) <= 12:
            return text
        lines[i] = lines[i][: len(lines[i]) - 4].rstrip("…") + "…"


def first_sentence(desc):
    if not desc:
        return ""
    s = re.split(r"(?<=[。！!])", desc["intro"])[0]
    return s if len(s) <= 60 else ""


def compose(cfg, results, budget, descs, recent):
    """今日の投稿候補を優先順に作る。返り値は [(商品コード, 本文)]."""
    base = cfg["base_url"].rstrip("/")
    posts = []
    for it in budget or []:
        if it["code"] in recent:
            continue
        d = descs.get(it["code"])
        stars = f"★{it['rating']:.2f}（レビュー{it['reviews']:,}件）" if it["reviews"] else ""
        lines = [f"【1000円台の売れ筋】{short_name(it['name'], 40)}",
                 f"{it['price']:,}円・送料無料 {stars}".strip()]
        if first_sentence(d):
            lines.append(first_sentence(d))
        posts.append((it["code"], fit(lines, f"{base}/{slug_of(it['code'])}")))
        break
    risers = sorted(((g, it) for g in cfg["genres"] for it in results.get(g["slug"], [])
                     if isinstance(it.get("move"), int) and it["move"] >= 5 and it["code"] not in recent),
                    key=lambda x: -x[1]["move"])
    cheaper = sorted(((g, it) for g in cfg["genres"] for it in results.get(g["slug"], [])
                      if it.get("price_diff", 0) < 0 and it["code"] not in recent),
                     key=lambda x: x[1]["price_diff"])
    if cheaper:
        g, it = cheaper[0]
        lines = [f"【値下がり】{g['title']}ランキング{it['rank']}位",
                 short_name(it["name"], 40),
                 f"{it['price'] - it['price_diff']:,}円 → {it['price']:,}円（{-it['price_diff']:,}円安）"]
        posts.append((it["code"], fit(lines, f"{base}/{g['slug']}.html")))
    if risers:
        g, it = risers[0]
        lines = [f"【急上昇】{g['title']}ランキングで{it['move']}位アップ→{it['rank']}位",
                 short_name(it["name"], 40), f"{it['price']:,}円"]
        posts.append((it["code"], fit(lines, f"{base}/{g['slug']}.html")))
    # 変動データがまだない日は、1000円台からもう1件
    for it in budget or []:
        if len(posts) >= len(SLOTS) + 1:
            break
        if it["code"] in recent or any(it["code"] == c for c, _ in posts):
            continue
        lines = [f"【買い回りの候補に】{short_name(it['name'], 40)}", f"{it['price']:,}円・送料無料"]
        posts.append((it["code"], fit(lines, f"{base}/{slug_of(it['code'])}")))
    return posts


def gql(key, query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as res:
        data = json.load(res)
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False)[:300])
    return data["data"]


def find_channel(key):
    if os.environ.get("BUFFER_CHANNEL_ID"):
        return os.environ["BUFFER_CHANNEL_ID"]
    orgs = gql(key, "query { account { organizations { id name } } }")["account"]["organizations"]
    for org in orgs:
        q = "query { channels(input: {organizationId: %s}) { id name service } }" % json.dumps(org["id"])
        chans = gql(key, q)["channels"]
        for c in chans:
            if c["service"].lower() in ("twitter", "x"):
                return c["id"]
    raise RuntimeError("Buffer に X のチャンネルが接続されていません")


CREATE = """mutation { createPost(input: {text: %s, channelId: %s, schedulingType: automatic, mode: customScheduled, dueAt: %s}) {
  ... on PostActionSuccess { post { id dueAt } }
  ... on MutationError { message } } }"""


def schedule(cfg, results, budget, descs, day):
    key = os.environ.get("BUFFER_API_KEY")
    log = []
    if not key:
        LOG.write_text(f"{day} BUFFER_API_KEY がないため投稿の予約をスキップ\n", encoding="utf-8")
        return
    posted = json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else {}
    if day in posted.values():
        LOG.write_text(f"{day} 本日分は予約済み\n", encoding="utf-8")
        return
    cutoff = (dt.date.fromisoformat(day) - dt.timedelta(days=14)).isoformat()
    posted = {k: v for k, v in posted.items() if v >= cutoff}
    posts = compose(cfg, results, budget, descs, set(posted))[: len(SLOTS)]
    try:
        channel = find_channel(key)
    except Exception as ex:  # noqa: BLE001
        LOG.write_text(f"{day} チャンネル取得失敗: {ex}\n", encoding="utf-8")
        return
    d = dt.date.fromisoformat(day)
    now = dt.datetime.now(JST) + dt.timedelta(minutes=10)
    slots = [(h, m) for h, m in SLOTS if dt.datetime(d.year, d.month, d.day, h, m, tzinfo=JST) > now]
    if not slots:
        LOG.write_text(f"{day} 本日の投稿枠はすべて過ぎています
", encoding="utf-8")
        return
    for (code, text), (h, m) in zip(posts, slots):
        due = dt.datetime(d.year, d.month, d.day, h, m, tzinfo=JST).astimezone(dt.timezone.utc)
        q = CREATE % (json.dumps(text), json.dumps(channel), json.dumps(due.strftime("%Y-%m-%dT%H:%M:%S.000Z")))
        try:
            r = gql(key, q)["createPost"]
            if r.get("message"):
                log.append(f"{code}: 失敗 {r['message']}")
                continue
            posted[code] = day
            log.append(f"{code}: {h:02d}:{m:02d} に予約 / {x_len(text)}文字\n{text}")
        except Exception as ex:  # noqa: BLE001
            log.append(f"{code}: 失敗 {ex}")
    POSTED.write_text(json.dumps(posted, ensure_ascii=False, indent=0), encoding="utf-8")
    LOG.write_text(f"{day}\n" + "\n---\n".join(log) + "\n", encoding="utf-8")
