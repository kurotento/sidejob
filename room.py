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
import urllib.parse
from pathlib import Path

from articles import short_name
import roomtext

DATA = Path(__file__).resolve().parent / "data"
HISTORY = DATA / "room_list.json"
PER_DAY = 12           # 1000円台・送料無料（買い回り向け）
NICHE_PER_GENRE = 5    # ROOM の中心層（30〜40代女性）に強いジャンルから
NICHE_GENRES = ("interior", "daily")  # インテリア・収納 / 日用品
FURUSATO_PER_DAY = 5
REPEAT_DAYS = 3  # 同じ商品をもう一度リストに出すまでの日数
e = html.escape


def room_url(code):
    return f"https://room.rakuten.co.jp/mix?itemcode={code}"


def plain(text):
    """らんくま口調の「〜だよ」「〜だね」を普通の文末にする（ROOM では投稿者本人の言葉に見せたいため）."""
    text = re.sub(r"(なん)?だ[よね]([。！!]|$)", r"です\2", text.strip())
    text = re.sub(r"を?(取り上げる|紹介する)よ?[。！!]?$", "です。", text)
    text = re.sub(r"(る|た)よ([。！!]|$)", r"\1\2", text)
    text = re.sub(r"いよ([。！!]|$)", r"いです\1", text)
    return re.sub(r"^(これは|こちらは)[、,]?\s*", "", text.strip())


EMOJI = ["✔", "・", "🔸", "▶", "◎"]


def fallback_body(desc, n):
    """AIの本文がないときの本文。商品ごとに形を変える."""
    first = plain(re.split(r"(?<=[。！!])", desc["intro"])[0])
    feats = [plain(f).rstrip("。") for f in desc["features"][:3]]
    who = plain(desc.get("for_whom", "")).rstrip("。")
    who = re.sub(r"(に向いている|に向いています|におすすめ)$", "", who)
    style = n % 4
    if style == 0:
        mark = EMOJI[n % len(EMOJI)]
        return "\n".join([first] + [f"{mark} {f}" for f in feats])
    if style == 1:
        return f"{who}に。\n{first}\n{feats[0]}のもポイント。" if who and feats else first
    if style == 2:
        return f"{first}\n\n" + "／".join(feats[:2])
    return f"{feats[0]}。\n{first}" + (f"\n{who}によさそう。" if who else "") if feats else first


def room_comment(it, desc, tag, furusato=False, budget=False, body=None, n=0):
    """ROOM用のおすすめコメント。商品の事実と特徴だけを書く（使ったふりの体験談は書かない）.

    本文は Gemini が型を変えて書いたもの（body）を使い、なければ紹介文から形を変えて組み立てる。
    """
    if not body and desc:
        body = fallback_body(desc, n)
    parts = [body or ""]
    stars = f"★{it['rating']:.1f}（{it['reviews']:,}件）" if it["reviews"] >= 10 else ""
    # サイズ・色などで値段が変わる商品は、ROOM の表示（最安値〜）とずれるので値段を書かない
    yen = "" if it.get("has_range") else f"{it['price']:,}円"
    if furusato:
        parts.append(f"{'寄付額' + yen + '｜' if yen else ''}{it['shop']} {stars}".strip())
        tags = ["#ふるさと納税", "#楽天ふるさと納税", "#返礼品"] + ([f"#{tag}"] if tag and tag != "ふるさと納税" else [])
    else:
        ship = ["・送料無料", "（送料無料）", "・送料込み"][n % 3] if budget else ""
        if not yen:
            ship = ship.strip("・（）")
        price = [f"{yen}{ship} {stars}", f"💰{yen}{ship} {stars}", f"{stars} / {yen}{ship}"][n % 3]
        parts.append((price if yen else price.replace("💰", "")).strip(" /"))
        base = [["#1000円台", "#送料無料", "#買い回り"], ["#買い回り", "#プチプラ", "#送料無料"],
                ["#お買い物マラソン", "#楽天お買い物", "#送料無料"]][n % 3] if budget else ["#楽天ランキング"]
        tags = base + ([f"#{tag}"] if tag else [])
    parts.append(" ".join(tags))
    return "\n".join(p for p in parts if p)


def season_note(day, budget):
    """今日のセール・イベントに合わせた、投稿のねらい."""
    from social import sale_tags

    d = dt.date.fromisoformat(day)
    notes = []
    if "お買い物マラソン" in sale_tags([it["name"] for it in budget or []]):
        notes.append("🏃 お買い物マラソン中：1000円台の「あと1店舗」向けを優先して投稿")
    if d.day % 5 == 0:
        notes.append("🎯 5と0のつく日：買う人が増える日なので、いつもより多めに投稿")
    if d.day == 1:
        notes.append("📅 毎月1日：ROOMのランクが更新される日。今月のオリジナル写真の条件をお知らせで確認")
    if d.month in (11, 12):
        notes.append("🔥 11〜12月は大型セールとふるさと納税の締め切りが重なる、1年でいちばん売れる時期。投稿数を増やす")
    elif d.month == 10:
        notes.append("🍂 11〜12月の繁忙期に向けて、いまのうちに投稿数とフォロワーを増やしておく時期")
    return notes


