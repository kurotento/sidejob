import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter
OUT = sys.argv[1]
SS = 2
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
W, H = 2560, 1440
img = grad(256, 144, RED1, RED2, RED3).resize((W * SS, H * SS), Image.BICUBIC)
d = ImageDraw.Draw(img, "RGBA")
for cx, cy, r in [(2200, 250, 360), (400, 1250, 380)]:
    d.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], outline=(255, 255, 255, 28), width=60 * SS)
F = lambda n: ImageFont.truetype(FONT_B, int(n * SS))
# 安全領域 1546x423（x 507-2053, y 508-931）に収める
cx0, cy0 = 680, 720
d.ellipse([(cx0 - 165) * SS, (cy0 - 165) * SS, (cx0 + 165) * SS, (cy0 + 165) * SS], fill=(255, 247, 230))
s = 4.3 * SS
bear(d, cx0 * SS - 32 * s, cy0 * SS - 31 * s, s)
x0 = 900 * SS
fk = F(34)
kick = "らんくま｜毎日ショート更新"
d.rounded_rectangle([x0, 532 * SS, x0 + d.textlength(kick, font=fk) + 44 * SS, 586 * SS], radius=27 * SS, fill=(255, 255, 255, 46))
d.text((x0 + 22 * SS, 539 * SS), kick, font=fk, fill=(255, 255, 255))
ft, fa = F(86), F(66)
d.text((x0, 600 * SS), "楽天の売れ筋", font=ft, fill=(255, 255, 255))
tx = x0 + d.textlength("楽天の売れ筋", font=ft) + 16 * SS
d.text((tx, 614 * SS), "＆", font=fa, fill=(255, 230, 200))
tx += d.textlength("＆", font=fa) + 16 * SS
d.text((tx, 600 * SS), "ふるさと納税", font=ft, fill=(255, 255, 255))
print("title right", tx / SS + d.textlength("ふるさと納税", font=ft) / SS)
fl, fd = F(32), F(36)
for i, (label, col, desc) in enumerate([("売れ筋", RED2, "1000円台・送料無料／値下がり／急上昇"),
                                         ("ふるさと納税", GREEN, "人気の返礼品をレビュー数順で")]):
    y = (734 + i * 66) * SS
    w = d.textlength(label, font=fl) + 36 * SS
    d.rounded_rectangle([x0, y, x0 + w, y + 52 * SS], radius=12 * SS, fill=(255, 255, 255))
    d.text((x0 + 18 * SS, y + 8 * SS), label, font=fl, fill=col)
    d.text((x0 + w + 20 * SS, y + 5 * SS), desc, font=fd, fill=(255, 245, 235))
tx = x0
for t, col in [("買い回りの候補探しに", RED2), ("返礼品えらびに", GREEN), ("#PR", RED2)]:
    w = d.textlength(t, font=fk) + 44 * SS
    d.rounded_rectangle([tx, 870 * SS, tx + w, 924 * SS], radius=27 * SS, fill=(255, 255, 255))
    d.text((tx + 22 * SS, 877 * SS), t, font=fk, fill=col)
    tx += w + 16 * SS
print("tags right", tx / SS)
img.resize((W, H), Image.LANCZOS).save(f"{OUT}/youtube_banner_2560x1440.png")
print("ok")
