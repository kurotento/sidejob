"""Threads・Instagram の投稿計画（data/sns_plan.json）を作る。予約は social.run_plan がまとめて行う.

- Threads : threads.py が作った「悩み別・採点つき」の投稿から点の高い順に1日3本
- Instagram: ショート動画をリールで1本・ストーリーに全部＋TOP3画像をフィードに1枚（キャプションのリンクは押せないのでプロフィールへ誘導）
  （プロアカウントなら自動投稿。個人アカウントだと Buffer の通知方式になる。切り替えたら Buffer でつなぎ直す）
"""
import datetime as dt
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
SNS_PLAN = DATA / "sns_plan.json"
JST = dt.timezone(dt.timedelta(hours=9))

THREADS_TIMES = [(12, 15), (19, 0), (21, 30)]  # 新しいアカウントなので最初は1日3本
# フォロワーが少ないうちは、フォロワー以外にも届くリールを中心にする（ストーリーはフォロワーにしか出ない）
INSTA_REEL_TIMES = [(18, 0), (21, 0)]
INSTA_FEED_TIME = (12, 0)
INSTA_STORY_TIMES = []  # フォロワーが100人くらいになったら [(18, 0), (21, 15)] に戻す

YOUTUBE_TIMES = [(17, 30), (20, 30)]  # ショート動画を YouTube に（Buffer で自動投稿）

# Instagram の検索は投稿文の言葉でも探されるので、1行目に検索される言葉を入れ、タグは内容に合う数個にしぼる
INSTA_TAGS = {
    "red": "#楽天購入品 #楽天お買い物マラソン #送料無料 #PR",
    "green": "#ふるさと納税 #ふるさと納税返礼品 #楽天ふるさと納税 #PR",
}
INSTA_LEAD = {
    "red": "楽天 1000円台 送料無料 おすすめ｜買い回りの候補に",
    "green": "ふるさと納税 おすすめ 返礼品｜レビューの多い人気どころ",
}


def item(service, kind, t, text, image="", video=""):
    return {"service": service, "kind": kind, "time": t.strftime("%m/%d %H:%M"),
            "due": t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "text": text, "image": image, "video": video, "codes": []}


def threads_posts(day, at):
    cache = json.loads((DATA / "threads_posts.json").read_text(encoding="utf-8")) if (DATA / "threads_posts.json").exists() else {}
    todays = sorted(((k, v) for k, v in cache.items() if k.startswith(day + ":") and v.get("patterns")),
                    key=lambda kv: -kv[1]["patterns"][0]["total"])
    out = []
    for (h, m), (k, v) in zip(THREADS_TIMES, todays):
        url = v.get("url")
        if not url:
            continue
        x = item("threads", "threads", at(h, m), v["patterns"][0]["text"])
        x["reply"] = f"{v['reply_lead']}👇\n{url}\n#PR"  # リンクは本文ではなく、自分への返信に入れる
        out.append(x)
    return out


def insta_posts(cfg, day, videos, at):
    base = cfg["base_url"].rstrip("/")
    out = []
    for (h, m), v in zip(INSTA_REEL_TIMES, videos or []):
        theme = v.get("theme") if v.get("theme") in INSTA_TAGS else "red"
        title = re.sub(r"\s*#\S+", "", v["title"]).strip()
        cap = (f"{INSTA_LEAD[theme]}\n{title}\n\nらんくまが30秒で紹介するよ🧸 気になったら保存しておいてね\n"
               f"商品はプロフィールのリンク（楽天ROOM）からまとめて見られます\n\n{INSTA_TAGS[theme]}")
        out.append(item("instagram", "reel", at(h, m), cap, video=f"{base}/{v['file']}"))
    for (h, m), v in zip(INSTA_STORY_TIMES, videos or []):
        out.append(item("instagram", "story", at(h, m), "", video=f"{base}/{v['file']}"))
    plan = DATA / "social_plan.json"
    if plan.exists():
        p = json.loads(plan.read_text(encoding="utf-8"))
        if p.get("day") == day:
            img = next((x for x in p["posts"] if x["kind"] == "budget" and x.get("image")), None)
            if img:
                lines = [ln for ln in img["text"].split("\n") if re.match(r"^[1-3]️⃣", ln)]
                cap = (INSTA_LEAD["red"] + "\n【1000円台・送料無料 売れ筋TOP3】\n\n" + "\n".join(lines) +
                       "\n\n商品はプロフィールのリンク（楽天ROOM）から見られます\n保存しておくと、買い回りのときに便利だよ\n\n"
                       + INSTA_TAGS["red"])
                out.append(item("instagram", "feed", at(*INSTA_FEED_TIME), cap, image=img["image"]))
    return out


