"""ブログ風ページ：1000円台の買い回り記事と、商品ごとの紹介ページ.

紹介文はすべて取得データ（価格・レビュー・順位・ポイント等）から組み立てる。
使用していない商品の体験談は書かない（ステマ規制・楽天アフィリエイト規約のため）。
"""
import hashlib
import re

from render import e, flags, link_attrs, page, stars, thumb

MASCOT = """<svg viewBox="0 0 64 64" aria-hidden="true"><path d="M20 10l5 6 7-9 7 9 5-6-2 10H22z" fill="#f2c230"/>
<circle cx="16" cy="24" r="8" fill="#a8693a"/><circle cx="48" cy="24" r="8" fill="#a8693a"/><circle cx="16" cy="24" r="4" fill="#e9b88c"/><circle cx="48" cy="24" r="4" fill="#e9b88c"/>
<circle cx="32" cy="38" r="21" fill="#b97a45"/><ellipse cx="32" cy="45" rx="10" ry="8" fill="#f1d3b3"/>
<circle cx="24" cy="35" r="2.6" fill="#2b1b10"/><circle cx="40" cy="35" r="2.6" fill="#2b1b10"/><ellipse cx="32" cy="41.5" rx="3.4" ry="2.4" fill="#2b1b10"/>
<path d="M28 47q4 3 8 0" stroke="#2b1b10" stroke-width="1.6" fill="none" stroke-linecap="round"/><circle cx="19" cy="42" r="2.6" fill="#f08a8a" opacity=".6"/><circle cx="45" cy="42" r="2.6" fill="#f08a8a" opacity=".6"/></svg>"""
MASCOT_NAME = "らんくま"

CSS = """
.post{max-width:780px;margin:-28px auto 0;position:relative;z-index:2;background:var(--card);border-radius:18px;box-shadow:var(--shadow);padding:28px clamp(16px,4vw,40px) 36px}
.post h2{font-size:1.25rem;font-weight:900;margin:2.2em 0 .8em;padding:.55em .8em;background:#fff4f5;border-left:6px solid var(--red);border-radius:4px}
.post h3{font-size:1.08rem;font-weight:900;margin:0 0 .6em;line-height:1.5}
.post p{margin:.8em 0}.post .lead{font-size:.95rem}
.talk{display:flex;gap:12px;align-items:flex-start;margin:1.2em 0}
.talk .face{flex:none;width:60px;text-align:center;font-size:.64rem;color:var(--sub);font-weight:700}
.talk .face svg{width:56px;height:56px;background:#fff7e6;border-radius:50%;border:2px solid #f3e2c0;display:block;margin:0 auto 2px}
.talk .bubble{position:relative;background:#fffaf0;border:2px solid #f3e2c0;border-radius:14px;padding:10px 14px;font-size:.9rem;line-height:1.7}
.talk .bubble:before{content:"";position:absolute;left:-9px;top:18px;border:8px solid transparent;border-right-color:#f3e2c0;border-left:0}
.toc{background:#faf8f4;border:1px solid var(--line);border-radius:12px;padding:14px 20px;font-size:.88rem;margin:1.4em 0}
.toc b{display:block;margin-bottom:4px}.toc ol{margin:0;padding-left:1.4em}.toc a{color:#2563eb;text-decoration:underline}
.note{font-size:.78rem;color:var(--sub);background:#faf8f4;border-radius:10px;padding:10px 14px}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:.6em 0 1em;align-items:center}
.filters button{font:inherit;font-size:.8rem;font-weight:700;padding:6px 14px;border-radius:999px;border:1.5px solid var(--line);background:#fff;color:#444;cursor:pointer}
.filters button[aria-pressed=true]{background:var(--ink);border-color:var(--ink);color:#fff}
.filters .count{font-size:.8rem;color:var(--sub);margin-left:auto}
.pitem{border:1px solid var(--line);border-radius:16px;padding:18px;margin:16px 0;scroll-margin-top:120px}
.pitem .no{display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:30px;border-radius:8px;background:var(--ink);color:#fff;font-size:.9rem;margin-right:8px;vertical-align:2px}
.pitem .no.n1{background:var(--gold)}.pitem .no.n2{background:var(--silver)}.pitem .no.n3{background:var(--bronze)}
.pbox{display:grid;grid-template-columns:200px 1fr;gap:18px;align-items:start}
.pbox .pic{background:#fff;border:1px solid #f0ede7;border-radius:12px;aspect-ratio:1;display:grid;place-items:center;position:relative}
.pbox .pic img{width:88%;height:88%;object-fit:contain}.pbox .pic .flags{position:absolute;right:8px;top:8px;display:flex;flex-direction:column;gap:4px;align-items:flex-end}
.facts{list-style:none;margin:0;padding:0;font-size:.84rem;display:grid;gap:4px}
.facts li{display:flex;gap:8px;border-bottom:1px dashed var(--line);padding-bottom:4px}.facts li span{flex:none;width:5.5em;color:var(--sub)}
.big-yen{font-size:1.5rem;font-weight:900;color:var(--red)}.big-yen small{font-size:.8rem}
.points{background:#f3fbf6;border:1px solid #cdebd8;border-radius:12px;padding:12px 16px;margin:12px 0;font-size:.88rem}
.points b{color:var(--good)}.points ul{margin:.3em 0 0;padding-left:1.3em}
.btns{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}
.btns .cta{margin:0}
.spec{width:100%;border-collapse:collapse;font-size:.86rem;margin:.6em 0}
.spec th,.spec td{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
.spec th{background:#faf8f4;width:8em;font-weight:700}
.quote{border-left:4px solid var(--line);background:#faf8f4;padding:10px 14px;font-size:.84rem;color:#444;border-radius:0 8px 8px 0}
.trend{width:100%;height:auto;background:#fcfbf9;border:1px solid var(--line);border-radius:10px}
.hero-img{max-width:340px;margin:0 auto;background:#fff;border:1px solid #f0ede7;border-radius:14px;aspect-ratio:1;display:grid;place-items:center}
.hero-img img{width:90%;height:90%;object-fit:contain}
.banner{display:flex;align-items:center;gap:16px;background:linear-gradient(135deg,#fff7e6,#ffe9ec);border:2px solid #f6d7b0;border-radius:18px;padding:18px 20px;margin-top:-24px;position:relative;z-index:2;box-shadow:var(--shadow)}
.banner svg{width:64px;height:64px;flex:none}.banner b{display:block;font-size:1.05rem;font-weight:900}.banner small{color:var(--sub)}
.banner .cta{margin:0 0 0 auto;white-space:nowrap;padding:10px 18px}
@media (max-width:760px){.pbox{grid-template-columns:1fr}.pbox .pic{max-width:260px;margin:0 auto;width:100%}.btns{grid-template-columns:1fr}
 .banner{flex-wrap:wrap}.banner .cta{margin:0;width:100%}}
"""


