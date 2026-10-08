"""X（旧Twitter）への投稿を作り、Buffer に予約投稿として登録する.

- 1日1件（セール期間は2件）の「TOP3まとめ」投稿。TOP3を1枚にまとめた画像を添付する
- 画像はサイト内（public/social/）に置き、そのURLを Buffer に渡す
- ハッシュタグは商品名から抜き出す（関係のないタグの大量付与はXのスパム規定に触れるため最大5個）
Buffer の個人用APIキーを環境変数 BUFFER_API_KEY（GitHub の Secrets）から読む。
"""
import datetime as dt
import io
import json
import os
import re
import unicodedata
import urllib.request
from pathlib import Path

from articles import short_name

API = "https://api.buffer.com"
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
POSTED = DATA / "posted.json"
LOG = DATA / "social_log.txt"
JST = dt.timezone(dt.timedelta(hours=9))
NORMAL_SLOTS = [(12, 0)]
SALE_SLOTS = [(12, 0), (20, 30)]
MAX_TAGS = 5
FONTS = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "C:/Windows/Fonts/YuGothB.ttc"]
STOP = {"送料無料", "セット", "公式", "まとめ買い", "大容量", "ギフト", "プレゼント", "選べる", "人気", "おしゃれ",
        "新作", "限定", "お得", "訳あり", "送料込", "本体", "対応", "日本製", "国産", "無添加", "人気商品", "楽天",
        "小玉", "小粒", "極小", "大玉", "骨とり", "骨取り", "骨なし", "新物", "無塩", "有塩", "冷凍", "業務用", "家庭用",
        "長袖", "半袖", "春夏", "秋冬", "子供", "大人", "男の子", "女の子", "メール便", "個包装", "産地直送", "北欧産",
        "プレミアム", "スタンダード", "ラベルレス", "ペットボトル", "即納", "メーカー保証付き", "ストレート", "レディース", "メンズ", "キッズ", "ブレンド", "オリジナル", "ランキング", "レビュー", "クーポン", "ポイント"}


# ---------- 文字数・タグ ----------

def x_len(text):
    """Xの文字数（全角は2、URLは23として数える）."""
    text = re.sub(r"https?://\S+", "x" * 23, text)
    return sum(2 if unicodedata.east_asian_width(c) in "FWA" else 1 for c in text)


NOUNS = ("ニット", "カットソー", "タオル", "パンツ", "シャツ", "スカート", "ワンピース", "ジャケット", "コート", "クリーム",
         "クレンジング", "シャンプー", "マスク", "キット", "セット", "ケース", "ボックス", "ブランケット", "シーツ", "ラグ",
         "カーテン", "ライト", "ケーブル", "フィルム", "スポンジ", "クリーナー", "ブラシ", "シール", "バッグ", "ソックス")


def product_tag(name, desc=None):
    """商品名から、商品の種類を表す語を1つ取り出す（例：炭酸水、ミックスナッツ、ヘアアイロン）."""
    cands = []
    for tok in re.split(r"[\s　/・|｜()（）〈〉<>、,]+", short_name(name, 80)):
        tok = re.sub(r"^[\d.]+|[\d.]+$", "", tok)
        if re.fullmatch(r"[ぁ-ヿ一-鿿ー]{2,12}", tok):
            cands.append(tok)
        else:  # 長くつながった語は、よくある商品名で終わる場合だけその部分を使う
            for n in NOUNS:
                if tok.endswith(n) and n != "セット":
                    cands.append(n)
                    break
    cands = [c for c in cands if c not in STOP and not c.endswith("産") and not re.fullmatch(r"[ぁ-ゟ]+", c)]
    intro = (desc or {}).get("intro", "")
    in_intro = [c for c in cands if c in intro]
    if in_intro:  # 紹介文にも出てくる語＝商品の中心。長い語ほど具体的
        return max(in_intro, key=len)
    return cands[0] if cands else None


def sale_tags(names):
    joined = "\n".join(names)
    tags = []
    if joined.count("マラソン") >= 5:
        tags += ["お買い物マラソン", "買い回り"]
    if len(re.findall(r"スーパーSALE|スーパーセール", joined)) >= 5:
        tags += ["楽天スーパーSALE"]
    return tags


def build_tags(items, sale, descs=None):
    tags = []
    for it in items:
        t = product_tag(it["name"], (descs or {}).get(it["code"]))
        if t and t not in tags:
            tags.append(t)
    tags = tags[:3] + sale
    if len(tags) < MAX_TAGS - 1:
        tags.append("楽天")
    return " ".join("#" + t for t in tags[: MAX_TAGS - 1] + ["PR"])


