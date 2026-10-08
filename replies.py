"""X の返信用「ネタ帳」ページ（public/replies.html、検索除外）を毎日作る.

返信はユーザーが手で行う（自動返信は X のルールで禁止）。
その日の売れ筋データを差し込んだ答えの例と、探すための検索リンクをまとめる。
"""
import html
import urllib.parse

from articles import short_name

e = html.escape

# 単語だけで探すと宣伝ボットの投稿ばかり出るので、困っている人の言い回しで探し、
# リンク付き・#PR・プレゼント企画などを除外する
NOISE = " lang:ja -filter:links -filter:retweets -PR -ROOM -アフィリエイト -プレゼント -キャンペーン -応募 -フォロー"
SEARCHES = [
    ("ふるさと納税 どれにしよう", '"ふるさと納税" ("迷う" OR "迷って" OR "決まらない" OR "どれにしよう" OR "悩む" OR "悩んで")'),
    ("ふるさと納税 おすすめ教えて", '"ふるさと納税" ("おすすめ教えて" OR "オススメ教えて" OR "おすすめある" OR "おすすめありますか" OR "何がいい")'),
    ("ふるさと納税 よくわからない", '"ふるさと納税" ("わからない" OR "分からない" OR "よくわからん" OR "初めて" OR "やり方")'),
    ("返礼品が届いた", '"ふるさと納税" ("届いた" OR "美味しかった" OR "おいしかった")'),
    ("マラソン 何買うか迷う", '("買い回り" OR "マラソン") ("何買う" OR "何買お" OR "買うもの" OR "決まらない")'),
    ("あと1店舗たりない", '("あと1店舗" OR "あと一店舗" OR "あと1ショップ" OR "あと何店舗")'),
    ("楽天 買ってよかった", '"楽天" ("買ってよかった" OR "買って良かった" OR "リピ買い")'),
]


def nm(it, n=20):
    """返信文に入れる商品名。途中で切れないよう、単語の区切りで短くする."""
    out = ""
    for w in short_name(it["name"], 80).split():
        if out and len(out) + 1 + len(w) > n:
            break
        out = (out + " " + w).strip()
    return out[: n + 6]


def build(cfg, budget, fcats, day, out_dir):
    m, d = int(day[5:7]), int(day[8:10])
    b = budget or []
    cat = {c["slug"]: c["items"] for c in fcats or []}
    pool = sorted({it["code"]: it for c in fcats or [] for it in c["items"]}.values(), key=lambda x: -x["reviews"])
    under10k = [it for it in pool if it["price"] <= 10000]

    qa = []
    if len(b) >= 2:
        qa.append(("買い回り、あと1店舗なに買おう？",
                   f"迷ったら消耗品が無難です！今日の楽天だと「{nm(b[0])}」{b[0]['price']:,}円や"
                   f"「{nm(b[1])}」{b[1]['price']:,}円あたりが送料無料で売れてますよ #PR"))
        qa.append(("1000円ちょうどくらいで送料無料のものない？",
                   f"1000円台で送料無料なら「{nm(b[2] if len(b) > 2 else b[0])}」がよく売れてます。"
                   "クーポンで1000円を下回らないよう、少し上の金額を選ぶのがコツです #PR"))
    qa.append(("お買い物マラソンっていつから？",
               "開催日は楽天の公式キャンペーンページで確認できます。エントリーが必要なので、始まる前に済ませておくと安心ですよ"))
    qa.append(("ポイントって何倍になるの？",
               "買い回りしたショップ数や、エントリーの有無、楽天カードの利用などで変わります。上限や条件は回ごとに違うので、公式ページで確認するのが確実です"))
    qa.append(("ふるさと納税、はじめてで何からやれば？",
               "まず楽天ふるさと納税の「寄付限度額シミュレーター」で上限の目安を出すのがおすすめです。"
               "そのあと、お米やお肉みたいに普段買うものから選ぶと失敗しにくいですよ"))
    qa.append(("ふるさと納税、結局どれがお得？",
               "人によりますが、普段買うもの（お米・お肉・日用品）を選ぶと家計に一番効く気がします。"
               "迷ったらレビューが多い定番から選ぶと安心です"))
    if len(cat.get("rice", [])) >= 2:
        r = cat["rice"]
        qa.append(("ふるさと納税でお米のおすすめある？",
                   f"レビューが多いのだと「{nm(r[0])}」（{r[0]['shop']}・寄付{r[0]['price']:,}円）や"
                   f"「{nm(r[1])}」（{r[1]['shop']}）が人気ですよ #PR"))
    if len(cat.get("meat", [])) >= 2:
        r = cat["meat"]
        qa.append(("ふるさと納税でお肉のおすすめは？",
                   f"「{nm(r[0])}」（{r[0]['shop']}・寄付{r[0]['price']:,}円）はレビューがかなり多くて定番です #PR"))
    if len(under10k) >= 2:
        qa.append(("ふるさと納税、1万円以内でいいのある？",
                   f"1万円以内だと「{nm(under10k[0])}」（寄付{under10k[0]['price']:,}円）や"
                   f"「{nm(under10k[1])}」（寄付{under10k[1]['price']:,}円）がレビュー多めで人気です #PR"))
    qa.append(("（返礼品が届いた・美味しかった という投稿に）",
               "おいしそう！それ気になってました。量はどのくらいでした？参考にさせてください"))
    qa.append(("（楽天で買ってよかった という投稿に）",
               "それ良さそうですね！どのくらい使ってますか？自分も買い回りの候補に入れようか迷ってました"))
    qa.append(("ふるさと納税っていつまでにやればいい？",
               "その年の控除の対象になるのは12月31日までの寄付です。年末は申し込みも配送も混むので、早めがおすすめです"))
    qa.append(("ワンストップ特例ってなに？",
               "確定申告をしない人が、条件を満たせば申請書を出すだけで控除を受けられる仕組みです。"
               "寄付先の数などに条件があるので、自治体や楽天のガイドで確認してくださいね"))

    search_links = "".join(
        f'<a class="s" href="https://x.com/search?q={urllib.parse.quote(q + NOISE)}&f=live" target="_blank" rel="noopener">🔍 {e(label)}</a>'
        for label, q in SEARCHES)
    cards = "".join(f"""<article class="c"><p class="q">Q. {e(q)}</p><textarea readonly rows="4">{e(a)}</textarea>
<button onclick="cp(this)">返信文をコピー</button></article>""" for q, a in qa)
    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>返信ネタ帳 {m}/{d}</title><style>
