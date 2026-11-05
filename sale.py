"""楽天のセール（お買い物マラソン・スーパーSALE）の記事ページ（sale.html）とトップのバナー.

セールの日程・条件は data/sales.json に、楽天の公式ページで確かめた値だけを書く（ここで推測しない）。
エントリーページ・クーポンページへのリンクはアフィリエイトリンクにする（商品が決まっていない人にも踏んでもらえる入り口）。
開催中のセールがないときは、ページを「次のセールまでお待ちください」にする（URL は残す）。
"""
import datetime as dt
import html
import json
import os
import urllib.parse
from pathlib import Path

SALES = Path(__file__).resolve().parent / "data" / "sales.json"
PATH = "sale.html"
WEEK = "月火水木金土日"
e = html.escape


def current(day):
    if not SALES.exists():
        return None
    sales = json.loads(SALES.read_text(encoding="utf-8"))
    return next((s for s in sales if s["start"][:10] <= day <= s["end"][:10]), None)


def when(iso):
    t = dt.datetime.fromisoformat(iso)
    return f"{t.month}月{t.day}日（{WEEK[t.weekday()]}）{t.hour}:{t.minute:02d}"


def aff(url):
    """楽天のページへのアフィリエイトリンク（ID がないときはそのまま）."""
    aid = os.environ.get("RAKUTEN_AFFILIATE_ID")
    if not aid:
        return url
    q = urllib.parse.quote(url, safe="")
    return f"https://hb.afl.rakuten.co.jp/hgc/{aid}/?pc={q}&m={q}"


def button(url, label):
    return (f'<p style="text-align:center;margin:1.2em 0"><a class="cta" href="{e(aff(url))}" target="_blank" '
            f'rel="nofollow sponsored noopener" style="display:inline-block;padding:14px 28px;font-size:1rem">{e(label)}</a></p>')


def banner(cfg, day):
    """トップに出すお知らせ（開催中だけ）."""
    s = current(day)
    if not s:
        return ""
    return (f'<a class="banner" href="{PATH}" style="margin-top:16px;background:linear-gradient(135deg,#fff1f2,#fff7e6);border-color:#fecdd3">'
            f'<span style="font-size:2.6rem">🏃</span><div><b>{e(s["name"])} 開催中（{e(when(s["end"]))}まで）</b>'
            f'<small>エントリーとクーポンの取り方、お店の数のかせぎ方</small></div><span class="cta">読む</span></a>')


def build(cfg, day, updated, demo, out_dir):
    """sale.html を書く。返り値はサイトマップに足すパス（開催中でなければ空）."""
    import articles
    from render import page
    s = current(day)
    budget_slug = cfg["budget"]["slug"] if cfg.get("budget") else ""
    if not s:
        body = ('<article class="post"><h1>楽天のセール情報</h1><p>いまは開催中のお買い物マラソン・スーパーSALEはありません。'
                '始まったらこのページでエントリーとクーポンの取り方をお知らせします。</p></article>')
        (out_dir / PATH).write_text(page(cfg, "楽天のセール情報", body, PATH, demo, updated, extra_css=articles.CSS), encoding="utf-8")
        return []
    a, b = dt.datetime.fromisoformat(s["start"]), dt.datetime.fromisoformat(s["end"])
    title = f"楽天{s['name']}（{a.month}/{a.day}〜{b.month}/{b.day}）エントリーとクーポンの取り方"
    hero = (f'<section class="hero"><div class="wrap"><span class="kicker">PR・{e(when(s["end"]))}まで</span>'
            f'<h1>{e(s["name"])}、<br>やることは3つだけ。</h1><p>エントリー・1店1,000円以上・クーポン。'
            f'条件は楽天の公式ページで確かめた内容です（{e(s["checked"][:10])}時点）。</p></div></section>')
    budget_link = (f'<p>1,000円台で送料無料の売れ筋は、<a href="{budget_slug}.html">1000円台の買い回りまとめ</a>に毎日入れ替えて載せています。'
                   'お店の数を増やすときに使ってください。</p>') if budget_slug else ""
    body = f"""<article class="post">
<p class="lead">楽天の{e(s["name"])}は、<b>{e(when(s["start"]))}〜{e(when(s["end"]))}</b>までです。
買ったお店の数に応じてポイントの倍率が上がるキャンペーンで、参加するにはエントリーが必要です。</p>
<div class="toc"><b>目次</b><ol><li><a href="#entry">エントリーする</a></li><li><a href="#shops">1店1,000円以上で、お店の数を増やす</a></li>
<li><a href="#coupon">クーポンを先に取る</a></li><li><a href="#caution">気をつけること</a></li></ol></div>
<h2 id="entry">1. エントリーする</h2>
<p>キャンペーンのページにある「エントリー」のボタンを押すだけです。エントリーする前に買った分も、期間中のお買い物なら対象になります。</p>
{button(s["entry_url"], "エントリーのページを開く（楽天）")}
<h2 id="shops">2. 1店1,000円以上で、お店の数を増やす</h2>
<p>1つのお店での合計が1,000円（税込）以上になると、1店として数えられます。999円以下は数えられません。</p>
<p>2店目からポイントの倍率が上がり、ショップ買いまわりは<b>{e(s["kaimawari"])}</b>です。
SPUやショップごとのポイントアップを合わせると{e(s["max_total"])}になります（一部は別にエントリーが要ります）。</p>
{budget_link}
{articles.talk("欲しいものが決まっていたら、そのお店で1,000円以上になるように、日用品などを足すとお店の数を増やしやすいよ。")}
<h2 id="coupon">3. クーポンを先に取る</h2>
<p>期間中は、ショップのクーポンやまとめ買いのクーポンが配られています。クーポンは<b>使う前に「取得」しておかないと使えません</b>。
買い物かごに入れる前に、クーポンのページで取っておきましょう。</p>
{button(s["coupon_url"], "クーポンのページを開く（楽天）")}
<h2 id="caution">気をつけること</h2>
<p>{e(s["caution"].replace(chr(10), ""))}（2025年10月から）。ポイントの計算には入れずに考えておくと安心です。</p>
<p>ポイントには上限があり、もらえるのは期間限定ポイントです。条件は変わることがあるので、最終的には楽天の公式ページで確かめてください。</p>
<p class="note">このページには楽天アフィリエイトのリンクを含みます（PR）。掲載の条件は{e(s["checked"])}した内容です。</p>
</article>"""
    (out_dir / PATH).write_text(page(cfg, title, body, PATH, demo, updated, hero=hero, extra_css=articles.CSS), encoding="utf-8")
    return [PATH]