def slug_of(code):
    return "item-" + re.sub(r"[^A-Za-z0-9_-]", "-", code) + ".html"


PROMO = re.compile(r"セール|SALE|限定|OFF|オフ|クーポン|ポイント|送料無料|予定|期間|マラソン|スーパー|半額|最大|\d+%|\d+％|円|お得|先着|まで|迄")


def short_name(name, limit=42):
    """商品名から宣伝文句を除き、商品そのものを表す部分を取り出す."""
    parts = re.split(r"[【】\[\]＼／★☆※●■◆♪!！]", name)
    parts = [re.sub(r"\s+", " ", x).strip() for x in parts]
    good = [x for x in parts if len(x) >= 8 and not PROMO.search(x)]
    n = good[0] if good else max(parts, key=len)
    return n if len(n) <= limit else n[:limit].rstrip() + "…"


def pick(code, options):
    h = int(hashlib.md5(code.encode()).hexdigest(), 16)
    return options[h % len(options)]


def talk(text):
    return (f'<div class="talk"><div class="face">{MASCOT}{MASCOT_NAME}</div>'
            f'<div class="bubble">{text}</div></div>')


def point_list(it):
    pts = [f"楽天総合ランキング <b>{it['rank']}位</b>（1000円台・送料無料の中で上位）"]
    if it["reviews"] >= 1000:
        pts.append(f"レビュー <b>{it['reviews']:,}件</b> の定番人気")
    elif it["reviews"] >= 100:
        pts.append(f"レビュー {it['reviews']:,}件")
    if it["rating"] >= 4.5 and it["reviews"] >= 30:
        pts.append(f"平均 <b>★{it['rating']:.2f}</b> の高評価")
    if it["point_rate"] >= 2:
        pts.append(f"今ならポイント <b>{it['point_rate']}倍</b>")
    mv = it.get("move")
    if isinstance(mv, int) and mv > 0:
        pts.append(f"前日から <b>{mv}位アップ</b>")
    if it.get("price_diff", 0) < 0:
        pts.append(f"前日より <b>{-it['price_diff']:,}円</b> 値下がり")
    pts.append("送料無料で、1ショップ1,000円以上の買い回り条件をクリアしやすい価格")
    if it.get("has_range"):
        pts.append("サイズ・数量などを選べる商品（選択によって価格が変わります）")
    return pts