# ---------- 投稿の中身 ----------

def candidates(cfg, results, budget, recent):
    """投稿の種類ごとにTOP3を作る。返り値は [(種類, 見出し, [(商品, 補足)], リンク先)]."""
    base = cfg["base_url"].rstrip("/")
    allg = [(g, it) for g in cfg["genres"] for it in results.get(g["slug"], []) if it["code"] not in recent]
    out = []
    cheaper = sorted((x for x in allg if x[1].get("price_diff", 0) < 0), key=lambda x: x[1]["price_diff"])[:3]
    if len(cheaper) == 3:
        out.append(("cheaper", "今日の値下がりTOP3", [(it, f"{-it['price_diff']:,}円↓") for _, it in cheaper], base + "/"))
    risers = sorted((x for x in allg if isinstance(x[1].get("move"), int) and x[1]["move"] >= 3),
                    key=lambda x: -x[1]["move"])[:3]
    if len(risers) == 3:
        out.append(("risers", "今日の急上昇TOP3", [(it, f"{it['move']}位UP") for _, it in risers], base + "/"))
    picks = [it for it in budget or [] if it["code"] not in recent][:3]
    if len(picks) == 3:
        out.append(("budget", "1000円台の売れ筋TOP3", [(it, "送料無料") for it in picks],
                    f"{base}/{cfg['budget']['slug']}.html"))
    return out


def compose_text(title, rows, url, tags, day):
    m, d = int(day[5:7]), int(day[8:10])
    nums = ["1️⃣", "2️⃣", "3️⃣"]
    limit = 26
    while True:
        lines = [f"【{title}】{m}/{d}"]
        lines += [f"{nums[i]}{short_name(it['name'], limit)} {it['price']:,}円（{note}）" for i, (it, note) in enumerate(rows)]
        text = "\n".join(lines + ["▼くわしくはこちら", url, tags])
        if x_len(text) <= 280 or limit <= 8:
            return text
        limit -= 2


# ---------- 画像 ----------

def font(size):
    from PIL import ImageFont
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def fetch_image(url):
    from PIL import Image
    if not url:
        return None
    url = re.sub(r"_ex=\d+x\d+", "_ex=400x400", url)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
            return Image.open(io.BytesIO(r.read())).convert("RGB")
    except Exception:  # noqa: BLE001
        return None


def wrap(draw, text, f, width, lines=2):
    out, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=f) > width:
            out.append(cur)
            cur = ch
            if len(out) == lines:
                break
        else:
            cur += ch
    if len(out) < lines and cur:
        out.append(cur)
    if len(out) == lines and "".join(out) != text:
        out[-1] = out[-1][:-1] + "…"
    return out


