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
import shutil
import time
import unicodedata
import urllib.request
from pathlib import Path

from articles import short_name, slug_of

API = "https://api.buffer.com"
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
POSTED = DATA / "posted.json"
LOG = DATA / "social_log.txt"
JST = dt.timezone(dt.timedelta(hours=9))
SLOTS = [(7, 30), (8, 15), (9, 0), (9, 45), (10, 30), (11, 15), (12, 0), (12, 45), (13, 30), (14, 15),
         (15, 0), (15, 45), (16, 30), (17, 15), (18, 0), (18, 45), (19, 30), (20, 15), (21, 0), (22, 0)]
BUFFER_CAP = 10  # Buffer無料プランで同時に予約できる件数。昼にもう一度予約して1日20件にする
MAX_TAGS = 5
FONTS = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "C:/Windows/Fonts/YuGothB.ttc"]
STOP = {"送料無料", "セット", "公式", "まとめ買い", "大容量", "ギフト", "プレゼント", "選べる", "人気", "おしゃれ",
        "新作", "限定", "お得", "訳あり", "送料込", "本体", "対応", "日本製", "国産", "無添加", "人気商品", "楽天",
        "小玉", "小粒", "極小", "大玉", "骨とり", "骨取り", "骨なし", "新物", "無塩", "有塩", "冷凍", "業務用", "家庭用",
        "長袖", "半袖", "春夏", "秋冬", "子供", "大人", "男の子", "女の子", "メール便", "個包装", "産地直送", "北欧産",
        "プレミアム", "スタンダード", "ラベルレス", "ペットボトル", "即納", "メーカー保証付き", "ストレート", "レディース", "メンズ", "キッズ", "ブレンド", "オリジナル", "ランキング", "レビュー", "クーポン", "ポイント",
        "内容量", "定期便", "先行予約", "予約", "数量限定", "期間限定", "早割", "選択可能", "お届け", "発送", "配送", "出荷", "新米", "当日"}


# ---------- 文字数・タグ ----------

def x_len(text):
    """Xの文字数（全角は2、URLは23として数える）."""
    text = re.sub(r"https?://\S+", "x" * 23, text)
    return sum(2 if unicodedata.east_asian_width(c) in "FWA" else 1 for c in text)


NOUNS = ("ニット", "カットソー", "タオル", "パンツ", "シャツ", "スカート", "ワンピース", "ジャケット", "コート", "クリーム",
         "クレンジング", "シャンプー", "マスク", "キット", "セット", "ケース", "ボックス", "ブランケット", "シーツ", "ラグ",
         "カーテン", "ライト", "ケーブル", "フィルム", "スポンジ", "クリーナー", "ブラシ", "シール", "バッグ", "ソックス")


def yen(it, prefix=""):
    """値段の表記。サイズ・色などで値段が変わる商品は、楽天の表示（最安値〜）とずれるので書かない."""
    return "" if it.get("has_range") else f"{prefix}{it['price']:,}円"


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
    cands = [c for c in cands if c not in STOP and not c.endswith("産") and not re.fullmatch(r"[ぁ-ゟ]{1,2}", c)]
    intro = (desc or {}).get("intro", "")
    in_intro = [c for c in cands if c in intro]
    if in_intro:  # 紹介文にも出てくる語＝商品の中心。長い語ほど具体的
        return max(in_intro, key=len)
    return cands[0] if cands else None


DT_PAT = r"(\d{1,2})/(\d{1,2})(?:\s*[（(][^）)]{1,3}[）)])?\s*(\d{1,2}):(\d{2})"


def sale_period(names, now):
    """商品名に書かれた「10/4 20:00〜10/9 01:59」などから、セールの開始・終了日時を推定する."""
    starts, ends = [], []
    for n in names:
        found = [(m.start(), m.end(), m.groups()) for m in re.finditer(DT_PAT, n)]
        for k, (s, e, (mo, d, h, mi)) in enumerate(found):
            try:
                t = dt.datetime(now.year, int(mo), int(d), int(h), int(mi), tzinfo=JST)
            except ValueError:
                continue
            if t - now > dt.timedelta(days=200):  # 年をまたぐ場合（12月に1月の日付など）
                t = t.replace(year=now.year - 1)
            elif now - t > dt.timedelta(days=200):
                t = t.replace(year=now.year + 1)
            before, after = n[max(0, s - 2):s], n[e:e + 3]
            if re.search(r"[~〜～]", after) or (len(found) == 2 and k == 0):
                starts.append(t)
            elif re.search(r"[~〜～]", before) or re.search(r"迄|まで", after) or (len(found) == 2 and k == 1):
                ends.append(t)
    common = lambda xs: max(set(xs), key=xs.count) if xs else None  # noqa: E731
    return common(starts), common(ends)


