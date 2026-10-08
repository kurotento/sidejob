"""楽天ROOM の投稿リストを毎日作る（投稿はユーザーが手で行う）.

- public/room-list.csv : Google スプレッドシートの IMPORTDATA で読み込む用
- public/room.html     : スマホ用。ボタンを押すとコメントをコピーしてROOMの投稿画面を開く
ROOM の規約は機械的な投稿を禁止しているため、ここでは投稿の準備だけを行う。
"""
import csv
import datetime as dt
import html
import io
import json
import re
from pathlib import Path

from articles import short_name

DATA = Path(__file__).resolve().parent / "data"
HISTORY = DATA / "room_list.json"
PER_DAY = 20
FURUSATO_PER_DAY = 5
REPEAT_DAYS = 3  # 同じ商品をもう一度リストに出すまでの日数
e = html.escape


def room_url(code):
    return f"https://room.rakuten.co.jp/mix?itemcode={code}"


def room_comment(it, desc, tag, furusato=False):
    """ROOM用のおすすめコメント。紹介文の要約と事実だけ（体験談は書かない）."""
    parts = []
    if desc:
        sents = re.split(r"(?<=[。！!])", desc["intro"])
        parts.append("".join(sents[:2]).strip())
        parts.append(" / ".join(desc["features"][:2]))
    stars = f"★{it['rating']:.1f}（レビュー{it['reviews']:,}件）" if it["reviews"] >= 10 else ""
    if furusato:
        parts.append(f"寄付額{it['price']:,}円｜{it['shop']} {stars}".strip())
        tags = ["#楽天ROOM", "#ふるさと納税", "#楽天ふるさと納税", "#返礼品"] + ([f"#{tag}"] if tag and tag != "ふるさと納税" else [])
    else:
        parts.append(f"{it['price']:,}円・送料無料 {stars}".strip())
        tags = ["#楽天ROOM", "#1000円台", "#送料無料", "#買い回り"] + ([f"#{tag}"] if tag else [])
    parts.append(" ".join(tags))
    return "\n".join(p for p in parts if p)


def build(cfg, budget, descs, day, out_dir, save=True, fcats=None, fdescs=None):
    from social import product_tag

    hist = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else {}
    cutoff = (dt.date.fromisoformat(day) - dt.timedelta(days=REPEAT_DAYS)).isoformat()
    hist = {k: v for k, v in hist.items() if k >= cutoff}
    recent = {c for k, codes in hist.items() if k != day for c in codes}
    picks = [it for it in budget or [] if it["code"] not in recent and descs.get(it["code"])][:PER_DAY]
    # ふるさと納税の返礼品を3件（各ジャンル上位から順に）
    fdescs = fdescs or {}
    fpicks = []
    for rank in range(30):
        for c in fcats or []:
            if len(fpicks) < FURUSATO_PER_DAY and rank < len(c["items"]):
                it = c["items"][rank]
                if it["code"] not in recent and fdescs.get(it["code"]) and it not in fpicks:
                    fpicks.append(it)
    furusato_codes = {it["code"] for it in fpicks}
    picks = picks + fpicks
    descs = {**descs, **fdescs}
    hist[day] = [it["code"] for it in picks]
    if save:
        HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=0), encoding="utf-8")

    rows = []
    for it in picks:
        tag = product_tag(it["name"], descs.get(it["code"]))
        rows.append({"it": it, "comment": room_comment(it, descs.get(it["code"]), tag, it["code"] in furusato_codes)})

    # スプレッドシート用CSV（改行は IMPORTDATA で崩れるので「 / 」に置き換える）
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["日付", "商品名", "価格", "ROOM投稿画面", "コメント（コピーして使う）", "商品ページ"])
    for r in rows:
        it = r["it"]
        w.writerow([day, short_name(it["name"], 50), it["price"], room_url(it["code"]),
                    r["comment"].replace("\n", " / "), it["url"]])
    (out_dir / "room-list.csv").write_text(buf.getvalue(), encoding="utf-8")

    cards = "".join(f"""<article class="c" id="i{n}"><img src="{e(r['it']['image'])}" alt="">
<div><h2>{n + 1}. {e(short_name(r['it']['name'], 40))}</h2><p class="p">{('寄付額' + format(r['it']['price'], ',') + '円｜' + e(r['it']['shop'])) if r['it']['code'] in furusato_codes else format(r['it']['price'], ',') + '円・送料無料'}</p>
<textarea readonly>{e(r['comment'])}</textarea>
<button onclick="go({n})">① コメントをコピーしてROOMを開く</button>
<a class="sub" href="{e(r['it']['url'])}" target="_blank" rel="noopener">開けないときは商品ページから「ROOMに投稿」</a>
<label><input type="checkbox" onchange="done({n},this.checked)"> 投稿した</label>
<a class="u" href="{e(room_url(r['it']['code']))}"></a></div></article>""" for n, r in enumerate(rows))
    m, d = int(day[5:7]), int(day[8:10])
    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>ROOM投稿リスト {m}/{d}</title><style>
body{{margin:0;font-family:system-ui,"Hiragino Sans",sans-serif;background:#f6f4f0;color:#1d1d1f}}
header{{background:#bf0000;color:#fff;padding:14px 16px}}header h1{{font-size:1.1rem;margin:0}}header p{{margin:4px 0 0;font-size:.8rem;opacity:.9}}
main{{padding:12px;max-width:640px;margin:0 auto}}
.c{{display:grid;grid-template-columns:84px 1fr;gap:12px;background:#fff;border-radius:14px;padding:12px;margin-bottom:12px}}
.c.ok{{opacity:.45}}.c img{{width:84px;height:84px;object-fit:contain}}h2{{font-size:.9rem;margin:0}}.p{{margin:2px 0 6px;color:#bf0000;font-weight:700}}
textarea{{width:100%;height:96px;font-size:.78rem;border:1px solid #ddd;border-radius:8px;box-sizing:border-box}}
button{{width:100%;margin-top:6px;padding:12px;border:0;border-radius:10px;background:#bf0000;color:#fff;font-weight:700;font-size:.9rem}}
.sub{{display:block;font-size:.72rem;color:#2563eb;margin-top:6px}}label{{display:block;margin-top:6px;font-size:.85rem}}
.note{{font-size:.75rem;color:#6e6e73;background:#fff;border-radius:10px;padding:10px}}</style></head><body>
<header><h1>楽天ROOM 投稿リスト（{m}月{d}日）</h1><p>ボタンを押す →「コメント」欄に貼り付け → 投稿。1件ずつ、間をあけて投稿してね</p></header>
<main><p class="note">このページは検索に表示されません。コメントは商品ごとに少し手直しすると、より自然になります。</p>{cards}</main>
<script>
const K='room-done-{day}';let s={{}};try{{s=JSON.parse(localStorage.getItem(K)||'{{}}')}}catch(e){{}}
function mark(){{document.querySelectorAll('.c').forEach((c,i)=>{{c.classList.toggle('ok',!!s[i]);c.querySelector('input').checked=!!s[i]}})}}
function done(i,v){{s[i]=v;try{{localStorage.setItem(K,JSON.stringify(s))}}catch(e){{}}mark()}}
async function go(i){{const c=document.getElementById('i'+i);const t=c.querySelector('textarea');
try{{await navigator.clipboard.writeText(t.value)}}catch(e){{t.select();document.execCommand('copy')}}
window.open(c.querySelector('a.u').href,'_blank')}}
mark();
</script></body></html>"""
    (out_dir / "room.html").write_text(page, encoding="utf-8")
    return len(rows)
