"""楽天のセール（お買い物マラソン・スーパーSALE）の記事ページ（sale.html）とトップのバナー.

セールの日程・条件は data/sales.json に、楽天の公式ページで確かめた値だけを書く（ここで推測しない）。
エントリーページ・クーポンページへのリンクはアフィリエイトリンクにする（商品が決まっていない人にも踏んでもらえる入り口）。

検索対策（2026-11-05 に調べた内容）:
- URL は sale.html に固定し、セールのたびに中身を差し替える（回ごとに新しい URL を作ると評価が積み上がらない）
- 題名は検索される言葉を左に寄せ、年月を入れる（「楽天お買い物マラソン【2026年11月】いつまで？」）
- 冒頭に結論（期間・やること）を置く。見出しは検索される言い方（いつまで・エントリー方法・クーポンの取り方）
- ほかのサイトにない情報として、このサイトの毎朝のランキングから「セール中に売れている1000円台」を載せる（毎日変わる）
- 出典（楽天の公式ページ）と確かめた日を書く。よくある質問は本文に書く（FAQ のリッチリザルトは 2026 年に終わったので構造化データは Article と パンくずだけ）
- セールのない日も「次回の目安・これまでの日程・しくみ」を載せ、「次回いつ」で探す人にも役立つページにする
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


def load():
    return json.loads(SALES.read_text(encoding="utf-8")) if SALES.exists() else []


def current(day):
    return next((s for s in load() if s["start"][:10] <= day <= s["end"][:10]), None)


def when(iso, time=True):
    t = dt.datetime.fromisoformat(iso)
    return f"{t.month}月{t.day}日（{WEEK[t.weekday()]}）" + (f"{t.hour}:{t.minute:02d}" if time else "")


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


def ld_json(cfg, title, desc, published, modified):
    """構造化データ（記事・パンくず）."""
    base = cfg["base_url"].rstrip("/")
    data = [
        {"@context": "https://schema.org", "@type": "Article", "headline": title[:110], "description": desc,
         "datePublished": published, "dateModified": modified, "inLanguage": "ja",
         "mainEntityOfPage": f"{base}/{PATH}",
         "author": {"@type": "Organization", "name": cfg["site_name"], "url": f"{base}/about.html"},
         "publisher": {"@type": "Organization", "name": cfg["site_name"], "url": f"{base}/"}},
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": cfg["site_name"], "item": f"{base}/"},
            {"@type": "ListItem", "position": 2, "name": "楽天のセール情報", "item": f"{base}/{PATH}"}]},
    ]
    return "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in data)


def faq(items):
    return '<h2 id="faq">よくある質問</h2>' + "".join(f"<h3>Q. {e(q)}</h3><p>{a}</p>" for q, a in items)


def selling_now(budget, cfg, limit=5):
    """このサイトの今朝のランキングから、セール中に売れている1000円台（ほかのサイトにない、毎日変わる情報）."""
    from articles import short_name
    from itemfilter import excluded, pick_varied
    if not budget:
        return ""
    picks = pick_varied([it for it in budget if not excluded(it)], limit)
    if not picks:
        return ""
    rows = "".join(f'<li><a href="{e(it["url"])}" target="_blank" rel="nofollow sponsored noopener">{e(short_name(it["name"], 40))}</a>'
                   f'　{it["price"]:,}円（★{it["rating"]:.1f}・レビュー{it["reviews"]:,}件）</li>' for it in picks)
    slug = cfg["budget"]["slug"] if cfg.get("budget") else ""
    more = f'<p>ほかの商品は<a href="{slug}.html">1000円台・送料無料の売れ筋まとめ</a>に載せています。</p>' if slug else ""
    return (f'<h2 id="now">いま売れている1000円台・送料無料（毎朝更新）</h2>'
            f'<p>このサイトで毎朝集めている楽天のランキングから、送料無料で1,000円台の商品を、似た物が並ばないように選んでいます。'
            f'お店の数を1つ増やしたいときの候補にどうぞ。</p><ol>{rows}</ol>{more}')


def build(cfg, day, updated, demo, out_dir, budget=None):
    """sale.html を書く。返り値はサイトマップに足すパス."""
    import articles
    from render import page
    sales = load()
    s = current(day)
    past = sorted((x for x in sales if x["end"][:10] < day), key=lambda x: x["start"], reverse=True)
    history = ("<h2 id=\"history\">これまでの開催日程</h2><ul>"
               + "".join(f"<li>{e(x['name'])}：{e(when(x['start']))}〜{e(when(x['end']))}</li>" for x in past[:8])
               + "</ul>") if past else ""
    if not s:
        last = past[0] if past else None
        title = "楽天お買い物マラソンは次いつ？エントリーとクーポンの取り方"
        desc = "楽天のお買い物マラソン・スーパーSALEの次回の目安と、これまでの開催日程、エントリーやクーポンの取り方をまとめています。開催が始まったら日程を更新します。"
        body = f"""<article class="post"><p class="lead">いまは開催中のお買い物マラソン・スーパーSALEはありません。始まったら、このページで日程・エントリー・クーポンの取り方を更新します。</p>
{('<p>前回は' + e(last['name']) + '（' + e(when(last['start'])) + '〜' + e(when(last['end'])) + '）でした。</p>') if last else ''}
<h2>お買い物マラソンのしくみ</h2><p>期間中にエントリーして、1つのお店で1,000円（税込）以上買うと1店として数えられ、お店の数に応じてポイントの倍率が上がります。
エントリーの前に買った分も、期間中なら対象になります。クーポンは使う前に取っておく必要があります。</p>
{history}
<p class="note">このページには楽天アフィリエイトのリンクを含みます（PR）。日程・条件は楽天の公式ページで確かめた内容だけを載せています。</p></article>"""
        head = ld_json(cfg, title, desc, day, day)
        (out_dir / PATH).write_text(page(cfg, title, body, PATH, demo, updated, active="sale", extra_css=articles.CSS, description=desc, head=head),
                                    encoding="utf-8")
        return [PATH]
    a, b = dt.datetime.fromisoformat(s["start"]), dt.datetime.fromisoformat(s["end"])
    title = f"楽天{s['name']}【{a.year}年{a.month}月】いつまで？エントリー・クーポンの取り方"
    desc = (f"楽天{s['name']}は{when(s['start'])}〜{when(s['end'])}。エントリー方法、クーポンの取り方、"
            f"ポイント{s['kaimawari_say']}になる買い回りの条件を、楽天の公式ページで確かめてまとめました。いま売れている1000円台も毎朝更新。")
    hero = (f'<section class="hero"><div class="wrap"><span class="kicker">PR・{e(when(s["end"]))}まで</span>'
            f'<h1>楽天{e(s["name"])}（{a.year}年{a.month}月）は<br>{e(when(s["end"]))}まで</h1>'
            f'<p>やることは、エントリー・1店1,000円以上・クーポンの3つ。{e(updated[:10])}更新。</p></div></section>')
    summary = (f'<div class="toc" style="background:#fff7e6;border-color:#f3e2c0"><b>結論：やることは3つ</b><ol>'
               f'<li>エントリーする（買ったあとでもOK）</li><li>1つのお店で1,000円以上買い、お店の数を増やす（{e(s["kaimawari"])}）</li>'
               f'<li>クーポンは使う前に取っておく</li></ol><p style="margin:.4em 0 0">期間：{e(when(s["start"]))}〜{e(when(s["end"]))}</p></div>')
    budget_slug = cfg["budget"]["slug"] if cfg.get("budget") else ""
    budget_link = (f'<p>1,000円台で送料無料の売れ筋は、<a href="{budget_slug}.html">1000円台の買い回りまとめ</a>に毎日入れ替えて載せています。</p>'
                   if budget_slug else "")
    questions = [
        (f"{s['name']}はいつからいつまで？", f"{e(when(s['start']))}から{e(when(s['end']))}までです。"),
        ("エントリーの前に買った分も対象になる？", "期間中にエントリーすれば、エントリー前のお買い物も買いまわりの対象になります（楽天の公式ページの記載）。"),
        ("何円から1店として数えられる？", "1つのお店での合計が1,000円（税込）以上で1店です。999円以下は数えられません。"),
        ("クーポンはどこで取る？", "キャンペーンのクーポンページや、各ショップのページで「取得」します。取らないと使えないので、買う前に取っておきます。"),
        ("ふるさと納税はポイントの対象？", e(s["caution"].replace("\n", "")) + "（2025年10月から）。"),
    ]
    body = f"""<article class="post">
