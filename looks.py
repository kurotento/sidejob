"""静止画（X の TOP3・TOP10、Pinterest のピン）の、pop 以外の作り.

型ごとにレイアウト・書体・飾りをまったく変えて、別の人の投稿に見えるようにする。
- magazine: 生成りの紙に明朝体。大きな写真と No.01 の番号、細い罫線だけ
- notebook: 方眼ノートにチェキを貼ったメモ。手書き風の文字・マスキングテープ・マーカー・赤ペンの丸
- news    : 紺の画面に速報テロップ。順位の黄色い箱と数字のグラフ
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter

import design
from articles import short_name
from social import fetch_image, yen

F = design.font


# ---------- 共通 ----------

def fit(pic, w, h, bg=(255, 255, 255)):
    """商品画像を w x h の白い枠に収める（拡大もする）."""
    box = Image.new("RGB", (w, h), bg)
    if pic:
        r = min(w / pic.width, h / pic.height)
        p = pic.resize((max(1, int(pic.width * r)), max(1, int(pic.height * r))), Image.LANCZOS)
        box.paste(p, ((w - p.width) // 2, (h - p.height) // 2))
    return box


def photo(it, w, h, size=600):
    return fit(fetch_image(it.get("image"), size), w, h)


def wrap(d, text, f, width, lines):
    out, cur = [], ""
    for ch in text:
        if d.textlength(cur + ch, font=f) > width:
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


def text_lines(d, xy, text, f, width, lines, fill, gap=1.35):
    x, y = xy
    for ln in wrap(d, text, f, width, lines):
        d.text((x, y), ln, font=f, fill=fill)
        y += int(f.size * gap)
    return y


def price_of(it, prefix=""):
    return yen(it, prefix)


def mmdd(day):
    return int(day[5:7]), int(day[8:10])


def shadow(img, box, radius=18, offset=(0, 10), alpha=70):
    """box の下に、ぼかした影を落とす."""
    x0, y0, x1, y1 = box
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle([x0 + offset[0], y0 + offset[1], x1 + offset[0], y1 + offset[1]], fill=(0, 0, 0, alpha))
    sh = sh.filter(ImageFilter.GaussianBlur(radius))
    img.paste(sh, (0, 0), sh)


# ---------- magazine ----------

MAG_BG, MAG_INK, MAG_SUB = (244, 239, 230), (34, 30, 26), (120, 110, 98)
MAG_ACC = {"red": (150, 52, 40), "green": (64, 96, 52)}


def mag_kicker(d, xy, text, size=22, fill=MAG_SUB):
    """字間を空けた小見出し（RAKUTEN PICKS など）."""
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=F("serif_light", size), fill=fill)
        x += d.textlength(ch, font=F("serif_light", size)) + size * 0.35
    return x


def magazine_top3(title, rows, day, path, theme):
    W, H = 1200, 675
    img = Image.new("RGB", (W, H), MAG_BG)
    d = ImageDraw.Draw(img)
    acc = MAG_ACC[theme]
    m, dd = mmdd(day)
    mag_kicker(d, (48, 52), "RAKUTEN PICKS")
    d.line([(48, 92), (390, 92)], fill=MAG_INK, width=1)
    t = title.replace("TOP3", "").strip()
    y = text_lines(d, (48, 120), t, F("serif", 44), 350, 4, MAG_INK, 1.4)
    d.text((48, y + 20), "BEST 3", font=F("serif", 30), fill=acc)
    d.text((48, H - 92), f"{m:02d}.{dd:02d}", font=F("serif_light", 40), fill=MAG_INK)
    d.text((48, H - 40), "#PR ・ 楽天アフィリエイト", font=F("serif_light", 18), fill=MAG_SUB)
    # 1位は大きく
    it, note = rows[0]
    shadow(img, (440, 48, 800, 408), 14, (0, 8), 50)
    img.paste(photo(it, 360, 360), (440, 48))
    d.text((440, 428), "No.01", font=F("serif", 26), fill=acc)
    y = text_lines(d, (440, 466), short_name(it["name"], 50), F("serif", 24), 360, 2, MAG_INK)
    d.text((440, y + 8), price_of(it), font=F("serif", 34), fill=MAG_INK)
    d.text((440, y + 56), note, font=F("serif_light", 20), fill=MAG_SUB)
    for k, (it, note) in enumerate(rows[1:3]):
        x, y0 = 850, 48 + k * 310
        img.paste(photo(it, 150, 150, 400), (x, y0))
        d.text((x + 168, y0 + 4), f"No.0{k + 2}", font=F("serif", 22), fill=acc)
        text_lines(d, (x + 168, y0 + 40), short_name(it["name"], 40), F("serif", 19), 150, 4, MAG_INK)
        d.text((x, y0 + 166), price_of(it), font=F("serif", 28), fill=MAG_INK)
        d.text((x, y0 + 206), note, font=F("serif_light", 18), fill=MAG_SUB)
        if k == 0:
            d.line([(x, y0 + 268), (W - 40, y0 + 268)], fill=(200, 192, 180), width=1)
    img.save(path, optimize=True)


def magazine_top10(title, items, day, path, prefix):
    W, H = 1200, 1500
    theme = "green" if prefix else "red"
    img = Image.new("RGB", (W, H), MAG_BG)
    d = ImageDraw.Draw(img)
    acc = MAG_ACC[theme]
    m, dd = mmdd(day)
    mag_kicker(d, (60, 50), f"RAKUTEN PICKS  ─  {m:02d}.{dd:02d}")
    d.text((60, 92), title, font=F("serif", 54), fill=MAG_INK)
    d.line([(60, 190), (W - 60, 190)], fill=MAG_INK, width=2)
    for i, it in enumerate(items[:10]):
        y = 212 + i * 124
        d.text((60, y + 20), f"{i + 1:02d}", font=F("serif", 54), fill=acc if i < 3 else MAG_SUB)
        img.paste(photo(it, 100, 100, 300), (170, y + 6))
        text_lines(d, (300, y + 12), short_name(it["name"], 60), F("serif", 26), 600, 2, MAG_INK)
        if prefix:
            d.text((300, y + 84), it.get("shop", "")[:20], font=F("serif_light", 20), fill=MAG_SUB)
        d.text((W - 60, y + 40), price_of(it, prefix), font=F("serif", 34), fill=MAG_INK, anchor="ra")
        d.line([(60, y + 118), (W - 60, y + 118)], fill=(205, 197, 186), width=1)
    d.text((W - 60, H - 40), "#PR ・ 楽天アフィリエイト", font=F("serif_light", 20), fill=MAG_SUB, anchor="ra")
    img.save(path, optimize=True)


def magazine_pin(it, kind, label, path):
    W, H = 1000, 1500
    theme = "green" if kind == "furusato" else "red"
    img = Image.new("RGB", (W, H), MAG_BG)
    d = ImageDraw.Draw(img)
    x = mag_kicker(d, (60, 56), "RAKUTEN PICKS")
    d.line([(x + 10, 72), (x + 70, 72)], fill=MAG_SUB, width=1)
    d.text((x + 84, 54), label, font=F("serif", 28), fill=MAG_ACC[theme])
    img.paste(photo(it, W, 900, 800), (0, 120))
    y = text_lines(d, (60, 1060), short_name(it["name"], 60), F("serif", 46), W - 120, 3, MAG_INK, 1.45)
    info = f"★{it['rating']:.1f}　レビュー {it['reviews']:,}件" if it.get("reviews", 0) >= 10 else ""
    if kind == "furusato":
        info = f"{it['shop']}　" + info
    d.text((60, y + 24), info, font=F("serif_light", 32), fill=MAG_SUB)
    d.line([(60, H - 90), (W - 60, H - 90)], fill=MAG_INK, width=1)
    d.text((60, H - 70), "楽天のランキングから", font=F("serif_light", 26), fill=MAG_SUB)
    d.text((W - 60, H - 70), "#PR", font=F("serif_light", 26), fill=MAG_SUB, anchor="ra")
    img.save(path, quality=85)


# ---------- notebook ----------

NOTE_BG, NOTE_LINE, NOTE_INK = (252, 250, 243), (214, 226, 238), (52, 56, 70)
PEN = {"red": (214, 48, 49), "green": (34, 139, 84)}
TAPES = [(246, 190, 196, 190), (180, 220, 236, 190), (250, 226, 150, 190), (196, 230, 196, 190)]


def grid_paper(W, H, step=36):
    img = Image.new("RGB", (W, H), NOTE_BG)
    d = ImageDraw.Draw(img)
    for x in range(step // 2, W, step):
        d.line([(x, 0), (x, H)], fill=NOTE_LINE, width=1)
    for y in range(step // 2, H, step):
        d.line([(0, y), (W, y)], fill=NOTE_LINE, width=1)
    return img


def marker(img, box, color=(255, 232, 92, 150)):
    """蛍光マーカーを引いたような帯."""
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    x0, y0, x1, y1 = box
    ImageDraw.Draw(lay).polygon([(x0, y0 + 4), (x1, y0), (x1 - 4, y1), (x0 + 3, y1 - 2)], fill=color)
    img.paste(lay, (0, 0), lay)


def pen_circle(d, box, color, seed=0):
    """赤ペンでぐるっと囲んだような、少しゆがんだ丸."""
    rnd = random.Random(seed)
    x0, y0, x1, y1 = box
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    pts = []
    for k in range(0, 400):
        a = k / 360 * 2 * math.pi - 0.4
        wob = 1 + 0.04 * math.sin(a * 3 + rnd.random())
        pts.append((cx + rx * wob * math.cos(a), cy + ry * wob * math.sin(a)))
    d.line(pts, fill=color, width=4, joint="curve")


def polaroid(pic_box, caption="", angle=0.0, tape=None, cap_font=None):
    """チェキ風の写真（白いふち＋下に手書きの一言）。RGBA で返す."""
    w, h = pic_box.size
    pad, bottom = int(w * 0.06), int(w * 0.2)
    card = Image.new("RGBA", (w + pad * 2, h + pad + bottom), (255, 255, 255, 255))
    card.paste(pic_box, (pad, pad))
    if caption:
        cd = ImageDraw.Draw(card)
        f = cap_font or F("hand", max(18, int(w * 0.075)))
        cd.text((card.width // 2, h + pad + bottom // 2), caption, font=f, fill=NOTE_INK, anchor="mm")
    if tape:
        td = ImageDraw.Draw(card)
        tw = int(card.width * 0.38)
        td.rectangle([card.width // 2 - tw // 2, 0, card.width // 2 + tw // 2, int(pad * 0.9)], fill=tape)
    # 影を付けてから回す
    out = Image.new("RGBA", (card.width + 40, card.height + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle([24, 28, 24 + card.width, 28 + card.height], fill=(0, 0, 0, 60))
    out = Image.alpha_composite(out, sh.filter(ImageFilter.GaussianBlur(8)))
    out.paste(card, (20, 20), card)
    return out.rotate(angle, resample=Image.BICUBIC, expand=True)


def tape_strip(img, cx, cy, w=130, h=34, angle=-8, color=None):
    color = color or TAPES[0]
    t = Image.new("RGBA", (w, h), color)
    t = t.rotate(angle, resample=Image.BICUBIC, expand=True)
    img.paste(t, (int(cx - t.width / 2), int(cy - t.height / 2)), t)


def notebook_top3(title, rows, day, path, theme):
    W, H = 1200, 675
    img = grid_paper(W, H)
    d = ImageDraw.Draw(img)
    m, dd = mmdd(day)
    pen = PEN[theme]
    tf = F("hand", 46)
    tw = d.textlength(title, font=tf)
    marker(img, (40, 50, 60 + tw, 92))
    d.text((50, 30), title, font=tf, fill=NOTE_INK)
    d.text((W - 50, 40), f"{m}/{dd} のメモ", font=F("hand", 30), fill=NOTE_INK, anchor="ra")
    angles = [-4, 3, -2]
    for k, (it, note) in enumerate(rows[:3]):
        x0 = 50 + k * 380
        p = polaroid(photo(it, 250, 250, 400), f"{k + 1}. {note}"[:14], angles[k], TAPES[k])
        img.paste(p, (x0 + 10, 112), p)
        y = text_lines(d, (x0 + 20, 470), short_name(it["name"], 40), F("hand", 26), 320, 2, NOTE_INK, 1.3)
        pr = price_of(it)
        if pr:
            pf = F("hand", 40)
            d.text((x0 + 30, y + 14), pr, font=pf, fill=pen)
            pen_circle(d, (x0 + 10, y + 4, x0 + 50 + d.textlength(pr, font=pf), y + 72), pen, k)
    d.text((W - 40, H - 22), "#PR", font=F("hand", 22), fill=NOTE_INK, anchor="rb")
    img.save(path, optimize=True)


def notebook_top10(title, items, day, path, prefix):
    W, H = 1200, 1500
    theme = "green" if prefix else "red"
    img = grid_paper(W, H)
    d = ImageDraw.Draw(img)
    m, dd = mmdd(day)
    tf = F("hand", 56)
    marker(img, (50, 70, 70 + d.textlength(title, font=tf), 122))
    d.text((60, 46), title, font=tf, fill=NOTE_INK)
    d.text((W - 60, 150), f"{m}/{dd} 保存用メモ", font=F("hand", 30), fill=NOTE_INK, anchor="ra")
    for i, it in enumerate(items[:10]):
        y = 210 + i * 126
        d.rectangle([60, y + 38, 96, y + 74], outline=NOTE_INK, width=3)
        d.line([(66, y + 54), (78, y + 68), (104, y + 30)], fill=PEN[theme], width=5)
        th = polaroid(photo(it, 84, 84, 200), "", (-3, 2, -1, 3)[i % 4])
        img.paste(th, (120, y - 4), th)
        text_lines(d, (260, y + 16), f"{i + 1}. " + short_name(it["name"], 50), F("hand", 30), 640, 2, NOTE_INK, 1.25)
        d.text((W - 60, y + 40), price_of(it, prefix), font=F("hand", 40), fill=PEN[theme], anchor="ra")
    d.text((W - 60, H - 30), "#PR", font=F("hand", 26), fill=NOTE_INK, anchor="rb")
    img.save(path, optimize=True)


def notebook_pin(it, kind, label, path):
    W, H = 1000, 1500
    theme = "green" if kind == "furusato" else "red"
    img = grid_paper(W, H, 40)
    d = ImageDraw.Draw(img)
    lf = F("hand", 58)
    marker(img, (60, 92, 80 + d.textlength(label, font=lf), 146))
    d.text((70, 66), label, font=lf, fill=NOTE_INK)
    d.text((W - 60, 84), "メモ", font=F("hand", 40), fill=PEN[theme], anchor="ra")
    p = polaroid(photo(it, 720, 720, 800), "楽天で人気", 2.5, None, F("hand", 52))
    img.paste(p, ((W - p.width) // 2, 190), p)
    tape_strip(img, W // 2 - 220, 230, 170, 44, -14, TAPES[1])
    tape_strip(img, W // 2 + 230, 240, 170, 44, 12, TAPES[2])
    y = text_lines(d, (70, 1150), short_name(it["name"], 60), F("hand", 44), W - 140, 3, NOTE_INK, 1.3)
    if it.get("reviews", 0) >= 10:
        info = f"★{it['rating']:.1f}  レビュー{it['reviews']:,}件"
        d.text((70, y + 18), info, font=F("hand", 38), fill=PEN[theme])
        tw = d.textlength(info, font=F("hand", 38))
        d.line([(70 + i * 12, y + 72 + (4 if i % 2 else 0)) for i in range(int(tw / 12) + 1)], fill=PEN[theme], width=3)
    d.text((W - 50, H - 40), "#PR", font=F("hand", 30), fill=NOTE_INK, anchor="rb")
    img.save(path, quality=85)


# ---------- news ----------

NAVY, NAVY2, YEL, WHITE = (10, 22, 46), (22, 40, 78), (255, 210, 0), (255, 255, 255)
TAG = {"red": ((214, 0, 30), "速報"), "green": ((20, 140, 80), "ふるさと納税")}


def news_bg(W, H):
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    for y in range(H):  # 下に行くほど少し明るく
        k = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(NAVY[i] + (NAVY2[i] - NAVY[i]) * k) for i in range(3)))
    for x in range(-H, W, 48):
        d.line([(x, H), (x + H, 0)], fill=(30, 48, 86), width=1)
    return img


def news_head(img, d, title, right, W, theme, h=96, size=40):
    col, tag = TAG[theme]
    tf = F("impact", 34)
    tw = d.textlength(tag, font=tf) + 44
    d.rectangle([0, 28, tw, 28 + h - 28], fill=col)
    d.text((tw / 2, 28 + (h - 28) / 2), tag, font=tf, fill=WHITE, anchor="mm")
    d.rectangle([tw, 28, W, 28 + h - 28], fill=WHITE)
    d.text((tw + 24, 28 + (h - 28) / 2), title, font=F("sans", size), fill=NAVY, anchor="lm")
    d.text((W - 24, 28 + (h - 28) / 2), right, font=F("sans", 24), fill=(90, 100, 120), anchor="rm")
    return 28 + h


def news_ticker(d, W, H, text, h=46):
    d.rectangle([0, H - h, W, H], fill=(214, 0, 30))
    d.text((24, H - h / 2), text, font=F("sans", 22), fill=WHITE, anchor="lm")


def rank_box(d, x, y, s, n):
    d.rectangle([x, y, x + s, y + s], fill=YEL)
    d.text((x + s / 2, y + s / 2 - 2), str(n), font=F("impact", int(s * 0.62)), fill=NAVY, anchor="mm")


def news_top3(title, rows, day, path, theme):
    W, H = 1200, 675
    img = news_bg(W, H)
    d = ImageDraw.Draw(img)
    m, dd = mmdd(day)
    news_head(img, d, title, f"{m}月{dd}日時点", W, theme)
    for k, (it, note) in enumerate(rows[:3]):
        y = 150 + k * 150
        rank_box(d, 40, y + 20, 92, k + 1)
        img.paste(photo(it, 130, 130, 300), (150, y + 1))
        text_lines(d, (305, y + 14), short_name(it["name"], 50), F("sans", 28), 520, 2, WHITE, 1.3)
        d.rectangle([305, y + 96, 305 + d.textlength(note, font=F("sans", 22)) + 24, y + 128], fill=TAG[theme][0])
        d.text((317, y + 112), note, font=F("sans", 22), fill=WHITE, anchor="lm")
        d.text((W - 40, y + 66), price_of(it), font=F("impact", 50), fill=YEL, anchor="rm")
        if k < 2:
            d.line([(40, y + 146), (W - 40, y + 146)], fill=(60, 80, 120), width=1)
    news_ticker(d, W, H, "楽天ランキング速報 ｜ #PR 楽天アフィリエイトを利用しています")
    img.save(path, optimize=True)


def news_top10(title, items, day, path, prefix):
    W, H = 1200, 1500
    theme = "green" if prefix else "red"
    img = news_bg(W, H)
    d = ImageDraw.Draw(img)
    m, dd = mmdd(day)
    news_head(img, d, title, f"{m}月{dd}日時点", W, theme, 120, 44)
    for i, it in enumerate(items[:10]):
        y = 180 + i * 124
        rank_box(d, 40, y + 14, 80, i + 1)
        img.paste(photo(it, 104, 104, 200), (140, y + 2))
        text_lines(d, (270, y + 12), short_name(it["name"], 50), F("sans", 27), 560, 2, WHITE, 1.3)
        if prefix:
            d.text((270, y + 84), it.get("shop", "")[:20], font=F("sans", 20), fill=(170, 185, 210))
        d.text((W - 40, y + 56), price_of(it, prefix), font=F("impact", 44), fill=YEL, anchor="rm")
        d.line([(40, y + 120), (W - 40, y + 120)], fill=(50, 70, 110), width=1)
    news_ticker(d, W, H, "楽天ランキング速報 ｜ #PR 楽天アフィリエイトを利用しています", 54)
    img.save(path, optimize=True)


def bar(d, x, y, w, h, ratio, label, value, col):
    d.text((x, y - 4), label, font=F("sans", 30), fill=(190, 200, 220))
    bx = x + 170
    d.rectangle([bx, y, bx + w, y + h], fill=(40, 60, 100))
    d.rectangle([bx, y, bx + int(w * max(0.04, min(1, ratio))), y + h], fill=col)
    d.text((bx + w + 20, y + h / 2), value, font=F("impact", 34), fill=WHITE, anchor="lm")


def news_pin(it, kind, label, path):
    W, H = 1000, 1500
    theme = "green" if kind == "furusato" else "red"
    img = news_bg(W, H)
    d = ImageDraw.Draw(img)
    news_head(img, d, label, "楽天ランキング", W, theme, 120, 44)
    d.rectangle([60, 184, W - 60, 184 + 820], fill=WHITE)
    img.paste(photo(it, W - 140, 780, 800), (70, 204))
    y = text_lines(d, (60, 1040), short_name(it["name"], 60), F("sans", 44), W - 120, 2, WHITE, 1.3)
    if it.get("reviews", 0) >= 10:
        bar(d, 60, y + 30, 520, 36, (it["rating"] - 3) / 2, "評価", f"★{it['rating']:.1f}", YEL)
        bar(d, 60, y + 100, 520, 36, math.log10(max(it["reviews"], 1)) / 5, "レビュー", f"{it['reviews']:,}件", (90, 200, 255))
    news_ticker(d, W, H, "楽天ランキング速報 ｜ #PR", 60)
    img.save(path, quality=85)


# ---------- 入り口 ----------

def top3(style, title, rows, day, path, theme="red"):
    path.parent.mkdir(parents=True, exist_ok=True)
    {"magazine": magazine_top3, "notebook": notebook_top3, "news": news_top3}[style](title, rows, day, path, theme)


def top10(style, title, items, day, path, prefix=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    {"magazine": magazine_top10, "notebook": notebook_top10, "news": news_top10}[style](title, items, day, path, prefix)


def pin(style, it, kind, label, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    {"magazine": magazine_pin, "notebook": notebook_pin, "news": news_pin}[style](it, kind, label, path)