SHEET_KIND = {"reel": "post", "story": "story", "feed": "image"}


def jpeg_url(url, out_dir):
    """Instagram の公式APIは JPEG しか受け付けないので、サイトに置いた PNG の横に JPEG を作る."""
    from PIL import Image
    name = url.rsplit("/", 1)[-1]
    src = DATA / "social_img" / name
    if not (src.exists() and out_dir):
        return url
    jpg = name.rsplit(".", 1)[0] + ".jpg"
    Image.open(src).convert("RGB").save(out_dir / "social" / jpg, quality=92)
    return url.rsplit("/", 1)[0] + "/" + jpg


def to_sheet(cfg, day, posts, out_dir):
    import igsheet
    rows = []
    for x in posts:
        due = dt.datetime.strptime(x["due"], "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=dt.timezone.utc).astimezone(JST)
        if due < dt.datetime.now(JST) + dt.timedelta(minutes=10):  # 過ぎた時間の分は入れない
            continue
        url = x["video"] or jpeg_url(x["image"], out_dir)
        rows.append({"日付": day, "投稿枠": "daily", "種別": SHEET_KIND[x["kind"]], "予約日時": due.strftime("%Y-%m-%d %H:%M:%S"),
                     "動画URL": url, "キャプション": x["text"]})
    n = igsheet.add_rows(cfg["instagram_sheet_id"], rows)
    print(f"[sns] Instagram 予約表に {n}件追加")


def youtube_posts(cfg, day, videos, at):
    if cfg.get("youtube_via") != "buffer" or day < cfg.get("youtube_from", ""):
        return []
    out = []
    for (h, m), v in zip(YOUTUBE_TIMES, videos or []):
        x = item("youtube", "short", at(h, m), v.get("desc", ""), video=f"{cfg['base_url'].rstrip('/')}/{v['file']}")
        x["title"] = v["title"][:100]
        out.append(x)
    return out


def build(cfg, day, videos, out_dir=None):
    d = dt.date.fromisoformat(day)
    now = dt.datetime.now(JST) + dt.timedelta(minutes=20)
    at = lambda h, m: dt.datetime(d.year, d.month, d.day, h, m, tzinfo=JST)  # noqa: E731
    old = json.loads(SNS_PLAN.read_text(encoding="utf-8")) if SNS_PLAN.exists() else {}
    if old.get("day") == day:  # 予約済みの状態を残したまま、足りない分だけ足す
        posts = old["posts"]
    else:
        posts = []
    have = {(x["service"], x["kind"], x["time"]) for x in posts}
    insta = insta_posts(cfg, day, videos, at)
    if cfg.get("instagram_via") == "sheet":  # Instagram はスプレッドシートの予約表から投稿する（Buffer は使わない）
        to_sheet(cfg, day, insta, out_dir)
        insta = []
    for x in threads_posts(day, at) + insta + youtube_posts(cfg, day, videos, at):
        if (x["service"], x["kind"], x["time"]) not in have and dt.datetime.strptime(
                x["due"], "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=dt.timezone.utc) > now:
            posts.append(x)
    posts.sort(key=lambda x: x["due"])
    SNS_PLAN.write_text(json.dumps({"day": day, "posts": posts}, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(posts)
