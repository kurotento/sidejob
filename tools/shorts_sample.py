"""ショート動画の見本を作る（声・BGM 付き。GitHub Actions の shorts-sample で動かす）.

使い方: python tools/shorts_sample.py 出力フォルダ [themes]
- 引数なし : 4つの型を1本ずつ（直近の1000円台の商品で）
- themes   : 曜日ごとのテーマの枠を、来週の7日分（楽天の検索・ふるさと納税の取得に RAKUTEN_* の鍵が要る）
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import design  # noqa: E402
import shorts  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "samples")
out.mkdir(parents=True, exist_ok=True)
cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
shorts.PER_DAY = 1
log = []
if len(sys.argv) > 2 and sys.argv[2] == "themes":
    import build
    import furusato
    fcats = furusato.fetch_all(cfg)
    last = sorted(p.name for p in (ROOT / "data" / "history").iterdir())[-1]  # 謎解き用：直近のランキングと前日からの順位の動き
    results = {}
    for g in cfg["genres"]:
        f = ROOT / "data" / "history" / last / f"{g['slug']}.json"
        if f.exists():
            results[g["slug"]] = build.annotate(json.loads(f.read_text(encoding="utf-8")), build.load_previous(last, g["slug"]))
    for c in fcats:  # クイズで量が読めた返礼品の数
        ok = [it for it in c["items"] if shorts.amount(it)]
        log.append(f"[量] {c['slug']}: {len(ok)}/{len(c['items'])}件 " + " / ".join(f"{shorts.amount(it):.0f}g {it['name'][:25]}" for it in ok[:3]))
    start = dt.date.today() + dt.timedelta(days=1)
    for k in range(7):
        day = (start + dt.timedelta(days=k)).isoformat()
        t = shorts.theme_topic(cfg, fcats, day, results)
        if not t:
            log.append(f"{day} テーマ {shorts.WEEKLY[dt.date.fromisoformat(day).weekday()]['key']}: 商品が足りず作れない")
            continue
        log.append(f"{day} {t['title'].replace(chr(10), ' ')}（型: {design.video_pattern(day, cfg)['key']}）")
        for it, note in t["items"]:
            log.append(f"   {note}｜{it['price']:,}円｜{it['name'][:60]}｜{t['fact'](it)}")
        orig = shorts.topics
        shorts.topics = lambda *a, t=t: [t]
        made = shorts.build(cfg, results, [], fcats, day, out / day, log)
        shorts.topics = orig
        for v in made:
            (out / day / v["file"]).rename(out / f"{day}-{v['key']}.mp4")
            log.append("   " + v["desc"].split("\n")[0])
elif len(sys.argv) > 2 and sys.argv[2] == "xmas":  # クリスマスの枠を、テーマごとに1本ずつ（冒頭の商品カット・タイトル込み）
    for k, th in enumerate(shorts.XMAS):
        day = (dt.date(2026, 11, 14) + dt.timedelta(days=k)).isoformat()
        t = shorts.theme_topic(cfg, [], day, {}, th=th)
        if not t:
            log.append(f"{th['key']}: 商品が足りず作れない")
            continue
        log.append(f"{th['key']}（型: {design.video_pattern(day, cfg)['key']}）")
        for it, note in t["items"]:
            log.append(f"   {note}｜{it['price']:,}円｜{it['name'][:60]}")
        orig = shorts.topics
        shorts.topics = lambda *a, t=t: [t]
        made = shorts.build(cfg, {}, [], [], day, out / day, log)
        shorts.topics = orig
        for v in made:
            (out / day / v["file"]).rename(out / f"{v['key']}.mp4")
            log.append("   タイトル: " + v["title"])
else:
    day = sorted(p.name for p in (ROOT / "data" / "history").iterdir())[-1]
    budget = json.loads((ROOT / "data" / "history" / day / "budget.json").read_text(encoding="utf-8"))
    for p in design.PATTERNS:
        made = shorts.build({**cfg, "genres": [], "design_pattern": p["key"]}, {}, budget, [], day, out / p["key"], log)
        for v in made:
            src = out / p["key"] / v["file"]
            src.rename(out / f"{p['key']}.mp4")
print("\n".join(log))
(out / "log.txt").write_text("\n".join(log), encoding="utf-8")
