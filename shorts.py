"""YouTube ショート動画（縦1080x1920）を毎日作る.

- 商品画像のスライド＋VOICEVOX の読み上げ。ffmpeg で mp4 にする
- 作り（見た目・構成・しゃべり方・声・BGM）は design.py の型で2週間ごとに丸ごと変わる。
  pop はこのファイルの anim_*、それ以外は reels.py
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

import design
from articles import short_name
from itemfilter import excluded, name_words, pick_varied, similar
from social import FONTS, fetch_image

VOICEVOX = "http://127.0.0.1:50021"
W, H = 1080, 1920
PER_DAY = 3  # テーマの枠・1000円台・ふるさと納税（YouTube の投稿枠 sns.YOUTUBE_TIMES と同じ数）
PAT = design.PATTERNS[0]  # build() でその日の型に差し替える
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


def credit():
    return f"VOICEVOX:{PAT['voice']['name']}"


def speaker_id(name, style="ノーマル"):
    """VOICEVOX の話者番号（見つからないときは None）."""
    with urllib.request.urlopen(VOICEVOX + "/speakers", timeout=30) as r:
        speakers = json.load(r)
    for sp in speakers:
        if sp["name"] == name:
            for st in sp["styles"]:
                if st["name"] == style:
                    return st["id"]
            return sp["styles"][0]["id"]
    return None


def synth(text, speaker, path):
    q = urllib.parse.urlencode({"text": text, "speaker": speaker})
    with urllib.request.urlopen(urllib.request.Request(f"{VOICEVOX}/audio_query?{q}", method="POST"), timeout=60) as r:
        query = json.load(r)
    query["speedScale"] = PAT["voice"]["speed"]
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
        if draw.textlength(cur + ch, font=f) > width and ch not in "、。！？!?）」ー":  # 句読点だけの行を作らない
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


def bear(d, ox, oy, s, mouth=0.0, blink=False):
    """案内役「らんくま」（64x64 座標系を倍率 s で描く）。mouth=口の開き(0〜1)、blink=目を閉じる."""
    P = lambda x, y: (ox + x * s, oy + y * s)  # noqa: E731
    dark = (43, 27, 16)

    def circ(x, y, r, col):
        d.ellipse([*P(x - r, y - r), *P(x + r, y + r)], fill=col)

    d.polygon([P(20, 10), P(25, 16), P(32, 7), P(39, 16), P(44, 10), P(42, 20), P(22, 20)], fill=(242, 194, 48))
    for x, y in ((20, 9), (32, 6), (44, 9)):
        circ(x, y, 1.6, (242, 194, 48))
    circ(16, 24, 8, (168, 105, 58)); circ(48, 24, 8, (168, 105, 58))  # noqa: E702
    circ(16, 24, 4, (233, 184, 140)); circ(48, 24, 4, (233, 184, 140))  # noqa: E702
    circ(32, 38, 21, (185, 122, 69))
    d.ellipse([*P(22, 37), *P(42, 53)], fill=(241, 211, 179))
    if blink:
        for x in (24, 40):
            d.arc([*P(x - 2.8, 33.5), *P(x + 2.8, 37.5)], 200, 340, fill=dark, width=max(2, int(1.4 * s)))
    else:
        circ(24, 35, 2.6, dark); circ(40, 35, 2.6, dark)  # noqa: E702
        circ(24.9, 34.1, 0.9, (255, 255, 255)); circ(40.9, 34.1, 0.9, (255, 255, 255))  # noqa: E702
    d.ellipse([*P(28.6, 39.1), *P(35.4, 43.9)], fill=dark)
    if mouth > 0.12:  # 口を開ける（声の大きさに合わせて縦に開く）
        h = 1.2 + 4.2 * mouth
        d.ellipse([*P(29, 45), *P(35, 45 + h)], fill=(120, 30, 40))
        d.ellipse([*P(30.2, 45 + h * 0.55), *P(33.8, 45 + h)], fill=(230, 110, 120))
    else:
        d.arc([*P(28, 44.5), *P(36, 49)], 20, 160, fill=dark, width=max(2, int(1.6 * s)))
    circ(19, 42, 2.6, (240, 138, 138)); circ(45, 42, 2.6, (240, 138, 138))  # noqa: E702


def title_slide(bg, title, sub, path, seed=0):
    from PIL import ImageDraw
    img = bg.copy()
    d = ImageDraw.Draw(img)
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
    pr_badge(d)
    medal = {1: (217, 164, 0), 2: (154, 165, 177), 3: (185, 114, 46)}[rank]
    top = max(caption(d, text, 140, 54) + 20, 360) if text else 200  # 上部に読み上げの字幕
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
    d.text((90, 1260), price_text(it), font=font(120), fill=accent)
    if note:
        tw = min(d.textlength(note, font=font(44)), 760)
        d.rounded_rectangle([90 + 0, 1395, 90 + tw + 52, 1455], radius=16, fill=accent)
        d.text((116, 1400), note, font=font(44), fill=(255, 255, 255))
    img.save(path)


def end_slide(bg, line1, path):
    from PIL import ImageDraw
    img = bg.copy()
    d = ImageDraw.Draw(img)
    pr_badge(d)
    d.ellipse([W // 2 - 170, 260, W // 2 + 170, 600], fill=(255, 247, 230))
    bear(d, W // 2 - 32 * 4.2, 430 - 33 * 4.2, 4.2)
    for y, (t, s) in zip((760, 900, 1040), (("くわしくは", 90), ("プロフィールの", 110), ("リンクから！", 110))):
        d.text((W // 2, y), t, font=font(s), fill=(255, 255, 255), anchor="mm", stroke_width=6, stroke_fill=(90, 0, 10))
    d.text((W // 2, 1200), line1, font=font(48), fill=(255, 240, 240), anchor="mm")
    d.text((W // 2, 1400), credit(), font=font(36), fill=(255, 235, 235), anchor="mm")
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

def caption(d, text, y0=150, size=56, cx=W // 2, width=W - 200):
    """読み上げの字幕。白文字＋黒縁で、画面上部（YouTubeの表示と重ならない位置）に出す."""
    f = font(size)
    lines = wrap(d, text, f, width, 3)
    y = y0
    for line in lines:
        d.text((cx, y), line, font=f, fill=(255, 255, 255), anchor="ma", stroke_width=8, stroke_fill=(20, 20, 20))
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


def confetti_frames(base_png, seconds, out_dir, seed=0, count=90):
    """静止画の上に、紙吹雪がひらひら降ってくるフレーム列（30fps）を作る."""
    import math
    import random
    from PIL import Image, ImageDraw
    rnd = random.Random(seed)
    cols = [(255, 214, 0), (255, 255, 255), (0, 200, 255), (255, 120, 180), (120, 230, 120)]
    parts = [dict(x=rnd.uniform(0, W), y=rnd.uniform(-H * 0.9, -20), v=rnd.uniform(500, 950),
                  sway=rnd.uniform(20, 60), ph=rnd.uniform(0, 6.3), w=rnd.randint(14, 26), h=rnd.randint(22, 40),
                  c=rnd.choice(cols), round=rnd.random() < 0.35) for _ in range(count)]
    base = Image.open(base_png).convert("RGB")
    frames = int(seconds * 30)
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in range(frames):
        t = f / 30
        img = base.copy()
        d = ImageDraw.Draw(img)
        for p in parts:
            y = p["y"] + p["v"] * t
            if y > H + 50:
                continue
            x = p["x"] + p["sway"] * math.sin(p["ph"] + t * 4)
            flip = abs(math.cos(p["ph"] + t * 6))  # くるくる回って見えるよう幅を変える
            w_ = max(3, int(p["w"] * flip))
            if p["round"]:
                d.ellipse([x, y, x + p["w"], y + p["w"]], fill=p["c"])
            else:
                d.rectangle([x, y, x + w_, y + p["h"]], fill=p["c"])
        img.save(out_dir / f"f{f:04d}.jpg", quality=88)
    return out_dir / "f%04d.jpg"


def make_video(slides, out_path, work, seed=0):
    """slides: [(画像パス, 音声パス, 秒)]。ゆっくりズーム＋切り替え時のフラッシュ、BGM付きで mp4 にする."""
    segs = []
    for i, (img, wav, sec, *opt) in enumerate(slides):
        dur = sec + 0.35
        frames = int(dur * 30)
        seg = work / f"seg{i}.mp4"
        if opt and opt[0]:  # 紙吹雪のアニメーション（ズームなし）
            pattern = confetti_frames(img, dur, work / f"fr{i}", seed + i)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "30", "-i", str(pattern), "-i", str(wav),
                            "-vf", "fade=t=in:st=0:d=0.18:color=white,format=yuv420p", "-c:v", "libx264",
                            "-preset", "veryfast", "-r", "30", "-c:a", "aac", "-ar", "44100", "-b:a", "128k",
                            "-t", f"{dur:.2f}", "-af", "apad", str(seg)], check=True)
            segs.append(seg)
            continue
        vf = (f"scale=1296:2304,zoompan=z='min(zoom+0.0005,1.05)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
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


# ---------- アニメーション（全スライドをフレームごとに描く） ----------

FPS = 30


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def bounce(x):
    """0→1 で、少し行き過ぎてから戻る（ポンッと弾む動き）."""
    x = min(max(x, 0.0), 1.0)
    return 1 + 2.70158 * (x - 1) ** 3 + 1.70158 * (x - 1) ** 2


def stripes_bg(theme):
    """斜めストライプ入りの背景（流れて見えるよう少し大きめに作り、毎フレームずらして切り出す）."""
    from PIL import ImageDraw
    big = background(theme).resize((W + 240, H + 240))
    d = ImageDraw.Draw(big, "RGBA")
    for k in range(-H, W + H, 120):
        d.polygon([(k, 0), (k + 60, 0), (k + 60 - H - 240, H + 240), (k - H - 240, H + 240)], fill=(255, 255, 255, 22))
    return big


def bg_at(big, t):
    off = int((t * 90) % 120)
    return big.crop((off, off, off + W, off + H))


def layer(size):
    from PIL import Image
    return Image.new("RGBA", size, (0, 0, 0, 0))


def paste_scaled(img, lay, cx, cy, s):
    if s <= 0.02:
        return
    w_, h_ = max(1, int(lay.width * s)), max(1, int(lay.height * s))
    img.paste(lay.resize((w_, h_)), (int(cx - w_ / 2), int(cy - h_ / 2)), lay.resize((w_, h_)))


def draw_confetti(d, parts, t):
    import math
    for p in parts:
        y = p["y"] + p["v"] * t
        if y > H + 50:
            continue
        x = p["x"] + p["sway"] * math.sin(p["ph"] + t * 4)
        w_ = max(3, int(p["w"] * abs(math.cos(p["ph"] + t * 6))))
        if p["round"]:
            d.ellipse([x, y, x + p["w"], y + p["w"]], fill=p["c"])
        else:
            d.rectangle([x, y, x + w_, y + p["h"]], fill=p["c"])


def confetti_parts(seed, count=90):
    import random
    rnd = random.Random(seed)
    cols = [(255, 214, 0), (255, 255, 255), (0, 200, 255), (255, 120, 180), (120, 230, 120)]
    return [dict(x=rnd.uniform(0, W), y=rnd.uniform(-H * 0.9, -20), v=rnd.uniform(500, 950),
                 sway=rnd.uniform(20, 60), ph=rnd.uniform(0, 6.3), w=rnd.randint(14, 26), h=rnd.randint(22, 40),
                 c=rnd.choice(cols), round=rnd.random() < 0.35) for _ in range(count)]


def mouth_curve(wav_path, seconds):
    """音声の大きさから、各フレームの口の開き(0〜1)を求める（口パク用）."""
    import numpy as np
    with wave.open(str(wav_path)) as w:
        sr = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float)
    step = sr / FPS
    vals = []
    for f in range(int(seconds * FPS)):
        seg = data[int(f * step):int((f + 1) * step)]
        vals.append(float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0)
    peak = max(max(vals), 1.0)
    return [min(1.0, v / peak * 1.4) for v in vals]


class Talker:
    """しゃべるらんくまのスプライト（口4段階×まばたき）を作っておき、フレームごとに選んで貼る."""

    def __init__(self, size, ring=True):
        from PIL import ImageDraw
        self.size = size
        self.sprites = {}
        for blink in (False, True):
            for lv in range(4):
                lay = layer((size, size))
                d = ImageDraw.Draw(lay)
                if ring:
                    d.ellipse([4, 4, size - 4, size - 4], fill=(255, 247, 230), outline=(255, 255, 255), width=8)
                s = size / 80
                bear(d, size / 2 - 32 * s, size / 2 - 31 * s, s, mouth=lv / 3, blink=blink)
                self.sprites[(blink, lv)] = lay

    def frame(self, t, mouth):
        import math
        blink = (t % 3.2) < 0.12  # 3秒ちょっとごとにまばたき
        lv = min(3, int(mouth * 3.99))
        bob = int(6 * math.sin(t * 9) * min(1, mouth * 3)) if mouth > 0.1 else 0  # 話しているときだけゆれる
        return self.sprites[(blink, lv)], bob


def sub_chunks(text):
    """字幕用に、読み上げを「、」「。」などで短く区切る（短すぎる区切りは次とつなぐ）."""
    parts = re.findall(r"[^、。！？!?]+[、。！？!?]*", text)
    out = []
    for p in parts:
        if out and len(out[-1]) < 8:
            out[-1] += p
        else:
            out.append(p)
    return out or [text]


def sub_at(chunks, t, dur):
    """経過時間 t に読んでいる区切り（文字数の割合で時間を配分する）."""
    speak = max(dur - 0.4, 0.1)
    total = sum(len(c) for c in chunks)
    acc = 0
    for c in chunks:
        acc += len(c)
        if t <= speak * acc / total:
            return c
    return chunks[-1]


def sub_lines(d, text, font_of, size, width=860):
    """字幕を2行以内に収める。句読点で切れるならそこで分ける（言葉の途中で改行しない）."""
    text = text.rstrip("、。")
    while size > 40 and d.textlength(text, font=font_of(size)) > width * 2:
        size -= 4
    f = font_of(size)
    lines = wrap(d, text, f, width, 2)
    if len(lines) == 2:
        cuts = [i + 1 for i, ch in enumerate(text[:-1]) if ch in "、。！？"]
        fit = [i for i in cuts if d.textlength(text[:i], font=f) <= width and d.textlength(text[i:], font=f) <= width]
        if fit:
            i = min(fit, key=lambda i: abs(i - len(text) / 2))
            lines = [text[:i], text[i:]]
    return f, lines


def draw_sub(d, text):
    """普通のショート動画と同じく、画面下側（YouTube のタイトル表示より上）に字幕を出す."""
    f, lines = sub_lines(d, text, font, 58)
    step = int(f.size * 1.3)
    y = 1600 - (len(lines) - 1) * step
    for line in lines:
        d.text((W // 2 - 30, y), line, font=f, fill=(255, 255, 255), anchor="mm", stroke_width=9, stroke_fill=(15, 15, 15))
        y += step


def anim_title(theme, title, sub, dur, out, seed, mouth=(), text="", hook="3位から発表！"):
    from PIL import ImageDraw
    chunks = sub_chunks(text) if text else []
    big = stripes_bg(theme)
    talker = Talker(400)
    text_l = layer((W, 560))
    td = ImageDraw.Draw(text_l)
    size = 110
    while size > 60 and any(td.textlength(x, font=font(size)) > W - 120 for x in title.split("\n")):
        size -= 6
    y = 70
    for line in wrap(td, title, font(size), W - 120, 3):
        td.text((W // 2, y), line, font=font(size), fill=(255, 255, 255), anchor="mm", stroke_width=7, stroke_fill=(90, 0, 10))
        y += int(size * 1.3)
    td.rounded_rectangle([W // 2 - 300, y + 10, W // 2 + 300, y + 110], radius=50, fill=(255, 255, 255))
    td.text((W // 2, y + 60), sub, font=font(52), fill=(30, 30, 30), anchor="mm")
    hook_y = 650 + y + 220
    parts = confetti_parts(seed)
    out.mkdir(parents=True, exist_ok=True)
    for f in range(int(dur * FPS)):
        t = f / FPS
        img = bg_at(big, t).convert("RGB")
        sprite, bob = talker.frame(t, mouth[f] if f < len(mouth) else 0)
        paste_scaled(img, sprite, W // 2, 420 + bob, bounce(t / 0.45))
        dy = int((1 - ease_out((t - 0.2) / 0.35)) * -300)
        if t > 0.2:
            img.paste(text_l, (0, 650 + dy), text_l)
        d = ImageDraw.Draw(img)
        if hook and t > 0.7 and int(t * 4) % 2 == 0:  # 「3位から発表！」を点滅
            d.text((W // 2, hook_y), hook, font=font(84), fill=(255, 226, 90), anchor="mm",
                   stroke_width=7, stroke_fill=(90, 0, 10))
        draw_confetti(d, parts, t)
        if chunks:
            draw_sub(d, sub_at(chunks, t, dur))
        pr_badge(d)
        img.save(out / f"f{f:04d}.jpg", quality=88)
    return [("whoosh", 0.0), ("pop", 0.25)]


def anim_hook(t, dur, out):
    """最初の1秒強：文字の表紙より先に、1位の商品の写真と値段を大きく出す（最初で飛ばされないように）."""
    from PIL import ImageDraw
    cd = t.get("order") == "countdown"  # 3位から明かす回（クイズ・VSなど）は答えを先に見せない
    it = t["items"][-1 if cd else 0][0]
    big = stripes_bg(t["theme"])
    pic = fetch_image(it.get("image"))
    accent = THEMES[t["theme"]][1]
    hook = t.get("hook") or ("この中でどれが1番？" if cd else None) or ("寄付額いくらで届く？" if t["theme"] == "green" else "いちばん売れてるのはコレ")
    out.mkdir(parents=True, exist_ok=True)
    for f in range(int(dur * FPS)):
        tt = f / FPS
        img = bg_at(big, tt).convert("RGB")
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([60, 330, W - 60, 1330], radius=50, fill=(255, 255, 255))
        if pic:
            box = 760 * (1.0 + 0.06 * tt / dur)  # ゆっくり寄る
            sc = box / max(pic.width, pic.height)
            p2 = pic.resize((int(pic.width * sc), int(pic.height * sc)))
            cx, cy = W // 2, 720
            img.paste(p2, (cx - p2.width // 2, cy - p2.height // 2))
            d = ImageDraw.Draw(img)
        d.text((W // 2, 200), hook, font=font(76), fill=(255, 255, 255), anchor="mm", stroke_width=8, stroke_fill=(60, 0, 10))
        d.rounded_rectangle([W // 2 - 330, 1180, W // 2 + 330, 1310], radius=30, fill=accent)
        d.text((W // 2, 1245), price_text(it), font=font(100), fill=(255, 255, 255), anchor="mm")
        pr_badge(d)
        img.save(out / f"f{f:04d}.jpg", quality=88)
    return [("pop", 0.0)]


def anim_item(theme, rank, it, price_label, note, text, dur, out, seed, mouth=(), label=None):
    from PIL import ImageDraw
    big = stripes_bg(theme)
    chunks = sub_chunks(text) if text else []
    top = 300  # 右上にしゃべるらんくま。字幕は画面下側に出す
    talker = Talker(250)
    # 商品カード（価格・バッジを除く）
    card_h = 1470 - top
    card = layer((W - 100, card_h))
    kd = ImageDraw.Draw(card)
    kd.rounded_rectangle([0, 0, W - 101, card_h - 1], radius=44, fill=(255, 255, 255))
    box = min(620, card_h - 470)
    pic = fetch_image(it.get("image"))
    if pic:
        scale = box / max(pic.width, pic.height)
        pic = pic.resize((int(pic.width * scale), int(pic.height * scale)))
        card.paste(pic, ((W - 100 - pic.width) // 2, 30 + (box - pic.height) // 2))
    y = box + 50
    for line in wrap(kd, short_name(it["name"], 60), font(50), 820, 2):
        kd.text((40, y), line, font=font(50), fill=(29, 29, 31))
        y += 66
    accent = THEMES[theme][1]
    if price_label:
        kd.text((40, 1172 - top), price_label, font=font(40), fill=(110, 110, 115))
    if note:
        tw = min(kd.textlength(note, font=font(44)), 760)
        kd.rounded_rectangle([40, 1395 - top, 40 + tw + 52, 1455 - top], radius=16, fill=accent)
        kd.text((66, 1400 - top), note, font=font(44), fill=(255, 255, 255))
    medal = {1: (217, 164, 0), 2: (154, 165, 177), 3: (185, 114, 46)}[rank]
    badge = layer((200, 200))
    bdg = ImageDraw.Draw(badge)
    bdg.ellipse([4, 4, 196, 196], fill=medal, outline=(255, 255, 255), width=9)
    if label:  # VS・謎解きなど、順位ではない見出し（2行まで）
        lines = label.split("\n")[:2]
        for k, ln in enumerate(lines):
            bdg.text((100, 100 + (k * 2 - (len(lines) - 1)) * 26), ln, font=font(44 if len(ln) <= 4 else 34), fill=(255, 255, 255), anchor="mm")
    else:
        bdg.text((100, 88), f"{rank}", font=font(104), fill=(255, 255, 255), anchor="mm")
        bdg.text((100, 160), "位", font=font(38), fill=(255, 255, 255), anchor="mm")
    price_l = layer((900, 170))
    pd = ImageDraw.Draw(price_l)
    pd.text((0, 10), price_text(it), font=font(120), fill=accent)
    parts = confetti_parts(seed) if rank == 1 else []
    out.mkdir(parents=True, exist_ok=True)
    for f in range(int(dur * FPS)):
        t = f / FPS
        img = bg_at(big, t).convert("RGB")
        dx = int((1 - ease_out(t / 0.35)) * W)  # 右からスライドイン
        img.paste(card, (50 + dx, top), card)
        if t > 0.6:  # 価格がドンッと出る
            s = 1 + 0.6 * (1 - ease_out((t - 0.6) / 0.25))
            paste_scaled(img, price_l, 90 + 450 * s, 1300, s)
        paste_scaled(img, badge, 160, top + 60, bounce((t - 0.3) / 0.35))
        sprite, bob = talker.frame(t, mouth[f] if f < len(mouth) else 0)
        img.paste(sprite, (W - 290, 150 + bob), sprite)
        d = ImageDraw.Draw(img)
        if parts:
            draw_confetti(d, parts, t)
        if chunks:
            draw_sub(d, sub_at(chunks, t, dur))
        pr_badge(d)
        img.save(out / f"f{f:04d}.jpg", quality=88)
    events = [("whoosh", 0.0), ("pop", 0.35), ("pop", 0.62)]
    if rank == 1:
        events.append(("fanfare", 0.3))
    return events


def anim_end(theme, line1, dur, out, mouth=(), text=""):
    import math
    from PIL import ImageDraw
    chunks = sub_chunks(text) if text else []
    big = stripes_bg(theme)
    talker = Talker(360)
    out.mkdir(parents=True, exist_ok=True)
    for f in range(int(dur * FPS)):
        t = f / FPS
        img = bg_at(big, t).convert("RGB")
        sprite, bob = talker.frame(t, mouth[f] if f < len(mouth) else 0)
        paste_scaled(img, sprite.rotate(5 * math.sin(t * 5)), W // 2, 430 + bob, bounce(t / 0.4))
        d = ImageDraw.Draw(img)
        s = 1 + 0.05 * math.sin(t * 8)  # 文字が脈打つ
        for y, (txt, sz) in zip((760, 900, 1040), (("楽天ROOMで", 90), ("「らんくま」と", 110), ("検索！", 110))):
            d.text((W // 2, y), txt, font=font(int(sz * s)), fill=(255, 255, 255), anchor="mm", stroke_width=7,
                   stroke_fill=(90, 0, 10))
        d.text((W // 2, 1200), line1, font=font(48), fill=(255, 240, 240), anchor="mm")
        d.text((W // 2, 1400), credit(), font=font(36), fill=(255, 235, 235), anchor="mm")
        if chunks:
            draw_sub(d, sub_at(chunks, t, dur))
        pr_badge(d)
        img.save(out / f"f{f:04d}.jpg", quality=88)
    return [("whoosh", 0.0), ("pop", 0.2)]


def make_sfx(events, seconds, path):
    """効果音（すべて自作）：whoosh＝切り替え、pop＝登場、fanfare＝1位."""
    import numpy as np
    sr = 44100
    n = int(sr * (seconds + 1))
    out = np.zeros(n)
    rng = np.random.default_rng(1)
    for kind, at in events:
        i0 = int(at * sr)
        if i0 >= n:
            continue
        if kind == "whoosh":
            ln = int(0.35 * sr)
            tt = np.arange(ln) / sr
            noise = rng.standard_normal(ln)
            sweep = np.convolve(noise, np.ones(8) / 8, mode="same")
            snd = 0.35 * sweep * np.sin(np.pi * tt / 0.35)
        elif kind == "pop":
            ln = int(0.12 * sr)
            tt = np.arange(ln) / sr
            snd = 0.5 * np.sin(2 * np.pi * (900 - 3000 * tt) * tt) * np.exp(-tt * 40)
        elif kind == "ding":  # 順位が埋まる「チーン」
            ln = int(0.6 * sr)
            tt = np.arange(ln) / sr
            snd = 0.3 * (np.sin(2 * np.pi * 1318.5 * tt) + 0.5 * np.sin(2 * np.pi * 2637 * tt)) * np.exp(-tt * 6)
        elif kind == "jan":  # 「ジャン！」
            ln = int(0.5 * sr)
            tt = np.arange(ln) / sr
            snd = sum(0.16 * np.sign(np.sin(2 * np.pi * f0 * tt)) for f0 in (261.6, 329.6, 392.0)) * np.exp(-tt * 5)
        elif kind == "page":  # 紙をめくる音
            ln = int(0.4 * sr)
            tt = np.arange(ln) / sr
            noise = np.convolve(rng.standard_normal(ln), np.ones(20) / 20, mode="same")
            snd = 0.5 * noise * np.sin(np.pi * tt / 0.4) ** 2
        else:  # fanfare
            ln = int(1.0 * sr)
            tt = np.arange(ln) / sr
            snd = sum(0.18 * np.sin(2 * np.pi * f0 * tt) for f0 in (523.25, 659.25, 783.99, 1046.5))
            snd = snd * np.minimum(1, tt * 30) * np.exp(-tt * 2.5)
        ln = min(len(snd), n - i0)
        out[i0:i0 + ln] += snd[:ln]
    out = np.clip(out, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((out * 32767).astype(np.int16).tobytes())


def make_video_anim(slides, out_path, work, seed=0):
    """slides: [(フレームのフォルダ, 音声パス, 秒, 効果音イベント)] を BGM・効果音付きの mp4 にする."""
    segs, events, t0 = [], [], 0.0
    for i, (frames, wav, dur, ev) in enumerate(slides):
        seg = work / f"seg{i}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(frames / "f%04d.jpg"),
                        "-i", str(wav), "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(FPS),
                        "-c:a", "aac", "-ar", "44100", "-b:a", "128k", "-t", f"{dur:.2f}", "-af", "apad", str(seg)],
                       check=True)
        segs.append(seg)
        events += [(k, t0 + at) for k, at in ev]
        t0 += dur
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{s.as_posix()}'\n" for s in segs), encoding="utf-8")
    voice = work / "voice.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(voice)], check=True)
    bgm, sfx = work / "bgm.wav", work / "sfx.wav"
    if PAT["video"] == "pop":
        make_bgm(t0, bgm, seed)
    else:
        import reels
        reels.bgm(PAT["video"], t0, bgm, seed)
    make_sfx(events, t0, sfx)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(voice), "-i", str(bgm), "-i", str(sfx),
                    "-filter_complex", "[1:a]volume=0.13[b];[2:a]volume=0.55[s];[0:a][b][s]amix=inputs=3:duration=first:normalize=0[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart", str(out_path)], check=True)


# ---------- 読み上げ用の商品名（g を「ジー」と読むなどの誤読を防ぐ） ----------

SPOKEN_CACHE = Path(__file__).resolve().parent / "data" / "spoken.json"
UNITS = [  # 長いものから順に置き換える
    (r"(\d)\s*kg", r"\1キログラム"), (r"(\d)\s*mg", r"\1ミリグラム"), (r"(\d)\s*g\b", r"\1グラム"),
    (r"(\d)\s*[mM][lL]", r"\1ミリリットル"), (r"(\d)\s*[lL]\b", r"\1リットル"), (r"(\d)\s*cm", r"\1センチ"),
    (r"(\d)\s*mm", r"\1ミリ"), (r"(\d)\s*m\b", r"\1メートル"), (r"(\d)\s*%", r"\1パーセント"),
    (r"[PＰ](\d+)倍", r"ポイント\1倍"), (r"(\d+)\s*[×xX＊*]\s*(\d+)\s*本", r"\1の\2本入り"),
    (r"(\d+)\s*[×xX＊*]\s*(\d+)", r"\1かける\2"), (r"(\d)\s*W\b", r"\1ワット"), (r"(\d)\s*V\b", r"\1ボルト"),
]

SPOKEN_PROMPT = """あなたは日本語の音声合成（読み上げ）用の原稿を作る係です。
楽天市場の商品名を、音声合成が自然に読み上げられる短い商品名に書き直してください。

