"""ショート動画の、pop 以外の作り（フレームを1枚ずつ描く）.

型ごとに画面の組み立て・動き・字幕・BGM・効果音をまったく変える。
- list    : 上に黒い帯の大きな2行タイトル、左に順位の一覧（👑3→1）。商品写真を画面いっぱいに出し、順位が埋まっていく
- aruaru  : 黄色い集中線の背景に「第3位」の極太文字。いらすとやのイラストと、赤・青・緑の枠のポイントが順に出る
- magazine: 生成りの紙に明朝体。大きな写真がゆっくり寄り、No.01 の番号と細い罫線だけの静かな紹介
いらすとやの素材は規約上、再配布できないので、リポジトリには入れず作るたびに取ってくる（1本で20点まで）。
"""
import math
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import design
import shorts as S
from articles import short_name

W, H, FPS = S.W, S.H, S.FPS
F = design.font
CACHE = Path(__file__).resolve().parent / "fonts" / "irasutoya"

# いらすとや（https://www.irasutoya.com/）の素材。キー: (ファイル名, 画像のURL)
_B = "https://blogger.googleusercontent.com/img/b/R29vZ2xl/"
IRASUTOYA = {
    "cart": _B + "AVvXsEiwhGLFDWur7F4S3xXPKzKsYjzDWejYzNZctPzrXt1yuD1I5leaHQf4DVcRr1JlttF9s0ZpLI66dkm-RPBq6NiI5qu2SwQH8rMjL60QDrDxT85MlzivZKQ0GAc7xS5lzZEPi48KOmNkpa61/s400/shopping_cart_woman.png",
    "super": _B + "AVvXsEgKJ6e1VKQm0Rt0gLHaStwvFDjFxq_XTvQ4_eX_FE5Ib00K0g9JFfb0dT6J3dZt_YENx6zAg309thHsEmU0rbBUGGPh0XLBV2nEfKaLHOco_0WEmGilH0oSdFOZMdVcET-mQHChBz1zZ_Vc/s400/shopping_supermarket_woman.png",
    "net": _B + "AVvXsEh44qQrkGwHbbMdWh8WpMZvP5VexI94OtpkcX252oi6BYgfCTzXzjsV5smsM0uH3WK96FSETbzbq80AVAXo6fEi5CV6Z9ltD4Ffm1ZDprmgE0KK6I59a62LyFMlzJwkx0AHcyPAAuX9WyY/s400/net_shopping_pc.png",
    "banzai": _B + "AVvXsEhWs7h9TMaX9-PKqp6c0ftEy435E-zYLYpDaUoqGeoh0aOzB0T7stgTxvby1teYWboek9JMK8JbsRvop5Sjk8Q-a7AL1G2yLJjiR9DqkCEJuIILSgjrOB7vNkLRj3IFTU2pGsnkZ0iifOY/s400/seikou_banzai_woman.png",
    "think": _B + "AVvXsEhr2t-1Tel6zajn_ytUpgsAJ3H0xj1ujr-ZrXH3JQD1YonyWsK5oNcpVvwgOaSGIv9CCVTfWB53I8K9zX_yw-e7qh5vJuDmGhQHx1P1MxoQZXTYn-pfuiZfz5xMSZnECI5WZ834Jgeu8Ptl/s400/pose_souzou_woman.png",
    "furusato": _B + "AVvXsEjs8Oa99UMSP6nB2nQZkkJfk2eCViSoKyZRcsvx-4QwmYlUTwYBFVygpxVrPnvShRxcsX2LCzUvbSNgL2mz20OfAnKXoo3yfLAbLOD6WrYrtPwS24nHzPcwUe0fyS_ATPfdf5JEeEg5ZSel/s400/furusato_nouzei.png",
    "closet": _B + "AVvXsEhbBA0B-2Ijlx9QoROexqMiCb56CvqYev00fao9BLFoaNg7cfa4lvb3PzbLziiuSHxNtEwdhtV1vmoQ8NZehtE7JZdM0W9-es-yXI34IwwVMtnr65HFWO9IcnzgGfZAQZwWF2gGvQhqWiDS/s400/closet_seiriseiton_yes.png",
    "senzai": _B + "AVvXsEhnuugkn6zMbgciWKx3wd6ydPAiTgsohKlpfP1WObmoa0K9wC9LbJmVLWJcBwsWv3ZOqZsJtb8XeV3IJIMOVm34xwwP3FR5MATcDihy4Fe5IHGMj1iQuvwdV48cJrgcmEOEyaaN_aqnWMs/s400/sentaku_senzai.png",
    "kome": _B + "AVvXsEjbF19T-Tr_BCfBRA2msvL_Y1N5HAdEtZQ2y4qndHhP8UI2lRpUuc5uCOiZSWf7mMUEQyalkSOLPBlvmQ4WCCw2kK9S8vpZkK1F1346DwmGeYK_M0zxwCxFSkkjwI_QsWe3bWhjeowsXnIu/s400/food_kome_pack_big.png",
    "niku": _B + "AVvXsEia5YQDgZhrAR7IudrlGQlDc15MSfCkIX5HDQC0u6DBkR83_peyCZrmkwh5i5KEm-mrfw9gzo5_6-sFFu4pAPvnDFAoGAatgRSi5uXMcmLgukUICJXidV9WJVLR8POX0Gcvr8vywYrav9-k/s400/food_niku_pack.png",
    "reitou": _B + "AVvXsEiR4OZrRl8f_42KgZz8u0-_gWyASoiDOnrA-53lHeAlafKdjeEJjoUY4G-ufKQeJOKzswkACuhgA5RdB9vQJy-YU3wXHzGL_wKvmf2TxJRYeZzNmLH5aGrBPEN-UZ0QX-bllE1sMhyphenhyphen1esGA/s400/food_reitou_syokuhin.png",
}
# 商品名の言葉 → イラスト
ILLUST_WORDS = [(("米", "こめ", "コメ", "精米"), "kome"), (("肉", "牛", "豚", "鶏", "ハンバーグ", "ステーキ"), "niku"),
                (("冷凍",), "reitou"), (("洗剤", "柔軟剤", "詰め替え", "詰替"), "senzai"),
                (("収納", "ボックス", "チェスト", "ラック", "ケース"), "closet")]


