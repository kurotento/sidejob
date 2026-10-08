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


def bear(d, ox, oy, s):
    """案内役「らんくま」（64x64 座標系を倍率 s で描く）."""
    P = lambda x, y: (ox + x * s, oy + y * s)  # noqa: E731

    def circ(x, y, r, col):
        d.ellipse([*P(x - r, y - r), *P(x + r, y + r)], fill=col)

    d.polygon([P(20, 10), P(25, 16), P(32, 7), P(39, 16), P(44, 10), P(42, 20), P(22, 20)], fill=(242, 194, 48))
    for x, y in ((20, 9), (32, 6), (44, 9)):
        circ(x, y, 1.6, (242, 194, 48))
    circ(16, 24, 8, (168, 105, 58)); circ(48, 24, 8, (168, 105, 58))  # noqa: E702
    circ(16, 24, 4, (233, 184, 140)); circ(48, 24, 4, (233, 184, 140))  # noqa: E702
    circ(32, 38, 21, (185, 122, 69))
    d.ellipse([*P(22, 37), *P(42, 53)], fill=(241, 211, 179))
    circ(24, 35, 2.6, (43, 27, 16)); circ(40, 35, 2.6, (43, 27, 16))  # noqa: E702
    circ(24.9, 34.1, 0.9, (255, 255, 255)); circ(40.9, 34.1, 0.9, (255, 255, 255))  # noqa: E702
    d.ellipse([*P(28.6, 39.1), *P(35.4, 43.9)], fill=(43, 27, 16))
    d.arc([*P(28, 44.5), *P(36, 49)], 20, 160, fill=(43, 27, 16), width=max(2, int(1.6 * s)))
    circ(19, 42, 2.6, (240, 138, 138)); circ(45, 42, 2.6, (240, 138, 138))  # noqa: E702