def sale_tags(names, now=None):
    """商品名からセール開催中かを判定する。期間が読み取れれば、その期間内のときだけ開催中とする."""
    now = now or dt.datetime.now(JST)
    tags = []
    marathon = [n for n in names if "マラソン" in n]
    if len(marathon) >= 5:
        start, end = sale_period(marathon, now)
        if not ((start and now < start) or (end and now > end)):
            tags += ["お買い物マラソン", "買い回り"]
    supersale = [n for n in names if re.search(r"スーパーSALE|スーパーセール", n)]
    if len(supersale) >= 5:
        start, end = sale_period(supersale, now)
        if not ((start and now < start) or (end and now > end)):
            tags += ["楽天スーパーSALE"]
    return tags


def build_tags(items, sale, descs=None):
    """新規の人に見つけてもらうためのタグ。商品名から最大3つ＋セール中のタグ.

    PR表記は投稿の先頭（「楽天 #PR」）で行うので、ここには含めない。
    """
    tags = []
    for it in items:
        t = product_tag(it["name"], (descs or {}).get(it["code"]))
        if t and t not in tags:
            tags.append(t)
    return " ".join("#" + t for t in tags[:3] + sale)


# ---------- 投稿の中身 ----------

def candidates(cfg, results, budget, recent, descs=None, day="2000-01-01", fcats=None):
    """1日分の投稿候補を、種類がばらけるように並べて返す.

    返り値は [(種類, 見出し, [(商品, 補足)], リンク先)]。単品紹介は rows が1件。
    同じ商品は同じ日に2回出さない。直近7日に投稿した商品は TOP3 からは除く。
    """
    base = cfg["base_url"].rstrip("/")
    used = set(recent)
    fresh = lambda it: it["code"] not in used  # noqa: E731

    def take(pairs, n=3):
        got = [p for p in pairs if fresh(p[0])][:n]
        if len(got) == n:
            used.update(p[0]["code"] for p in got)
            return got
        return None

    allg = [it for g in cfg["genres"] for it in results.get(g["slug"], [])]
    tops = []
    cheaper = take([(it, f"{-it['price_diff']:,}円↓") for it in sorted(
        (x for x in allg if x.get("price_diff", 0) < 0 and not x.get("has_range")), key=lambda x: x["price_diff"])])
    if cheaper:
        tops.append(("cheaper", "今日の値下がりTOP3", cheaper, base + "/"))
    risers = take([(it, f"{it['move']}位UP") for it in sorted(
        (x for x in allg if isinstance(x.get("move"), int) and x["move"] >= 3), key=lambda x: -x["move"])])
    if risers:
        tops.append(("risers", "今日の急上昇TOP3", risers, base + "/"))
    picks = take([(it, "送料無料") for it in budget or []])
    if picks:
        tops.append(("budget", "1000円台の売れ筋TOP3", picks, f"{base}/{cfg['budget']['slug']}.html"))
    # ジャンル別TOP3（日替わりで並び順を回す）
    gs = cfg["genres"]
    k = dt.date.fromisoformat(day).toordinal() % len(gs)
    for g in gs[k:] + gs[:k]:
        rows = take([(it, f"{it['rank']}位") for it in results.get(g["slug"], [])])
        if rows:
            tops.append((f"genre-{g['slug']}", f"{g['title']}の売れ筋TOP3", rows, f"{base}/{g['slug']}.html"))
    # 単品紹介（紹介文がある1000円台の商品）
    singles = []
    for it in budget or []:
        if fresh(it) and (descs or {}).get(it["code"]):
            used.add(it["code"])
            singles.append(("single", "1000円台の注目商品", [(it, "送料無料")], f"{base}/{slug_of(it['code'])}"))
    # TOP3 と単品を交互に並べる
    out = []
    while tops or singles:
        if tops:
            out.append(tops.pop(0))
        if singles:
            out.append(singles.pop(0))
    # ふるさと納税を3件ごとに1件差し込む
    ftops, fsingles = furusato_candidates(cfg, fcats, used, descs or {}, day)
    fq = []
    while ftops or fsingles:
        if ftops:
            fq.append(ftops.pop(0))
        if fsingles:
            fq.append(fsingles.pop(0))
    mixed = []
    for i, x in enumerate(out):
        mixed.append(x)
        if (i + 1) % 3 == 0 and fq:
            mixed.append(fq.pop(0))
    return mixed + fq


HOOKS = {
    "cheaper": ["昨日より安くなってるの見つけた👀", "値下がりしてる…！今のうちにチェック", "お、値下がりしてる！"],
    "risers": ["今これ急に売れてる📈", "ランキング急上昇中のやつ", "昨日からぐんぐん順位が上がってる"],
    "budget": ["1000円台・送料無料で今売れてるやつ", "買い回りの1店舗に使える1000円台", "送料無料の1000円台、今売れてるのはこれ"],
    "genre": ["{g}、今日はこれが売れてる", "{g}の売れ筋チェック✍️", "{g}で今いちばん売れてるのはこの3つ"],
}


def pick(seed, options):
    return options[sum(map(ord, seed)) % len(options)]


def finish(lines, url, tags):
    return "\n".join(["楽天 #PR"] + lines + ["👇", url] + ([tags] if tags else []))