def comment(it):
    """データに基づく案内コメント。体験談は書かない."""
    c, mv = it["code"], it.get("move")
    if it.get("price_diff", 0) < 0:
        return pick(c, [f"前日より{-it['price_diff']:,}円も安くなってるよ！価格が戻る前にチェックしてみてね。",
                        f"今日は{-it['price_diff']:,}円の値下がりを確認したよ。買い回りの1店舗にちょうどいいね。"])
    if isinstance(mv, int) and mv >= 10:
        return pick(c, [f"前日から{mv}位も順位を上げてる注目株！いま買う人が増えているみたい。",
                        f"ぐんぐん順位アップ中（前日比+{mv}位）。売り切れる前に在庫を確認しておこう。"])
    if it["reviews"] >= 1000 and it["rating"] >= 4.3:
        return pick(c, [f"レビュー{it['reviews']:,}件で平均★{it['rating']:.2f}。たくさんの人が評価している定番だから、迷ったときの候補に◎。",
                        f"★{it['rating']:.2f}・{it['reviews']:,}件のレビューがある人気者だよ。口コミはリンク先でじっくり読めるよ。"])
    if it["point_rate"] >= 5:
        return pick(c, [f"ポイント{it['point_rate']}倍がついてるよ！買い回りと組み合わせるとさらにおトク。",
                        f"今はポイント{it['point_rate']}倍。期間限定のことが多いから早めにチェックしてね。"])
    if it["rank"] <= 100:
        return pick(c, [f"楽天全体のランキングで{it['rank']}位！1000円台の中でもトップクラスの売れ筋だよ。",
                        f"総合{it['rank']}位の人気商品。送料無料で1,000円台だから買い回りに組み込みやすいね。"])
    return pick(c, ["送料無料の1000円台だから、買い回りの「あと1店舗」にぴったり。",
                    "ショップ数を増やしたいときの候補にどうぞ。詳しい内容はリンク先で確認してね。"])


def facts(it):
    range_mark = "〜" if it.get("has_range") else ""
    return f"""<ul class="facts"><li><span>価格</span><b class="big-yen">{it['price']:,}<small>円{range_mark}（税込・送料無料）</small></b></li>
<li><span>レビュー</span>{stars(it)}</li>
<li><span>ポイント</span>{it['point_rate']}倍</li><li><span>ショップ</span>{e(it['shop'])}</li>
<li><span>総合順位</span>{it['rank']}位</li></ul>"""


def product_block(pos, it):
    n = f" n{pos}" if pos <= 3 else ""
    pts = "".join(f"<li>{p}</li>" for p in point_list(it))
    return f"""<section class="pitem" id="p{pos}" data-rating="{it['rating']}" data-reviews="{it['reviews']}" data-pt="{it['point_rate']}" data-price="{it['price']}">
<h3><span class="no{n}">{pos}</span>{e(short_name(it['name']))}</h3>
<div class="pbox"><a class="pic" {link_attrs(it)}>{thumb(it)}<span class="flags">{flags(it)}</span></a><div>{facts(it)}</div></div>
<div class="points"><b>ここがポイント</b><ul>{pts}</ul></div>
{talk(e(comment(it)))}
<div class="btns"><a class="cta" {link_attrs(it)}>楽天で詳細を見る</a><a class="cta ghost" href="{slug_of(it['code'])}">この商品をくわしく</a></div></section>"""


FILTER_JS = """<script>
(function(){var st={};var bs=document.querySelectorAll('.filters button');var cnt=document.querySelector('.filters .count');
function apply(){var n=0;document.querySelectorAll('.pitem').forEach(function(el){var ok=true;
if(st.r&&!(+el.dataset.rating>=4&&+el.dataset.reviews>=10))ok=false;if(st.p&&!(+el.dataset.pt>=2))ok=false;if(st.l&&!(+el.dataset.price<1500))ok=false;
el.style.display=ok?'':'none';if(ok)n++;});cnt.textContent=n+'件を表示中';}
bs.forEach(function(b){b.addEventListener('click',function(){st[b.dataset.k]=!st[b.dataset.k];b.setAttribute('aria-pressed',st[b.dataset.k]);apply();});});apply();})();
</script>"""


