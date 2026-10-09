"""画像・動画の見た目と声を、一定の期間ごとに切り替える（同じ見た目が続いて見飽きられないように）.

PERIOD_DAYS 日ごとに PATTERNS を順に回す。X の画像・Pinterest のピン・ショート動画がまとめて切り替わる。
config.json の "design_pattern" に番号かキーを入れると、その型に固定できる（確認用）。
"""
import datetime as dt
from pathlib import Path

PERIOD_DAYS = 14
EPOCH = dt.date(2026, 9, 28)  # 9/28〜10/11 が最初の型。ここから2週間ごとに次の型へ

SANS = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "C:/Windows/Fonts/YuGothB.ttc"]
SERIF = ["/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc", "C:/Windows/Fonts/yumindb.ttf"]

# red = 楽天の売れ筋、green = ふるさと納税
PATTERNS = [
    dict(key="pop", name="ポップ（赤・ストライプ）", font="sans",
         bg=(246, 244, 240), deco="none", card=(255, 255, 255), ink=(29, 29, 31), muted=(110, 110, 115),
         head="band", head_ink=(255, 255, 255),
         grad={"red": ((165, 0, 0), (214, 0, 47), (255, 59, 92)), "green": ((6, 92, 56), (11, 122, 75), (43, 181, 124))},
         accent={"red": (191, 0, 0), "green": (11, 122, 75)},
         stroke={"red": (90, 0, 10), "green": (0, 60, 30)}, hook=(255, 226, 90), overlay="stripes", enter="slide",
         ring=(255, 247, 230), vcard=(255, 255, 255), vink=(29, 29, 31),
         confetti=[(255, 214, 0), (255, 255, 255), (0, 200, 255), (255, 120, 180), (120, 230, 120)],
         bgm=dict(bpm=120, prog=[[0, 4, 7], [7, 11, 14], [9, 12, 16], [5, 9, 12]], shape="pluck", kick=0.5),
         voice=dict(name="ずんだもん", style="ノーマル", speed=1.15, da="なのだ", suru="するのだ", check="チェックするのだ")),
    dict(key="natural", name="ナチュラル（生成り・明朝）", font="serif",
         bg=(240, 232, 219), deco="none", card=(255, 252, 246), ink=(58, 42, 30), muted=(130, 112, 95),
         head="line", head_ink=(58, 42, 30),
         grad={"red": ((120, 72, 50), (160, 98, 66), (196, 134, 96)), "green": ((62, 82, 44), (92, 114, 64), (138, 156, 98))},
         accent={"red": (176, 82, 46), "green": (86, 108, 44)},
         stroke={"red": (60, 34, 20), "green": (34, 48, 20)}, hook=(255, 238, 196), overlay="grid", enter="rise",
         ring=(255, 250, 240), vcard=(255, 252, 246), vink=(58, 42, 30),
         confetti=[(255, 236, 190), (214, 160, 90), (150, 170, 100), (255, 255, 255)],
         bgm=dict(bpm=96, prog=[[5, 9, 12], [0, 4, 7], [2, 5, 9], [10, 14, 17]], shape="bell", kick=0.3),
         voice=dict(name="春日部つむぎ", style="ノーマル", speed=1.12, da="です", suru="します", check="チェックしてね")),
    dict(key="pastel", name="パステル（ピンク・水玉）", font="sans",
         bg=(255, 241, 244), deco="dots", card=(255, 255, 255), ink=(60, 40, 50), muted=(140, 110, 120),
         head="pill", head_ink=(255, 255, 255),
         grad={"red": ((246, 120, 140), (255, 158, 168), (255, 200, 196)), "green": ((60, 170, 150), (110, 200, 178), (170, 226, 208))},
         accent={"red": (226, 70, 100), "green": (22, 140, 118)},
         stroke={"red": (160, 30, 64), "green": (10, 96, 80)}, hook=(255, 248, 140), overlay="dots", enter="zoom",
         ring=(255, 255, 255), vcard=(255, 255, 255), vink=(60, 40, 50),
         confetti=[(255, 255, 255), (255, 214, 230), (190, 230, 255), (255, 245, 160), (200, 240, 210)],
         bgm=dict(bpm=132, prog=[[0, 4, 7], [9, 12, 16], [5, 9, 12], [7, 11, 14]], shape="square", kick=0.45),
         voice=dict(name="四国めたん", style="ノーマル", speed=1.12, da="です", suru="します", check="チェックしてくださいね")),
    dict(key="chic", name="シック（黒・ゴールド）", font="serif",
         bg=(26, 26, 30), deco="none", card=(40, 40, 46), ink=(245, 242, 235), muted=(170, 165, 155),
         head="gold", head_ink=(222, 188, 92),
         grad={"red": ((18, 18, 22), (40, 18, 26), (84, 22, 36)), "green": ((14, 22, 20), (20, 42, 34), (30, 66, 50))},
         accent={"red": (222, 188, 92), "green": (222, 188, 92)},
         stroke={"red": (0, 0, 0), "green": (0, 0, 0)}, hook=(232, 198, 100), overlay="checker", enter="drop",
         ring=(250, 240, 215), vcard=(36, 36, 42), vink=(245, 242, 235),
         confetti=[(232, 198, 100), (250, 230, 170), (200, 160, 70)],
         bgm=dict(bpm=88, prog=[[9, 12, 16], [5, 9, 12], [0, 4, 7], [7, 11, 14]], shape="sine", kick=0.35),
         voice=dict(name="冥鳴ひまり", style="ノーマル", speed=1.1, da="です", suru="します", check="チェックしてみてください")),
]


