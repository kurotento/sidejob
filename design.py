"""画像・動画の「作り」を一定の期間ごとに丸ごと切り替える（同じ人の投稿だと見飽きられないように）.

色だけでなく、レイアウト・書体・キャラクターの有無・動画の構成・しゃべり方・声・BGM まで型ごとに変える。
- pop     : らんくま（クマ）が3位から発表する、にぎやかなランキング（ずんだもん）
- magazine: 雑誌の特集ページ風。大きな写真と明朝体、No.01〜03 の順に静かに紹介（冥鳴ひまり）
- notebook: 画像は方眼ノートのチェキ風メモ、動画は集中線＋いらすとやの「3選」風（春日部つむぎ）
- news    : 画像は速報テロップ風、動画は黒帯タイトル＋順位一覧の「TOP○」まとめ風（No.7 アナウンス）
PERIOD_DAYS 日ごとに順に回す。config.json の "design_pattern" にキーを入れると、その型に固定できる（確認用）。
"""
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FONT_DIR = ROOT / "fonts"
PERIOD_DAYS = 14
EPOCH = dt.date(2026, 9, 28)  # 9/28〜10/11 が最初の型。ここから2週間ごとに次の型へ

# 書体（Google Fonts のオープンなフォント。初回に fonts/ へ取ってくる）
WEB_FONTS = {
    "hand": "kleeone/KleeOne-SemiBold.ttf",
    "impact": "delagothicone/DelaGothicOne-Regular.ttf",
}
SYSTEM = {
    "sans": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "C:/Windows/Fonts/YuGothB.ttc"],
    "serif": ["/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc", "C:/Windows/Fonts/yumindb.ttf"],
    "serif_light": ["/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", "C:/Windows/Fonts/yumin.ttf"],
}

PATTERNS = [
    dict(key="pop", video="pop", name="ポップ（らんくまのランキング）",
         voice=dict(name="ずんだもん", style="ノーマル", speed=1.15),
         script=dict(intro="{what}トップ3を紹介するのだ！",
                     item=["第3位は、{name}。{fact}なのだ。", "第2位は、{name}。{fact}なのだ。", "堂々の第1位は、{name}。{fact}なのだ。"],
                     end="気になったら、プロフィールのリンクからチェックするのだ！", order="countdown")),
    dict(key="magazine", video="magazine", name="マガジン（写真と明朝体の特集ページ）",
         voice=dict(name="冥鳴ひまり", style="ノーマル", speed=1.08),
         script=dict(intro="{what}を、3つ選びました。",
                     item=["ひとつめは、{name}。{fact}です。", "ふたつめは、{name}。{fact}です。", "みっつめは、{name}。{fact}です。"],
                     end="ほかのアイテムは、プロフィールのリンクからどうぞ。", order="forward")),
    dict(key="notebook", video="aruaru", name="イラスト（集中線といらすとや／画像は手書きメモ風）",
         voice=dict(name="春日部つむぎ", style="ノーマル", speed=1.12),
         script=dict(intro="{what}、3つ選んでみたよ！",
                     item=["第3位は、{name}。{fact}だよ！", "第2位は、{name}。{fact}だよ！", "第1位は、{name}。{fact}だよ！"],
                     end="保存しておくと、あとで見返せるよ！", order="countdown")),
    dict(key="news", video="list", name="まとめ（黒帯タイトルと順位一覧／画像は速報風）",
         voice=dict(name="No.7", style="アナウンス", speed=1.1),
         script=dict(intro="{what}、上位3つを順番に発表します。",
                     item=["3位、{name}。{fact}です。", "2位、{name}。{fact}です。", "そして1位は、{name}。{fact}です。"],
                     end="詳しい情報は、プロフィールのリンクからご確認ください。", order="countdown")),
]
BY_KEY = {p["key"]: p for p in PATTERNS}


def pattern(day, cfg=None):
    """その日に使う型（day は 'YYYY-MM-DD'）."""
    if cfg is None:
        conf = ROOT / "config.json"
        cfg = json.loads(conf.read_text(encoding="utf-8")) if conf.exists() else {}
    fixed = cfg.get("design_pattern")
    if fixed in BY_KEY:
        return BY_KEY[fixed]
    n = (dt.date.fromisoformat(day) - EPOCH).days // PERIOD_DAYS
    return PATTERNS[max(n, 0) % len(PATTERNS)]


def schedule(day, count=4):
    """今の型と、このあと切り替わる日と型（ポータル表示用）."""
    d = dt.date.fromisoformat(day)
    n = max((d - EPOCH).days // PERIOD_DAYS, 0)
    return [(EPOCH + dt.timedelta(days=(n + k) * PERIOD_DAYS), PATTERNS[(n + k) % len(PATTERNS)]) for k in range(count)]


def _web_font(kind):
    path = FONT_DIR / Path(WEB_FONTS[kind]).name
    if not path.exists():
        try:
            FONT_DIR.mkdir(exist_ok=True)
            url = "https://github.com/google/fonts/raw/main/ofl/" + WEB_FONTS[kind]
            with urllib.request.urlopen(url, timeout=60) as r:
                path.write_bytes(r.read())
        except Exception:  # noqa: BLE001
            return None
    return path


_cache = {}


def font(kind, size):
    """kind: sans / serif / serif_light / hand / impact（取れないときはゴシックにする）."""
    from PIL import ImageFont
    key = (kind, size)
    if key not in _cache:
        paths = [_web_font(kind)] if kind in WEB_FONTS else SYSTEM.get(kind, [])
        for f in [p for p in paths if p] + SYSTEM["sans"]:
            if Path(f).exists():
                _cache[key] = ImageFont.truetype(str(f), size)
                break
        else:
            _cache[key] = ImageFont.load_default()
    return _cache[key]


def lines_for(script, what, items):
    """読み上げの原稿。items は [(name, fact)]（1位から順）。返り値は (intro, [(順位, 原稿)], end)."""
    ranks = [3, 2, 1] if script["order"] == "countdown" else [1, 2, 3]
    body = [(r, script["item"][k].format(name=items[r - 1][0], fact=items[r - 1][1])) for k, r in enumerate(ranks)]
    return script["intro"].format(what=what), body, script["end"]
