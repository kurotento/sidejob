"""Threads 用の投稿を毎日作る（public/threads.html、検索除外）.

やり方：
  1. 「誰の・どんな悩みか」（ターゲット）と商品を組み合わせる
  2. Gemini に切り口の違う3パターン（共感・価格ギャップ・時短）を書かせ、5項目で採点させる
  3. いちばん点の高い案を本文に、リンクは1件目の返信（ひとことの誘導＋PR）に分ける
体験談のでっちあげ・効果の断定は書かせない（ステマ規制・薬機法）。材料は商品の事実だけ。
"""
import datetime as dt
import html
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from articles import short_name
from writer import BANNED, ENDPOINT, MODELS

CACHE = Path(__file__).resolve().parent / "data" / "threads_posts.json"
PER_DAY = 5
MAX_PRICE = 6000
e = html.escape

# ターゲット（ROOM・楽天の中心層＝30〜40代女性の悩み）と、商品を選ぶ場所
TARGETS = [
    ("収納が片付かない", "物が多くて部屋が片付かず、収納を見直したい30〜40代の女性", "interior"),
    ("家事をラクにしたい", "仕事や育児で忙しく、毎日の家事を少しでも短くしたい共働きの女性", "daily"),
    ("買い回りあと1店舗", "楽天お買い物マラソンで、あと1店舗を1000円台の必需品で済ませたい人", "budget"),
    ("ふるさと納税が決められない", "ふるさと納税をやりたいけど、どの返礼品にするか毎年迷う人", "furusato"),
    ("食費を浮かせたい", "物価が上がって食費や日用品代を少しでも抑えたい家庭", "budget"),
    ("寒くなってきた", "朝晩が冷えてきて、家の寒さ対策を考えはじめた人", "interior"),
]

SYSTEM = """あなたはThreadsで暮らしと買い物の情報を発信している、30代の女性アカウントの中の人です。
指定された「ターゲットの悩み」と「商品の事実」から、Threadsの投稿を3パターン書き、採点します。

3パターンの切り口:
 A 共感：ターゲットの悩みに「わかる」と思わせる1行目から入る
 B 価格ギャップ：価格や量（事実の数字）と中身の差で驚かせる
 C 時短・手軽さ：手間がどう減るかで引きつける

必ず守るルール:
- 自分が使った・食べた・買った・効果が出た、という体験談は絶対に書かない（「使ってみたら」「〜になったの」「リピ」「愛用」「届いた」は禁止）。共感は「〜って人多いよね」「〜な日ある」のように、相手側の気持ちで書く
- 商品情報にないことは書かない。効果・効能を断定しない（「治る」「消える」「痩せる」などは禁止）
- No.1・最安・大人気・話題・完璧・神アイテム などの言葉は使わない
- 1行目（フック）は25字以内で、続きを読みたくなる言い回しにする
- 本文は全体で90〜200字。改行を多めに。絵文字は0〜2個。ハッシュタグとURLは書かない
- 最後の1文は、コメントしたくなる問いかけか、保存したくなる一言にする

採点（各20点・合計100点）: フック力 / 具体性 / 共感性 / 意外性 / コメント誘発

出力は次のJSONだけ:
{"patterns":[{"type":"共感","text":"本文","scores":{"フック力":0,"具体性":0,"共感性":0,"意外性":0,"コメント誘発":0},"why":"なぜ伸びそうか1文"}, ...3件],
 "reply_lead":"返信欄でリンクの前に置く、ひとことの誘導（20字以内。例：気になる人はここから見られるよ）"}"""

EXPERIENCE = re.compile(r"使ってみ|使ったら|食べたら|飲んだら|になったの|変わったの|届いた|リピ|愛用|うちでは|我が家では|私は毎|治る|消える|痩せ")


def pick_items(results, budget, fcats, descs, used):
    """ターゲットごとに、まだ使っていない商品を1つずつ選ぶ."""
    pools = {"budget": budget or [], "furusato": [it for c in fcats or [] for it in c["items"]]}
    pools.update(results or {})
    out = []
    for label, who, src in TARGETS:
        for it in pools.get(src, []):
            if src != "furusato" and it["price"] > MAX_PRICE:  # 暮らしの悩み向けなので、手が届く価格の物だけ
                continue
            if it["code"] not in used and it["code"] not in {x["code"] for _, _, x in out}:
                out.append((label, who, it))
                break
    return out[:PER_DAY]