def compose_text(title, rows, url, tags, day, kind="budget"):
    """TOP3 の投稿。人が話すような短い書き出し＋3商品."""
    nums = ["1️⃣", "2️⃣", "3️⃣"]
    if kind.startswith("genre"):
        hook = pick(day + kind, HOOKS["genre"]).format(g=title.replace("の売れ筋TOP3", ""))
    else:
        hook = pick(day + kind, HOOKS.get(kind, HOOKS["budget"]))
    limit = 26
    while True:
        lines = [hook] + [f"{nums[i]}{short_name(it['name'], limit)} {yen(it)}（{note}）".replace(" （", "（")
                          for i, (it, note) in enumerate(rows)]
        text = finish(lines, url, tags)
        if x_len(text) <= 280 or limit <= 8:
            return text
        limit -= 2


def single_hook(it, day):
    if it.get("price_diff", 0) < 0 and not it.get("has_range"):
        return f"は！昨日より{-it['price_diff']:,}円値下がりしてる！"
    if isinstance(it.get("move"), int) and it["move"] >= 10:
        return f"昨日から{it['move']}位も上がってる📈"
    if it["reviews"] >= 1000:
        return f"レビュー{it['reviews'] // 1000 * 1000:,}件超えの定番"
    if it["point_rate"] >= 5:
        return f"今ならポイント{it['point_rate']}倍✨"
    return pick(day + it["code"], ["送料無料の1000円台、買い回りの1店舗に", "1000円台で送料無料のやつ見つけた",
                                   "これ1000円台なのに送料無料"])


def compose_single(it, desc, url, tags, day):
    """1商品の投稿。データに基づく一言＋紹介文の最初の一文（体験談は書かない）."""
    stars = f"（★{it['rating']:.1f}）" if it["reviews"] >= 10 else ""
    lead = re.split(r"(?<=[。！!])", desc["intro"])[0] if desc else ""
    limit = 40
    while True:
        lines = [single_hook(it, day), "", short_name(it["name"], limit), f"{yen(it) + '、' if yen(it) else ''}送料無料！{stars}"]
        if lead:
            lines.append(lead)
        text = finish(lines, url, tags)
        if x_len(text) <= 280:
            return text
        if lead:
            lead = ""
            continue
        if limit <= 10:
            return text
        limit -= 4


def event_posts(day, url, sale):
    """楽天の毎月の定番イベント日・セール中のお知らせ（リンク先は1000円台のまとめ）.

    キャンペーンの細かい条件は変わることがあるため、断定せず公式ページの確認を促す。
    """
    d = int(day[8:10])
    out = []
    if d % 5 == 0:
        out.append("今日は5と0のつく日！\n楽天カードで買う人はエントリーを忘れずに✍️\n（条件は楽天の公式ページで確認してね）")
    if d == 1:
        out.append("今日は毎月1日のワンダフルデー！\nエントリーを忘れずに✍️\n（条件は楽天の公式ページで確認してね）")
    if d == 18:
        out.append("今日は楽天のご愛顧感謝デー！\n会員ランクによってポイントが変わる日だよ\n（条件は楽天の公式ページで確認してね）")
    if sale:
        out.append("お買い物マラソン開催中！\n1ショップ1,000円以上の買い回りでポイント倍率が上がるやつ\n送料無料の1000円台、まとめてます")
    return [finish([t], url, "#お買い物マラソン" if sale and "マラソン" in t else "") for t in out[:2]]


# ---------- ふるさと納税 ----------

FURUSATO_HOOKS = ["ふるさと納税、{g}ならこのへんが人気", "{g}の返礼品、レビューが多いのはこの3つ",
                  "今年のふるさと納税に。{g}の定番返礼品"]
FURUSATO_TAGS = "#ふるさと納税 #楽天ふるさと納税"


def furusato_candidates(cfg, fcats, used, descs, day):
    """ふるさと納税のTOP3（2ジャンル）と返礼品紹介（最大4件）."""
    from furusato import item_path
    if not fcats:
        return [], []
    base = cfg["base_url"].rstrip("/") + "/furusato"
    k = dt.date.fromisoformat(day).toordinal() % len(fcats)
    rotated = fcats[k:] + fcats[:k]
    tops, singles = [], []
    for c in rotated:
        if len(tops) >= 2:
            break
        rows = [(it, it["shop"]) for it in c["items"] if it["code"] not in used][:3]
        if len(rows) == 3:
            used.update(it["code"] for it, _ in rows)
            tops.append(("furusato-top", c["title"], rows, f"{base}/{c['slug']}.html"))
    for c in rotated:
        for it in c["items"][:10]:
            if len(singles) >= 4:
                break
            if it["code"] not in used and descs.get(it["code"]):
                used.add(it["code"])
                singles.append(("furusato-single", c["title"], [(it, it["shop"])], f"{base}/{item_path(it)}"))
    return tops, singles


def furusato_tags(items, descs):
    tags = []
    for it in items:
        t = product_tag(it["name"], descs.get(it["code"]))
        if t and t not in tags and t != "ふるさと納税":
            tags.append(t)
    return " ".join(["#" + t for t in tags[:2]] + [FURUSATO_TAGS])