<p class="lead">楽天の{e(s["name"])}は、<b>{e(when(s["start"]))}〜{e(when(s["end"]))}</b>までです。
買ったお店の数に応じてポイントの倍率が上がるキャンペーンで、参加するにはエントリーが必要です。</p>
{summary}
<div class="toc"><b>目次</b><ol><li><a href="#entry">エントリー方法</a></li><li><a href="#shops">ポイントが上がる条件（買い回り）</a></li>
<li><a href="#coupon">クーポンの取り方</a></li><li><a href="#now">いま売れている1000円台</a></li><li><a href="#faq">よくある質問</a></li></ol></div>
<h2 id="entry">エントリー方法</h2>
<p>キャンペーンのページにある「エントリー」のボタンを押すだけです。エントリーする前に買った分も、期間中のお買い物なら対象になります。</p>
{button(s["entry_url"], "エントリーのページを開く（楽天）")}
<h2 id="shops">ポイントが上がる条件（買い回り）</h2>
<p>1つのお店での合計が1,000円（税込）以上になると、1店として数えられます。999円以下は数えられません。</p>
<p>2店目からポイントの倍率が上がり、ショップ買いまわりは<b>{e(s["kaimawari"])}</b>です。
SPUやショップごとのポイントアップを合わせると{e(s["max_total"])}になります（一部は別にエントリーが要ります）。</p>
{budget_link}
{articles.talk("欲しいものが決まっていたら、そのお店で1,000円以上になるように日用品などを足すと、お店の数を増やしやすいよ。")}
<h2 id="coupon">クーポンの取り方</h2>
<p>期間中は、ショップのクーポンやまとめ買いのクーポンが配られています。クーポンは<b>使う前に「取得」しておかないと使えません</b>。
買い物かごに入れる前に、クーポンのページで取っておきましょう。</p>
{button(s["coupon_url"], "クーポンのページを開く（楽天）")}
{selling_now(budget, cfg)}
<h2 id="caution">気をつけること</h2>
<p>{e(s["caution"].replace(chr(10), ""))}（2025年10月から）。ポイントの計算には入れずに考えておくと安心です。</p>
<p>ポイントには上限があり、もらえるのは期間限定ポイントです。条件は変わることがあるので、最終的には楽天の公式ページで確かめてください。</p>
{faq(questions)}
{history}
<p class="note">出典：<a href="{e(s["entry_url"])}" target="_blank" rel="noopener">楽天市場 {e(s["name"])} 公式ページ</a>（{e(s["checked"])}）。
このページには楽天アフィリエイトのリンクを含みます（PR）。</p>
</article>"""
    head = ld_json(cfg, title, desc, s["checked"][:10], day)
    (out_dir / PATH).write_text(page(cfg, title, body, PATH, demo, updated, active="sale", hero=hero, extra_css=articles.CSS, description=desc, head=head),
                                encoding="utf-8")
    return [PATH]