def plan_box(day, budget):
    notes = "".join(f"<li>{e(n)}</li>" for n in season_note(day, budget))
    return f"""<details class="plan" open><summary>今日の作戦</summary>
{f'<ul class="season">{notes}</ul>' if notes else ''}
<ol>
<li><b>20〜22時に投稿</b>：ROOMがいちばん見られる時間。1件ずつ間をあけて（1時間100件・1日200件を超えると投稿できなくなる目安）</li>
<li><b>オリジナル写真を1枚</b>：届いた返礼品や、自分で買った物を撮って投稿。ランクB以上の条件で、買う人がいちばん重視するのもこれ（週3枚が目標）</li>
<li><b>いいね・フォローは手で</b>：同じジャンルの人の投稿に。自動ツールやAIエージェントでの操作は禁止で、凍結のおそれあり</li>
<li><b>コメントは少し手直し</b>：AIっぽい文が増えているので、ひとこと自分の言葉を足すと差がつく。使っていない物を「使ってみた」とは書かない</li>
</ol>
<p><a href="room-engage.html">👉 いいね・フォロー回りのリストはこちら</a></p>
<p class="ng">NG：アカウントの複数持ち／家族・知人に「私のROOMから買って」と頼む・買ったことをコメントで知らせてもらう</p>
</details>"""