def compose_furusato_top(genre, rows, url, tags, day):
    hook = pick(day + genre, FURUSATO_HOOKS).format(g=genre)
    nums = ["1️⃣", "2️⃣", "3️⃣"]
    limit = 22
    while True:
        lines = [hook] + [f"{nums[i]}{short_name(it['name'], limit)} {yen(it, '寄付')}（{muni}）".replace(" （", "（")
                          for i, (it, muni) in enumerate(rows)]
        text = finish(lines, url, tags)
        if x_len(text) <= 280 or limit <= 8:
            return text
        limit -= 2


def compose_furusato_single(it, desc, url, tags, day):
    hook = pick(day + it["code"], ["ふるさと納税の定番返礼品", f"📍{it['shop']}の人気返礼品",
                                   f"レビュー{it['reviews'] // 100 * 100:,}件超えの返礼品" if it["reviews"] >= 100 else "人気の返礼品"])
    lead = re.split(r"(?<=[。！!])", desc["intro"])[0] if desc else ""
    limit = 40
    while True:
        lines = [hook, "", short_name(it["name"], limit), f"{yen(it, '寄付額') + '｜' if yen(it) else ''}{it['shop']}"]
        if lead:
            lines.append(lead)
        text = finish(lines, url, tags)
        if x_len(text) <= 280:
            return text
        if lead:
            lead = ""
            continue
        if limit <= 10:
            return text
        limit -= 4


# ---------- 画像 ----------

def font(size):
    from PIL import ImageFont
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def fetch_image(url, size=400):
    from PIL import Image
    if not url:
        return None
    url = re.sub(r"_ex=\d+x\d+", f"_ex={size}x{size}", url)
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
        d.text((x + 18, y + 378), yen(it), font=font(44), fill=(191, 0, 0))
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


def find_channel(key, services=("twitter", "x")):
    if services == ("twitter", "x") and os.environ.get("BUFFER_CHANNEL_ID"):
        return os.environ["BUFFER_CHANNEL_ID"]
    for org in gql(key, "query { account { organizations { id name } } }")["account"]["organizations"]:
        q = "query { channels(input: {organizationId: %s}) { id name service } }" % json.dumps(org["id"])
        for c in gql(key, q)["channels"]:
            if c["service"].lower() in services:
                return c["id"]
    raise RuntimeError(f"Buffer に {services[0]} のチャンネルが接続されていません")


CREATE_VIDEO = """mutation { createPost(input: {text: %s, channelId: %s, schedulingType: automatic, mode: customScheduled,
  dueAt: %s, assets: [{video: {url: %s}}]}) {
  ... on PostActionSuccess { post { id dueAt } }
  ... on MutationError { message } } }"""

CREATE_NOIMG = """mutation { createPost(input: {text: %s, channelId: %s, schedulingType: automatic, mode: customScheduled,
  dueAt: %s}) {
  ... on PostActionSuccess { post { id dueAt } }
  ... on MutationError { message } } }"""

CREATE = """mutation { createPost(input: {text: %s, channelId: %s, schedulingType: automatic, mode: customScheduled,
  dueAt: %s, assets: [{image: {url: %s}}]}) {
  ... on PostActionSuccess { post { id dueAt } }
  ... on MutationError { message } } }"""


PLAN = DATA / "social_plan.json"
IMG_DIR = DATA / "social_img"


# ---------- 追加の投稿（セール速報・週1回のまとめ・ショート動画） ----------

ROOM_LINES = [
    ["今日の売れ筋、楽天ROOMにもまとめたよ🛍", "1000円台・送料無料の買い回り候補はこちら"],
    ["収納・日用品の人気どころを楽天ROOMに集めてます📦", "寝る前のお買い物チェックにどうぞ"],
    ["ふるさと納税の人気返礼品も楽天ROOMで一覧にしてるよ🎁", "レビューが多い定番を中心に"],
    ["楽天ROOMを更新したよ✨", "今日ランキングに入っていたものを追加しました"],
]


def room_posts(cfg, day):
    """毎晩、ROOM がよく見られる時間（21時）に ROOM への案内を1件。返り値は [(日時JST, 本文)]."""
    if not cfg.get("room_url"):
        return []
    d = dt.date.fromisoformat(day)
    lines = ROOM_LINES[d.toordinal() % len(ROOM_LINES)]
    return [(dt.datetime(d.year, d.month, d.day, 21, 0, tzinfo=JST),
             finish(lines, cfg["room_url"], "#楽天ROOM #楽天ルーム #買い回り"))]


