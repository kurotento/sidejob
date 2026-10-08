"""楽天ふるさと納税の返礼品データを、楽天市場の商品検索APIから取得する.

返礼品は自治体ごとのショップ（ショップコードが「f＋6桁の自治体コード-」で始まる）が出品している。
キーワード検索の結果から自治体ショップの商品だけを残し、レビュー件数の多い順に並べる。
（楽天ふるさと納税の特設ランキングページの読み取りは規約上避ける）
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SEARCH_ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
MUNI_SHOP = re.compile(r"^f\d{6}-")

CATEGORIES = [
    {"slug": "meat", "title": "肉", "icon": "🥩", "keyword": "ふるさと納税 肉"},
    {"slug": "seafood", "title": "海鮮・魚介", "icon": "🦀", "keyword": "ふるさと納税 海鮮"},
    {"slug": "rice", "title": "お米", "icon": "🍚", "keyword": "ふるさと納税 米"},
    {"slug": "fruit", "title": "フルーツ", "icon": "🍇", "keyword": "ふるさと納税 フルーツ"},
    {"slug": "sweets", "title": "スイーツ", "icon": "🍰", "keyword": "ふるさと納税 スイーツ"},
    {"slug": "daily", "title": "日用品", "icon": "🧻", "keyword": "ふるさと納税 日用品"},
]


def search(keyword, base_url, page=1, min_price=None, max_price=None):
    from build import normalize_item
    params = {
        "applicationId": os.environ["RAKUTEN_APP_ID"],
        "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
        "keyword": keyword,
        "sort": "-reviewCount",
        "hits": 30,
        "page": page,
        "availability": 1,
        "formatVersion": 2,
    }
    if min_price:
        params["minPrice"] = min_price
    if max_price:
        params["maxPrice"] = max_price
    if os.environ.get("RAKUTEN_AFFILIATE_ID"):
        params["affiliateId"] = os.environ["RAKUTEN_AFFILIATE_ID"]
    req = urllib.request.Request(SEARCH_ENDPOINT + "?" + urllib.parse.urlencode(params), headers={
        "Referer": base_url.rstrip("/") + "/",
        "Origin": urllib.parse.urlsplit(base_url)._replace(path="").geturl(),
        "User-Agent": "rakuten-ranking-site/1.0",
    })
    with urllib.request.urlopen(req, timeout=30) as res:
        data = json.load(res)
    out = []
    for raw in data.get("Items", []):
        it = raw.get("Item", raw)
        shop = it.get("shopCode", "")
        if not MUNI_SHOP.match(shop):
            continue
        n = normalize_item(it)
        n["shop_code"] = shop
        out.append(n)
    return out


def fetch_category(cat, base_url, pages=2):
    seen, items = set(), []
    for p in range(1, pages + 1):
        try:
            got = search(cat["keyword"], base_url, page=p)
        except urllib.error.HTTPError as ex:
            print(f"[furusato:{cat['slug']}] HTTP {ex.code}: {ex.read().decode('utf-8', 'replace')[:200]}", file=sys.stderr)
            break
        time.sleep(1.1)
        for it in got:
            if it["code"] not in seen:
                seen.add(it["code"])
                items.append(it)
    items.sort(key=lambda x: -x["reviews"])
    for i, it in enumerate(items):
        it["rank"] = i + 1
    return items


def probe(base_url):
    """取得できるかの確認用。件数と上位の例を表示する."""
    for cat in CATEGORIES:
        items = fetch_category(cat, base_url, pages=1)
        top = " / ".join(f"{it['name'][:20]}({it['price']:,}円・{it['reviews']:,}件・{it['shop']})" for it in items[:2])
        print(f"[furusato:{cat['slug']}] 自治体ショップ {len(items)}件 例: {top}")


# ---------- サイト生成 ----------

BANDS = [("〜5,000円", 0, 5000), ("5,001〜10,000円", 5001, 10000), ("10,001〜20,000円", 10001, 20000),
         ("20,001円〜", 20001, 10 ** 9)]

GREEN_CSS = """
:root{--red:#0b7a4b;--red2:#14a06a}
.hero{background:radial-gradient(1200px 400px at 85% -10%,#7ee2b055,transparent 60%),linear-gradient(135deg,#065c38,#0b7a4b 55%,#2bb57c)}
.logo .mark{background:linear-gradient(135deg,#14a06a,#065c38)}.chip{background:#e8f6ef}.cta:hover{background:#065c38}
.ghost:hover{background:#e8f6ef}.tabs a.on{background:#065c38}
.guide{background:var(--card);border-radius:16px;box-shadow:var(--shadow);padding:6px 22px 14px;margin-top:28px;font-size:.92rem}
.guide h2{font-size:1.1rem}.guide a{color:#065c38;text-decoration:underline}.muni{font-size:.74rem;font-weight:700;color:#065c38}
"""

GUIDE = """<div class="guide"><h2>はじめての方へ：ふるさと納税のきほん</h2>
<p>ふるさと納税は、応援したい自治体に寄付をすると、寄付額のうち2,000円を超える部分が所得税・住民税から控除される仕組みです（控除には上限があります）。寄付のお礼として、自治体から返礼品が届きます。</p>
<p>控除される上限額は、年収や家族構成などで変わります。寄付する前に、楽天ふるさと納税の<a href="https://event.rakuten.co.jp/furusato/" rel="noopener">寄付限度額シミュレーター</a>で目安を確認しておくと安心です。</p>
<p>その年の控除の対象になるのは、1月1日〜12月31日に行った寄付です。年末は申し込みが集中するので、早めの準備がおすすめです。手続き（ワンストップ特例・確定申告）の詳しい条件は、各自治体や楽天ふるさと納税のご利用ガイドでご確認ください。</p></div>"""


def site_cfg(cfg):
    return {
        "site_name": "ふるさと納税 人気返礼品ランキング",
        "site_description": "楽天ふるさと納税で人気の返礼品を、ジャンル別・寄付金額別にまとめています。レビューの多い定番から選べます。",
        "base_url": cfg["base_url"].rstrip("/") + "/furusato",
        "genres": CATEGORIES,
        "home_label": "🏠 トップ",
        "x_url": cfg.get("x_url", ""),
        "room_url": cfg.get("room_url", ""),
        "extra_tabs": [("price.html", "💴 寄付金額から探す", "price"), ("../", "🏆 楽天ランキング", "main")],
        "footer_note": "掲載している寄付額・在庫・レビューは{updated}時点の情報です。お申し込み前に必ず楽天ふるさと納税の返礼品ページでご確認ください。",
    }


def item_path(it):
    return "item-" + re.sub(r"[^A-Za-z0-9_-]", "-", it["code"]) + ".html"


def render_site(cfg, cats, descs, demo, day, updated, out_dir):
    from articles import CSS as ART_CSS, desc_html, short_name, talk
    from render import card, e, link_attrs, page, row, section, stars, thumb

    sc = site_cfg(cfg)
    out = out_dir / "furusato"
    out.mkdir(parents=True, exist_ok=True)
    css = ART_CSS + GREEN_CSS
    m, d = int(day[5:7]), int(day[8:10])

    def write(name, html_text):
        (out / name).write_text(html_text, encoding="utf-8")

    def localize(html_text, it):
        html_text = html_text.replace(f'<div class="shop">{e(it["shop"])}</div>',
                                      f'<div class="shop"><span class="muni">📍{e(it["shop"])}</span></div>', 1)
        html_text = html_text.replace('<span class="yen">', '<span class="yen"><small>寄付額 </small>')
        html_text = html_text.replace("楽天で詳細を見る", "返礼品を見る").replace("楽天で見る", "返礼品を見る")
        if it["code"] in has_page:  # 紹介ページがある返礼品には「くわしく」を付ける
            more = f'<a class="cta ghost" href="{item_path(it)}">くわしく見る</a>'
            if html_text.endswith("</div></article>"):
                html_text = html_text[: -len("</div></article>")] + more + "</div></article>"
            else:
                html_text = html_text[: -len("</article>")] + more + "</article>"
        return html_text

    has_page = {it["code"] for c in cats for it in c["items"][:10]}
    clean = lambda it: {**it, "name": short_name(it["name"], 50)}  # noqa: E731 - 宣伝文句を除いた名前で表示
    fcard = lambda it, cat=None: localize(card(clean(it), genre=cat), it)  # noqa: E731
    frow = lambda it: localize(row(clean(it)), it)  # noqa: E731

    paths = []
    for cat in cats:
        items = cat["items"]
        if not items:
            continue
        hero = f"""<section class="hero sm"><div class="wrap"><div class="crumb"><a href="index.html">トップ</a> › {e(cat['title'])}</div>
<h1>{e(cat['icon'])} ふるさと納税<br>{e(cat['title'])}の人気返礼品 TOP{len(items)}</h1>
<p>{m}月{d}日時点。楽天ふるさと納税で、レビューが多く寄せられている{e(cat['title'])}の返礼品を集めました。</p></div></section>"""
        body = section("TOP3", "👑", "レビュー件数が特に多い定番の返礼品", f'<div class="podium">{"".join(fcard(it) for it in items[:3])}</div>')
        body += section(f"4位〜{len(items)}位", "📋", "レビュー件数の多い順", f'<div class="rows">{"".join(frow(it) for it in items[3:])}</div>')
        write(f"{cat['slug']}.html", page(sc, f"ふるさと納税 {cat['title']}の人気返礼品ランキング【{m}月】", body + GUIDE,
                                          f"{cat['slug']}.html", demo, updated, active=cat["slug"], hero=hero, extra_css=css))
        paths.append(f"{cat['slug']}.html")

    pool = {}
    for cat in cats:
        for it in cat["items"]:
            pool.setdefault(it["code"], (it, cat))
    allitems = sorted(pool.values(), key=lambda x: -x[0]["reviews"])
    body = ""
    for label, lo, hi in BANDS:
        band = [(it, c) for it, c in allitems if lo <= it["price"] <= hi][:8]
        if band:
            body += section(f"寄付額 {label}", "💴", "レビュー件数の多い順",
                            f'<div class="grid">{"".join(fcard(it, c) for it, c in band)}</div>')
    hero = f"""<section class="hero sm"><div class="wrap"><div class="crumb"><a href="index.html">トップ</a> › 寄付金額から探す</div>
<h1>💴 寄付金額から探す<br>ふるさと納税の人気返礼品</h1><p>控除の上限に合わせて選びやすいよう、寄付額ごとに人気の返礼品をまとめました（{m}月{d}日時点）。</p></div></section>"""
    write("price.html", page(sc, f"寄付金額別 ふるさと納税の人気返礼品【{m}月】", body + GUIDE, "price.html", demo, updated,
                             active="price", hero=hero, extra_css=css))
    paths.append("price.html")

    for cat in cats:
        for it in cat["items"][:10]:
            desc = descs.get(it["code"])
            hero = f"""<section class="hero sm"><div class="wrap"><div class="crumb"><a href="index.html">トップ</a> › <a href="{cat['slug']}.html">{e(cat['title'])}</a> › 返礼品紹介</div>
<h1>{e(short_name(it['name'], 60))}</h1><p>📍{e(it['shop'])}｜{e(cat['title'])}の人気返礼品 {it['rank']}位（{m}月{d}日時点）</p></div></section>"""
            intro = talk(e(desc["intro"])) if desc else ""
            feat = ("<h2>どんな返礼品？</h2>" + desc_html(desc, "主な特徴")) if desc else ""
            caption = (f'<h2>自治体による説明（抜粋）</h2><blockquote class="quote">{e(it["caption"])}…</blockquote>'
                       f'<p class="note">出典：{e(it["shop"])}（楽天ふるさと納税の返礼品ページより）</p>') if it.get("caption") else ""
            body = f"""<article class="post"><a class="hero-img" {link_attrs(it)}>{thumb(it)}</a>{intro}{feat}
<div class="btns"><a class="cta" {link_attrs(it)}>楽天ふるさと納税で見る</a><a class="cta ghost" href="{cat['slug']}.html">{e(cat['title'])}のランキングへ</a></div>
<h2>基本情報</h2><table class="spec"><tr><th>返礼品</th><td>{e(it['name'])}</td></tr>
<tr><th>寄付額</th><td>{it['price']:,}円</td></tr><tr><th>自治体</th><td>{e(it['shop'])}</td></tr>
<tr><th>レビュー</th><td>{stars(it)}</td></tr></table>{caption}
<a class="cta" {link_attrs(it)}>楽天ふるさと納税で見る</a>
<p class="note">紹介文は自治体の説明をもとに作成しています。寄付額・内容・配送時期は変わる場合があります。お申し込み前に返礼品ページでご確認ください。</p></article>{GUIDE}"""
            write(item_path(it), page(sc, f"{short_name(it['name'], 30)}｜{it['shop']}のふるさと納税返礼品", body,
                                      item_path(it), demo, updated, active=cat["slug"], hero=hero, extra_css=css))
            paths.append(item_path(it))

    hero = f"""<section class="hero"><div class="wrap"><span class="kicker">{m}月{d}日の人気返礼品</span>
<h1>ふるさと納税、<br>みんなが選んでいる返礼品。</h1>
<p>楽天ふるさと納税でレビューが多く寄せられている定番の返礼品を、ジャンル別・寄付金額別にまとめています。</p>
<div class="stats"><div><b>{len(cats)}</b>ジャンル</div><div><b>{len(pool)}</b>返礼品を掲載</div><div><b>毎日</b>更新</div></div></div></section>"""
    body = ""
    for cat in cats:
        if cat["items"]:
            more = f'<a class="more" href="{cat["slug"]}.html">TOP{len(cat["items"])}を見る ›</a>'
            body += section(f"{cat['title']}の人気返礼品", cat["icon"], "レビュー件数の多い順",
                            f'<div class="grid">{"".join(fcard(it) for it in cat["items"][:4])}</div>', more)
    tiles = "".join(f'<a class="tile" href="{c["slug"]}.html"><span class="ico">{e(c["icon"])}</span><span>{e(c["title"])}<small>TOP{len(c["items"])}を見る</small></span></a>' for c in cats)
    tiles += '<a class="tile" href="price.html"><span class="ico">💴</span><span>寄付金額から探す<small>〜5,000円から</small></span></a>'
    body += section("ジャンル・金額から探す", "🗂", "", f'<div class="tiles">{tiles}</div>') + GUIDE
    write("index.html", page(sc, sc["site_name"], body, "", demo, updated, hero=hero, extra_css=css))
    paths.insert(0, "")

    about = """<div class="about"><h2>運営者情報・免責事項</h2>
<p>当サイトは、楽天ふるさと納税で人気の返礼品をジャンル別・寄付金額別にご紹介するサイトです。返礼品の情報は楽天ウェブサービスの提供データをもとに掲載しています。</p>
<p>当サイトは楽天アフィリエイトに参加しており、掲載リンクから寄付のお申し込みがあると運営者に紹介料が支払われる場合があります（広告／PR）。</p>
<p>税金の控除については一般的な説明です。個別の控除額や手続きは、お住まいの自治体・税務署、楽天ふるさと納税のご利用ガイドでご確認ください。</p></div>"""
    write("about.html", page(sc, "運営者情報・免責事項", about, "about.html", demo, updated, active="about", extra_css=css))
    paths.append("about.html")
    return [f"furusato/{p}" for p in paths]


def demo_cats():
    import random
    rnd = random.Random(1)
    cats = []
    for c in CATEGORIES:
        items = [{"rank": i + 1, "code": f"demo:{c['slug']}{i}", "name": f"【ふるさと納税】{c['title']}の返礼品サンプル{i + 1}",
                  "price": rnd.choice([5000, 8000, 10000, 12000, 15000, 20000, 30000]), "url": "#", "shop": "北海道サンプル町",
                  "image": "", "reviews": 3000 - i * 90, "rating": 4.5, "point_rate": 1, "caption": ""} for i in range(30)]
        cats.append({**c, "items": items})
    return cats


def fetch_all(cfg):
    cats = []
    for c in CATEGORIES:
        items = fetch_category(c, cfg["base_url"], pages=2)[:30]
        for i, it in enumerate(items):
            it["rank"] = i + 1
        cats.append({**c, "items": items})
        print(f"[furusato:{c['slug']}] {len(items)}件")
    return cats