def make_image(title, rows, day, path):
    from PIL import Image, ImageDraw
    W, H = 1200, 675
    img = Image.new("RGB", (W, H), (246, 244, 240))
    d = ImageDraw.Draw(img)
    for y in range(120):  # 見出しの帯
        t = y / 120
        d.line([(0, y), (W, y)], fill=(int(165 + 50 * t), 0, int(0 + 47 * t)))
    m, dd = int(day[5:7]), int(day[8:10])
    d.text((40, 28), title, font=font(54), fill=(255, 255, 255))
    d.text((W - 40, 46), f"{m}月{dd}日時点", font=font(30), fill=(255, 235, 235), anchor="ra")
    medal = [(217, 164, 0), (154, 165, 177), (185, 114, 46)]
    for i, (it, note) in enumerate(rows):
        x, y, w, h = 30 + i * 390, 145, 360, 500
        d.rounded_rectangle([x, y, x + w, y + h], radius=22, fill=(255, 255, 255))
        pic = fetch_image(it.get("image"))
        if pic:
            pic.thumbnail((260, 260))
            img.paste(pic, (x + (w - pic.width) // 2, y + 20 + (260 - pic.height) // 2))
        d.ellipse([x + 14, y + 14, x + 74, y + 74], fill=medal[i])
        d.text((x + 44, y + 44), str(i + 1), font=font(34), fill=(255, 255, 255), anchor="mm")
        for j, line in enumerate(wrap(d, short_name(it["name"], 40), font(24), w - 36)):
            d.text((x + 18, y + 296 + j * 34), line, font=font(24), fill=(29, 29, 31))
        d.text((x + 18, y + 378), f"{it['price']:,}円", font=font(44), fill=(191, 0, 0))
        d.rounded_rectangle([x + 18, y + 442, x + 18 + d.textlength(note, font=font(24)) + 28, y + 480],
                            radius=10, fill=(232, 89, 12) if "UP" in note else (15, 157, 88))
        d.text((x + 32, y + 447), note, font=font(24), fill=(255, 255, 255))
    d.text((W - 30, H - 22), "楽天ランキング速報 ｜ #PR", font=font(20), fill=(110, 110, 115), anchor="rb")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)


# ---------- Buffer ----------

def gql(key, query):
    body = json.dumps({"query": query}).encode()
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
    for org in gql(key, "query { account { organizations { id name } } }")["account"]["organizations"]:
        q = "query { channels(input: {organizationId: %s}) { id name service } }" % json.dumps(org["id"])
        for c in gql(key, q)["channels"]:
            if c["service"].lower() in ("twitter", "x"):
                return c["id"]
    raise RuntimeError("Buffer に X のチャンネルが接続されていません")


CREATE = """mutation { createPost(input: {text: %s, channelId: %s, schedulingType: automatic, mode: customScheduled,
  dueAt: %s, assets: [{image: {url: %s}}]}) {
  ... on PostActionSuccess { post { id dueAt } }
  ... on MutationError { message } } }"""


def schedule(cfg, results, budget, descs, day, out_dir):
    key = os.environ.get("BUFFER_API_KEY")
    if not key:
        LOG.write_text(f"{day} BUFFER_API_KEY がないため投稿の予約をスキップ\n", encoding="utf-8")
        return
    posted = json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else {}
    if posted.get("_scheduled") == day:
        LOG.write_text(f"{day} 本日分は予約済み\n", encoding="utf-8")
        return
    cutoff = (dt.date.fromisoformat(day) - dt.timedelta(days=7)).isoformat()
    posted = {k: v for k, v in posted.items() if k.startswith("_") or v >= cutoff}
    recent = {k for k in posted if not k.startswith("_")}

    names = [it["name"] for it in budget or []] + [it["name"] for v in results.values() for it in v]
    sale = sale_tags(names)
    d = dt.date.fromisoformat(day)
    now = dt.datetime.now(JST) + dt.timedelta(minutes=10)
    slots = [(h, m) for h, m in (SALE_SLOTS if sale else NORMAL_SLOTS)
             if dt.datetime(d.year, d.month, d.day, h, m, tzinfo=JST) > now]
    cands = candidates(cfg, results, budget, recent)
    if not slots or not cands:
        LOG.write_text(f"{day} 予約なし（残りの投稿枠 {len(slots)} / 候補 {len(cands)}）\n", encoding="utf-8")
        return
    channel = find_channel(key)
    log, base = [f"{day} セール判定: {sale or 'なし'}"], cfg["base_url"].rstrip("/")
    k = d.toordinal() % len(cands)  # 日替わりで種類を回す
    ordered = cands[k:] + cands[:k]
    ok = False
    for (h, m), (kind, title, rows, url) in zip(slots, ordered):
        img_name = f"social/{day}-{kind}.png"
        make_image(title, rows, day, out_dir / img_name)
        text = compose_text(title, rows, url, build_tags([it for it, _ in rows], sale, descs), day)
        due = dt.datetime(d.year, d.month, d.day, h, m, tzinfo=JST).astimezone(dt.timezone.utc)
        q = CREATE % (json.dumps(text), json.dumps(channel), json.dumps(due.strftime("%Y-%m-%dT%H:%M:%S.000Z")),
                      json.dumps(f"{base}/{img_name}"))
        try:
            r = gql(key, q)["createPost"]
            if r.get("message"):
                log.append(f"{kind}: 失敗 {r['message']}")
                continue
            for it, _ in rows:
                posted[it["code"]] = day
            ok = True
            log.append(f"{kind}: {h:02d}:{m:02d} に予約 / {x_len(text)}文字 / 画像 {base}/{img_name}\n{text}")
        except Exception as ex:  # noqa: BLE001
            log.append(f"{kind}: 失敗 {ex}")
    if ok:
        posted["_scheduled"] = day
    POSTED.write_text(json.dumps(posted, ensure_ascii=False, indent=0), encoding="utf-8")
    LOG.write_text("\n---\n".join(log) + "\n", encoding="utf-8")
