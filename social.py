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

def candidates(cfg, results, budget, recent, descs=None, day="2000-01-01"):
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
        (x for x in allg if x.get("price_diff", 0) < 0), key=lambda x: x["price_diff"])])
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
    return out


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
        lines = [hook] + [f"{nums[i]}{short_name(it['name'], limit)} {it['price']:,}円（{note}）"
                          for i, (it, note) in enumerate(rows)]
        text = finish(lines, url, tags)
        if x_len(text) <= 280 or limit <= 8:
            return text
        limit -= 2


def single_hook(it, day):
    if it.get("price_diff", 0) < 0:
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
        lines = [single_hook(it, day), "", short_name(it["name"], limit), f"{it['price']:,}円、送料無料！{stars}"]
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


def plan(cfg, results, budget, descs, day, out_dir):
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
    cands = candidates(cfg, results, budget, recent, descs, day)
    events = event_posts(day, f"{cfg['base_url'].rstrip('/')}/{cfg['budget']['slug']}.html", sale)
    for n, t in enumerate(events):  # 朝いちばんと夕方にお知らせを入れる
        cands.insert(min(n * 10, len(cands)), ("event", t, [], ""))
    base = cfg["base_url"].rstrip("/")
    items = []
    for n, ((h, m), (kind, title, rows, url)) in enumerate(zip(slots, cands)):
        tags = build_tags([it for it, _ in rows], sale, descs)
        if kind == "event":
            text, image = title, ""
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
            gen = [t for t in ("#買い回り", "#お買い物マラソン") if t in tl]
            tl.remove(gen[0] if gen else max(tl, key=len))
            old, tags = tags, " ".join(tl)
            text = text.replace("\n" + old, "\n" + tags if tags else "")
        due = dt.datetime(d.year, d.month, d.day, h, m, tzinfo=JST).astimezone(dt.timezone.utc)
        items.append({"kind": kind, "time": f"{h:02d}:{m:02d}", "due": due.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                      "text": text, "image": image, "codes": [it["code"] for it, _ in rows]})
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


def run_plan():
    """計画のうち未予約の投稿を、Buffer の空き枠（同時予約の上限 BUFFER_CAP）の範囲で予約する.

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
    now = dt.datetime.now(dt.timezone.utc)
    due = lambda post: dt.datetime.strptime(post["due"], "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=dt.timezone.utc)  # noqa: E731
    pending = sum(1 for x in p["posts"] if x.get("scheduled") and due(x) > now)
    room = BUFFER_CAP - pending
    todo = [x for x in p["posts"] if not x.get("scheduled") and due(x) > now + dt.timedelta(minutes=5)]
    posted = json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else {}
    log = LOG.read_text(encoding="utf-8").rstrip("\n").split("\n") if LOG.exists() else []
    log.append(f"--- {dt.datetime.now(JST):%H:%M} 予約処理: 空き枠 {room} / 未予約 {len(todo)}")
    if todo and room > 0:
        channel = find_channel(key)
        for post in todo[:room]:
            if post["image"] and not wait_until_live(post["image"]):
                log.append(f"{post['time']} {post['kind']}: 失敗 画像が公開されていない")
                continue
            args = (json.dumps(post["text"]), json.dumps(channel), json.dumps(post["due"]))
            q = CREATE % (*args, json.dumps(post["image"])) if post["image"] else CREATE_NOIMG % args
            try:
                r = gql(key, q)["createPost"]
                if r.get("message"):
                    log.append(f"{post['time']} {post['kind']}: 失敗 {r['message']}")
                    continue
                post["scheduled"] = True
                for c in post["codes"]:
                    posted[c] = day
                log.append(f"{post['time']} {post['kind']}: 予約 / {x_len(post['text'])}文字")
            except Exception as ex:  # noqa: BLE001
                log.append(f"{post['time']} {post['kind']}: 失敗 {ex}")
    cutoff = (dt.date.fromisoformat(day) - dt.timedelta(days=7)).isoformat()
    posted = {k: v for k, v in posted.items() if not k.startswith("_") and v >= cutoff}
    POSTED.write_text(json.dumps(posted, ensure_ascii=False, indent=0), encoding="utf-8")
    PLAN.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    LOG.write_text("\n".join(log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run_plan()
