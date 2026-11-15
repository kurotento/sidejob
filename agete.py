"""「神商品あげてけ」型のショート（2026-11-16〜）.

伸びている商品紹介ショートの型：暗い背景（商品写真をぼかしたもの）に大きな「第N位」、商品写真、
掲示板の書き込み風の吹き出しを2〜3個。6位から1位まで数えていく。

前の日に商品を決めて（prepare）、副業 Muse に★5のレビューを読んで言い換えた良い点を書いてもらい
（tools/agete_muse.py がこのPCで依頼と取り込みをする）、次の日の朝の更新で動画にする（topic）。
レビューが届いていない商品は、レビューの点数・件数・値段だけの吹き出しにする。
吹き出しの言葉は、実際のレビューの意味を変えずに言い換えたもの（作り話は入れない）。
"""
import datetime as dt
import json
import random
from pathlib import Path

DIR = Path(__file__).resolve().parent / "data" / "agete"
N = 6  # 第6位から第1位まで
BUBBLE_COLORS = [(230, 40, 60), (40, 170, 70), (40, 90, 220)]


def item_page(it):
    """アフィリエイトでない商品ページ（Muse がレビューを読みに行く入口）."""
    shop, _, iid = it["code"].partition(":")
    return f"https://item.rakuten.co.jp/{shop}/{iid}/"


