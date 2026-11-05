"""楽天のセール（お買い物マラソン・スーパーSALE）が始まったときのショート動画を作る.

商品のランキングではなく「やること」を順に見せる型。最後は ROOM へ（セール中に ROOM の商品を踏んでもらえば、
そのあとのお買い物も成果になる）。中身は data/sales.json の今のセールから作る。

使い方: python tools/sale_short.py [日付] [出力先]
  手元で作るときは VOICEVOX（127.0.0.1:50021）と ffmpeg が要る。
"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import shorts  # noqa: E402
from shorts import FPS, W, Talker, bg_at, bounce, draw_sub, ease_out, font, layer, paste_scaled, pr_badge, stripes_bg  # noqa: E402

SALES = ROOT / "data" / "sales.json"
WEEK = "月火水木金土日"


def current_sale(day):
    """その日に開催中のセール（なければ None）."""
    sales = json.loads(SALES.read_text(encoding="utf-8"))
    return next((s for s in sales if s["start"][:10] <= day <= s["end"][:10]), None)


def when(iso):
    t = dt.datetime.fromisoformat(iso)
    return f"{t.month}/{t.day}({WEEK[t.weekday()]}) {t.hour}:{t.minute:02d}"


def anim_step(theme, num, head, body, text, dur, out, mouth=()):
    """「やること」1つ分の画面。番号・見出し・説明を大きく出す."""
    from PIL import ImageDraw
    big = stripes_bg(theme)
    chunks = shorts.sub_chunks(text) if text else []
    talker = Talker(250)
    top = 430
    card = layer((W - 100, 720))
    kd = ImageDraw.Draw(card)
    kd.rounded_rectangle([0, 0, W - 101, 719], radius=44, fill=(255, 255, 255))
    accent = shorts.THEMES[theme][1]
    y = 190
    for line in head.split("\n"):
        kd.text(((W - 100) // 2, y), line, font=font(104), fill=accent, anchor="mm")
        y += 130
    y += 70
    for line in body.split("\n"):
        kd.text(((W - 100) // 2, y), line, font=font(72), fill=(29, 29, 31), anchor="mm")
        y += 105
    badge = layer((200, 200))
    bd = ImageDraw.Draw(badge)
    bd.ellipse([4, 4, 196, 196], fill=(217, 164, 0), outline=(255, 255, 255), width=9)
    bd.text((100, 100), num, font=font(96 if len(num) == 1 else 54), fill=(255, 255, 255), anchor="mm")
    out.mkdir(parents=True, exist_ok=True)
    for f in range(int(dur * FPS)):
        t = f / FPS
        img = bg_at(big, t).convert("RGB")
        dx = int((1 - ease_out(t / 0.35)) * W)
        img.paste(card, (50 + dx, top), card)
        paste_scaled(img, badge, 170, top - 30, bounce((t - 0.3) / 0.35))
        sprite, bob = talker.frame(t, mouth[f] if f < len(mouth) else 0)
        img.paste(sprite, (W - 290, 120 + bob), sprite)
        d = ImageDraw.Draw(img)
        if chunks:
            draw_sub(d, shorts.sub_at(chunks, t, dur))
        pr_badge(d)
        img.save(out / f"f{f:04d}.jpg", quality=88)
    return [("whoosh", 0.0), ("pop", 0.35)]


def script(s):
    """読み上げと画面の文字。数字・条件は data/sales.json（楽天の公式ページで確かめた値）だけを使う."""
    end = dt.datetime.fromisoformat(s["end"])
    end_say = f"{end.month}月{end.day}日の、夜中{end.hour}時{end.minute}分まで" if end.hour < 5 else f"{end.month}月{end.day}日の{end.hour}時{end.minute}分まで"
    steps = [
        ("1", "エントリー", "ボタンを押すだけ\n買ったあとでもOK",
         "まずはエントリー。ボタンを押すだけで、買ったあとからでも間に合うのだ。"),
        ("2", "1店1,000円以上", f"お店の数でポイント\n{s['kaimawari']}",
         f"次に、1つのお店で1000円以上買うこと。買ったお店の数で、ポイントが{s['kaimawari_say']}になるのだ。"),
        ("3", "クーポンを取る", "使う前に取っておく\n（取らないと使えない）",
         "最後に、クーポンは使う前に取っておくのだ。"),
    ]
    if s.get("caution"):
        steps.append(("!", "注意", s["caution"], s["caution_say"]))
    return {
        "title": f"{s['name']}\n開催中！",
        "sub": f"{when(s['end'])}まで",
        "intro": f"楽天の{s['name']}が始まったのだ！{end_say}なのだ。やることは3つだけなのだ。",
        "steps": steps,
        "end": "1000円台の送料無料で、お店の数をかせぐなら、楽天ルームで、らんくま、と検索するのだ！",
    }


def build(day, out_path):
    s = current_sale(day)
    if not s:
        raise SystemExit(f"{day} に開催中のセールが data/sales.json にありません")
    shorts.PAT = shorts.design.PATTERNS[0]  # ずんだもん・ポップの型
    spk = shorts.speaker_id("ずんだもん") or 3
    sc = script(s)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        slides = []
        a = work / "s0.wav"
        sec = shorts.synth(sc["intro"], spk, a) + 0.4
        ev = shorts.anim_title("red", sc["title"], sc["sub"], sec, work / "f0", seed=1,
                               mouth=shorts.mouth_curve(a, sec), text=sc["intro"], hook="やることは3つ！")
        slides.append((work / "f0", a, sec, ev))
        for k, (num, head, body, say) in enumerate(sc["steps"], 1):
            a = work / f"s{k}.wav"
            sec = shorts.synth(say, spk, a) + 0.4
            ev = anim_step("red", num, head, body, say, sec, work / f"f{k}", mouth=shorts.mouth_curve(a, sec))
            slides.append((work / f"f{k}", a, sec, ev))
        a = work / "s9.wav"
        sec = shorts.synth(sc["end"], spk, a) + 0.4
        ev = shorts.anim_end("red", "楽天ランキング速報", sec, work / "f9", mouth=shorts.mouth_curve(a, sec), text=sc["end"])
        slides.append((work / "f9", a, sec, ev))
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        shorts.make_video_anim(slides, Path(out_path), work, seed=dt.date.fromisoformat(day).toordinal())
    return s, round(sum(x[2] for x in slides))


if __name__ == "__main__":
    day = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat()
    out = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "public" / "shorts" / f"{day}-sale.mp4")
    sale, sec = build(day, out)
    print(f"{out} {sec}秒 {sale['name']}")
