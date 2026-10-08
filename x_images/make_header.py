import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter
OUT = sys.argv[1]
SS = 4  # 拡大して描いてから縮小（なめらかにする）
FONT_B = "C:/Windows/Fonts/YuGothB.ttc"

def grad(w, h, c1, c2, c3):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for x in range(w):
        for y in range(h):
            t = (x / w * 0.7 + y / h * 0.3)
            a, b, u = (c1, c2, t / 0.55) if t < 0.55 else (c2, c3, (t - 0.55) / 0.45)
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * u) for i in range(3))
    return img

def hexc(h): return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))

def bear(d, ox, oy, s):
    """64x64 座標系のらんくまを (ox,oy) 起点・倍率 s で描く."""
    P = lambda x, y: (ox + x * s, oy + y * s)
    def circ(x, y, r, col): d.ellipse([*P(x - r, y - r), *P(x + r, y + r)], fill=col)
    def ell(x, y, rx, ry, col): d.ellipse([*P(x - rx, y - ry), *P(x + rx, y + ry)], fill=col)
    # 王冠
    d.polygon([P(20, 10), P(25, 16), P(32, 7), P(39, 16), P(44, 10), P(42, 20), P(22, 20)], fill=hexc("#f2c230"))
    for x in (20, 32, 44):
        circ(x, 9 if x != 32 else 6, 1.6, hexc("#f2c230"))
    circ(16, 24, 8, hexc("#a8693a")); circ(48, 24, 8, hexc("#a8693a"))
    circ(16, 24, 4, hexc("#e9b88c")); circ(48, 24, 4, hexc("#e9b88c"))
    circ(32, 38, 21, hexc("#b97a45"))
    ell(32, 45, 10, 8, hexc("#f1d3b3"))
    circ(24, 35, 2.6, hexc("#2b1b10")); circ(40, 35, 2.6, hexc("#2b1b10"))
    circ(24.9, 34.1, 0.9, (255, 255, 255)); circ(40.9, 34.1, 0.9, (255, 255, 255))
    ell(32, 41.5, 3.4, 2.4, hexc("#2b1b10"))
    d.arc([*P(28, 44.5), *P(36, 49)], 20, 160, fill=hexc("#2b1b10"), width=max(2, int(1.6 * s)))
    circ(19, 42, 2.6, (240, 138, 138)); circ(45, 42, 2.6, (240, 138, 138))

RED1, RED2, RED3 = hexc("#a50000"), hexc("#d6002f"), hexc("#ff3b5c")
GREEN = hexc("#1f8a4c")
HW, HH = 1500 * SS, 500 * SS
hdr = grad(HW, HH, RED1, RED2, RED3)
d = ImageDraw.Draw(hdr, "RGBA")
for cx, cy, r in [(1380, 60, 260), (1180, 520, 200), (120, -40, 180)]:
    d.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], outline=(255, 255, 255, 28), width=34 * SS)
F = lambda n: ImageFont.truetype(FONT_B, int(n * SS))
x0 = 330 * SS
f3 = F(28)
kick = "楽天で今、売れているもの"
d.rounded_rectangle([x0, 70 * SS, x0 + d.textlength(kick, font=f3) + 40 * SS, 116 * SS], radius=23 * SS, fill=(255, 255, 255, 46))
d.text((x0 + 20 * SS, 76 * SS), kick, font=f3, fill=(255, 255, 255))
# タイトル
ft = F(64)
d.text((x0, 130 * SS), "楽天の売れ筋", font=ft, fill=(255, 255, 255))
tx = x0 + d.textlength("楽天の売れ筋", font=ft) + 14 * SS
print("title", 0)
d.text((tx, 138 * SS), "＆", font=F(50), fill=(255, 230, 200))
tx += d.textlength("＆", font=F(50)) + 14 * SS
d.text((tx, 130 * SS), "ふるさと納税", font=ft, fill=(255, 255, 255))
# 2行の説明（ラベル付き）
fl, fd = F(26), F(29)
for i, (label, col, desc) in enumerate([("売れ筋", RED2, "1000円台・送料無料／値下がり／急上昇"),
                                         ("ふるさと納税", GREEN, "人気の返礼品をレビュー数順で")]):
    y = (238 + i * 54) * SS
    w = d.textlength(label, font=fl) + 32 * SS
    d.rounded_rectangle([x0, y, x0 + w, y + 42 * SS], radius=10 * SS, fill=(255, 255, 255))
    d.text((x0 + 16 * SS, y + 6 * SS), label, font=fl, fill=col)
    d.text((x0 + w + 16 * SS, y + 4 * SS), desc, font=fd, fill=(255, 245, 235))
# タグ
tx = x0
for t, col in [("毎日更新", RED2), ("買い回りの候補探しに", RED2), ("返礼品えらびに", GREEN), ("#PR", RED2)]:
    w = d.textlength(t, font=f3) + 40 * SS
    d.rounded_rectangle([tx, 370 * SS, tx + w, 416 * SS], radius=23 * SS, fill=(255, 255, 255))
    d.text((tx + 20 * SS, 376 * SS), t, font=f3, fill=col)
    tx += w + 14 * SS
print("right edge", tx / SS)
s = 3.4 * SS
d.ellipse([1245 * SS, 125 * SS, 1465 * SS, 345 * SS], fill=(255, 247, 230))
bear(d, 1355 * SS - 32 * s, 235 * SS - 31 * s, s)
hdr.resize((1500, 500), Image.LANCZOS).save(f"{OUT}/header_1500x500.png")
print("ok")
