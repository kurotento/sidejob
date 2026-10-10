"""4つの型のショート動画を1本ずつ作る（声・BGM 付きの見本。GitHub Actions の shorts-sample で動かす）.

使い方: python tools/shorts_sample.py 出力フォルダ
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import design  # noqa: E402
import shorts  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "samples")
out.mkdir(parents=True, exist_ok=True)
day = sorted(p.name for p in (ROOT / "data" / "history").iterdir())[-1]
budget = json.loads((ROOT / "data" / "history" / day / "budget.json").read_text(encoding="utf-8"))
cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
shorts.PER_DAY = 1
log = []
for p in design.PATTERNS:
    made = shorts.build({**cfg, "genres": [], "design_pattern": p["key"]}, {}, budget, [], day, out / p["key"], log)
    for v in made:
        src = out / p["key"] / v["file"]
        src.rename(out / f"{p['key']}.mp4")
print("\n".join(log))
(out / "log.txt").write_text("\n".join(log), encoding="utf-8")