def illust(key):
    """いらすとやの画像（透過PNG）。取れないときは None."""
    path = CACHE / f"{key}.png"
    if not path.exists():
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(IRASUTOYA[key], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                path.write_bytes(r.read())
        except Exception:  # noqa: BLE001
            return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception:  # noqa: BLE001
        return None


def illust_for(it, theme, k):
    for words, key in ILLUST_WORDS:
        if any(w in it["name"] for w in words):
            return key
    if theme == "green":
        return "furusato"
    return ["cart", "super", "net"][k % 3]


def outlined(d, xy, text, f, fill, stroke=(0, 0, 0), sw=10, anchor="mm", outer=None):
    """縁取り文字。outer を渡すと、白縁の外側にさらに黒縁を付ける（2重の縁）."""
    if outer:
        d.text(xy, text, font=f, fill=outer, anchor=anchor, stroke_width=sw + 8, stroke_fill=outer)
    d.text(xy, text, font=f, fill=fill, anchor=anchor, stroke_width=sw, stroke_fill=stroke)


def fit_size(d, text, kind, size, width, minimum=40):
    while size > minimum and d.textlength(text, font=F(kind, size)) > width:
        size -= 4
    return F(kind, size)


def product(it, size=800):
    return S.fetch_image(it.get("image"), size)


def contain(pic, w, h, bg=(255, 255, 255, 255)):
    box = Image.new("RGBA", (w, h), bg)
    if pic:
        r = min(w / pic.width, h / pic.height)
        p = pic.resize((max(1, int(pic.width * r)), max(1, int(pic.height * r))), Image.LANCZOS)
        box.paste(p, ((w - p.width) // 2, (h - p.height) // 2))
    return box


def save(img, out, f):
    img.convert("RGB").save(out / f"f{f:04d}.jpg", quality=88)


def frames(dur):
    return range(int(dur * FPS))


def mini_name(it, n=9):
    """一覧に出す短い商品名（単語の区切りで n 文字くらいまで）."""
    out = ""
    for w in short_name(it["name"], 40).replace("｜", " ").split():
        if out and len(out) + len(w) > n:
            break
        out += w
    return out[: n + 2] or short_name(it["name"], n)


def pr_tag(d, x=40, y=50, dark=False):
    d.rounded_rectangle([x, y, x + 96, y + 52], radius=10, fill=(30, 30, 30) if dark else (255, 255, 255))
    d.text((x + 48, y + 26), "PR", font=F("sans", 34), fill=(255, 255, 255) if dark else (30, 30, 30), anchor="mm")


# ======================================================================
# list：黒帯タイトル＋左の順位一覧（参考：「〜TOP6」系のまとめショート）
# ======================================================================

CROWN = {1: (240, 190, 40), 2: (200, 205, 215), 3: (205, 130, 70)}
BAND = 430


def crown(d, x, y, s, col):
    d.polygon([(x, y + s), (x, y + s * 0.3), (x + s * 0.28, y + s * 0.6), (x + s * 0.5, y), (x + s * 0.72, y + s * 0.6),
               (x + s, y + s * 0.3), (x + s, y + s)], fill=col, outline=(60, 40, 0))


def list_band(img, title):
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, BAND], fill=(0, 0, 0))
    l1, _, l2 = title.partition("\n")
    outlined(d, (W // 2, 190), l1, fit_size(d, l1, "sans", 104, W - 80), (255, 255, 255), (0, 0, 0), 4)
    outlined(d, (W // 2, 330), l2 or "", fit_size(d, l2 or " ", "sans", 110, W - 80), (255, 226, 0), (0, 0, 0), 4)
    pr_tag(d, 30, 30, dark=False)


def list_media(it, t, punch=0.0):
    """黒帯の下の、商品写真を画面いっぱいに見せる部分（ぼかした拡大を背景に敷く）."""
    pic = product(it)
    mh = H - BAND
    bg = Image.new("RGB", (W, mh), (30, 30, 30))
    if pic:
        r = max(W / pic.width, mh / pic.height) * 1.1
        big = pic.resize((int(pic.width * r), int(pic.height * r))).filter(ImageFilter.GaussianBlur(30))
        bg.paste(big, ((W - big.width) // 2, (mh - big.height) // 2))
        bg = Image.blend(bg, Image.new("RGB", bg.size, (0, 0, 0)), 0.35)
    return bg, pic


def list_rows(d, revealed, current, x=40, y=BAND + 70):
    """左の順位一覧（1〜3位）。revealed: {順位: 名前}."""
    for r in (1, 2, 3):
        yy = y + (r - 1) * 96
        crown(d, x, yy, 56, CROWN[r])
        d.text((x + 28, yy + 38), str(r), font=F("sans", 30), fill=(40, 30, 0), anchor="mm")
        name = revealed.get(r)
        if name:
            on = r == current
            f = F("sans", 54 if on else 46)
            outlined(d, (x + 80, yy + 30), name, f, (255, 255, 255) if on else (190, 190, 190),
                     (0, 0, 0), 7 if on else 5, anchor="lm")


def list_title(t, items, dur, out, text):
    chunks = S.sub_chunks(text)
    pics = [contain(product(it, 400), 300, 300) for it, _ in items]
    out.mkdir(parents=True, exist_ok=True)
    for f in frames(dur):
        tt = f / FPS
        img = Image.new("RGB", (W, H), (20, 20, 20))
        for k, p in enumerate(pics):  # 3つの商品を「？」で隠して並べる
            s = S.ease_out((tt - 0.15 * k) / 0.4)
            if s <= 0:
                continue
            x, y = 90 + k * 310, BAND + 520 + (k % 2) * 160
            q = p.copy().filter(ImageFilter.GaussianBlur(14 * (1 - min(1, tt / 3))))
            S.paste_scaled(img, q, x + 150, y + 150, s)
            dq = ImageDraw.Draw(img)
            outlined(dq, (x + 150, y + 150), "？", F("sans", 140), (255, 255, 255), (0, 0, 0), 8)
        list_band(img, t["title"])
        d = ImageDraw.Draw(img)
        list_rows(d, {}, None)
        S.draw_sub(d, S.sub_at(chunks, tt, dur))
        save(img, out, f)
    return [("whoosh", 0.0), ("ding", 0.3)]


def list_item(t, rank, pos, it, note, dur, out, text, revealed):
    chunks = S.sub_chunks(text)
    bg, pic = list_media(it, t)
    card = contain(pic, 580, 580) if pic else None
    price = S.price_text(it)
    out.mkdir(parents=True, exist_ok=True)
    for f in frames(dur):
        tt = f / FPS
        img = Image.new("RGB", (W, H))
        img.paste(bg, (0, BAND))
        if card:
            s = 1.0 + 0.18 * (1 - S.ease_out(tt / 0.25)) + 0.04 * tt / max(dur, 1)  # ドンと出て、ゆっくり寄る
            S.paste_scaled(img, card, W // 2 + 70, BAND + 670, s)
        list_band(img, t["title"])
        d = ImageDraw.Draw(img)
        shown = {**revealed, rank: mini_name(it)} if tt > 0.35 else dict(revealed)
        list_rows(d, shown, rank)
        if tt > 0.8:  # 値段の札
            s = S.bounce((tt - 0.8) / 0.3)
            tag = Image.new("RGBA", (520, 150), (0, 0, 0, 0))
            td = ImageDraw.Draw(tag)
            td.rounded_rectangle([0, 0, 519, 149], radius=24, fill=(255, 226, 0), outline=(0, 0, 0), width=6)
            td.text((260, 54), price, font=fit_size(td, price, "sans", 84, 480), fill=(0, 0, 0), anchor="mm")
            td.text((260, 122), note[:16], font=F("sans", 30), fill=(60, 60, 60), anchor="mm")
            S.paste_scaled(img, tag, W - 300, BAND + 975, s)
        S.draw_sub(d, S.sub_at(chunks, tt, dur))
        save(img, out, f)
    return [("whoosh", 0.0), ("ding", 0.35), ("pop", 0.82)] + ([("fanfare", 0.4)] if rank == 1 else [])


def list_end(t, dur, out, text, line1, revealed):
    chunks = S.sub_chunks(text)
    out.mkdir(parents=True, exist_ok=True)
    for f in frames(dur):
        tt = f / FPS
        img = Image.new("RGB", (W, H), (20, 20, 20))
        list_band(img, t["title"])
        d = ImageDraw.Draw(img)
        list_rows(d, revealed, None, 120, BAND + 160)
        s = S.bounce((tt - 0.2) / 0.35)
        box = Image.new("RGBA", (900, 230), (0, 0, 0, 0))
        bd = ImageDraw.Draw(box)
        bd.rounded_rectangle([0, 0, 899, 229], radius=30, fill=(255, 226, 0))
        bd.text((450, 75), "くわしくは", font=F("sans", 56), fill=(0, 0, 0), anchor="mm")
        bd.text((450, 160), "プロフィールのリンクから", font=F("sans", 64), fill=(0, 0, 0), anchor="mm")
        S.paste_scaled(img, box, W // 2, BAND + 720, s)
        d.text((W // 2, BAND + 930), f"{line1}　{S.credit()}", font=F("sans", 32), fill=(200, 200, 200), anchor="mm")
        S.draw_sub(d, S.sub_at(chunks, tt, dur))
        save(img, out, f)
    return [("whoosh", 0.0), ("pop", 0.25)]


# ======================================================================
# aruaru：集中線＋極太文字＋いらすとや（参考：「〜3選」のイラストまとめショート）
# ======================================================================

SUN = {"red": ((255, 196, 20), (255, 150, 0)), "green": ((150, 220, 90), (60, 170, 80))}
BOX_COLS = [(220, 30, 40), (30, 70, 210), (30, 150, 60)]
_sun_cache = {}


def sunburst(theme, tt):
    """ゆっくり回る集中線の背景（1周期分を先に作って使い回す）."""
    key = theme
    if key not in _sun_cache:
        c1, c2 = SUN[theme]
        n, period = 20, 18.0  # 20本の線。18度で同じ形に戻る
        size = int(math.hypot(W, H)) + 20
        base = Image.new("RGB", (size, size), c1)
        d = ImageDraw.Draw(base)
        cx = cy = size / 2
        for k in range(n):
            a0 = 2 * math.pi * k / n
            a1 = a0 + math.pi / n
            d.polygon([(cx, cy), (cx + size * math.cos(a0), cy + size * math.sin(a0)),
                       (cx + size * math.cos(a1), cy + size * math.sin(a1))], fill=c2)
        glow = Image.new("L", (size, size), 0)
        ImageDraw.Draw(glow).ellipse([cx - 420, cy - 420, cx + 420, cy + 420], fill=255)
        base.paste(Image.new("RGB", base.size, (255, 236, 150) if theme == "red" else (220, 245, 190)), (0, 0),
                   glow.filter(ImageFilter.GaussianBlur(160)))
        steps = 24
        _sun_cache[key] = []
        for i in range(steps):
            r = base.rotate(period * i / steps, resample=Image.BILINEAR)
            _sun_cache[key].append(r.crop((int(cx - W / 2), int(cy - H / 2) + 120, int(cx + W / 2), int(cy + H / 2) + 120)))
    seq = _sun_cache[key]
    return seq[int(tt * 8) % len(seq)].copy()


def big_label(d, xy, text, size, fill=(255, 255, 255), kind="impact", width=W - 80):
    f = fit_size(d, text, kind, size, width)
    outlined(d, xy, text, f, fill, (0, 0, 0), 14)


def red_label(d, xy, text, size, width=W - 80):
    f = fit_size(d, text, "impact", size, width)
    outlined(d, xy, text, f, (232, 30, 30), (255, 255, 255), 10, outer=(0, 0, 0))


def paste_illust(img, key, cx, bottom, h, tt, delay=0.0):
    pic = illust(key)
    if not pic:
        return
    r = h / pic.height
    p = pic.resize((int(pic.width * r), int(pic.height * r)), Image.LANCZOS)
    s = S.bounce((tt - delay) / 0.4)
    bob = int(10 * math.sin(tt * 5))
    S.paste_scaled(img, p, cx, bottom - h / 2 + bob, s)


def point_box(text, col, w=920, h=200):
    box = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(box)
    bd.rounded_rectangle([6, 6, w - 7, h - 7], radius=34, fill=(255, 255, 255), outline=col, width=14)
    f = fit_size(bd, text, "sans", 64, w - 90, 40)
    lines = S.wrap(bd, text, f, w - 90, 2)
    y = h / 2 - (len(lines) - 1) * f.size * 0.6
    for ln in lines:
        bd.text((50, y), ln, font=f, fill=(20, 20, 20), anchor="lm")
        y += f.size * 1.2
    return box


def aruaru_title(t, items, dur, out, text):
    chunks = S.sub_chunks(text)
    l1, _, l2 = t["title"].partition("\n")
    out.mkdir(parents=True, exist_ok=True)
    for f in frames(dur):
        tt = f / FPS
        img = sunburst(t["theme"], tt)
        d = ImageDraw.Draw(img)
        if tt > 0.05:
            big_label(d, (W // 2, 330), l1, 120)
        if tt > 0.35:
            s = S.bounce((tt - 0.35) / 0.35)
            lay = Image.new("RGBA", (W, 420), (0, 0, 0, 0))
            red_label(ImageDraw.Draw(lay), (W // 2, 210), l2, 150)
            S.paste_scaled(img, lay, W // 2, 640, s)
        paste_illust(img, "furusato" if t["theme"] == "green" else "cart", W // 2, 1480, 560, tt, 0.6)
        pr_tag(d)
        S.draw_sub(d, S.sub_at(chunks, tt, dur))
        save(img, out, f)
    return [("jan", 0.0), ("pop", 0.35)]


def aruaru_item(t, rank, pos, it, note, dur, out, text, revealed):
    chunks = S.sub_chunks(text)
    card = contain(product(it, 600), 620, 620)
    name = mini_name(it, 8)
    facts = [S.price_text(it) + ("（寄付額）" if t["theme"] == "green" else "（送料無料）" if "送料無料" in note else ""),
             f"★{it['rating']:.1f}・レビュー{it['reviews']:,}件" if it.get("reviews", 0) >= 10 else "楽天で人気",
             note]
    boxes = [point_box(x, BOX_COLS[k]) for k, x in enumerate(facts)]
    key = illust_for(it, t["theme"], pos)
    switch = max(1.6, dur * 0.42)  # 前半は商品、後半はポイントの3つの枠
    out.mkdir(parents=True, exist_ok=True)
    for f in frames(dur):
        tt = f / FPS
        img = sunburst(t["theme"], tt)
        d = ImageDraw.Draw(img)
        big_label(d, (W // 2, 200), f"第{rank}位", 170)
        if tt < switch:
            red_label(d, (W // 2, 420), name, 150)
            s = S.bounce((tt - 0.2) / 0.35)
            S.paste_scaled(img, card, W // 2, 900, s * 0.95)
            paste_illust(img, key, W - 220, 1480, 380, tt, 0.5)
        else:
            for k, b in enumerate(boxes):
                s = S.bounce((tt - switch - 0.35 * k) / 0.3)
                S.paste_scaled(img, b, W // 2, 470 + k * 250, s)
            paste_illust(img, key, W // 2, 1500, 420, tt, switch)
        pr_tag(d)
        S.draw_sub(d, S.sub_at(chunks, tt, dur))
        save(img, out, f)
    ev = [("jan", 0.0), ("pop", 0.2), ("pop", switch), ("pop", switch + 0.35), ("pop", switch + 0.7)]
    return ev + ([("fanfare", 0.1)] if rank == 1 else [])


def aruaru_end(t, dur, out, text, line1, revealed):
    chunks = S.sub_chunks(text)
    out.mkdir(parents=True, exist_ok=True)
    for f in frames(dur):
        tt = f / FPS
        img = sunburst(t["theme"], tt)
        d = ImageDraw.Draw(img)
        big_label(d, (W // 2, 300), "くわしくは", 130)
        s = S.bounce((tt - 0.25) / 0.35)
        lay = Image.new("RGBA", (W, 400), (0, 0, 0, 0))
        red_label(ImageDraw.Draw(lay), (W // 2, 200), "プロフィールへ", 140)
        S.paste_scaled(img, lay, W // 2, 560, s)
        paste_illust(img, "banzai", W // 2, 1420, 600, tt, 0.4)
        outlined(d, (W // 2, 1470), S.credit(), F("sans", 34), (255, 255, 255), (0, 0, 0), 4)
        pr_tag(d)
        S.draw_sub(d, S.sub_at(chunks, tt, dur))
        save(img, out, f)
    return [("jan", 0.0), ("pop", 0.3)]


# ======================================================================
# magazine：紙と明朝体、写真がゆっくり寄る（静かな特集ページ）
# ======================================================================

PAPER, INK, SUB = (244, 239, 230), (34, 30, 26), (120, 110, 98)
ACC = {"red": (150, 52, 40), "green": (64, 96, 52)}


def fade(img, base, a):
    """紙の色から a（0→1）で浮かび上がらせる."""
    return Image.blend(base, img, max(0.0, min(1.0, a)))


def kicker(d, xy, text, size=30, fill=SUB, anchor_center=False):
    f = F("serif_light", size)
    width = sum(d.textlength(c, font=f) + size * 0.4 for c in text)
    x, y = xy
    if anchor_center:
        x -= width / 2
    for c in text:
        d.text((x, y), c, font=f, fill=fill)
        x += d.textlength(c, font=f) + size * 0.4


def mag_sub(d, text):
    f, lines = S.sub_lines(d, text, lambda s: F("serif", s), 46, 900)
    y = 1590 - (len(lines) - 1) * f.size * 0.7
    for ln in lines:
        d.text((W // 2, y), ln, font=f, fill=INK, anchor="mm")
        y += f.size * 1.4


def mag_pr(d):
    d.rectangle([40, 50, 120, 96], outline=INK, width=2)
    d.text((80, 73), "PR", font=F("serif", 28), fill=INK, anchor="mm")


def magazine_title(t, items, dur, out, text):
    chunks = S.sub_chunks(text)
    base = Image.new("RGB", (W, H), PAPER)
    thumbs = [contain(product(it, 400), 280, 280) for it, _ in items]
    m, dd = int(t["day"][5:7]), int(t["day"][8:10])
    out.mkdir(parents=True, exist_ok=True)
    for f in frames(dur):
        tt = f / FPS
        img = base.copy()
        d = ImageDraw.Draw(img)
        kicker(d, (W // 2, 330), "RAKUTEN PICKS", 34, anchor_center=True)
        half = 380 * S.ease_out(tt / 0.8)
        d.line([(W / 2 - half, 400), (W / 2 + half, 400)], fill=INK, width=2)
        y = 500
        for ln in t["title"].split("\n"):
            d.text((W // 2, y), ln, font=fit_size(d, ln, "serif", 96, W - 160), fill=INK, anchor="mm")
            y += 130
        d.text((W // 2, y + 30), f"{m:02d}.{dd:02d}", font=F("serif_light", 48), fill=ACC[t["theme"]], anchor="mm")
        for k, p in enumerate(thumbs):
            a = (tt - 0.5 - 0.25 * k) / 0.5
            if a > 0:
                lay = fade(p.convert("RGB"), Image.new("RGB", p.size, PAPER), a)
                img.paste(lay, (90 + k * 310, 1060 + int(30 * (1 - min(1, a)))))
        img = fade(img, base, tt / 0.5)
        d = ImageDraw.Draw(img)
        mag_pr(d)
        mag_sub(d, S.sub_at(chunks, tt, dur))
        save(img, out, f)
    return [("page", 0.0)]


def magazine_item(t, rank, pos, it, note, dur, out, text, revealed):
    chunks = S.sub_chunks(text)
    base = Image.new("RGB", (W, H), PAPER)
    pic = contain(product(it, 800), 1000, 1000).convert("RGB")
    acc = ACC[t["theme"]]
    out.mkdir(parents=True, exist_ok=True)
    for f in frames(dur):
        tt = f / FPS
        img = base.copy()
        z = 1.0 + 0.07 * tt / max(dur, 1)  # ゆっくり寄る
        cw = int(1000 / z)
        crop = pic.crop(((1000 - cw) // 2, (1000 - cw) // 2, (1000 + cw) // 2, (1000 + cw) // 2)).resize((960, 960))
        img.paste(crop, (60, 150 - int(24 * (1 - S.ease_out(tt / 0.6)))))
        d = ImageDraw.Draw(img)
        d.text((60, 1150), f"No.0{pos + 1}", font=F("serif", 60), fill=acc)
        d.line([(260, 1186), (W - 60, 1186)], fill=SUB, width=1)
        S_y = 1230
        for ln in S.wrap(d, short_name(it["name"], 60), F("serif", 48), W - 120, 2):
            d.text((60, S_y), ln, font=F("serif", 48), fill=INK)
            S_y += 66
        d.text((60, S_y + 14), S.price_text(it), font=F("serif", 64), fill=INK)
        d.text((W - 60, S_y + 40), note[:18], font=F("serif_light", 34), fill=SUB, anchor="ra")
        img = fade(img, base, tt / 0.45)
        d = ImageDraw.Draw(img)
        mag_pr(d)
        mag_sub(d, S.sub_at(chunks, tt, dur))
        save(img, out, f)
    return [("page", 0.0)]


def magazine_end(t, dur, out, text, line1, revealed):
    chunks = S.sub_chunks(text)
    base = Image.new("RGB", (W, H), PAPER)
    out.mkdir(parents=True, exist_ok=True)
    for f in frames(dur):
        tt = f / FPS
        img = base.copy()
        d = ImageDraw.Draw(img)
        d.line([(200, 560), (W - 200, 560)], fill=INK, width=1)
        d.text((W // 2, 680), "ほかのアイテムは", font=F("serif", 64), fill=INK, anchor="mm")
        d.text((W // 2, 800), "プロフィールのリンクから", font=F("serif", 72), fill=INK, anchor="mm")
        d.line([(200, 920), (W - 200, 920)], fill=INK, width=1)
        kicker(d, (W // 2, 1000), "RAKUTEN PICKS", 30, anchor_center=True)
        d.text((W // 2, 1100), f"{line1}　{S.credit()}", font=F("serif_light", 30), fill=SUB, anchor="mm")
        img = fade(img, base, tt / 0.6)
        d = ImageDraw.Draw(img)
        mag_pr(d)
        mag_sub(d, S.sub_at(chunks, tt, dur))
        save(img, out, f)
    return [("page", 0.0)]


STYLES = {
    "list": (list_title, list_item, list_end),
    "aruaru": (aruaru_title, aruaru_item, aruaru_end),
    "magazine": (magazine_title, magazine_item, magazine_end),
}


# ======================================================================
# BGM（型ごとに曲の作りを変える。すべてプログラムで作る）
# ======================================================================

def bgm(style, seconds, path, seed=0):
    import wave
    sr = 44100
    n = int(sr * (seconds + 1))
    t = np.arange(n) / sr
    out = np.zeros(n)
    rng = np.random.default_rng(seed)

    def note(freq, start, dur, vol, kind="sine", decay=4.0):
        i0, i1 = int(start * sr), min(int((start + dur) * sr), n)
        if i0 >= n:
            return
        tt = t[i0:i1] - start
        env = np.exp(-tt * decay) * np.minimum(1, tt * 300)
        if kind == "piano":
            w = np.sin(2 * np.pi * freq * tt) + 0.35 * np.sin(4 * np.pi * freq * tt) + 0.12 * np.sin(6 * np.pi * freq * tt)
        elif kind == "saw":
            w = 2 * ((freq * tt) % 1) - 1
        elif kind == "square":
            w = np.sign(np.sin(2 * np.pi * freq * tt)) * 0.6
        else:
            w = np.sin(2 * np.pi * freq * tt)
        out[i0:i1] += vol * env * w

    def hit(start, kind):
        i0 = int(start * sr)
        if i0 >= n:
            return
        if kind == "kick":
            ln = min(int(0.18 * sr), n - i0)
            kk = np.arange(ln) / sr
            out[i0:i0 + ln] += 0.55 * np.sin(2 * np.pi * (120 - 380 * kk) * kk) * np.exp(-kk * 22)
        elif kind == "snare":
            ln = min(int(0.15 * sr), n - i0)
            out[i0:i0 + ln] += 0.22 * rng.standard_normal(ln) * np.exp(-np.arange(ln) / sr * 30)
        else:  # hat
            ln = min(int(0.03 * sr), n - i0)
            out[i0:i0 + ln] += 0.06 * rng.standard_normal(ln) * np.exp(-np.arange(ln) / sr * 120)

    root = 261.63 * 2 ** ([0, 2, 5, 7][seed % 4] / 12)
    hz = lambda semi: root * 2 ** (semi / 12)  # noqa: E731
    if style == "list":  # ローファイ寄りのヒップホップ（BPM 88）
        beat = 60 / 88
        prog = [[9, 12, 16, 19], [5, 9, 12, 16], [0, 4, 7, 11], [7, 11, 14, 17]]
        k = 0
        while k * beat * 4 < seconds + 1:
            s = k * beat * 4
            for semi in prog[k % 4]:
                note(hz(semi - 12), s, beat * 4, 0.07, "piano", 0.8)
            note(hz(prog[k % 4][0] - 24), s, beat * 2, 0.25, "sine", 1.5)
            for j in range(4):
                hit(s + j * beat, "kick" if j in (0, 2) else "snare")
                hit(s + j * beat + beat / 2, "hat")
            k += 1
    elif style == "aruaru":  # 明るいマーチ風（BPM 140）
        beat = 60 / 140
        prog = [[0, 4, 7], [5, 9, 12], [7, 11, 14], [0, 4, 7]]
        melody = [12, 14, 16, 12, 17, 16, 14, 11]
        k = 0
        while k * beat * 4 < seconds + 1:
            s = k * beat * 4
            ch = prog[k % 4]
            for j in range(4):
                note(hz(ch[0] - 12), s + j * beat, beat * 0.5, 0.2, "square", 8)
                note(hz(ch[(j % 2) + 1]), s + j * beat + beat / 2, beat * 0.4, 0.08, "square", 10)
                hit(s + j * beat, "kick" if j % 2 == 0 else "snare")
            for j in range(8):
                note(hz(melody[(k * 2 + j) % len(melody)]), s + j * beat / 2, beat / 2, 0.07, "sine", 6)
            k += 1
    else:  # magazine：静かなピアノ（BPM 72・打楽器なし）
        beat = 60 / 72
        prog = [[0, 7, 16], [9, 16, 24], [5, 12, 21], [7, 14, 23]]
        k = 0
        while k * beat * 4 < seconds + 1:
            s = k * beat * 4
            ch = prog[k % 4]
            note(hz(ch[0] - 12), s, beat * 4, 0.16, "piano", 0.7)
            for j, semi in enumerate([ch[1], ch[2], ch[1] + 12, ch[2]]):
                note(hz(semi), s + j * beat, beat * 1.5, 0.08, "piano", 1.2)
            k += 1
    fadeout = int(sr * 1.5)
    out[-fadeout:] *= np.linspace(1, 0, fadeout)
    out = out / max(np.abs(out).max(), 1e-6) * 0.8
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((out * 32767).astype(np.int16).tobytes())