def title_slide(bg, title, sub, path, seed=0):
    from PIL import ImageDraw
    img = bg.copy()
    d = ImageDraw.Draw(img)
    confetti(d, seed, (0, 120, W, 1500), 70)
    pr_badge(d)
    d.ellipse([W // 2 - 190, 230, W // 2 + 190, 610], fill=(255, 247, 230))
    bear(d, W // 2 - 32 * 4.6, 420 - 33 * 4.6, 4.6)
    size = 110  # 改行指定した各行が1行に収まるまで文字を小さくする
    while size > 60 and any(d.textlength(t, font=font(size)) > W - 120 for t in title.split("\n")):
        size -= 6
    y = 720
    for line in wrap(d, title, font(size), W - 120, 3):
        d.text((W // 2, y), line, font=font(size), fill=(255, 255, 255), anchor="mm", stroke_width=6,
               stroke_fill=(90, 0, 10))
        y += int(size * 1.3)
    d.rounded_rectangle([W // 2 - 300, y + 10, W // 2 + 300, y + 110], radius=50, fill=(255, 255, 255))
    d.text((W // 2, y + 60), sub, font=font(52), fill=(30, 30, 30), anchor="mm")
    d.text((W // 2, y + 220), "3位から発表！", font=font(80), fill=(255, 226, 90), anchor="mm", stroke_width=6,
           stroke_fill=(90, 0, 10))
    img.save(path)


def item_slide(bg, rank, it, price_label, note, theme, path, text=""):
    """上部に字幕、その下に商品カード。ショートの表示が重なる下部約400px・右端は避ける."""
    from PIL import ImageDraw
    img = bg.copy()
    d = ImageDraw.Draw(img)
    if rank == 1:
        confetti(d, rank * 7, (0, 300, W, 1500), 50)
    pr_badge(d)
    medal = {1: (217, 164, 0), 2: (154, 165, 177), 3: (185, 114, 46)}[rank]
    top = max(caption(d, text, 140, 54) + 20, 360) if text else 200
    d.rounded_rectangle([50, top, W - 50, 1470], radius=44, fill=(255, 255, 255))
    box = min(620, 1470 - top - 470)
    pic = fetch_image(it.get("image"))
    if pic:
        scale = box / max(pic.width, pic.height)
        pic = pic.resize((int(pic.width * scale), int(pic.height * scale)))
        img.paste(pic, ((W - pic.width) // 2, top + 30 + (box - pic.height) // 2))
    d.ellipse([70, top - 30, 250, top + 150], fill=medal, outline=(255, 255, 255), width=8)
    d.text((160, top + 50), f"{rank}", font=font(100), fill=(255, 255, 255), anchor="mm")
    d.text((160, top + 122), "位", font=font(36), fill=(255, 255, 255), anchor="mm")
    y = top + box + 50
    for line in wrap(d, short_name(it["name"], 60), font(50), 820, 2):
        d.text((90, y), line, font=font(50), fill=(29, 29, 31))
        y += 66
    accent = THEMES[theme][1]
    if price_label:
        d.text((90, 1225), price_label, font=font(40), fill=(110, 110, 115))
    d.text((90, 1260), f"{it['price']:,}円", font=font(120), fill=accent)
    if note:
        tw = min(d.textlength(note, font=font(44)), 760)
        d.rounded_rectangle([90 + 0, 1395, 90 + tw + 52, 1455], radius=16, fill=accent)
        d.text((116, 1400), note, font=font(44), fill=(255, 255, 255))
    img.save(path)


def end_slide(bg, line1, path):
    from PIL import ImageDraw
    img = bg.copy()
    d = ImageDraw.Draw(img)
    confetti(d, 99, (0, 120, W, 1500), 60)
    pr_badge(d)
    d.ellipse([W // 2 - 170, 260, W // 2 + 170, 600], fill=(255, 247, 230))
    bear(d, W // 2 - 32 * 4.2, 430 - 33 * 4.2, 4.2)
    for y, (t, s) in zip((760, 900, 1040), (("くわしくは", 90), ("プロフィールの", 110), ("リンクから！", 110))):
        d.text((W // 2, y), t, font=font(s), fill=(255, 255, 255), anchor="mm", stroke_width=6, stroke_fill=(90, 0, 10))
    d.text((W // 2, 1200), line1, font=font(48), fill=(255, 240, 240), anchor="mm")
    d.text((W // 2, 1400), CREDIT, font=font(36), fill=(255, 235, 235), anchor="mm")
    img.save(path)


# ---------- BGM（自作。外部音源の再配布規約を気にしなくてよいように毎回プログラムで作る） ----------

def make_bgm(seconds, path, seed=0):
    """明るいポップ調のループ（BPM120、I-V-vi-IV）を作って WAV に保存する."""
    import numpy as np
    sr, bpm = 44100, 120
    beat = 60 / bpm
    n = int(sr * (seconds + 1))
    t = np.arange(n) / sr
    out = np.zeros(n)
    keys = [0, 2, 5, 7]  # 日替わりで調を変える
    root = 261.63 * 2 ** (keys[seed % len(keys)] / 12)
    prog = [[0, 4, 7], [7, 11, 14], [9, 12, 16], [5, 9, 12]]  # C G Am F
    bar = beat * 4

    def tone(freq, start, dur, vol, shape="sine"):
        i0, i1 = int(start * sr), min(int((start + dur) * sr), n)
        if i0 >= n:
            return
        tt = t[i0:i1] - start
        env = np.exp(-tt * 6) * np.minimum(1, tt * 200)
        wave_ = np.sin(2 * np.pi * freq * tt)
        if shape == "pluck":
            wave_ = wave_ + 0.4 * np.sin(4 * np.pi * freq * tt)
        out[i0:i1] += vol * env * wave_

    k = 0
    while k * bar < seconds + 1:
        chord = prog[k % 4]
        s = k * bar
        for j in range(8):  # 8分音符のアルペジオ
            semi = chord[j % 3] + (12 if j % 4 == 3 else 0)
            tone(root * 2 ** (semi / 12), s + j * beat / 2, beat / 2, 0.16, "pluck")
        for j in range(4):  # ベース
            tone(root / 2 * 2 ** (chord[0] / 12), s + j * beat, beat * 0.9, 0.22)
        for j in range(4):  # キックとハイハット
            i0 = int((s + j * beat) * sr)
            if i0 < n:
                kk = np.arange(min(int(0.15 * sr), n - i0)) / sr
                out[i0:i0 + len(kk)] += 0.5 * np.sin(2 * np.pi * (110 - 400 * kk) * kk) * np.exp(-kk * 25)
            h0 = int((s + j * beat + beat / 2) * sr)
            if h0 < n:
                ln = min(int(0.04 * sr), n - h0)
                out[h0:h0 + ln] += 0.05 * np.random.default_rng(k * 4 + j).standard_normal(ln) * np.exp(-np.arange(ln) / sr * 80)
        k += 1
    fade = int(sr * 1.5)
    out[-fade:] *= np.linspace(1, 0, fade)
    out = out / max(np.abs(out).max(), 1e-6) * 0.8
    data = (out * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


# ---------- 字幕・演出 ----------

def caption(d, text, y0=150, size=56):
    """読み上げの字幕。白文字＋黒縁で、画面上部（YouTubeの表示と重ならない位置）に出す."""
    f = font(size)
    lines = wrap(d, text, f, W - 120, 3)
    y = y0
    for line in lines:
        d.text((W // 2, y), line, font=f, fill=(255, 255, 255), anchor="ma", stroke_width=8, stroke_fill=(20, 20, 20))
        y += int(size * 1.25)
    return y


def confetti(d, seed, area=(0, 0, W, H), count=60):
    import random
    rnd = random.Random(seed)
    cols = [(255, 214, 0), (255, 255, 255), (0, 200, 255), (255, 120, 180), (120, 230, 120)]
    for _ in range(count):
        x, y = rnd.randint(area[0], area[2]), rnd.randint(area[1], area[3])
        w_, h_ = rnd.randint(10, 22), rnd.randint(18, 34)
        c = rnd.choice(cols)
        if rnd.random() < 0.5:
            d.rectangle([x, y, x + w_, y + h_], fill=c)
        else:
            d.ellipse([x, y, x + w_, y + w_], fill=c)


def make_video(slides, out_path, work, seed=0):
    """slides: [(画像パス, 音声パス, 秒)]。ゆっくりズーム＋切り替え時のフラッシュ、BGM付きで mp4 にする."""
    segs = []
    for i, (img, wav, sec) in enumerate(slides):
        dur = sec + 0.35
        frames = int(dur * 30)
        seg = work / f"seg{i}.mp4"
        vf = (f"scale=1296:2304,zoompan=z='min(zoom+0.0008,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={frames}:s={W}x{H}:fps=30,fade=t=in:st=0:d=0.18:color=white,format=yuv420p")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(img), "-i", str(wav),
                        "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-r", "30",
                        "-c:a", "aac", "-ar", "44100", "-b:a", "128k", "-t", f"{dur:.2f}", "-af", "apad",
                        str(seg)], check=True)
        segs.append(seg)
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{s.as_posix()}'\n" for s in segs), encoding="utf-8")
    voice = work / "voice.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(voice)], check=True)
    total = sum(s[2] + 0.35 for s in slides)
    bgm = work / "bgm.wav"
    make_bgm(total, bgm, seed)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 声はそのまま、BGMは小さめに重ねる
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(voice), "-i", str(bgm),
                    "-filter_complex", "[1:a]volume=0.13[b];[0:a][b]amix=inputs=2:duration=first:normalize=0[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart", str(out_path)], check=True)


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


def video_title(t, m, d):
    """タイトルにもハッシュタグを入れる（検索・おすすめで見つけてもらうため。100文字以内）."""
    base = f"{t['title'].replace(chr(10), ' ')}【{m}/{d}】"
    tags = ["#Shorts", "#楽天"] + (["#ふるさと納税", "#楽天ふるさと納税"] if t["theme"] == "green"
                                   else ["#楽天市場", f"#{t['tag']}"])
    out = base
    for tg in tags:
        if len(out) + 1 + len(tg) <= 100:
            out += " " + tg
    return out


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
                title_slide(bg, t["title"], f"{m}月{d}日時点", p, seed=n)
                slides.append((p, a, synth(t["intro"], spk, a)))
                for rank in (3, 2, 1):  # 3位から発表
                    it, note = t["items"][rank - 1]
                    p, a = work / f"s{rank}.png", work / f"s{rank}.wav"
                    text = f"{'第' if rank > 1 else '堂々の第'}{rank}位は、{speakable(it['name'])}。{t['say'](it)}"
                    item_slide(bg, rank, it, t["label"], note, t["theme"], p, text=text)
                    slides.append((p, a, synth(text, spk, a)))
                p, a = work / "s9.png", work / "s9.wav"
                end_slide(bg, "楽天ランキング速報" if t["theme"] == "red" else "ふるさと納税 人気返礼品ランキング", p)
                slides.append((p, a, synth("気になったら、プロフィールのリンクからチェックするのだ！", spk, a)))
                name = f"shorts/{day}-{n + 1}.mp4"
                make_video(slides, out_dir / name, work, seed=dt.date.fromisoformat(day).toordinal() + n)
            made.append({"file": name, "title": video_title(t, m, d), "desc": description(t, day, site),
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