body{{margin:0;font-family:system-ui,"Hiragino Sans",sans-serif;background:#f6f4f0;color:#1d1d1f}}
header{{background:#111;color:#fff;padding:14px 16px}}header h1{{font-size:1.1rem;margin:0}}header p{{margin:4px 0 0;font-size:.8rem;opacity:.85}}
main{{padding:12px;max-width:560px;margin:0 auto}}h2{{font-size:1rem;margin:18px 0 8px}}
.s{{display:inline-block;margin:0 6px 8px 0;padding:8px 12px;border-radius:999px;background:#fff;border:1px solid #ddd;color:#111;text-decoration:none;font-size:.85rem}}
.c{{background:#fff;border-radius:14px;padding:12px;margin-bottom:12px}}.q{{margin:0 0 6px;font-weight:700;font-size:.92rem}}
textarea{{width:100%;box-sizing:border-box;font-size:.85rem;border:1px solid #ddd;border-radius:8px;padding:8px}}
button{{width:100%;margin-top:6px;padding:10px;border:0;border-radius:10px;background:#111;color:#fff;font-weight:700}}
.tip{{background:#fff8e1;border-radius:12px;padding:10px 14px;font-size:.85rem}}.tip li{{margin:4px 0}}</style></head><body>
<header><h1>𝕏 返信ネタ帳（{m}月{d}日）</h1><p>①検索で困っている人を探す → ②近い質問の答えをコピー → 自分の言葉に少し直して返信</p></header>
<main>
<div class="tip"><b>使うときの注意</b><ul>
<li>同じ文をそのまま何度も貼らない（スパム扱いされます）。必ず少し言い換えてね</li>
<li>商品をすすめる返信には「#PR」を残す（ステマ規制）</li>
<li>リンクは貼らないのが基本。気になった人はプロフィールを見に来てくれます</li>
<li>1日5〜10件、相手の質問にちゃんと答えるのがコツ</li></ul></div>
<h2>① 探す（X の最新の投稿を開きます）</h2><p style="font-size:.8rem;margin:0 0 8px">リンク付き・#PR・プレゼント企画などの宣伝投稿は除いて検索します。出てこない日は、少し時間をおいて開き直してね</p>{search_links}
<h2>② 答える（今日の売れ筋入り）</h2>{cards}
</main>
<script>async function cp(b){{const t=b.previousElementSibling;try{{await navigator.clipboard.writeText(t.value)}}catch(e){{t.select();document.execCommand('copy')}}b.textContent='コピーしました';setTimeout(()=>b.textContent='返信文をコピー',1500)}}</script>
</body></html>"""
    (out_dir / "replies.html").write_text(page, encoding="utf-8")
    return len(qa)