def pattern(day, cfg=None):
    """その日に使う型（day は 'YYYY-MM-DD'）."""
    if cfg is None:
        import json
        conf = Path(__file__).resolve().parent / "config.json"
        cfg = json.loads(conf.read_text(encoding="utf-8")) if conf.exists() else {}
    fixed = cfg.get("design_pattern")
    if fixed is not None:
        for i, p in enumerate(PATTERNS):
            if fixed in (i, p["key"]):
                return p
    n = (dt.date.fromisoformat(day) - EPOCH).days // PERIOD_DAYS
    return PATTERNS[max(n, 0) % len(PATTERNS)]


def schedule(day, count=4):
    """今の型と、次に切り替わる日と型（ポータル表示用）."""
    d = dt.date.fromisoformat(day)
    n = max((d - EPOCH).days // PERIOD_DAYS, 0)
    out = []
    for k in range(count):
        start = EPOCH + dt.timedelta(days=(n + k) * PERIOD_DAYS)
        out.append((start, PATTERNS[(n + k) % len(PATTERNS)]))
    return out


def font(pat, size, head=False):
    from PIL import ImageFont
    for f in (SERIF if head and pat["font"] == "serif" else []) + SANS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def tone(pat, text):
    """「〜なのだ」の原稿を、その型の声の話し方にする."""
    v = pat["voice"]
    return text.replace("チェックするのだ", v["check"]).replace("するのだ", v["suru"]).replace("なのだ", v["da"])


def canvas(pat, W, H):
    """静止画の下地（模様つき）."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), pat["bg"])
    if pat["deco"] == "dots":
        d = ImageDraw.Draw(img)
        dot = tuple(max(0, c - 14) for c in pat["bg"])
        for y in range(0, H, 44):
            for x in range((y // 44) % 2 * 22, W, 44):
                d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=dot)
    return img


def header(img, pat, theme, title, right, h, title_size, right_size, pad=40):
    """見出し部分を描き、見出しの下端の y を返す."""
    from PIL import ImageDraw
    W = img.width
    d = ImageDraw.Draw(img)
    c1, c2, _ = pat["grad"][theme]
    tf, rf = font(pat, title_size, head=True), font(pat, right_size)
    if pat["head"] == "band":
        for y in range(h):
            k = y / h
            d.line([(0, y), (W, y)], fill=tuple(int(c1[i] + (c2[i] - c1[i]) * k) for i in range(3)))
        d.text((pad, h // 2), title, font=tf, fill=pat["head_ink"], anchor="lm")
        d.text((W - pad, h // 2), right, font=rf, fill=(255, 235, 235), anchor="rm")
    elif pat["head"] == "line":
        acc = pat["accent"][theme]
        d.text((pad, h // 2), title, font=tf, fill=pat["head_ink"], anchor="lm")
        d.text((W - pad, h // 2), right, font=rf, fill=pat["muted"], anchor="rm")
        d.line([(pad, h - 6), (W - pad, h - 6)], fill=acc, width=4)
        d.line([(pad, h + 2), (W - pad, h + 2)], fill=acc, width=1)
    elif pat["head"] == "pill":
        acc = pat["accent"][theme]
        tw = d.textlength(title, font=tf)
        d.rounded_rectangle([pad - 10, 14, min(pad + tw + 40, W - pad - 10), h - 14], radius=(h - 28) // 2, fill=acc)
        d.text((pad + 15, h // 2), title, font=tf, fill=pat["head_ink"], anchor="lm")
        d.text((W - pad, h // 2), right, font=rf, fill=pat["muted"], anchor="rm")
    else:  # gold
        acc = pat["accent"][theme]
        d.text((pad, h // 2), title, font=tf, fill=pat["head_ink"], anchor="lm")
        d.text((W - pad, h // 2), right, font=rf, fill=pat["muted"], anchor="rm")
        d.line([(pad, h - 4), (W - pad, h - 4)], fill=acc, width=2)
    return h