def trend_svg(points):
    """[(日付, 順位, 価格)] から価格の折れ線グラフ."""
    if len(points) < 2:
        return ""
    w, h, pad = 640, 180, 32
    prices = [p[2] for p in points]
    lo, hi = min(prices), max(prices)
    span = max(hi - lo, 1)
    xs = [pad + i * (w - 2 * pad) / (len(points) - 1) for i in range(len(points))]
    ys = [h - pad - (p - lo) / span * (h - 2 * pad) for p in prices]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(zip(xs, ys)))
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#bf0000"/>' for x, y in zip(xs, ys))
    labels = (f'<text x="{pad}" y="{h - 8}" font-size="11" fill="#6e6e73">{points[0][0][5:]}</text>'
              f'<text x="{w - pad}" y="{h - 8}" font-size="11" fill="#6e6e73" text-anchor="end">{points[-1][0][5:]}</text>'
              f'<text x="4" y="{pad - 8}" font-size="11" fill="#6e6e73">最高 {hi:,}円</text>'
              f'<text x="4" y="{h - pad + 14}" font-size="11" fill="#6e6e73">最安 {lo:,}円</text>')
    return (f'<svg class="trend" viewBox="0 0 {w} {h}" role="img" aria-label="価格の推移">'
            f'<path d="{path}" fill="none" stroke="#bf0000" stroke-width="2.5"/>{dots}{labels}</svg>')


def render_budget(cfg, items, series, demo, day, updated, write):
    b = cfg["budget"]
    m, d = int(day[5:7]), int(day[8:10])
    slug = b["slug"] + ".html"
    n = len(items)
    title = f"楽天お買い物マラソンの買い回りにおすすめ！1000円台の売れ筋{n}選【{m}月{d}日版】"
    hero = f"""<section class="hero sm"><div class="wrap"><div class="crumb"><a href="index.html">総合</a> › 1000円台の売れ筋</div>
<h1>💰 買い回りにおすすめ！<br>1000円台の売れ筋{n}選</h1>
<p>{m}月{d}日時点の楽天総合ランキングから、1,000〜1,999円・送料無料・在庫ありの商品だけをまとめました。</p></div></section>"""
    toc = """<nav class="toc"><b>目次</b><ol><li><a href="#why">買い回りで1000円台の商品が選ばれる理由</a></li>
<li><a href="#list">1000円台の売れ筋ランキング</a></li><li><a href="#matome">まとめ</a></li></ol></nav>"""
    body = f"""<article class="post">
{talk(f"こんにちは、案内役の{MASCOT_NAME}だよ！このページでは、楽天で<b>いま本当に売れている1000円台の商品</b>を、送料無料のものだけに絞って紹介するね。お買い物マラソンの買い回り先さがしに使ってね。")}
{toc}
<h2 id="why">買い回りで1000円台の商品が選ばれる理由</h2>
<p class="lead">楽天のお買い物マラソンやスーパーSALEの「買い回り」では、<b>1ショップあたり1,000円（税込）以上</b>の買い物をしたショップの数に応じて、ポイント倍率が上がっていきます。</p>
<p>そのため「送料無料で、1,000円を少し超えるくらいの商品」は、少ない出費でショップ数を増やせる買い回りの定番です。ここでは、楽天全体の売れ筋ランキングに入っている商品だけを集めているので、<b>実際に多くの人が選んでいる商品</b>から探せます。</p>
<p class="note">※ポイント倍率の上限やエントリーの要否など、キャンペーンの細かい条件は開催ごとに異なります。参加前に楽天公式のキャンペーンページを必ずご確認ください。</p>
{talk("1,000円ちょうどより少し上の商品を選ぶと、クーポンで割引されても1,000円を下回りにくいから安心だよ。")}
<h2 id="list">1000円台の売れ筋ランキング</h2>
<p>楽天総合ランキングの順位が高い順に並べています。ボタンで絞り込めます。</p>
<div class="filters"><button type="button" data-k="r" aria-pressed="false">★4以上</button><button type="button" data-k="p" aria-pressed="false">ポイント2倍以上</button>
<button type="button" data-k="l" aria-pressed="false">1,500円未満</button><span class="count"></span></div>
{"".join(product_block(i + 1, it) for i, it in enumerate(items))}
<h2 id="matome">まとめ</h2>
<p>{m}月{d}日時点で、楽天の売れ筋ランキングに入っている1000円台・送料無料の商品は{n}点でした。価格やポイント倍率は日々変わるため、気になる商品は早めにリンク先で最新の情報を確認してください。</p>
{talk("このページは毎日新しいランキングに入れ替えているよ。買い回りの前にまたのぞいてみてね！")}
<p class="note">掲載情報は{e(updated)}時点のものです。価格・送料・在庫・ポイント倍率は変動する場合があります。</p>
</article>{FILTER_JS}"""
    write(slug, page(cfg, title, body, slug, demo, updated, active="budget", hero=hero, extra_css=CSS))

    paths = [slug]
    for i, it in enumerate(items):
        path = slug_of(it["code"])
        write(path, render_item(cfg, it, i + 1, items, series.get(it["code"], []), demo, day, updated))
        paths.append(path)
    return paths