def sale_alerts(names, d, url):
    """商品名から読み取ったセールの開始・終了時刻にあわせた速報投稿。返り値は [(日時JST, 本文)]."""
    now = dt.datetime.now(JST)
    out = []
    for label, pat, tags in (("お買い物マラソン", r"マラソン", "#お買い物マラソン #買い回り"),
                             ("楽天スーパーSALE", r"スーパーSALE|スーパーセール", "#楽天スーパーSALE #買い回り")):
        hits = [n for n in names if re.search(pat, n)]
        if len(hits) < 5:
            continue
        start, end = sale_period(hits, now)
        day0 = dt.datetime(d.year, d.month, d.day, tzinfo=JST)
        if start and day0 <= start < day0 + dt.timedelta(days=1):
            hh = f"{start.hour}時" + (f"{start.minute}分" if start.minute else "")
            out.append((start - dt.timedelta(hours=3), f"今夜{hh}から{label}スタート！\n1000円台・送料無料の買い回り候補、先にチェックしておこう", tags))
            out.append((start - dt.timedelta(minutes=10), f"まもなく{label}スタート⏰\n{hh}になったらエントリーを忘れずに✍️", tags))
        if end and day0 < end <= day0 + dt.timedelta(hours=30):
            for before, msg in ((5, "残り5時間"), (2, "残り2時間"), (0.5, "ラスト30分")):
                out.append((end - dt.timedelta(hours=before), f"{label}、{msg}！⏰\n買い回りのあと1店舗、まだ間に合う", tags))
    return [(t, finish([txt], url, tg)) for t, txt, tg in out]


