"""YouTube ショート動画（縦1080x1920）を毎日作る.

- 商品画像のスライド＋ずんだもん（VOICEVOX）の読み上げ。ffmpeg で mp4 にする
- アップロードはユーザーが YouTube アプリで行う（API の自動アップロードは審査前は非公開に固定されるため）
- public/shorts.html に動画・タイトル・説明文をまとめる（検索除外）
VOICEVOX は GitHub Actions のサービスコンテナ（http://127.0.0.1:50021）で動かす。
"""
import datetime as dt
import html
import json
import re
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import wave
from pathlib import Path

from articles import short_name
from social import FONTS, fetch_image

VOICEVOX = "http://127.0.0.1:50021"
W, H = 1080, 1920
PER_DAY = 4
CREDIT = "VOICEVOX:ずんだもん"
e = html.escape

THEMES = {
    "red": ((165, 0, 0), (214, 0, 47), (255, 59, 92)),
    "green": ((6, 92, 56), (11, 122, 75), (43, 181, 124)),
}


# ---------- 音声 ----------

def voicevox_ready(timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(VOICEVOX + "/version", timeout=5):
                return True
        except Exception:  # noqa: BLE001
            time.sleep(3)
    return False


def zundamon_id():
    with urllib.request.urlopen(VOICEVOX + "/speakers", timeout=30) as r:
        for sp in json.load(r):
            if sp["name"] == "ずんだもん":
                for st in sp["styles"]:
                    if st["name"] == "ノーマル":
                        return st["id"]
    return 3


def synth(text, speaker, path):
    q = urllib.parse.urlencode({"text": text, "speaker": speaker})
    with urllib.request.urlopen(urllib.request.Request(f"{VOICEVOX}/audio_query?{q}", method="POST"), timeout=60) as r:
        query = json.load(r)
    query["speedScale"] = 1.15
    req = urllib.request.Request(f"{VOICEVOX}/synthesis?speaker={speaker}", data=json.dumps(query).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        path.write_bytes(r.read())
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def speakable(name, limit=22):
    """読み上げ用の短い商品名（記号や数字の羅列を減らす）."""
    n = short_name(name, 60)
    n = re.sub(r"[〜~／/|｜()（）\[\]【】]", " ", n)
    words, out = n.split(), ""
    for w_ in words:
        if len(out) + len(w_) > limit:
            break
        out += ("" if not out else " ") + w_
    return out or n[:limit]


# ---------- 画像 ----------

def font(size):
    from PIL import ImageFont
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def background(theme):
    from PIL import Image
    c1, c2, c3 = THEMES[theme]
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / H
        a, b, u = (c1, c2, t / 0.5) if t < 0.5 else (c2, c3, (t - 0.5) / 0.5)
        col = tuple(int(a[i] + (b[i] - a[i]) * u) for i in range(3))
        for x in range(W):
            px[x, y] = col
    return img


def wrap(draw, text, f, width, lines):
    if "\n" in text:  # 明示的な改行があれば、それぞれを折り返す
        out = []
        for part in text.split("\n"):
            out += wrap(draw, part, f, width, lines - len(out))
        return out[:lines]
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
    return out


def pr_badge(d):
    d.rounded_rectangle([40, 60, 170, 120], radius=14, fill=(255, 255, 255))
    d.text((105, 90), "PR", font=font(40), fill=(30, 30, 30), anchor="mm")


def title_slide(bg, title, sub, path):
    from PIL import ImageDraw
    img = bg.copy()
    d = ImageDraw.Draw(img)
    pr_badge(d)
    size = 110  # 改行指定した各行が1行に収まるまで文字を小さくする
    while size > 60 and any(d.textlength(t, font=font(size)) > W - 120 for t in title.split("\n")):
        size -= 6
    y = 560
    for line in wrap(d, title, font(size), W - 120, 3):
        d.text((W // 2, y), line, font=font(size), fill=(255, 255, 255), anchor="mm")
        y += int(size * 1.3)
    d.rounded_rectangle([W // 2 - 300, y + 30, W // 2 + 300, y + 130], radius=50, fill=(255, 255, 255))
    d.text((W // 2, y + 80), sub, font=font(52), fill=(30, 30, 30), anchor="mm")
    d.text((W // 2, y + 260), "3位から発表！", font=font(72), fill=(255, 240, 200), anchor="mm")
    img.save(path)


def item_slide(bg, rank, it, price_label, note, theme, path):
    """ショートは下部約400pxと右端にボタン・説明文が重なるため、情報は y=150〜1450・x<920 に収める."""
    from PIL import ImageDraw
    img = bg.copy()
    d = ImageDraw.Draw(img)
    pr_badge(d)
    medal = {1: (217, 164, 0), 2: (154, 165, 177), 3: (185, 114, 46)}[rank]
    d.rounded_rectangle([50, 150, W - 50, 1460], radius=44, fill=(255, 255, 255))
    pic = fetch_image(it.get("image"))
    if pic:
        scale = 700 / max(pic.width, pic.height)
        pic = pic.resize((int(pic.width * scale), int(pic.height * scale)))
        img.paste(pic, ((W - pic.width) // 2, 190 + (700 - pic.height) // 2))
    d.ellipse([80, 170, 260, 350], fill=medal)
    d.text((170, 250), f"{rank}", font=font(100), fill=(255, 255, 255), anchor="mm")
    d.text((170, 322), "位", font=font(36), fill=(255, 255, 255), anchor="mm")
    y = 920
    for line in wrap(d, short_name(it["name"], 60), font(54), 820, 3):
        d.text((90, y), line, font=font(54), fill=(29, 29, 31))
        y += 72
    accent = THEMES[theme][1]
    if price_label:
        d.text((90, 1150), price_label, font=font(44), fill=(110, 110, 115))
    d.text((90, 1200), f"{it['price']:,}円", font=font(130), fill=accent)
    if note:
        tw = min(d.textlength(note, font=font(48)), 780)
        d.rounded_rectangle([90, 1360, 90 + tw + 56, 1432], radius=18, fill=accent)
        d.text((118, 1370), note, font=font(48), fill=(255, 255, 255))
    img.save(path)


def end_slide(bg, line1, path):
    from PIL import ImageDraw
    img = bg.copy()
    d = ImageDraw.Draw(img)
    pr_badge(d)
    d.text((W // 2, 760), "くわしくは", font=font(90), fill=(255, 255, 255), anchor="mm")
    d.text((W // 2, 900), "プロフィールの", font=font(110), fill=(255, 255, 255), anchor="mm")
    d.text((W // 2, 1040), "リンクから！", font=font(110), fill=(255, 255, 255), anchor="mm")
    d.text((W // 2, 1250), line1, font=font(48), fill=(255, 240, 240), anchor="mm")
    d.text((W // 2, 1400), CREDIT, font=font(36), fill=(255, 235, 235), anchor="mm")
    img.save(path)


# ---------- 動画 ----------

def make_video(slides, out_path, work):
    """slides: [(画像パス, 音声パス, 秒)] を1本の mp4 にする."""
    segs = []
    for i, (img, wav, sec) in enumerate(slides):
        seg = work / f"seg{i}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(img), "-i", str(wav),
                        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "30",
                        "-c:a", "aac", "-ar", "44100", "-b:a", "128k", "-t", f"{sec + 0.35:.2f}",
                        "-af", "apad", str(seg)], check=True)
        segs.append(seg)
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{s.as_posix()}'\n" for s in segs), encoding="utf-8")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", "-movflags", "+faststart", str(out_path)], check=True)


def topics(cfg, results, budget, fcats, day):
    """その日の動画のテーマ（最大 PER_DAY 本）."""
    allg = [it for g in cfg["genres"] for it in results.get(g["slug"], [])]
    out = []
    cheaper = sorted((x for x in allg if x.get("price_diff", 0) < 0), key=lambda x: x["price_diff"])[:3]
    if len(cheaper) == 3:
        out.append(dict(theme="red", title="今日の楽天\n値下がりTOP3", tag="値下がり", label="楽天の価格",
                        items=[(it, f"前日より{-it['price_diff']:,}円安い") for it in cheaper],
                        intro="今日の楽天で、値下がりした商品トップ3を紹介するのだ！",
                        say=lambda it: f"{-it['price_diff']:,}円安くなって、{it['price']:,}円なのだ。"))
    risers = sorted((x for x in allg if isinstance(x.get("move"), int) and x["move"] >= 3), key=lambda x: -x["move"])[:3]
    if len(risers) == 3:
        out.append(dict(theme="red", title="今日の楽天\n急上昇TOP3", tag="急上昇", label="楽天の価格",
                        items=[(it, f"{it['move']}位アップ") for it in risers],
                        intro="今日の楽天で、ランキングが急上昇している商品トップ3なのだ！",
                        say=lambda it: f"昨日から{it['move']}位も上がって、{it['price']:,}円なのだ。"))
    if budget and len(budget) >= 3:
        out.append(dict(theme="red", title="1000円台・送料無料\n売れ筋TOP3", tag="1000円台", label="",
                        items=[(it, "送料無料") for it in budget[:3]],
                        intro="楽天で今売れている、1000円台で送料無料の商品トップ3なのだ！",
                        say=lambda it: f"送料無料で{it['price']:,}円なのだ。"))
    if fcats:
        k = dt.date.fromisoformat(day).toordinal() % len(fcats)
        c = fcats[k]
        if len(c["items"]) >= 3:
            out.append(dict(theme="green", title=f"ふるさと納税\n{c['title']}の人気TOP3", tag="ふるさと納税",
                            label="寄付額", items=[(it, it["shop"]) for it in c["items"][:3]],
                            intro=f"楽天ふるさと納税で、レビューが多い{c['title']}の返礼品トップ3なのだ！",
                            say=lambda it: f"{it['shop']}の返礼品で、寄付額は{it['price']:,}円なのだ。"))
    return out[:PER_DAY]


def description(t, day, site):
    m, d = int(day[5:7]), int(day[8:10])
    lines = [f"{t['title'].replace(chr(10), ' ')}（{m}月{d}日時点）", ""]
    for i, (it, note) in enumerate(t["items"]):
        price = f"寄付額{it['price']:,}円（{it['shop']}）" if t["theme"] == "green" else f"{it['price']:,}円"
        lines.append(f"{i + 1}位 {short_name(it['name'], 40)}｜{price}")
    lines += ["", "▶くわしくはプロフィールのリンクから", site, "",
              "※価格・寄付額は動画作成時点のものです。最新情報は販売ページでご確認ください。",
              "※楽天アフィリエイトを利用しています（PR）", CREDIT, "",
              f"#Shorts #PR #楽天 #{t['tag']}" + (" #楽天ふるさと納税" if t["theme"] == "green" else " #楽天市場")]
    return "\n".join(lines)


def build(cfg, results, budget, fcats, day, out_dir, log):
    if not voicevox_ready():
        log.append("[shorts] VOICEVOX に接続できないため動画作成をスキップ")
        return 0
    spk = zundamon_id()
    m, d = int(day[5:7]), int(day[8:10])
    site = cfg["base_url"].rstrip("/") + "/"
    made = []
    for n, t in enumerate(topics(cfg, results, budget, fcats, day)):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                bg = background(t["theme"])
                slides = []
                p, a = work / "s0.png", work / "s0.wav"
                title_slide(bg, t["title"], f"{m}月{d}日時点", p)
                slides.append((p, a, synth(t["intro"], spk, a)))
                for rank in (3, 2, 1):  # 3位から発表
                    it, note = t["items"][rank - 1]
                    p, a = work / f"s{rank}.png", work / f"s{rank}.wav"
                    item_slide(bg, rank, it, t["label"], note, t["theme"], p)
                    text = f"{'第' if rank > 1 else '堂々の第'}{rank}位は、{speakable(it['name'])}。{t['say'](it)}"
                    slides.append((p, a, synth(text, spk, a)))
                p, a = work / "s9.png", work / "s9.wav"
                end_slide(bg, "楽天ランキング速報" if t["theme"] == "red" else "ふるさと納税 人気返礼品ランキング", p)
                slides.append((p, a, synth("気になったら、プロフィールのリンクからチェックするのだ！", spk, a)))
                name = f"shorts/{day}-{n + 1}.mp4"
                make_video(slides, out_dir / name, work)
            made.append({"file": name, "title": f"{t['title'].replace(chr(10), ' ')}【{m}/{d}】#Shorts", "desc": description(t, day, site),
                         "sec": round(sum(s[2] + 0.35 for s in slides))})
            log.append(f"[shorts] {name} {made[-1]['sec']}秒 {t['title']}")
        except Exception as ex:  # noqa: BLE001
            log.append(f"[shorts] 失敗 {t['title']}: {ex}")
    page(made, day, out_dir)
    return len(made)


def page(made, day, out_dir):
    m, d = int(day[5:7]), int(day[8:10])
    cards = "".join(f"""<article class="c"><video src="{e(v['file'])}" controls playsinline preload="metadata"></video>
<a class="btn" href="{e(v['file'])}" download>① 動画を保存</a>
<p class="lb">タイトル</p><textarea readonly rows="2">{e(v['title'])}</textarea><button onclick="cp(this)">② タイトルをコピー</button>
<p class="lb">説明文</p><textarea readonly rows="8">{e(v['desc'])}</textarea><button onclick="cp(this)">③ 説明文をコピー</button>
<label><input type="checkbox" onchange="done({i},this.checked)"> アップロードした</label></article>""" for i, v in enumerate(made))
    html_text = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>ショート動画 {m}/{d}</title><style>
body{{margin:0;font-family:system-ui,"Hiragino Sans",sans-serif;background:#f6f4f0;color:#1d1d1f}}
header{{background:#c4302b;color:#fff;padding:14px 16px}}header h1{{font-size:1.1rem;margin:0}}header p{{margin:4px 0 0;font-size:.8rem}}
main{{padding:12px;max-width:520px;margin:0 auto}}.c{{background:#fff;border-radius:14px;padding:12px;margin-bottom:14px}}.c.ok{{opacity:.45}}
video{{width:100%;max-height:70vh;background:#000;border-radius:10px}}textarea{{width:100%;box-sizing:border-box;font-size:.8rem;border:1px solid #ddd;border-radius:8px}}
.btn,button{{display:block;width:100%;box-sizing:border-box;text-align:center;margin:6px 0;padding:11px;border:0;border-radius:10px;background:#c4302b;color:#fff;font-weight:700;font-size:.9rem;text-decoration:none}}
button{{background:#333}}.lb{{margin:10px 0 2px;font-size:.8rem;font-weight:700}}label{{display:block;margin-top:6px}}</style></head><body>
<header><h1>YouTube ショート（{m}月{d}日）</h1><p>①保存 → YouTubeアプリで「＋」→「ショート」→保存した動画を選ぶ → ②③を貼り付けて公開</p></header>
<main>{cards or '<p>今日の動画はありません。</p>'}</main>
<script>
const K='shorts-done-{day}';let s={{}};try{{s=JSON.parse(localStorage.getItem(K)||'{{}}')}}catch(e){{}}
function mark(){{document.querySelectorAll('.c').forEach((c,i)=>{{c.classList.toggle('ok',!!s[i]);c.querySelector('input').checked=!!s[i]}})}}
function done(i,v){{s[i]=v;try{{localStorage.setItem(K,JSON.stringify(s))}}catch(e){{}}mark()}}
async function cp(b){{const t=b.previousElementSibling;try{{await navigator.clipboard.writeText(t.value)}}catch(e){{t.select();document.execCommand('copy')}}b.textContent='コピーしました';}}
mark();</script></body></html>"""
    (out_dir / "shorts.html").write_text(html_text, encoding="utf-8")