def build(cfg, budget, descs, day, out_dir, save=True, fcats=None, fdescs=None, results=None):
    from social import product_tag

    hist = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else {}
    cutoff = (dt.date.fromisoformat(day) - dt.timedelta(days=REPEAT_DAYS)).isoformat()
    hist = {k: v for k, v in hist.items() if k >= cutoff}
    recent = {c for k, codes in hist.items() if k != day for c in codes}
    picks = [it for it in budget or [] if it["code"] not in recent and descs.get(it["code"])][:PER_DAY]
    budget_codes = seen = {it["code"] for it in picks}
    seen = set(seen)
    for g in NICHE_GENRES:  # インテリア・収納／日用品のランキングから（ROOM でいちばん投稿・購入が多いジャンル）
        n = 0
        for it in (results or {}).get(g, []):
            if n < NICHE_PER_GENRE and it["code"] not in recent and it["code"] not in seen:
                picks.append(it)
                seen.add(it["code"])
                n += 1
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

    tags = {it["code"]: product_tag(it["name"], descs.get(it["code"])) for it in picks}
    bodies = roomtext.write(picks, descs, day, tags) if save else {}
    rows = []
    for n, it in enumerate(picks):
        tag = tags[it["code"]]
        rows.append({"it": it, "tag": tag, "comment": room_comment(it, descs.get(it["code"]), tag, it["code"] in furusato_codes,
                                                                   it["code"] in budget_codes, bodies.get(it["code"]), n)})

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
<div><h2>{n + 1}. {e(short_name(r['it']['name'], 40))}</h2><p class="p">{('寄付額' + format(r['it']['price'], ',') + '円｜' + e(r['it']['shop'])) if r['it']['code'] in furusato_codes else format(r['it']['price'], ',') + ('円・送料無料' if r['it']['code'] in budget_codes else '円')}</p>
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
.plan{{background:#fff;border-radius:14px;padding:12px 14px;margin-bottom:12px;font-size:.84rem;line-height:1.6}}
.plan summary{{font-weight:700;font-size:.95rem;cursor:pointer}}.plan ol,.plan ul{{padding-left:1.2em;margin:8px 0}}
.season{{list-style:none;padding:8px 10px!important;background:#fff4e5;border-radius:10px}}.ng{{color:#b42318;font-size:.78rem;margin:4px 0 0}}
.note{{font-size:.75rem;color:#6e6e73;background:#fff;border-radius:10px;padding:10px}}</style></head><body>
<header><h1>楽天ROOM 投稿リスト（{m}月{d}日）</h1><p>ボタンを押す →「コメント」欄に貼り付け → 投稿。1件ずつ、間をあけて投稿してね</p></header>
<main>{plan_box(day, budget)}<p class="note">このページは検索に表示されません。コメントは商品ごとに少し手直しすると、より自然になります。</p>{cards}</main>
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
    engage_page(cfg, day, [r["tag"] for r in rows if r["tag"]], out_dir)
    return len(rows)


# ---------- いいね・フォロー回り（手で行う。ここでは探すためのリンクだけを作る） ----------

USER_WORDS = ["整理収納", "日用品", "時短家事", "キッチン", "買い回り", "ふるさと納税", "プチプラ", "子育て", "インテリア"]
FOLLOW_GOAL, LIKE_GOAL = 20, 50


def engage_page(cfg, day, tags, out_dir):
    base = "https://room.rakuten.co.jp"
    me = re.sub(r"/items/?$", "", cfg.get("room_url", "").rstrip("/"))
    q = urllib.parse.quote
    words = list(dict.fromkeys(tags))[:12] or ["収納", "日用品"]
    users = "".join(f'<a class="s" href="{base}/search/user?keyword={q(w)}" target="_blank" rel="noopener">👤 {e(w)}</a>'
                    for w in USER_WORDS)
    items = "".join(f'<a class="s" href="{base}/search/item?keyword={q(w)}" target="_blank" rel="noopener">♡ {e(w)}</a>'
                    for w in words)
    m, d = int(day[5:7]), int(day[8:10])
    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>ROOM いいね・フォロー {m}/{d}</title><style>
body{{margin:0;font-family:system-ui,"Hiragino Sans",sans-serif;background:#f6f4f0;color:#1d1d1f}}
header{{background:#bf0000;color:#fff;padding:14px 16px}}header h1{{font-size:1.1rem;margin:0}}header p{{margin:4px 0 0;font-size:.8rem;opacity:.9}}
main{{padding:12px;max-width:640px;margin:0 auto}}section{{background:#fff;border-radius:14px;padding:12px 14px;margin-bottom:12px;font-size:.85rem;line-height:1.6}}
h2{{font-size:.98rem;margin:0 0 6px}}.s{{display:inline-block;margin:0 6px 8px 0;padding:8px 12px;border-radius:999px;background:#f6f4f0;border:1px solid #ddd;color:#111;text-decoration:none}}
.big{{display:block;text-align:center;padding:12px;border-radius:10px;background:#bf0000;color:#fff;font-weight:700;text-decoration:none}}
.cnt{{display:flex;align-items:center;gap:10px;margin-top:6px}}.cnt button{{padding:8px 14px;border:0;border-radius:8px;background:#111;color:#fff;font-weight:700}}
.cnt b{{font-size:1.1rem}}ul{{padding-left:1.2em;margin:6px 0}}.ng{{color:#b42318;font-size:.78rem}}a{{color:#2563eb}}</style></head><body>
<header><h1>楽天ROOM いいね・フォロー回り（{m}月{d}日）</h1><p>20〜22時に。上から順に、1件ずつ中身を見ながら手で</p></header>
<main>
<section><h2>① フォロー返し（最初に）</h2>
<p>フォローしてくれた人を確認して、同じジャンルの人にはフォローを返す。</p>
<a class="big" href="{e(me)}/followers" target="_blank" rel="noopener">自分のフォロワー一覧を開く</a></section>
<section><h2>② フォローする人を探す（目標 {FOLLOW_GOAL}人）</h2>
<ul><li>フォロワー<b>100〜3,000人</b>くらいで、<b>最近も投稿している</b>人がフォローを返してくれやすい</li>
<li>1万人をこえる人は返ってきにくいので、参考に見るだけでOK</li>
<li>自分と同じジャンル（収納・日用品・ふるさと納税）の人を選ぶ</li></ul>
{users}
<div class="cnt">フォローした数 <b id="f">0</b> / {FOLLOW_GOAL}<button onclick="add('f')">＋1</button></div></section>
<section><h2>③ いいね回り（目標 {LIKE_GOAL}件）</h2>
<p>今日のリストの商品ジャンルで探すと、同じものに興味がある人に届く。オリジナル写真の投稿を優先して、気に入ったものだけに。</p>
{items}
<div class="cnt">いいねした数 <b id="l">0</b> / {LIKE_GOAL}<button onclick="add('l')">＋1</button></div></section>
<section><h2>やらないこと</h2>
<p class="ng">自動ツール・AIエージェントでのいいね／フォロー、短時間での連打（制限がかかります）、フォロー解除をくり返すこと、「フォロー返してね」「私のROOMから買って」のお願い</p>
<p><a href="room.html">← 今日の投稿リストへ戻る</a></p></section>
</main>
<script>
const K='room-eng-{day}';let s={{f:0,l:0}};try{{s=Object.assign(s,JSON.parse(localStorage.getItem(K)||'{{}}'))}}catch(e){{}}
function show(){{document.getElementById('f').textContent=s.f;document.getElementById('l').textContent=s.l}}
function add(k){{s[k]++;try{{localStorage.setItem(K,JSON.stringify(s))}}catch(e){{}}show()}}
show();
</script></body></html>"""
    (out_dir / "room-engage.html").write_text(page, encoding="utf-8")