ルール:
- 何の商品かがわかる最小限にする（15〜25文字程度）。宣伝文句・型番・色やサイズの羅列は省く
- 単位は読みをカタカナで書く（g→グラム、kg→キログラム、ml→ミリリットル、L→リットル、cm→センチ、%→パーセント）
- 英字のブランド名・商品名はカタカナの読みにする（例：Anker→アンカー、WILKINSON→ウィルキンソン）。読みがわからない英字は省く
- 「×」「/」「|」「【】」「()」などの記号は使わない。「500ml×24本」は「500ミリリットル24本入り」のように書く
- 数字は算用数字のままでよい
- 漢字の読みが難しい固有名詞（地名・品種など）や、美容・商品の造語（例：水光→すいこう）はひらがなにする
- 出力は書き直した商品名だけ（説明や引用符は付けない）"""


# 音声合成が読み間違える言葉（見つけたら足していく）
READINGS = {"水光": "すいこう", "市田柿": "いちだがき", "干し柿": "ほしがき", "干柿": "ほしがき", "訳あり": "わけあり",
            "訳有り": "わけあり", "詰替": "つめかえ", "1day": "ワンデー", "1DAY": "ワンデー", "ワンデイ": "ワンデー"}


def normalize_reading(text):
    """単位・記号を読み上げ向けに置き換える（Gemini が使えないときの予備にもなる）."""
    for word, kana in READINGS.items():
        text = text.replace(word, kana)
    for pat, rep in UNITS:
        text = re.sub(pat, rep, text)
    text = re.sub(r"\s*[×xX＊*]\s*(\d+)\s*(本|個|袋|枚|缶|パック|食|箱)", r" \1\2入り", text)
    text = re.sub(r"[／/|｜()（）\[\]【】〈〉<>「」『』～〜~×＊*]", " ", text)
    text = re.sub(r"\b[A-Za-z][A-Za-z0-9.-]*\b", " ", text)  # 英字はアルファベット読みになるので外す
    return re.sub(r"\s+", " ", text).strip()


def ask_gemini_reading(name):
    import os
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    from writer import ENDPOINT, MODELS
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": SPOKEN_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": name}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 200},
    }).encode()
    for model in MODELS:
        try:
            req = urllib.request.Request(ENDPOINT.format(model=model), data=body,
                                         headers={"Content-Type": "application/json", "x-goog-api-key": key})
            with urllib.request.urlopen(req, timeout=60) as r:
                parts = json.load(r)["candidates"][0]["content"]["parts"]
            out = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip().strip("「」\"'")
            out = out.splitlines()[0].strip() if out else ""
            if 4 <= len(out) <= 40 and not re.search(r"[A-Za-z]{2,}", out):  # 英字が残っていれば不採用
                return out
            return None
        except Exception:  # noqa: BLE001
            continue
    return None


def spoken_name(it, cache):
    """読み上げ用の商品名。作ったものは data/spoken.json に保存して使い回す."""
    code = it["code"]
    if code not in cache:
        got = ask_gemini_reading(short_name(it["name"], 80))
        if got:
            cache[code] = normalize_reading(got)
    return normalize_reading(cache.get(code) or speakable(it["name"]))  # 保存済みの読みにも辞書を当てる


SEARCH = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
_fresh = {}


def latest(it, base_url):
    """動画を作る直前に、商品の最新の値段と在庫を楽天の商品検索で確かめる.

    サイズ・色で値段が変わる商品は「買える種類のうちいちばん安い値段〜」にする。
    返り値は値段を差し替えた商品（買えない・見つからないときは None）。確かめられないときは元のまま。
    """
    import os
    if not os.environ.get("RAKUTEN_APP_ID"):
        return it
    code = it["code"]
    if code not in _fresh:
        params = {"applicationId": os.environ["RAKUTEN_APP_ID"], "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
                  "itemCode": code, "formatVersion": 2}
        req = urllib.request.Request(SEARCH + "?" + urllib.parse.urlencode(params), headers={
            "Referer": base_url.rstrip("/") + "/", "User-Agent": "rakuten-ranking-site/1.0",
            "Origin": urllib.parse.urlsplit(base_url)._replace(path="").geturl()})
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                found = json.load(res).get("Items", [])
            time.sleep(1)  # API の毎秒の上限を避ける
        except Exception:  # noqa: BLE001
            _fresh[code] = it
            return it
        raw = found[0].get("Item", found[0]) if found else None
        if not raw or str(raw.get("availability", "1")) != "1":
            _fresh[code] = None
        else:
            lo = int(raw.get("itemPriceMin3") or raw.get("itemPrice") or it["price"])
            hi = int(raw.get("itemPriceMax3") or lo)
            prev = it["price"] - it.get("price_diff", 0)  # 前日の値段
            _fresh[code] = {**it, "price": lo, "from": hi > lo, "price_diff": lo - prev if "price_diff" in it else 0}
    return _fresh[code]


def price_text(it):
    return f"{it['price']:,}円" + ("〜" if it.get("from") else "")


def price_say(it):
    return f"{it['price']:,}円" + ("から" if it.get("from") else "")


def pick3(cands, base_url, ok=lambda it: True):
    """候補の上から、最新の値段で条件に合う商品を3つ選ぶ.

    売り切れ・見つからないものと、ROOM と同じ判定（itemfilter）で出さない商品・すでに選んだ物と似た商品は飛ばす。
    """
    out = []
    for it in cands:
        if excluded(it) or any(similar(it, o) for o in out):
            continue
        f = latest(it, base_url)
        if f and ok(f):
            out.append(f)
            if len(out) == 3:
                break
    return out


# ---------- 毎日変わるテーマの枠（2026-11-01〜。それまでの「急上昇」「値下がり」の枠と入れ替え） ----------
# 楽天を使うかどうかに関係なく「その商品が気になる人」に届くテーマにする。kind ごとに話の運び方（構成）が違う。
# - search : words を楽天の商品検索（レビューの多い順）で探し、名前の最初のほうが must に合う商品を3位から紹介
# - vs     : 同じ種類の安い・ふつう・高いを比べる（VSバトル）
# - mystery: 急上昇している商品の「なんで売れてる？」を説明文から読み取って答え合わせ（謎解き）
# - check  : 買う前に見るポイント3つと、それに合う商品（選び方チェック）
# - quiz   : ふるさと納税「1万円で何kg届く？」
# - best   : その週にいちばん見られたテーマをもう一度（分からないときは THEMES_EXTRA を週ごとに）
# lead・tags は Instagram の1行目とタグ。
OSHI = dict(key="oshikatsu", kind="search", tag="推し活", title="推し活グッズ\n人気TOP3", what="楽天でレビューが多い推し活グッズ",
            words=["推し活 グッズ", "アクスタ ケース", "痛バッグ", "ペンライト ケース"], must=r"推し|アクスタ|痛バ|ペンライト|缶バッジ|うちわ",
            ng=r"医療|瞳孔|看護|ナース|診察", lead="推し活グッズ おすすめ｜レビューの多い人気どころ", tags="#推し活 #推し活グッズ #痛バ #楽天購入品 #PR")
NEKO = dict(key="neko", kind="search", tag="猫", title="猫グッズ\n人気TOP3", what="楽天でレビューが多い猫グッズ",
            words=["猫 ベッド", "猫 おもちゃ", "猫 爪とぎ"], must=r"猫|ねこ|ネコ|キャット",
            lead="猫グッズ おすすめ｜猫飼いさんに人気のもの", tags="#猫 #猫グッズ #猫のいる暮らし #楽天購入品 #PR")
INU = dict(key="inu", kind="search", tag="犬", title="犬グッズ\n人気TOP3", what="楽天でレビューが多い犬グッズ",
           words=["犬 ベッド", "犬 服", "犬 おやつ"], must=r"犬|いぬ|ドッグ|わんちゃん|ペット",
           lead="犬グッズ おすすめ｜わんちゃんに人気のもの", tags="#犬 #犬グッズ #犬のいる暮らし #楽天購入品 #PR")
THEMES_EXTRA = [  # 日曜に「よく見られたテーマ」が分からないとき、週ごとに順に使う
    dict(key="setsuden", kind="search", tag="節約", title="冬の電気代を下げる\nグッズTOP3", what="冬の電気代を下げたい人に人気のグッズ",
         words=["着る毛布", "電気毛布", "断熱シート 窓", "湯たんぽ"], must=r"毛布|断熱|湯たんぽ|ブランケット", ng=r"バッテリー",
         lead="冬の電気代 節約グッズ｜レビューの多い人気どころ", tags="#節約 #電気代節約 #冬支度 #楽天購入品 #PR"),
    dict(key="hitori", kind="search", tag="一人暮らし", title="一人暮らしの\n便利グッズTOP3", what="一人暮らしの人に人気の便利グッズ",
         words=["一人暮らし 便利グッズ", "一人用 鍋", "炊飯器 1合"], must=r"一人|1人|ひとり|ミニ|コンパクト|1合|一人用",
         ng=r"の素|グルメ|食品|お取り寄せ", lead="一人暮らし 便利グッズ｜レビューの多い人気どころ",
         tags="#一人暮らし #一人暮らしグッズ #新生活 #楽天購入品 #PR"),
    dict(key="attaka", kind="search", tag="あったかグッズ", title="冬のあったか\nグッズTOP3", what="冬に人気のあったかグッズ",
         words=["ルームシューズ あったか", "ネックウォーマー", "レッグウォーマー"], must=r"あったか|暖|ウォーマー|ボア|裏起毛|もこもこ|ルームシューズ",
         lead="冬のあったかグッズ｜レビューの多い人気どころ", tags="#あったかグッズ #冬支度 #寒さ対策 #楽天購入品 #PR"),
]
# 季節の枠：クリスマス前は、毎日同じ型だった「1000円台 売れ筋TOP3」の枠をクリスマスの商品に替える（日替わりで順に）
XMAS_SEASON = ("11-14", "12-24")
XMAS = [
    dict(key="xmas-coffret", kind="search", anywhere=True, tag="クリスマスコフレ", title="クリスマスコフレ\n人気TOP3", what="楽天でレビューが多いクリスマスコフレ",
         words=["クリスマスコフレ", "ホリデーコフレ", "クリスマス コスメ セット"], must=r"コフレ|ホリデー.{0,6}(セット|キット|コレクション)",
         ng=r"福袋|サンプル|空箱|ラッピング袋のみ|メンズ", lead="クリスマスコフレ 2026｜レビューの多い人気どころ",
         tags="#クリスマスコフレ #ホリデーコフレ #コスメ #楽天購入品 #PR"),
    dict(key="xmas-gift-her", kind="search", anywhere=True, tag="クリスマスプレゼント", title="女性へのクリスマス\nプレゼントTOP3", what="クリスマスプレゼントで人気の女性向けギフト",
         words=["クリスマスプレゼント 女性", "クリスマス ギフト レディース", "クリスマスプレゼント 彼女"], must=r"クリスマス|ギフト|プレゼント",
         ng=r"子供|キッズ|ベビー|メンズ|男性|食品|スイーツ|お菓子|花束", lead="クリスマスプレゼント 女性向け｜レビューの多い人気どころ",
         tags="#クリスマスプレゼント #プレゼント #ギフト #楽天購入品 #PR"),
    dict(key="xmas-gift-him", kind="search", anywhere=True, tag="クリスマスプレゼント", title="男性へのクリスマス\nプレゼントTOP3", what="クリスマスプレゼントで人気の男性向けギフト",
         words=["クリスマスプレゼント 男性", "クリスマスプレゼント 彼氏", "クリスマス ギフト メンズ"], must=r"クリスマス|ギフト|プレゼント|メンズ",
         ng=r"子供|キッズ|ベビー|レディース|女性|食品|スイーツ|お菓子|花束", lead="クリスマスプレゼント 男性向け｜レビューの多い人気どころ",
         tags="#クリスマスプレゼント #彼氏へのプレゼント #ギフト #楽天購入品 #PR"),
    dict(key="xmas-deco", kind="search", anywhere=True, tag="クリスマス", title="クリスマスの\n飾りつけTOP3", what="楽天でレビューが多いクリスマスの飾り",
         words=["クリスマスツリー", "クリスマス 飾り", "クリスマス イルミネーション 室内"], must=r"クリスマス|ツリー|イルミネーション|リース", ng=r"花束|ブーケ|収納|バッグ|ケーキ|食品",
         lead="クリスマスの飾りつけ｜レビューの多い人気どころ", tags="#クリスマス #クリスマスツリー #クリスマス飾り #楽天購入品 #PR"),
    dict(key="xmas-kids", kind="search", ranking=566382, rank_name="おもちゃ", tag="クリスマスプレゼント",
         title="子どもへのクリスマス\nおもちゃ人気TOP3", what="楽天のおもちゃランキングで、いま売れているおもちゃ",
         words=[], must=r".", ng=r"トレカ|トレーディングカード|カードゲーム|BOX|ボックス|パック|拡張|福袋|景品|大量|縁日|アダルト|大人用",
         lead="子どものクリスマスプレゼント｜楽天のおもちゃランキングから", tags="#クリスマスプレゼント #おもちゃ #子どものいる暮らし #楽天購入品 #PR"),
]


def xmas_theme(day):
    """クリスマス前の日なら、その日のクリスマスの枠のテーマ（日替わり）。それ以外は None."""
    md = day[5:]
    if not (XMAS_SEASON[0] <= md <= XMAS_SEASON[1]):
        return None
    return XMAS[dt.date.fromisoformat(day).toordinal() % len(XMAS)]


WEEKLY = [
    OSHI,                                   # 月：推し活（カウントダウン）
    dict(key="vs", kind="vs"),              # 火：VSバトル
    dict(key="nazo", kind="mystery"),       # 水：謎解き
    dict(key="pet", kind="pet"),            # 木：猫と犬を週ごとに交互
    dict(key="furusato-qty", kind="quiz"),  # 金：ふるさと納税クイズ（ジャンルは週ごとに替える）
    dict(key="check", kind="check"),        # 土：選び方チェック
    dict(key="best", kind="best"),          # 日：その週いちばん見られたテーマをもう一度
]
# VSバトルで比べる物（週ごとに順に）。(名前, 名前の最初のほうに入っているべき言葉)
VS_CATS = [("加湿器", r"加湿器"), ("ドライヤー", r"ドライヤー"), ("電気毛布", r"電気毛布|電気ブランケット"), ("枕", r"枕|まくら|ピロー"),
           ("ワイヤレスイヤホン", r"イヤホン"), ("電気ケトル", r"ケトル"), ("フライパン", r"フライパン"), ("掃除機", r"掃除機|クリーナー")]
VS_TIERS = [(3, "安い", 1000, 3999), (2, "ふつう", 4000, 8999), (1, "高い", 9000, 40000)]  # (順, 見出し, 下限, 上限)
# 選び方チェック（週ごとに順に）。ポイントは (読み上げる文, 商品名に入っていれば合うとみなす言葉)
CHECK_CATS = [
    ("加湿器", r"加湿器", [("お手入れが楽な、上から水を入れられるもの", r"上部給水|上から給水"),
                           ("寝室に置くなら、音が静かなもの", r"静音"), ("部屋の広さに合う、加湿できる畳数を見ること", r"\d+畳")]),
    ("電気毛布", r"電気毛布|電気ブランケット", [("丸ごと洗えるもの", r"洗える|丸洗い"), ("つけっぱなしが心配なら、タイマー付き", r"タイマー"),
                                               ("敷いても掛けても使えるもの", r"掛け敷き|掛敷|掛け・敷き")]),
    ("着る毛布", r"着る毛布|着るブランケット", [("足元まで隠れる、長めの丈", r"ロング|足元まで|足まで"), ("洗濯機で洗えるもの", r"洗える|洗濯機"),
                                               ("袖があって、手が動かしやすいもの", r"袖")]),
    ("ドライヤー", r"ドライヤー", [("髪が早く乾く、大風量のもの", r"大風量|速乾"), ("軽くて、腕が疲れにくいもの", r"軽量|軽い"),
                                   ("髪をまとめたいなら、イオン付き", r"イオン")]),
]
THEME_HISTORY = Path(__file__).resolve().parent / "data" / "theme_history.json"  # テーマの枠で出した商品（4週間は出さない）
POINTS = Path(__file__).resolve().parent / "data" / "points.json"  # Gemini で作った商品の特徴・売れている理由（作り直さない）
QTY_CATS = ("meat", "seafood", "rice", "fruit")  # 量で比べられるふるさと納税のジャンル
CHANNEL_SHORTS = "https://www.youtube.com/@rankumasidejob/shorts"

POINT_PROMPT = """あなたは楽天の商品を短い動画で紹介する係です。商品名と説明文を読んで、{purpose}を、読み上げ用の話し言葉で1文にしてください。
ルール：
- 20〜35文字。文末は「〜ところ」「〜こと」で終える（例：上から水を入れられて、お手入れが楽なところ）
- 説明文に書いてあることだけを使う。書いていない効果・数字・評判は書かない
- 使った感想・おすすめ・「最強」「神」などの大げさな言葉は書かない
- 商品名・値段・記号・英字・絵文字は入れない
1文だけを出力してください。"""


def search_items(word, base_url, lo=500, hi=20000):
    """楽天の商品検索（レビューの多い順）。アフィリエイトのリンクで返す。鍵がないときは空."""
    import os
    if not os.environ.get("RAKUTEN_APP_ID"):
        return []
    from build import normalize_item
    params = {"applicationId": os.environ["RAKUTEN_APP_ID"], "accessKey": os.environ.get("RAKUTEN_ACCESS_KEY", ""),
              "keyword": word, "sort": "-reviewCount", "hits": 30, "availability": 1,
              "minPrice": lo, "maxPrice": hi, "formatVersion": 2}
    if os.environ.get("RAKUTEN_AFFILIATE_ID"):
        params["affiliateId"] = os.environ["RAKUTEN_AFFILIATE_ID"]
    req = urllib.request.Request(SEARCH + "?" + urllib.parse.urlencode(params), headers={
        "Referer": base_url.rstrip("/") + "/", "User-Agent": "rakuten-ranking-site/1.0",
        "Origin": urllib.parse.urlsplit(base_url)._replace(path="").geturl()})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            raws = json.load(res).get("Items", [])
        time.sleep(1)
    except Exception:  # noqa: BLE001
        return []
    return [normalize_item(x.get("Item", x)) for x in raws]


def point(it, purpose, cache):
    """商品の特徴・売れている理由を、説明文から Gemini で1文に（作れないときは None）."""
    import os
    key = f"{it['code']}|{purpose}"
    if key in cache:
        return cache[key]
    api = os.environ.get("GEMINI_API_KEY")
    if not api:
        return None
    from writer import BANNED, ENDPOINT, MODELS
    text = f"商品名：{it['name']}\n説明文：{(it.get('caption_long') or it.get('caption') or it.get('catch') or '')[:1200]}"
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": POINT_PROMPT.format(purpose=purpose)}]},
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 200},
    }).encode()
    for model in MODELS:
        try:
            req = urllib.request.Request(ENDPOINT.format(model=model), data=body,
                                         headers={"Content-Type": "application/json", "x-goog-api-key": api})
            with urllib.request.urlopen(req, timeout=60) as r:
                parts = json.load(r)["candidates"][0]["content"]["parts"]
            out = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip().strip("「」\"'。")
            out = out.splitlines()[0].strip() if out else ""
            ok = 12 <= len(out) <= 45 and not re.search(r"[A-Za-z]{2,}|最強|神", out) and not BANNED.search(out)
            cache[key] = out if ok else None
            return cache[key]
        except Exception:  # noqa: BLE001
            continue
    return None


def grams(text, low=False):
    """文から量（グラム）を読む（「500g×3」は1500g）。ふつうはいちばん大きい数を全体の量とみなし、
    low=True（「1.5kg〜4kg から選べる」など）は、いちばん安い寄付額に合ういちばん少ない量にする。読めないときは None."""
    found = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(kg|ｋｇ|キロ|g|ｇ)(?:\s*[×xX✕＊*]\s*(\d+))?", text or ""):
        g = float(m.group(1)) * (1000 if m.group(2) in ("kg", "ｋｇ", "キロ") else 1) * int(m.group(3) or 1)
        if 50 <= g <= 60000:
            found.append(g)
    if low:
        # 量が1つしか書かれていない（「最大2kg」など）と、いちばん安い寄付額の量か分からないので使わない
        return min(found) if len(found) >= 2 else None
    return max(found) if found and max(found) >= 300 else None


def amount(it):
    """返礼品の量（グラム）。量は商品名か、説明文の「内容量」のところから読む.

    容量を選べる返礼品（寄付額が「〜」・名前に「〜」「選べる」）は、いちばん少ない量（＝いちばん安い寄付額のもの）にする。
    """
    low = bool(it.get("has_range") or it.get("from") or re.search(r"[～〜]|選べる|選択|から選", it["name"]))
    g = grams(it["name"], low)
    if g is None and not low:
        m = re.search(r"内容量\s*[:：】\]]?\s*(.{0,120})", it.get("caption_long") or it.get("caption") or "")
        g = grams(m.group(1)) if m else None
    return g


def head_of(it):
    """宣伝文を除いた商品名の最初のほう（テーマに合うかはここで見る。名前の後ろに検索用の言葉を並べただけの商品を拾わない）."""
    return " ".join(name_words(it["name"])[:3])


def week_pick(d, seq):
    return seq[d.isocalendar()[1] % len(seq)]


BEST_WORDS = {"oshikatsu": "推し活グッズ", "vs": "安い vs 高い", "nazo": "なんでこれが", "neko": "猫グッズ", "inu": "犬グッズ",
              "check": "買う前に"}  # タイトルに入る言葉 → テーマ（日曜の再演用。クイズはふるさと納税の枠と重なるので除く）


def best_theme(d):
    """日曜用：この6日間でいちばん再生されたテーマ（YouTube のショート一覧の再生数から）。分からないときは THEMES_EXTRA を週ごとに.

    再演できるのは、毎回ちがう商品で作れる「search」のテーマだけ（猫・犬・推し活）。VS などがいちばんなら、そのまま同じ構成で作る。
    """
    try:
        req = urllib.request.Request(CHANNEL_SHORTS, headers={"Accept-Language": "ja", "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            page = r.read().decode("utf-8", "replace")
        views = {}
        week = {d - dt.timedelta(days=k) for k in range(1, 7)}
        for m in re.finditer(r'"accessibilityText":"([^"]{0,200}?)([\d,]+) ?回視聴', page):
            text, n = m.group(1), int(m.group(2).replace(",", ""))
            dm = re.search(r"【(\d+)/(\d+)】", text)
            if not dm or dt.date(d.year, int(dm.group(1)), int(dm.group(2))) not in week:
                continue
            for k, word in BEST_WORDS.items():
                if word in text:
                    views[k] = max(views.get(k, 0), n)
        if views:
            best = max(views, key=views.get)
            th = {"oshikatsu": OSHI, "neko": NEKO, "inu": INU}.get(best) or next(x for x in WEEKLY if x["key"] == best)
            return {**th, "replay": True}
    except Exception:  # noqa: BLE001
        pass
    return week_pick(d, THEMES_EXTRA)


def theme_topic(cfg, fcats, day, results=None, th=None):
    """その日の曜日のテーマの動画（作れないときは None）。th を渡すとそのテーマで作る（季節の枠）."""
    d = dt.date.fromisoformat(day)
    th = th or WEEKLY[d.weekday()]
    if th["kind"] == "best":
        th = best_theme(d)
    if th["kind"] == "pet":
        th = {**week_pick(d, [NEKO, INU]), "replay": th.get("replay")}
    base = cfg["base_url"]
    hist = json.loads(THEME_HISTORY.read_text(encoding="utf-8")) if THEME_HISTORY.exists() else {}
    cutoff = (d - dt.timedelta(days=28)).isoformat()
    hist = {k: v for k, v in hist.items() if cutoff <= k < day}
    used = {c for codes in hist.values() for c in codes}
    cache = json.loads(POINTS.read_text(encoding="utf-8")) if POINTS.exists() else {}
    fresh = lambda it: it["code"] not in used and it["reviews"] >= 30 and it["image"] and not excluded(it)  # noqa: E731
    if th["kind"] == "quiz":
        cats = [c for c in fcats or [] if c["slug"] in QTY_CATS]
        if not cats:
            return None
        c = week_pick(d, cats)
        scored = []
        for it in c["items"]:
            if it["code"] in used or it.get("reviews", 0) < 20 or excluded(it) or amount(it) is None:
                continue
            f = latest(it, base)  # 最新の寄付額（容量を選べる物は、いちばん安い寄付額）
            g = amount(f) if f else None
            if g and f["price"]:
                scored.append((g / f["price"] * 10000 / 1000, f))  # 寄付1万円あたりの kg
        scored.sort(key=lambda x: -x[0])
        per = {f["code"]: kg for kg, f in scored}
        picks = pick_varied([f for _, f in scored], 3)
        if len(picks) < 3:
            return None
        kg_say = lambda it: f"{per[it['code']]:.1f}".rstrip("0").rstrip(".")  # noqa: E731
        t = dict(key="furusato-qty", theme="green", title="ふるさと納税クイズ\n1万円で何kg届く？", tag="ふるさと納税",
                 label="寄付額", items=[(it, f"1万円で約{kg_say(it)}kg") for it in picks],
                 what=f"ふるさと納税の{c['title']}で、寄付1万円あたりの量が多い返礼品",
                 intro=f"クイズです。ふるさと納税の{c['title']}で、寄付1万円あたりの量がいちばん多いのはどれでしょう？",
                 order="countdown",
                 fact=lambda it: f"寄付1万円あたり、約{kg_say(it)}キロ。{it['shop']}の返礼品で、寄付額は{price_say(it)}",
                 lead="ふるさと納税 量が多い返礼品｜寄付1万円あたりで比べました",
                 tags="#ふるさと納税 #ふるさと納税返礼品 #コスパ #楽天ふるさと納税 #PR")
    elif th["kind"] == "vs":
        name, must = week_pick(d, VS_CATS)
        picks = {}
        for rank, _, lo, hi in VS_TIERS:  # 値段の帯ごとに、レビューのいちばん多いもの
            pool = [it for it in search_items(name, base, lo, hi) if fresh(it) and re.search(must, head_of(it))]
            got = pick3(pool, base, lambda f, lo=lo, hi=hi: lo <= f["price"] <= hi)[:1]
            if not got:
                return None
            picks[rank] = got[0]
        pts = {it["code"]: point(it, "この商品のいちばんの特徴", cache) for it in picks.values()}
        POINTS.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
        if not all(pts.values()):
            return None
        t = dict(key="vs", theme="red", title=f"{name}\n安い vs 高い", tag=name, label="楽天の価格",
                 items=[(picks[r], lab) for r, lab, _, _ in sorted(VS_TIERS)],
                 labels={r: lab for r, lab, _, _ in VS_TIERS}, order="countdown",
                 what=f"{name}の安いものと高いもの",
                 intro=f"{name}って、安いのと高いので何が違うの？3つの値段で比べてみます。",
                 say={3: "まずは安いほう、{name}。{fact}", 2: "真ん中の値段は、{name}。{fact}", 1: "そして高いほう、{name}。{fact}"},
                 fact=lambda it: f"{pts[it['code']]}。値段は{price_say(it)}",
                 end="あなたならどれを選ぶ？コメントで教えてね。",
                 lead=f"{name} 安いのと高いの、何が違う？｜値段の帯ごとに比べました",
                 tags=f"#{name} #比較 #買い物 #楽天購入品 #PR")
    elif th["kind"] == "mystery":
        allg = [it for g in cfg["genres"] for it in (results or {}).get(g["slug"], [])]
        risers = sorted((x for x in allg if isinstance(x.get("move"), int) and x["move"] >= 5 and fresh(x)), key=lambda x: -x["move"])
        picks, pts = [], {}
        for it in risers:
            if len(picks) == 3:
                break
            if any(similar(it, o) for o in picks):
                continue
            p = point(it, "この商品がいま選ばれていそうな理由（季節・使いみち・手軽さなど、説明文から読み取れる範囲で）", cache)
            f = latest(it, base) if p else None
            if f:
                picks.append(f)
                pts[f["code"]] = p
        POINTS.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
        if len(picks) < 3:
            return None
        t = dict(key="nazo", theme="red", title="なんでこれが\n売れてるの？", tag="楽天ランキング", label="楽天の価格",
                 items=[(it, f"{it['move']}位アップ") for it in picks],
                 labels={3: "謎その1", 2: "謎その2", 1: "謎その3"}, order="countdown",
                 what="楽天でいま急に売れている商品",
                 intro="楽天でいま急に売れてる、ちょっと気になる3つ。なんで売れてるのか、理由を見てみます。",
                 say={3: "ひとつめ、{name}。{fact}", 2: "ふたつめ、{name}。{fact}", 1: "みっつめ、{name}。{fact}"},
                 fact=lambda it: f"売れてる理由は、{pts[it['code']]}かも。昨日から{it['move']}位も上がって、{price_say(it)}",
                 end="気になったものはあった？保存しておくと、あとで見返せるよ。",
                 lead="楽天で急に売れてる商品｜なんで売れてる？を説明文から読み解きました",
                 tags="#楽天ランキング #楽天市場 #売れてる #楽天購入品 #PR")
    elif th["kind"] == "check":
        name, must, points = week_pick(d, CHECK_CATS)
        pool = [it for it in search_items(name, base, 1000, 30000) if fresh(it) and re.search(must, head_of(it))]
        chosen = {}
        for rank, (_, ok) in zip((3, 2, 1), points):  # ポイントごとに、それに合ういちばんレビューの多いもの
            cand = [it for it in pool if re.search(ok, it["name"]) and all(o["code"] != it["code"] for o in chosen.values())]
            got = pick3(cand, base)[:1]
            if not got:
                return None
            chosen[rank] = got[0]
        text = {chosen[rank]["code"]: p for rank, (p, _) in zip((3, 2, 1), points)}
        t = dict(key="check", theme="red", title=f"{name}を買う前に\nチェック3つ", tag=name, label="楽天の価格",
                 items=[(chosen[r], f"チェック{4 - r}") for r in (1, 2, 3)],
                 labels={3: "チェック1", 2: "チェック2", 1: "チェック3"}, order="countdown",
                 what=f"{name}を選ぶときのポイント",
                 intro=f"{name}を買う前に、見ておきたいポイントを3つ紹介します。",
                 say={3: "ひとつめのチェックは、{fact}。この条件なら、{name}", 2: "ふたつめは、{fact}。たとえば、{name}",
                      1: "みっつめは、{fact}。それなら、{name}"},
                 fact=lambda it: text[it["code"]],
                 end="保存しておくと、買うときに見返せるよ。",
                 lead=f"{name}の選び方｜買う前に見たいポイント3つ", tags=f"#{name} #選び方 #買う前に #楽天購入品 #PR")
    else:  # search：テーマの商品を3位から
        must, ng = re.compile(th["must"]), re.compile(th.get("ng") or "$^")
        pool, seen = [], set()
        if th.get("ranking"):  # 楽天のジャンル別ランキング（売れている順）から選ぶ。レビュー数より「いま人気」を出せる
            from build import fetch_ranking
            for page in (1, 2):
                try:
                    for it in fetch_ranking(th["ranking"], base, page):
                        if it["code"] not in seen and not ng.search(it["name"]) and it["code"] not in used and it["image"] and not excluded(it):
                            seen.add(it["code"])
                            pool.append(it)
                except Exception:  # noqa: BLE001
                    pass
            picks = pick3(pool, base)
            if len(picks) < 3:
                return None
            t = dict(key=th["key"], theme="red", title=th["title"], tag=th["tag"], label="楽天の価格",
                     items=[(it, f"ランキング{it['rank']}位") for it in picks], what=th["what"],
                     fact=lambda it: f"楽天の{th['rank_name']}ランキングで{it['rank']}位、{price_say(it)}",
                     lead=th["lead"], tags=th["tags"])
            t["is_theme"] = True
            hist[day] = list(dict.fromkeys((json.loads(THEME_HISTORY.read_text(encoding="utf-8")).get(day, []) if THEME_HISTORY.exists() else []) + [it["code"] for it, _ in t["items"]]))
            THEME_HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=0), encoding="utf-8")
            return t
        for w in th["words"]:
            for it in search_items(w, base):
                if it["code"] not in seen and must.search(it["name"] if th.get("anywhere") else head_of(it)) and not ng.search(it["name"]) and fresh(it):
                    seen.add(it["code"])
                    pool.append(it)
        pool.sort(key=lambda x: -x["reviews"])
        picks = pick3(pool, base)
        if len(picks) < 3:
            return None
        t = dict(key=th["key"], theme="red", title=th["title"], tag=th["tag"], label="楽天の価格",
                 items=[(it, f"レビュー{it['reviews']:,}件") for it in picks], what=th["what"],
                 fact=lambda it: f"レビューが{it['reviews']:,}件もあって、{price_say(it)}",
                 lead=th["lead"], tags=th["tags"])
        if th.get("replay"):
            t["intro"] = f"今週いちばん見られたテーマを、もう一度。{th['what']}を、別の3つで紹介します。"
    t["is_theme"] = True  # X・Threads もこの日のテーマの商品で投稿する（made の theme_items）
    full = json.loads(THEME_HISTORY.read_text(encoding="utf-8")) if THEME_HISTORY.exists() else {}
    hist[day] = list(dict.fromkeys((full.get(day, []) if t["key"].startswith("xmas") else []) + [it["code"] for it, _ in t["items"]]))
    THEME_HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=0), encoding="utf-8")
    return t


def topics(cfg, results, budget, fcats, day):
    """その日の動画のテーマ（最大 PER_DAY 本）。値段は作る直前に最新のものを確かめる."""
    base = cfg["base_url"]
    out = []
    t = theme_topic(cfg, fcats, day, results)  # 曜日ごとのテーマ（推し活・猫・ふるさと納税クイズなど）
    if t:
        out.append(t)
    xt = xmas_theme(day)
    xv = theme_topic(cfg, fcats, day, results, th=xt) if xt else None  # クリスマス前は1000円台の枠の代わりに
    if xv:
        out.append(xv)
    picks = pick3(budget or [], base, lambda f: 1000 <= f["price"] < 2000) if not xv else []  # 最新の値段でも1000円台のものだけ
    if len(picks) == 3:
        out.append(dict(key="budget", theme="red", title="1000円台・送料無料\n売れ筋TOP3", tag="1000円台", label="",
                        items=[(it, "送料無料") for it in picks],
                        what="楽天で今売れている、1000円台で送料無料の商品",
                        fact=lambda it: f"送料無料で{price_say(it)}"))
    if fcats:
        k = dt.date.fromisoformat(day).toordinal() % len(fcats)
        c = fcats[k]
        fpicks = pick3(c["items"], base)
        if len(fpicks) == 3:
            out.append(dict(key=f"furusato-{c['slug']}", theme="green", title=f"ふるさと納税\n{c['title']}の人気TOP3", tag="ふるさと納税",
                            label="寄付額", items=[(it, it["shop"]) for it in fpicks],
                            what=f"楽天ふるさと納税でレビューが多い{c['title']}の返礼品",
                            fact=lambda it: f"{it['shop']}の返礼品で、寄付額は{price_say(it)}"))
    return out[:PER_DAY]


def video_title(t, m, d):
    """タイトルにもハッシュタグを入れる（検索・おすすめで見つけてもらうため。100文字以内）."""
    base = f"{t['title'].replace(chr(10), ' ')}【{m}/{d}】"
    if t.get("order") != "countdown" and not t.get("say"):  # ランキングの回は、毎日同じ題にならないよう1位の商品名を頭に
        base = f"1位は{price_text(t['items'][0][0])}｜{base}"  # 毎日同じ題にならないよう、1位の値段を頭に（商品名は宣伝文が混ざるので使わない）
    tags = ["#Shorts", "#楽天"] + (["#ふるさと納税", "#楽天ふるさと納税"] if t["theme"] == "green"
                                   else ["#楽天市場", f"#{t['tag']}"])
    out = base
    for tg in tags:
        if len(out) + 1 + len(tg) <= 100:
            out += " " + tg
    return out


ROOM_CTA = {  # 動画の最後の読み上げ（型のしゃべり方に合わせる。ROOM は英字だと読み間違えるのでカタカナ）
    "pop": "紹介した商品は、楽天ルームで、らんくま、と検索するのだ！",
    "notebook": "紹介した商品は、楽天ルームで、らんくま、って検索してね！",
    "": "紹介した商品は、楽天ルームで、らんくま、と検索してください。",
}


def description(t, day, site):
    m, d = int(day[5:7]), int(day[8:10])
    lines = [f"{t['title'].replace(chr(10), ' ')}（{m}月{d}日時点）", ""]
    for i, (it, note) in enumerate(t["items"]):
        price = f"寄付額{price_text(it)}（{it['shop']}）" if t["theme"] == "green" else price_text(it)
        head = t.get("labels", {}).get(i + 1, f"{i + 1}位").replace("\n", "")
        lines.append(f"{head} {short_name(it['name'], 40)}｜{price}")
    lines += ["", "▶紹介した商品は、楽天ROOMで「らんくま」と検索", site, "",
              "※価格・寄付額は動画作成時点のものです。最新情報は販売ページでご確認ください。",
              "※楽天アフィリエイトを利用しています（PR）", credit(), "",
              f"#Shorts #PR #楽天 #{t['tag']}" + (" #楽天ふるさと納税" if t["theme"] == "green" else " #楽天市場")]
    return "\n".join(lines)


def build(cfg, results, budget, fcats, day, out_dir, log):
    global PAT
    if not voicevox_ready():
        log.append("[shorts] VOICEVOX に接続できないため動画作成をスキップ")
        return []
    PAT = design.video_pattern(day, cfg)
    spk = speaker_id(PAT["voice"]["name"], PAT["voice"]["style"])
    if spk is None:  # その声が VOICEVOX にないときは、ずんだもんの声で作る（作りはそのまま）
        log.append(f"[shorts] {PAT['voice']['name']} の声が見つからないため、ずんだもんの声で作成")
        PAT = {**PAT, "voice": design.PATTERNS[0]["voice"]}
        spk = speaker_id("ずんだもん") or 3
    log.append(f"[shorts] 作り：{PAT['name']}／声：{PAT['voice']['name']}")
    if PAT["video"] != "pop":
        import reels
        title_fn, item_fn, end_fn = reels.STYLES[PAT["video"]]
    reading = json.loads(SPOKEN_CACHE.read_text(encoding="utf-8")) if SPOKEN_CACHE.exists() else {}
    m, d = int(day[5:7]), int(day[8:10])
    site = cfg.get("room_url") or cfg["base_url"].rstrip("/") + "/"  # 説明欄は ROOM へ（ショートで見て、ROOM で買ってもらう）
    made = []
    for n, t in enumerate(topics(cfg, results, budget, fcats, day)):
        t["day"] = day
        try:
            with tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                script = {**PAT["script"], "order": t.get("order", PAT["script"]["order"])}  # クイズは答えを最後に出すので3位から
                intro, body, end_text = design.lines_for(
                    script, t["what"], [(spoken_name(it, reading), t["fact"](it)) for it, _ in t["items"]])
                intro = t.get("intro", intro)
                if t.get("say"):  # VS・謎解き・選び方：順位ではない読み上げ（語尾だけ型のしゃべり方に合わせる）
                    tail = {"pop": "なのだ。", "notebook": "だよ！"}.get(PAT["key"], "です。")
                    body = [(r, t["say"][r].format(name=n, fact=t["fact"](t["items"][r - 1][0])) + tail)
                            for r, n in ((r, spoken_name(t["items"][r - 1][0], reading)) for r, _ in body)]
                # 最後は必ず「楽天ROOMで、らんくまと検索」（ショートは説明欄のリンクを押せないので、ROOM のアプリ内検索で来てもらう）
                end_text = (t["end"] + " " if t.get("end") else "") + ROOM_CTA.get(PAT["key"], ROOM_CTA[""])
                line1 = "楽天ランキング速報" if t["theme"] == "red" else "ふるさと納税 人気返礼品ランキング"
                slides = []
                hw = work / "h.wav"  # 最初の1.3秒は声なし（BGMと効果音だけ）で商品を見せる
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                                "-t", "1.3", str(hw)], check=True)
                slides.append((work / "fh", hw, 1.3, anim_hook(t, 1.3, work / "fh")))
                a = work / "s0.wav"
                sec = synth(intro, spk, a) + 0.4
                if PAT["video"] == "pop":
                    ev = anim_title(t["theme"], t["title"], f"{m}月{d}日時点", sec, work / "f0", seed=n,
                                    mouth=mouth_curve(a, sec), text=intro)
                else:
                    ev = title_fn(t, t["items"], sec, work / "f0", intro)
                slides.append((work / "f0", a, sec, ev))
                revealed = {}
                for pos, (rank, text) in enumerate(body):
                    it, note = t["items"][rank - 1]
                    a = work / f"s{rank}.wav"
                    sec = synth(text, spk, a) + 0.4
                    if PAT["video"] == "pop":
                        ev = anim_item(t["theme"], rank, it, t["label"], note, text, sec, work / f"f{rank}",
                                       seed=n * 10 + rank, mouth=mouth_curve(a, sec), label=t.get("labels", {}).get(rank))
                    else:
                        ev = item_fn(t, rank, pos, it, note, sec, work / f"f{rank}", text, dict(revealed))
                        import reels
                        revealed[rank] = reels.mini_name(it)
                    slides.append((work / f"f{rank}", a, sec, ev))
                a = work / "s9.wav"
                sec = synth(end_text, spk, a) + 0.4
                if PAT["video"] == "pop":
                    ev = anim_end(t["theme"], line1, sec, work / "f9", mouth=mouth_curve(a, sec), text=end_text)
                else:
                    ev = end_fn(t, sec, work / "f9", end_text, line1, revealed)
                slides.append((work / "f9", a, sec, ev))
                # ファイル名はテーマごとに決める（同じ日に作り直しても、予約済みのタイトルと中身がずれないように）
                name = f"shorts/{day}-{t['key']}.mp4"
                make_video_anim(slides, out_dir / name, work, seed=dt.date.fromisoformat(day).toordinal() + n)
            made.append({"file": name, "title": video_title(t, m, d), "desc": description(t, day, site), "theme": t["theme"], "key": t["key"],
                         "lead": t.get("lead"), "tags": t.get("tags"),  # Instagram の1行目とタグ（テーマの枠だけ）
                         # 曜日のテーマの商品（X・Threads の投稿にも使う）。見出し（安い・チェック1など）も添える
                         "theme_items": [{**it, "label": t.get("labels", {}).get(r + 1, ""), "fact": t["fact"](it)}
                                         for r, (it, _) in enumerate(t["items"])] if t.get("is_theme") else None,
                         "sec": round(sum(s[2] for s in slides)),
                         # Instagram のコメントに DM で返すときの商品リンク（動画と同じ順）
                         "items": [{"name": short_name(it["name"], 30), "price": price_text(it), "url": it["url"], "code": it["code"]}
                                   for it, _ in t["items"]]})
            log.append(f"[shorts] {name} {made[-1]['sec']}秒 {t['title']}")
        except Exception as ex:  # noqa: BLE001
            log.append(f"[shorts] 失敗 {t['title']}: {ex}")
    SPOKEN_CACHE.write_text(json.dumps(reading, ensure_ascii=False, indent=0), encoding="utf-8")
    page(made, day, out_dir)
    return made


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