def call(prompt, key, model):
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9, "maxOutputTokens": 3000, "responseMimeType": "application/json"},
    }).encode()
    req = urllib.request.Request(ENDPOINT.format(model=model), data=body, headers={
        "Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=120) as res:
        raw = json.loads(res.read().decode("utf-8", "replace"))
    parts = raw["candidates"][0]["content"]["parts"]
    content = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return json.loads(re.search(r"\{.*\}", content, re.S).group(0))


def clean(d):
    """ルール違反の案を落とし、合計点の高い順に並べる."""
    pats = []
    for p in d.get("patterns", []):
        text = str(p.get("text", "")).strip()
        if not text or BANNED.search(text) or EXPERIENCE.search(text) or re.search(r"https?://|#", text):
            continue
        if not 60 <= len(re.sub(r"\s", "", text)) <= 240:
            continue
        sc = {k: int(v) for k, v in (p.get("scores") or {}).items() if str(v).isdigit()}
        pats.append({"type": p.get("type", ""), "text": text, "scores": sc, "total": sum(sc.values()), "why": p.get("why", "")})
    pats.sort(key=lambda x: -x["total"])
    lead = str(d.get("reply_lead", "")).strip()[:30] or "気になる人はここから見られるよ"
    return {"patterns": pats, "reply_lead": lead} if pats else None


def write(picks, descs, day):
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    key = os.environ.get("GEMINI_API_KEY")
    model = MODELS[0]
    for label, who, it in picks:
        ck = f"{day}:{it['code']}"
        if ck in cache:
            cache[ck].setdefault("url", it["url"])
            continue
        if not key:
            continue
        d = descs.get(it["code"]) or {"intro": it.get("caption", "")[:400]}
        prompt = (f"ターゲットの悩み: {who}\n商品名: {short_name(it['name'], 60)}\n価格: {it['price']:,}円\n"
                  f"レビュー: {it.get('reviews', 0):,}件 平均{it.get('rating', 0)}\n紹介文: {d.get('intro', '')}\n"
                  f"特徴: {' / '.join(d.get('features', []))}\n向いている人: {d.get('for_whom', '')}")
        for _ in range(2):
            try:
                r = clean(call(prompt, key, model))
            except urllib.error.HTTPError as ex:
                if ex.code == 404 and model != MODELS[-1]:
                    model = MODELS[MODELS.index(model) + 1]
                    continue
                r = None
                if ex.code == 429:
                    key = None
            except Exception:  # noqa: BLE001
                r = None
            time.sleep(7)
            if r or not key:
                break
        if r:
            cache[ck] = {**r, "url": it["url"]}
    cutoff = (dt.date.fromisoformat(day) - dt.timedelta(days=14)).isoformat()
    cache = {k: v for k, v in cache.items() if k[:10] >= cutoff}
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    return cache


def build(cfg, results, budget, fcats, descs, day, out_dir):
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    used = {k[11:] for k in cache if k[:10] != day}  # 2週間は同じ商品を使わない
    picks = pick_items(results, budget, fcats, descs, used)
    cache = write(picks, descs, day)
    cards = []
    for n, (label, who, it) in enumerate(picks):
        r = cache.get(f"{day}:{it['code']}")
        if not r:
            continue
        best, rest = r["patterns"][0], r["patterns"][1:]
        reply = f"{r['reply_lead']}👇\n{it['url']}\n#PR"
        bars = "".join(f"<span>{e(k)} {v}</span>" for k, v in best["scores"].items())
        others = "".join(f"""<details><summary>{e(p['type'])}案（{p['total']}点）</summary>
<textarea readonly rows="6">{e(p['text'])}</textarea><button onclick="cp(this)">この案をコピー</button></details>""" for p in rest)
        cards.append(f"""<article class="c"><p class="tg">🎯 {e(label)}｜{e(short_name(it['name'], 30))} {it['price']:,}円</p>
<p class="lb">① 本文（{e(best['type'])}案・{best['total']}点）</p><textarea readonly rows="8">{e(best['text'])}</textarea>
<button onclick="cp(this)">本文をコピー</button><p class="sc">{bars}</p><p class="why">{e(best['why'])}</p>
<p class="lb">② 投稿したら、自分の投稿に返信（リンクはこちら）</p><textarea readonly rows="4">{e(reply)}</textarea>
<button onclick="cp(this)">返信をコピー</button>{others}</article>""")
    m, d = int(day[5:7]), int(day[8:10])
    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Threads 投稿 {m}/{d}</title><style>
body{{margin:0;font-family:system-ui,"Hiragino Sans",sans-serif;background:#f4f4f4;color:#111}}
header{{background:#111;color:#fff;padding:14px 16px}}header h1{{font-size:1.1rem;margin:0}}header p{{margin:4px 0 0;font-size:.8rem;opacity:.85}}
main{{padding:12px;max-width:600px;margin:0 auto}}.c{{background:#fff;border-radius:14px;padding:12px;margin-bottom:14px}}
.tg{{margin:0 0 8px;font-weight:700;font-size:.9rem}}.lb{{margin:10px 0 4px;font-size:.8rem;color:#555;font-weight:700}}
textarea{{width:100%;box-sizing:border-box;font-size:.88rem;border:1px solid #ddd;border-radius:8px;padding:8px;line-height:1.5}}
button{{width:100%;margin-top:6px;padding:10px;border:0;border-radius:10px;background:#111;color:#fff;font-weight:700}}
.sc span{{display:inline-block;font-size:.72rem;background:#f0f0f0;border-radius:999px;padding:2px 8px;margin:4px 4px 0 0}}
.why{{font-size:.78rem;color:#555;margin:4px 0 0}}details{{margin-top:8px;font-size:.85rem}}
.tip{{background:#fff8e1;border-radius:12px;padding:10px 14px;font-size:.84rem;margin-bottom:12px}}.tip li{{margin:3px 0}}</style></head><body>
<header><h1>Threads 投稿リスト（{m}月{d}日）</h1><p>悩み別に5本。本文 → 投稿 → 自分の投稿にリンクを返信</p></header>
<main><div class="tip"><b>使い方</b><ol>
<li>①の本文をコピーして投稿（いちばん点の高い案を上に出しています。ほかの案は下から選べます）</li>
<li>投稿できたら、その投稿に②を返信（リンクは本文ではなく返信に入れる）</li>
<li>「#PR」は消さない。自分が使っていない物を「使ってよかった」と書き足さない</li>
<li>1日2〜5本、時間をあけて。昼12時台・夜21時台が見られやすい</li></ol></div>
{''.join(cards) or '<p>今日の投稿はまだ作られていません。</p>'}</main>
<script>async function cp(b){{const t=b.previousElementSibling;try{{await navigator.clipboard.writeText(t.value)}}catch(e){{t.select();document.execCommand('copy')}}const o=b.textContent;b.textContent='コピーしました';setTimeout(()=>b.textContent=o,1500)}}</script>
</body></html>"""
    (out_dir / "threads.html").write_text(page, encoding="utf-8")
    return len(cards)