def make_top10_image(title, items, day, path, price_prefix=""):
    """10商品を2列×5段に並べた保存版まとめ画像（1200x1500）."""
    from PIL import Image, ImageDraw
    Wd, Hd = 1200, 1500
    img = Image.new("RGB", (Wd, Hd), (246, 244, 240))
    d = ImageDraw.Draw(img)
    for y in range(150):
        k = y / 150
        d.line([(0, y), (Wd, y)], fill=(int(165 + 50 * k), 0, int(47 * k)))
    m, dd = int(day[5:7]), int(day[8:10])
    d.text((40, 40), title, font=font(58), fill=(255, 255, 255))
    d.text((Wd - 40, 110), f"{m}月{dd}日時点 ｜ 保存版", font=font(26), fill=(255, 230, 230), anchor="rs")
    for i, it in enumerate(items[:10]):
        col, row = i % 2, i // 2
        x, y = 30 + col * 590, 175 + row * 262
        d.rounded_rectangle([x, y, x + 560, y + 245], radius=18, fill=(255, 255, 255))
        pic = fetch_image(it.get("image"))
        if pic:
            pic.thumbnail((210, 210))
            img.paste(pic, (x + 15 + (210 - pic.width) // 2, y + 18 + (210 - pic.height) // 2))
        badge = (217, 164, 0) if i == 0 else (154, 165, 177) if i == 1 else (185, 114, 46) if i == 2 else (60, 60, 65)
        d.ellipse([x + 8, y + 8, x + 62, y + 62], fill=badge)
        d.text((x + 35, y + 35), str(i + 1), font=font(30), fill=(255, 255, 255), anchor="mm")
        for j, line in enumerate(wrap(d, short_name(it["name"], 40), font(24), 310, 3)):
            d.text((x + 240, y + 22 + j * 34), line, font=font(24), fill=(29, 29, 31))
        d.text((x + 240, y + 150), yen(it, price_prefix), font=font(44), fill=(191, 0, 0))
        if price_prefix:
            d.text((x + 240, y + 205), f"📍{it.get('shop', '')}"[:16], font=font(22), fill=(6, 92, 56))
    d.text((Wd - 30, Hd - 18), "楽天ランキング速報 ｜ #PR", font=font(22), fill=(110, 110, 115), anchor="rb")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)


def weekly_posts(cfg, budget, fcats, day, out_dir):
    """毎週日曜：保存版TOP10（1000円台・ふるさと納税1万円以下）。返り値は [(日時JST, 本文, 画像URL)]."""
    d = dt.date.fromisoformat(day)
    if d.weekday() != 6:
        return []
    base = cfg["base_url"].rstrip("/")
    out = []
    if budget and len(budget) >= 10:
        name = f"social/{day}-weekly-budget.png"
        make_top10_image("今週の1000円台 売れ筋TOP10", budget[:10], day, IMG_DIR / Path(name).name)
        text = finish(["保存版📌 今週の1000円台・送料無料 売れ筋TOP10", "買い回りの候補に使ってね"],
                      f"{base}/{cfg['budget']['slug']}.html", "#楽天 #楽天市場 #1000円台 #買い回り")
        out.append((dt.datetime(d.year, d.month, d.day, 19, 10, tzinfo=JST), text, f"{base}/{name}"))
    pool = sorted({it["code"]: it for c in fcats or [] for it in c["items"] if it["price"] <= 10000}.values(),
                  key=lambda x: -x["reviews"])
    if len(pool) >= 10:
        name = f"social/{day}-weekly-furusato.png"
        make_top10_image("ふるさと納税 寄付1万円以下 人気TOP10", pool[:10], day, IMG_DIR / Path(name).name, "寄付")
        text = finish(["保存版📌 ふるさと納税 寄付1万円以下の人気返礼品TOP10", "レビューの多い定番から選べるよ"],
                      f"{base}/furusato/price.html", "#ふるさと納税 #楽天ふるさと納税 #返礼品")
        out.append((dt.datetime(d.year, d.month, d.day, 21, 10, tzinfo=JST), text, f"{base}/{name}"))
    for _, _, img in out:
        (out_dir / "social").mkdir(parents=True, exist_ok=True)
        fname = img.rsplit("/", 1)[1]
        shutil.copy(IMG_DIR / fname, out_dir / "social" / fname)
    return out


def video_posts(cfg, videos, day):
    """その日のショート動画を X にも投稿する（昼と夜に1本ずつ）。返り値は [(日時JST, 本文, 動画URL)]."""
    d = dt.date.fromisoformat(day)
    base = cfg["base_url"].rstrip("/")
    out = []
    for (h, m), v in zip(((12, 30), (19, 45)), videos or []):
        title = re.sub(r"\s*#\S+", "", v["title"]).strip()
        green = v.get("theme") == "green"
        url = f"{base}/furusato/" if green else f"{base}/{cfg['budget']['slug']}.html"
        tags = "#ふるさと納税 #楽天ふるさと納税" if green else "#楽天 #楽天市場 #買い回り"
        text = finish([f"🎬{title}", "らんくまが30秒で紹介するよ"], url, tags)
        out.append((dt.datetime(d.year, d.month, d.day, h, m, tzinfo=JST), text, f"{base}/{v['file']}"))
    return out


def plan(cfg, results, budget, descs, day, out_dir, fcats=None, videos=None):
    """投稿の計画（本文・画像・時刻）を作り、画像をサイト内に置く。予約はサイト公開後に run_plan で行う."""
    if PLAN.exists() and json.loads(PLAN.read_text(encoding="utf-8")).get("day") == day:
        return  # 本日の計画は作成済み（予約状況を保持する）
    posted = json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else {}
    cutoff = (dt.date.fromisoformat(day) - dt.timedelta(days=7)).isoformat()
    recent = {k for k, v in posted.items() if not k.startswith("_") and v >= cutoff}
    names = [it["name"] for it in budget or []] + [it["name"] for v in results.values() for it in v]
    sale = sale_tags(names)
    d = dt.date.fromisoformat(day)
    now = dt.datetime.now(JST) + dt.timedelta(minutes=20)  # 公開と予約にかかる時間を見込む
    slots = [(h, m) for h, m in SLOTS if dt.datetime(d.year, d.month, d.day, h, m, tzinfo=JST) > now]
    cands = candidates(cfg, results, budget, recent, descs, day, fcats)
    events = event_posts(day, f"{cfg['base_url'].rstrip('/')}/{cfg['budget']['slug']}.html", sale)
    for n, t in enumerate(events):  # 朝いちばんと夕方にお知らせを入れる
        cands.insert(min(n * 10, len(cands)), ("event", t, [], ""))
    base = cfg["base_url"].rstrip("/")
    items = []
    for n, ((h, m), (kind, title, rows, url)) in enumerate(zip(slots, cands)):
        tags = build_tags([it for it, _ in rows], sale, descs)
        if kind == "event":
            text, image = title, ""
        elif kind == "furusato-single":
            it = rows[0][0]
            tags = furusato_tags([it], descs or {})
            text = compose_furusato_single(it, (descs or {}).get(it["code"]), url, tags, day)
            image = re.sub(r"_ex=\d+x\d+", "_ex=600x600", it.get("image", ""))
        elif kind == "furusato-top":
            img_name = f"social/{day}-{n:02d}-{kind}.png"
            make_image(f"ふるさと納税 {title}の人気TOP3", rows, day, IMG_DIR / Path(img_name).name)
            (out_dir / "social").mkdir(parents=True, exist_ok=True)
            shutil.copy(IMG_DIR / Path(img_name).name, out_dir / img_name)
            tags = furusato_tags([it for it, _ in rows], descs or {})
            text = compose_furusato_top(title, rows, url, tags, day)
            image = f"{base}/{img_name}"
        elif kind == "single":
            it = rows[0][0]
            text = compose_single(it, (descs or {}).get(it["code"]), url, tags, day)
            image = re.sub(r"_ex=\d+x\d+", "_ex=600x600", it.get("image", ""))
        else:
            img_name = f"social/{day}-{n:02d}-{kind}.png"
            # 画像は data/social_img に保存し（コミットされて残る）、サイトを作るたびに public/social へ公開する
            make_image(title, rows, day, IMG_DIR / Path(img_name).name)
            (out_dir / "social").mkdir(parents=True, exist_ok=True)
            shutil.copy(IMG_DIR / Path(img_name).name, out_dir / img_name)
            text = compose_text(title, rows, url, tags, day, kind)
            image = f"{base}/{img_name}"
        while x_len(text) > 280 and tags:  # 長すぎるときは一般的なタグ→長いタグの順に外す（PR表記は先頭に残る）
            tl = tags.split()
            gen = [t for t in ("#買い回り", "#お買い物マラソン", "#楽天ふるさと納税") if t in tl]
            tl.remove(gen[0] if gen else max(tl, key=len))
            old, tags = tags, " ".join(tl)
            text = text.replace("\n" + old, "\n" + tags if tags else "")
        due = dt.datetime(d.year, d.month, d.day, h, m, tzinfo=JST).astimezone(dt.timezone.utc)
        items.append({"kind": kind, "time": f"{h:02d}:{m:02d}", "due": due.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                      "text": text, "image": image, "codes": [it["code"] for it, _ in rows]})
    # 1) TOP3 系の投稿は1つおきにリンクなしにする（X は外部リンク付きの投稿の表示を抑えがちなため）
    alt = 0
    for it_, (kind, _, _, url) in zip(items, cands):
        if kind in ("cheaper", "risers", "budget", "furusato-top") or kind.startswith("genre"):
            alt += 1
            if alt % 2 == 0 and url:
                it_["text"] = it_["text"].replace("👇\n" + url, "📌くわしくはプロフィールのリンクから")
    # 2) セール速報・週1回のまとめ・ショート動画（通常の枠とは別に追加）
    later = now - dt.timedelta(minutes=10)
    extra = [(t, txt, "", "") for t, txt in sale_alerts(names, d, f"{base}/{cfg['budget']['slug']}.html")]
    extra += [(t, txt, img, "") for t, txt, img in weekly_posts(cfg, budget, fcats, day, out_dir)]
    extra += [(t, txt, "", vid) for t, txt, vid in video_posts(cfg, videos, day)]
    extra += [(t, txt, "", "") for t, txt in room_posts(cfg, day)]
    for t, txt, img, vid in extra:
        if t > later:
            due = t.astimezone(dt.timezone.utc)
            items.append({"kind": "video" if vid else ("weekly" if img else "alert"), "time": t.strftime("%m/%d %H:%M"),
                          "due": due.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "text": txt, "image": img, "video": vid,
                          "codes": []})
    items.sort(key=lambda x: x["due"])
    for f in IMG_DIR.glob("*.png"):  # 3日より前の投稿画像は消す（投稿済みのため不要）
        if f.name[:10] < (d - dt.timedelta(days=3)).isoformat():
            f.unlink()
    PLAN.write_text(json.dumps({"day": day, "sale": sale, "posts": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    LOG.write_text(f"{day} 計画 {len(items)}件（セール判定: {sale or 'なし'} / 残り枠 {len(slots)} / 候補 {len(cands)}）\n",
                   encoding="utf-8")


def wait_until_live(url, tries=20):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(15)
    return False


def create(key, post, channel, meta="", notify=False):
    args = (json.dumps(post["text"]), json.dumps(channel), json.dumps(post["due"]))
    if post.get("video"):
        q = CREATE_VIDEO % (*args, json.dumps(post["video"]))
    elif post["image"]:
        q = CREATE % (*args, json.dumps(post["image"]))
    else:
        q = CREATE_NOIMG % args
    if meta:
        q = q.replace(", schedulingType:", f", metadata: {meta}, schedulingType:", 1)
    if notify:  # 個人アカウントの Instagram は自動公開できず、時間になるとスマホに通知が来る方式
        q = q.replace("schedulingType: automatic", "schedulingType: notification", 1)
    return gql(key, q)["createPost"]


# Instagram は投稿の種類（フィード・リール・ストーリー）を指定する
INSTA_META = {"feed": "{instagram: {type: post, shouldShareToFeed: true}}",
              "reel": "{instagram: {type: reel, shouldShareToFeed: true}}",
              "story": "{instagram: {type: story, shouldShareToFeed: false}}"}
SERVICES = {"x": ("twitter", "x"), "threads": ("threads",), "instagram": ("instagram",), "youtube": ("youtube",)}
SNS_PLAN = DATA / "sns_plan.json"
SCHEMA = DATA / "buffer_schema.txt"


def log_schema(key):
    """Buffer の投稿APIの項目を一度だけ記録する（Threads の返信や Instagram の種類指定の調整用）."""
    if SCHEMA.exists() and "v3" in SCHEMA.read_text(encoding="utf-8")[:10]:
        return
    out, seen = ["v3"], set()
    todo = ["YoutubePostMetadataInput", "ThreadsPostMetadataInput", "PostType", "SchedulingType"]
    q = '{ __type(name: "%s") { kind inputFields { name type { name kind ofType { name kind ofType { name kind ofType { name } } } } } enumValues { name } } }'
    while todo and len(seen) < 12:
        name = todo.pop(0)
        if name in seen:
            continue
        seen.add(name)
        try:
            t = gql(key, q % name)["__type"]
        except Exception as ex:  # noqa: BLE001
            out.append(f"{name}: {ex}")
            continue
        out.append(f"{name}: {json.dumps(t, ensure_ascii=False)}")
        for f in (t or {}).get("inputFields") or []:
            ty = f["type"]
            while ty and not ty.get("name"):
                ty = ty.get("ofType")
            if ty and ty.get("name") and ty["name"] not in ("String", "Boolean", "Int", "Float", "ID", "DateTime"):
                todo.append(ty["name"])
    SCHEMA.write_text(chr(10).join(out) + chr(10), encoding="utf-8")


def schedule(key, posts, service, log, posted, day):
    """posts（同じチャンネル向け）のうち未予約のものを、空き枠の範囲で予約する."""
    now = dt.datetime.now(dt.timezone.utc)
    due = lambda post: dt.datetime.strptime(post["due"], "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=dt.timezone.utc)  # noqa: E731
    pending = sum(1 for x in posts if x.get("scheduled") and due(x) > now)
    room = BUFFER_CAP - pending
    todo = sorted((x for x in posts if not x.get("scheduled") and due(x) > now + dt.timedelta(minutes=5)), key=due)
    log.append(f"--- {dt.datetime.now(JST):%H:%M} 予約処理[{service}]: 空き枠 {room} / 未予約 {len(todo)}")
    if not todo or room <= 0:
        return
    try:
        channel = find_channel(key, SERVICES[service])
    except Exception as ex:  # noqa: BLE001
        log.append(f"[{service}] {ex}")
        return
    for post in todo[:room]:
        media = post.get("video") or post["image"]
        if media and not wait_until_live(media):
            log.append(f"{post['time']} {post['kind']}: 失敗 画像が公開されていない")
            continue
        meta = INSTA_META.get(post["kind"], "") if service == "instagram" else ""
        if service == "youtube":  # タイトル必須。カテゴリはハウツー・スタイル、子ども向けではない、公開
            meta = "{youtube: {title: %s, categoryId: \"26\", privacy: public, madeForKids: false, notifySubscribers: true}}" % json.dumps(post.get("title", ""))
        if service == "threads" and post.get("reply"):  # 本文＋自分への返信（リンク）のスレッドにする
            items = ", ".join("{text: %s, assets: []}" % json.dumps(t) for t in (post["text"], post["reply"]))
            meta = "{threads: {type: thread, thread: [%s]}}" % items
        send = post
        try:
            try:
                r = create(key, send, channel, meta)
                err = r.get("message") if service == "threads" and meta else None
                if err:
                    raise RuntimeError(err)
            except RuntimeError as ex:  # 種類の指定が通らなければ、指定なしでもう一度
                if not meta:
                    raise
                if service == "threads":  # スレッドにできなければ、リンクを本文に足して1件で
                    send = {**post, "text": post["text"] + "\n\n" + post["reply"]}
                    meta = ""
                log.append(f"{post['time']} {post['kind']}: 種類指定でエラー（{str(ex)[:120]}）→ 指定なしで再試行")
                r = create(key, send, channel)
            how = ""
            if "notification scheduling" in (r.get("message") or ""):
                r = create(key, send, channel, meta, notify=True)
                how = "（通知で投稿）"
            if r.get("message"):
                log.append(f"{post['time']} {post['kind']}: 失敗 {r['message']}")
                continue
            post["scheduled"] = True
            for c in post["codes"]:
                posted[c] = day
            log.append(f"{post['time']} {post['kind']}: 予約{how}{'（返信つき）' if meta and service == 'threads' else ''} / {x_len(send['text'])}文字")
        except Exception as ex:  # noqa: BLE001
            log.append(f"{post['time']} {post['kind']}: 失敗 {ex}")


def run_plan():
    """計画のうち未予約の投稿を、Buffer の空き枠（チャンネルごとの同時予約の上限 BUFFER_CAP）の範囲で予約する.

    朝のビルド後と、昼（前半の投稿が済んで枠が空いたころ）に実行される。
    """
    key = os.environ.get("BUFFER_API_KEY")
    if not PLAN.exists():
        return
    p = json.loads(PLAN.read_text(encoding="utf-8"))
    day = p["day"]
    if not key:
        LOG.write_text(f"{day} BUFFER_API_KEY がないため投稿の予約をスキップ\n", encoding="utf-8")
        return
    posted = json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else {}
    log = LOG.read_text(encoding="utf-8").rstrip("\n").split("\n") if LOG.exists() else []
    schedule(key, p["posts"], "x", log, posted, day)
    if SNS_PLAN.exists():  # Threads・Instagram
        sp = json.loads(SNS_PLAN.read_text(encoding="utf-8"))
        try:
            log_schema(key)
        except Exception:  # noqa: BLE001
            pass
        for service in ("threads", "instagram", "youtube"):
            schedule(key, [x for x in sp["posts"] if x["service"] == service], service, log, posted, day)
        SNS_PLAN.write_text(json.dumps(sp, ensure_ascii=False, indent=1), encoding="utf-8")
    cutoff = (dt.date.fromisoformat(day) - dt.timedelta(days=7)).isoformat()
    posted = {k: v for k, v in posted.items() if not k.startswith("_") and v >= cutoff}
    POSTED.write_text(json.dumps(posted, ensure_ascii=False, indent=0), encoding="utf-8")
    PLAN.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    LOG.write_text("\n".join(log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run_plan()
