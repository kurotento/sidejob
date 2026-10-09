"""Pinterest 用のピン（縦長画像＋まとめて作成用の CSV）を週1回作る.

Pinterest の公式APIで自動投稿するには審査が必要なため、ビジネスアカウントの
「CSV でピンをまとめて作成」機能を使う。毎週月曜に public/pins.csv を作り、ユーザーがアップロードする。
CSV には1週間分（1日5ピン）の公開日時を入れておくので、アップロード後は Pinterest が順に公開する。

ピンは何か月も検索に出続けるので、画像には値段を入れない（値段が変わってもずれないように）。
"""
import csv
import datetime as dt
import io
import json
import re
import shutil
from pathlib import Path

from articles import short_name, slug_of
from social import fetch_image, font, wrap, yen  # noqa: F401  (yen は将来の説明文用)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
IMG_DIR = DATA / "pin_img"
HISTORY = DATA / "pins_history.json"
ICON = ROOT / "x_images" / "icon_400x400.png"
JST = dt.timezone(dt.timedelta(hours=9))
REPEAT_DAYS = 60  # 同じ商品を次にピンにするまでの日数
TIMES = [(7, 30), (12, 0), (17, 0), (20, 30), (22, 0)]  # 1日5ピン（Pinterest がよく見られる時間）

# ボード名（Pinterest で同じ名前のボードを作っておく）
BOARDS = {
    "budget": "1000円台・送料無料の売れ筋",
    "interior": "収納・インテリアの人気アイテム",
    "daily": "日用品の人気アイテム",
    "furusato": "ふるさと納税 人気返礼品",
}
LABEL = {"budget": "1000円台・送料無料", "interior": "収納・インテリア", "daily": "日用品", "furusato": "ふるさと納税"}
KEYWORDS = {
    "budget": "楽天,1000円台,送料無料,買い回り,お買い物マラソン,プチプラ",
    "interior": "収納,収納アイデア,インテリア,片付け,楽天,暮らし",
    "daily": "日用品,ストック,まとめ買い,楽天,暮らし,節約",
    "furusato": "ふるさと納税,返礼品,ふるさと納税おすすめ,楽天ふるさと納税,節約",
}
# サプリ・健康食品は Pinterest の審査で弾かれる（健康の表現の決まりも厳しい）ので入れない
SKIP = re.compile(r"サプリ|栄養機能食品|機能性表示食品|特定保健用食品|トクホ|プロテイン|ダイエット")
RED, GREEN = (191, 0, 0), (31, 138, 76)