def prepare(results, day, base_url):
    """day（明日）の「あげてけ」の商品を、今日のランキングから選んで data/agete/<day>.json に置く."""
    from itemfilter import excluded, similar
    DIR.mkdir(parents=True, exist_ok=True)
    path = DIR / f"{day}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    used = set()
    for p in sorted(DIR.glob("20*.json"))[-14:]:  # 2週間は同じ商品を出さない
        if not p.stem.endswith("reviews"):
            used |= {x["code"] for x in json.loads(p.read_text(encoding="utf-8")).get("items", [])}
    pool = [it for items in (results or {}).values() for it in items
            if it.get("reviews", 0) >= 100 and (it.get("rating") or 0) >= 4.3 and 800 <= it.get("price", 0) <= 8000
            and it.get("image") and not excluded(it) and it["code"] not in used]
    pool.sort(key=lambda x: (-x["reviews"]))
    picks = []
    for it in pool:
        if any(similar(it, o) for o in picks):
            continue
        picks.append(it)
        if len(picks) == N:
            break
    if len(picks) < N:
        return None
    data = {"day": day, "items": [{**it, "page": item_page(it)} for it in picks]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    return data


def topic(cfg, day):
    """今日の「あげてけ」の回（前の日に準備した商品で）。作れないときは None."""
    from shorts import latest, short_name
    path = DIR / f"{day}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    rv_path = DIR / f"{day}_reviews.json"
    reviews = json.loads(rv_path.read_text(encoding="utf-8")) if rv_path.exists() else {}
    items = []
    for it in data["items"]:
        f = latest(it, cfg["base_url"])  # 売り切れは外し、値段は最新に
        if f:
            items.append(f)
    if len(items) < 5:
        return None
    items = list(reversed(items[:N]))  # 6位（レビューの少ないほう）から1位の順に並べる
    bubbles = {}
    for it in items:
        got = [s.strip() for s in reviews.get(it["code"], []) if 4 <= len(s.strip()) <= 34][:3]
        rate = f"★{it['rating']:.1f}" if it.get("rating") else ""
        fact = [f"レビュー{it['reviews']:,}件で{rate}", f"{it['price']:,}円{'〜' if it.get('from') else ''}で買える"]
        bubbles[it["code"]] = (got + fact)[:3] if got else fact
    return dict(key="agete", kind="agete", theme="red", title="楽天で買ってよかった\n神商品あげてけ", tag="楽天購入品", label="楽天の価格",
                items=[(it, f"第{len(items) - i}位") for i, it in enumerate(items)],
                labels={i + 1: f"第{len(items) - i}位" for i in range(len(items))},
                bubbles=bubbles, has_reviews=bool(reviews),
                what="楽天で買ってよかった神商品", order="countdown",
                fact=lambda it: f"{it['price']:,}円",
                lead="楽天で買ってよかった神商品｜レビューの多い人気どころ",
                tags="#楽天購入品 #買ってよかった #楽天市場 #神商品 #PR",
                short=lambda it: short_name(it["name"], 22))


# ---------- 描画 ----------

def _bg(pic, W, H):
    """商品写真を画面いっぱいに広げてぼかし、暗くした背景."""
    from PIL import Image, ImageEnhance, ImageFilter
    if pic is None:
        return Image.new("RGB", (W, H), (18, 18, 28))
    s = max(W / pic.width, H / pic.height)
    big = pic.convert("RGB").resize((int(pic.width * s) + 2, int(pic.height * s) + 2))
    big = big.crop(((big.width - W) // 2, (big.height - H) // 2, (big.width - W) // 2 + W, (big.height - H) // 2 + H))
    big = big.filter(ImageFilter.GaussianBlur(28))
    return ImageEnhance.Brightness(big).enhance(0.38)


def _bubble(d, font, text, x, y, w, color):
    from shorts import wrap
    lines = wrap(d, text, font(50), w - 60, 2)
    h = 40 + 64 * len(lines)
    d.rectangle([x, y, x + w, y + h], fill=(255, 255, 255), outline=color, width=8)
    for i, ln in enumerate(lines):
        d.text((x + 30, y + 22 + i * 64), ln, font=font(50), fill=(20, 20, 20))
    return h


def item_frames(it, rank, bubbles, dur, out, seed=0):
    from PIL import ImageDraw
    from shorts import FPS, H, W, fetch_image, font, pr_badge, short_name
    pic = fetch_image(it.get("image"))
    bg = _bg(pic, W, H)
    rnd = random.Random(seed)
    cols = BUBBLE_COLORS[:]
    rnd.shuffle(cols)
    out.mkdir(parents=True, exist_ok=True)
    appear = [0.5 + i * (max(dur - 1.2, 1.0) / max(len(bubbles), 1)) for i in range(len(bubbles))]
    for f in range(int(dur * FPS)):
        t = f / FPS
        img = bg.copy()
        d = ImageDraw.Draw(img)
        s = 1.0 + 0.25 * max(0.0, 1 - t / 0.18)  # 「第N位」が少し大きく出てから落ち着く
        d.text((W // 2, 230), f"第{rank}位", font=font(int(190 * s)), fill=(255, 255, 255), anchor="mm",
               stroke_width=12, stroke_fill=(0, 0, 0))
        if pic:
            box = 620
            sc = box / max(pic.width, pic.height)
            p2 = pic.convert("RGB").resize((int(pic.width * sc), int(pic.height * sc)))
            img.paste(p2, ((W - p2.width) // 2, 420 + (box - p2.height) // 2))
            d = ImageDraw.Draw(img)
        name = short_name(it["name"], 24)
        d.text((W // 2, 1100), name, font=font(54), fill=(255, 255, 255), anchor="mm", stroke_width=6, stroke_fill=(0, 0, 0))
        y = 1170
        for i, (txt, at) in enumerate(zip(bubbles, appear)):
            if t >= at:
                y += _bubble(d, font, txt, 80, y, W - 220, cols[i % 3]) + 22
        pr_badge(d)
        img.save(out / f"f{f:04d}.jpg", quality=88)
    return [("pop", at) for at in appear] + [("whoosh", 0.0)]


def title_frames(t, dur, out):
    """最初の画面：6つの商品写真を敷き詰めて暗くし、大きな見出し."""
    from PIL import Image, ImageDraw, ImageEnhance
    from shorts import FPS, H, W, fetch_image, font, pr_badge
    canvas = Image.new("RGB", (W, H), (15, 15, 25))
    pics = [fetch_image(it.get("image")) for it, _ in t["items"]]
    cw, ch = W // 2, H // 3
    for i, p in enumerate(pics[:6]):
        if p:
            s = max(cw / p.width, ch / p.height)
            q = p.convert("RGB").resize((int(p.width * s) + 1, int(p.height * s) + 1)).crop((0, 0, cw, ch))
            canvas.paste(q, ((i % 2) * cw, (i // 2) * ch))
    canvas = ImageEnhance.Brightness(canvas).enhance(0.35)
    out.mkdir(parents=True, exist_ok=True)
    for f in range(int(dur * FPS)):
        tt = f / FPS
        img = canvas.copy()
        d = ImageDraw.Draw(img)
        s = 1.0 + 0.3 * max(0.0, 1 - tt / 0.2)
        d.text((W // 2, 760), "楽天で買ってよかった", font=font(int(88 * s)), fill=(255, 255, 255), anchor="mm",
               stroke_width=9, stroke_fill=(0, 0, 0))
        d.text((W // 2, 920), "神商品あげてけ", font=font(int(130 * s)), fill=(255, 225, 60), anchor="mm",
               stroke_width=12, stroke_fill=(0, 0, 0))
        d.text((W // 2, 1080), "第6位から発表", font=font(64), fill=(255, 255, 255), anchor="mm", stroke_width=6, stroke_fill=(0, 0, 0))
        pr_badge(d)
        img.save(out / f"f{f:04d}.jpg", quality=88)
    return [("whoosh", 0.0)]


def end_frames(dur, out):
    from PIL import Image, ImageDraw
    from shorts import FPS, H, W, font, pr_badge
    out.mkdir(parents=True, exist_ok=True)
    for f in range(int(dur * FPS)):
        img = Image.new("RGB", (W, H), (15, 15, 25))
        d = ImageDraw.Draw(img)
        for y, (txt, sz, col) in zip((700, 860, 1000, 1200), (("ほかにもあったら", 80, (255, 255, 255)), ("コメントで教えて", 96, (255, 225, 60)),
                                                               ("", 10, (0, 0, 0)), ("楽天ROOMで「らんくま」と検索", 58, (255, 255, 255)))):
            if txt:
                d.text((W // 2, y), txt, font=font(sz), fill=col, anchor="mm", stroke_width=7, stroke_fill=(0, 0, 0))
        pr_badge(d)
        img.save(out / f"f{f:04d}.jpg", quality=88)
    return [("pop", 0.1)]


def slides(t, spk, work, reading):
    """make_video_anim に渡す [(フレーム, 声, 秒, 効果音)]."""
    from shorts import spoken_name, synth
    out = []
    a = work / "a0.wav"
    sec = synth("楽天で買ってよかった、神商品あげてけ。第6位から発表します。", spk, a) + 0.3
    out.append((work / "a0", a, sec, title_frames(t, sec, work / "a0")))
    for i, (it, label) in enumerate(t["items"]):
        rank = len(t["items"]) - i
        a = work / f"a{rank}.wav"
        sec = max(synth(f"第{rank}位、{spoken_name(it, reading)}。", spk, a) + 0.4, 1.0 + 0.9 * len(t["bubbles"][it["code"]]))
        out.append((work / f"a{rank}", a, sec, item_frames(it, rank, t["bubbles"][it["code"]], sec, work / f"a{rank}", seed=rank)))
    a = work / "a9.wav"
    sec = synth("ほかにもあったら、コメントで教えてね。紹介した商品は、楽天ルームで、らんくま、と検索してください。", spk, a) + 0.4
    out.append((work / "a9", a, sec, end_frames(sec, work / "a9")))
    return out


def is_day(day):
    """あげてけを出す日（曜日のテーマの枠と1日おきに交代）."""
    return dt.date.fromisoformat(day).toordinal() % 2 == 0


def tomorrow(day):
    return (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