def render_item(cfg, it, pos, items, points, demo, day, updated):
    b = cfg["budget"]
    name = short_name(it["name"], 60)
    m, d = int(day[5:7]), int(day[8:10])
    title = f"{short_name(it['name'], 34)}｜価格・レビュー評価・ランキング推移"
    hero = f"""<section class="hero sm"><div class="wrap"><div class="crumb"><a href="index.html">総合</a> › <a href="{b['slug']}.html">1000円台の売れ筋</a> › 商品紹介</div>
<h1>{e(name)}</h1><p>{m}月{d}日時点：楽天総合ランキング{it['rank']}位／1000円台の売れ筋 {pos}番目</p></div></section>"""
    pts = "".join(f"<li>{p}</li>" for p in point_list(it))
    caption = (f'<h2>ショップによる商品説明（抜粋）</h2><blockquote class="quote">{e(it["caption"])}…</blockquote>'
               f'<p class="note">出典：{e(it["shop"])}（楽天市場の商品ページより）</p>') if it.get("caption") else ""
    catch = f"<p><b>{e(it['catch'])}</b></p>" if it.get("catch") else ""
    if len(points) >= 2:
        rows = "".join(f"<tr><td>{p[0][5:].replace('-', '/')}</td><td>{p[1]}位</td><td>{p[2]:,}円</td></tr>" for p in points[-7:][::-1])
        trend = (f"<h2>価格と順位の推移</h2>{trend_svg(points)}"
                 f'<table class="spec"><tr><th>日付</th><th>総合順位</th><th>価格</th></tr>{rows}</table>')
    else:
        trend = (f"<h2>価格と順位の推移</h2><p>{m}月{d}日から記録を始めました。日ごとの価格・順位の変化は、明日以降このページに追加されます。</p>")
    near = [x for x in items if x["code"] != it["code"]][:6]
    related = "".join(f'<li><a href="{slug_of(x["code"])}">{e(short_name(x["name"], 36))}</a>（{x["price"]:,}円）</li>' for x in near)
    body = f"""<article class="post">
<a class="hero-img" {link_attrs(it)}>{thumb(it)}</a>
{talk(e(comment(it)))}
{catch}
<div class="points"><b>ここがポイント</b><ul>{pts}</ul></div>
<div class="btns"><a class="cta" {link_attrs(it)}>楽天で詳細・口コミを見る</a><a class="cta ghost" href="{b['slug']}.html">1000円台の売れ筋一覧へ</a></div>
<h2>基本情報</h2>
<table class="spec"><tr><th>商品名</th><td>{e(it['name'])}</td></tr>
<tr><th>価格</th><td>{it['price']:,}円{'〜' if it.get('has_range') else ''}（税込・送料無料）</td></tr>
<tr><th>レビュー</th><td>{stars(it)}</td></tr><tr><th>ポイント</th><td>{it['point_rate']}倍（{m}月{d}日時点）</td></tr>
<tr><th>ショップ</th><td>{e(it['shop'])}</td></tr><tr><th>総合順位</th><td>{it['rank']}位</td></tr></table>
{caption}
{trend}
{talk("実際の使い心地は、リンク先の楽天レビューで購入者の声をチェックしてみてね。")}
<a class="cta" {link_attrs(it)}>楽天で詳細・口コミを見る</a>
<h2>ほかの1000円台の売れ筋</h2><ul>{related}</ul>
<p class="note">掲載情報は{e(updated)}時点のものです。価格・送料・在庫・ポイント倍率は変動する場合があります。</p>
</article>"""
    path = slug_of(it["code"])
    return page(cfg, title, body, path, demo, updated, active="budget", hero=hero, extra_css=CSS)


def banner(cfg, items):
    b = cfg["budget"]
    return (f'<div class="banner">{MASCOT}<div><b>買い回りにおすすめ！1000円台の売れ筋{len(items)}選</b>'
            f'<small>送料無料・在庫ありの人気商品だけを毎日入れ替え</small></div>'
            f'<a class="cta" href="{b["slug"]}.html">記事を読む</a></div>')