def make_pin(it, kind, path):
    """1000x1500 の縦長ピン画像."""
    from PIL import Image, ImageDraw
    W, H = 1000, 1500
    accent = GREEN if kind == "furusato" else RED
    img = Image.new("RGB", (W, H), (246, 244, 240))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 170], fill=accent)
    d.text((50, 46), LABEL[kind], font=font(64), fill=(255, 255, 255))
    d.text((W - 50, 70), "楽天で人気", font=font(40), fill=(255, 230, 230), anchor="ra")
    d.rounded_rectangle([50, 210, W - 50, 1060], radius=36, fill=(255, 255, 255))
    pic = fetch_image(it.get("image"), 800)
    if pic:  # 楽天の画像は小さめなので、枠いっぱいまで拡大する
        r = min(780 / pic.width, 780 / pic.height)
        pic = pic.resize((int(pic.width * r), int(pic.height * r)), Image.LANCZOS)
        img.paste(pic, ((W - pic.width) // 2, 245 + (780 - pic.height) // 2))
    for j, line in enumerate(wrap(d, short_name(it["name"], 60), font(46), W - 100, 3)):
        d.text((50, 1090 + j * 62), line, font=font(46), fill=(29, 29, 31))
    info = f"★{it['rating']:.1f}（レビュー{it['reviews']:,}件）" if it.get("reviews", 0) >= 10 else ""
    if kind == "furusato":
        info = (f"{it['shop']}  " + info).strip()
    d.text((50, 1290), info, font=font(40), fill=accent)
    d.line([(50, 1365), (W - 50, 1365)], fill=(225, 220, 212), width=2)
    if ICON.exists():
        bear = Image.open(ICON).convert("RGB").resize((90, 90))
        img.paste(bear, (50, 1385))
    d.text((160, 1410), "らんくま｜楽天の売れ筋・ふるさと納税", font=font(32), fill=(110, 110, 115))
    d.text((W - 50, 1410), "#PR", font=font(32), fill=(110, 110, 115), anchor="ra")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, quality=82)


def pin_text(it, kind, desc):
    name = short_name(it["name"], 28)
    if kind == "furusato":
        title = f"【ふるさと納税】{name}｜{it['shop']}の人気返礼品"
    elif kind == "budget":
        title = f"【1000円台・送料無料】{name}｜楽天の売れ筋"
    else:
        title = f"【{LABEL[kind]}】{name}｜楽天で人気"
    parts = []
    if desc:
        from room import plain  # 「〜だよ」をふつうの文末にする
        parts.append(plain(re.split(r"(?<=[。！!])", desc["intro"])[0]))
        parts += [f"・{plain(f).rstrip('。')}" for f in desc.get("features", [])[:3]]
        if desc.get("for_whom"):
            parts.append(plain(desc["for_whom"]))
    elif it.get("catch") or it.get("caption"):  # 紹介文のない商品は、ショップのキャッチコピーを短く使う
        parts.append(re.sub(r"\s+", " ", it.get("catch") or it["caption"])[:120])
    parts.append("楽天のレビュー件数・ランキングをもとに毎日まとめています。")
    parts.append("※楽天アフィリエイトを利用しています（PR）")
    return title[:100], " ".join(parts)[:500]  # 改行は CSV の取り込みで崩れることがあるので使わない


def link_for(it, kind, base):
    if kind == "furusato":
        return f"{base}/furusato/{slug_of(it['code'])}"
    if kind == "budget":
        return f"{base}/{slug_of(it['code'])}"
    a = re.sub(r"[^A-Za-z0-9_-]", "-", it["code"])  # Pinterest は同じリンクのピンを受け付けないので商品ごとに変える
    return f"{base}/{kind}.html?p={a}#{a}"


def build(cfg, results, budget, fcats, descs, day, out_dir, force=False):
    """月曜（またはファイルがないとき）に1週間分のピンを作る。返り値はピンの数."""
    d = dt.date.fromisoformat(day)
    out_csv = out_dir / "pins.csv"
    hist = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else {}
    if not (force or d.weekday() == 0 or not hist):
        restore(out_dir)  # 週の途中は、月曜に作ったものをサイトに置き直すだけ
        return 0
    if hist.get("_week") == day:
        restore(out_dir)
        return 0
    cutoff = (d - dt.timedelta(days=REPEAT_DAYS)).isoformat()
    recent = {k for k, v in hist.items() if not k.startswith("_") and v >= cutoff}
    base = cfg["base_url"].rstrip("/")
    pools = {
        "budget": [it for it in budget or [] if descs.get(it["code"])],
        "interior": [it for it in (results or {}).get("interior", []) if it["price"] <= 10000],
        "daily": [it for it in (results or {}).get("daily", []) if it["price"] <= 10000],
        "furusato": [it for c in fcats or [] for it in c["items"] if descs.get(it["code"])],
    }
    order = ["budget", "interior", "furusato", "daily", "budget"]  # 1日5ピンの並び
    pools = {k: [x for x in v if not SKIP.search(x["name"])] for k, v in pools.items()}
    picks = []
    used = set(recent)
    for n in range(7 * len(TIMES)):
        kind = order[n % len(order)]
        it = next((x for x in pools[kind] if x["code"] not in used), None)
        if not it:
            continue
        used.add(it["code"])
        day_i, slot = divmod(len(picks), len(TIMES))
        h, m = TIMES[slot]
        when = dt.datetime(d.year, d.month, d.day, h, m, tzinfo=JST) + dt.timedelta(days=day_i + 1)
        picks.append((kind, it, when))
    if IMG_DIR.exists():
        shutil.rmtree(IMG_DIR)
    rows = []
    for kind, it, when in picks:
        name = re.sub(r"[^A-Za-z0-9_-]", "-", it["code"]) + ".jpg"
        make_pin(it, kind, IMG_DIR / name)
        title, desc_text = pin_text(it, kind, descs.get(it["code"]))
        rows.append([title, f"{base}/pins/{name}", BOARDS[kind], "", desc_text, link_for(it, kind, base),
                     when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), KEYWORDS[kind]])
        hist[it["code"]] = day
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Title", "Media URL", "Pinterest board", "Thumbnail", "Description", "Link", "Publish date", "Keywords"])
    w.writerows(rows)
    (DATA / "pins.csv").write_text(buf.getvalue(), encoding="utf-8", newline="")
    hist["_week"] = day
    hist = {k: v for k, v in hist.items() if k.startswith("_") or v >= cutoff}
    HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=0), encoding="utf-8")
    restore(out_dir)
    return len(rows)


def restore(out_dir):
    """サイトは毎回作り直されるので、ピンの画像と CSV を data から置き直す."""
    if IMG_DIR.exists():
        shutil.copytree(IMG_DIR, out_dir / "pins", dirs_exist_ok=True)
    if (DATA / "pins.csv").exists():
        shutil.copy(DATA / "pins.csv", out_dir / "pins.csv")
