"""サイトのHTML生成（見た目）."""
import html
import shutil
from pathlib import Path

e = html.escape

CROWN = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M3 7l4.5 4L12 4l4.5 7L21 7l-2 12H5L3 7z"/>'
         '<rect x="5" y="20" width="14" height="2" rx="1" fill="currentColor"/></svg>')

CSS = """
:root{color-scheme:light;--bg:#f6f4f0;--ink:#1d1d1f;--sub:#6e6e73;--line:#e8e4dc;--card:#fff;--red:#bf0000;--red2:#e60033;
--gold:#d9a400;--silver:#9aa5b1;--bronze:#b9722e;--up:#e8590c;--good:#0f9d58;--shadow:0 1px 2px rgba(0,0,0,.04),0 6px 20px rgba(0,0,0,.06)}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Noto Sans JP",system-ui,-apple-system,"Hiragino Sans",sans-serif;line-height:1.6;font-feature-settings:"palt"}
a{color:inherit;text-decoration:none}img{display:block;max-width:100%}
.wrap{max-width:1120px;margin:0 auto;padding:0 16px}
/* header */
.top{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.92);backdrop-filter:saturate(1.6) blur(10px);border-bottom:1px solid var(--line)}
.top .bar{display:flex;align-items:center;justify-content:space-between;height:56px;gap:12px}
.logo{display:flex;align-items:center;gap:8px;font-weight:900;font-size:1.05rem;letter-spacing:.02em;white-space:nowrap}
.logo .mark{width:30px;height:30px;border-radius:8px;background:linear-gradient(135deg,var(--red2),var(--red));color:#fff;display:grid;place-items:center}
.logo .mark svg{width:18px;height:18px}.logo b{color:var(--red)}
.prtag{font-size:.7rem;color:var(--sub);border:1px solid var(--line);border-radius:999px;padding:2px 10px;white-space:nowrap}
.tabs{display:flex;gap:6px;overflow-x:auto;padding:0 16px 10px;max-width:1120px;margin:0 auto;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tabs a{flex:none;font-size:.82rem;font-weight:700;padding:6px 14px;border-radius:999px;background:#f1eee8;color:#444;transition:.15s}
.tabs a:hover{background:#e9e4da}.tabs a.on{background:var(--ink);color:#fff}
/* hero */
.hero{background:radial-gradient(1200px 400px at 85% -10%,#ff4d6d55,transparent 60%),linear-gradient(135deg,#a50000,#d6002f 55%,#ff3b5c);color:#fff;padding:44px 0 56px;position:relative;overflow:hidden}
.hero:after{content:"";position:absolute;right:-60px;top:-40px;width:320px;height:320px;border-radius:50%;border:40px solid rgba(255,255,255,.07)}
.kicker{display:inline-flex;align-items:center;gap:6px;font-size:.78rem;font-weight:700;background:rgba(255,255,255,.18);padding:4px 12px;border-radius:999px}
.kicker:before{content:"";width:7px;height:7px;border-radius:50%;background:#7CFFB2;box-shadow:0 0 0 3px rgba(124,255,178,.3)}
.hero h1{font-size:clamp(1.7rem,5vw,2.7rem);line-height:1.25;margin:.5em 0 .35em;font-weight:900;letter-spacing:.01em}
.hero p{margin:0;opacity:.92;max-width:40em;font-size:.95rem}
.stats{display:flex;gap:24px;margin-top:22px;flex-wrap:wrap}
.stats div{font-size:.75rem;opacity:.9}.stats b{display:block;font-size:1.5rem;font-weight:900;line-height:1.2}
.hero.sm{padding:28px 0 34px}.hero.sm h1{font-size:clamp(1.5rem,4vw,2.1rem)}
.crumb{font-size:.78rem;opacity:.85}.crumb a{text-decoration:underline}
/* sections */
main{padding-bottom:40px}
.sec{margin-top:36px}.sec-h{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin-bottom:14px}
.sec-h h2{margin:0;font-size:1.3rem;font-weight:900;display:flex;align-items:center;gap:8px}
.sec-h h2 .ico{font-size:1.2rem}.sec-h p{margin:2px 0 0;color:var(--sub);font-size:.82rem}
.more{font-size:.82rem;font-weight:700;color:var(--red);white-space:nowrap}
.notice{margin-top:-24px;position:relative;z-index:2;background:var(--card);border-radius:14px;box-shadow:var(--shadow);padding:14px 18px;font-size:.88rem;display:flex;gap:10px;align-items:center}
/* card grid */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:16px}
.card{background:var(--card);border-radius:16px;box-shadow:var(--shadow);overflow:hidden;display:flex;flex-direction:column;transition:transform .15s,box-shadow .15s}
.card:hover{transform:translateY(-3px);box-shadow:0 2px 4px rgba(0,0,0,.05),0 14px 32px rgba(0,0,0,.1)}
.thumb{position:relative;aspect-ratio:1;background:#fff;display:grid;place-items:center;border-bottom:1px solid #f0ede7}
.thumb img{width:82%;height:82%;object-fit:contain}
.noimg{color:#bbb;font-size:.8rem}
.rk{position:absolute;left:10px;top:10px;min-width:38px;height:38px;padding:0 6px;border-radius:10px;background:var(--ink);color:#fff;font-weight:900;font-size:1.05rem;display:grid;place-items:center;line-height:1}
.rk small{font-size:.6rem;font-weight:700}
.rk1{background:linear-gradient(135deg,#f7d046,var(--gold))}.rk2{background:linear-gradient(135deg,#cfd6dd,var(--silver))}.rk3{background:linear-gradient(135deg,#e2a46b,var(--bronze))}
.flags{position:absolute;right:10px;top:10px;display:flex;flex-direction:column;gap:4px;align-items:flex-end}
.flag{font-size:.7rem;font-weight:900;padding:3px 8px;border-radius:6px;color:#fff;line-height:1.3}
.f-up{background:var(--up)}.f-new{background:var(--red2)}.f-down{background:#5b6b7d}.f-pt{background:#fff;color:var(--red);border:1.5px solid var(--red)}.f-cheap{background:var(--good)}
.body{padding:12px 14px 14px;display:flex;flex-direction:column;gap:6px;flex:1}
.chip{align-self:flex-start;font-size:.7rem;font-weight:700;color:var(--red);background:#fff0f2;border-radius:999px;padding:2px 10px}
.nm{margin:0;font-size:.86rem;font-weight:500;line-height:1.5;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;min-height:3.9em}
.rv{display:flex;align-items:center;gap:6px;font-size:.76rem;color:var(--sub)}
.stars{position:relative;display:inline-block;color:#e3ded4;font-size:.9rem;letter-spacing:1px;line-height:1}
.stars:before{content:"★★★★★"}.stars i{position:absolute;left:0;top:0;overflow:hidden;white-space:nowrap;color:#f5a623}.stars i:before{content:"★★★★★"}
.rv b{color:var(--ink)}
.price{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-top:auto}
.yen{font-size:1.35rem;font-weight:900;color:var(--red);letter-spacing:-.01em}.yen small{font-size:.75rem;margin-left:1px}
.save{font-size:.72rem;font-weight:700;color:var(--good)}
.shop{font-size:.72rem;color:var(--sub);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cta{display:flex;align-items:center;justify-content:center;gap:6px;margin-top:4px;background:var(--red);color:#fff;font-weight:700;font-size:.85rem;padding:10px;border-radius:10px;transition:.15s}
.cta:hover{background:#9a0000}.cta:after{content:"›";font-size:1.1rem;line-height:1}
.ghost{background:transparent;color:var(--red);border:1.5px solid var(--red)}.ghost:hover{background:#fff0f2}
/* podium */
.podium{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.podium .card{border-top:5px solid var(--gold)}.podium .card:nth-child(2){border-color:var(--silver)}.podium .card:nth-child(3){border-color:var(--bronze)}
.podium .yen{font-size:1.6rem}
/* rows */
.rows{display:grid;gap:10px}
.row{display:grid;grid-template-columns:44px 104px 1fr auto;gap:14px;align-items:center;background:var(--card);border-radius:14px;box-shadow:var(--shadow);padding:12px 16px}
.rnum{font-size:1.35rem;font-weight:900;text-align:center;color:#555}.rnum small{font-size:.65rem}
.row .pic{width:104px;height:104px;background:#fff;display:grid;place-items:center;position:relative}
.row .pic img{width:100%;height:100%;object-fit:contain}
.row .nm{min-height:0;-webkit-line-clamp:2;font-size:.9rem}
.row .meta{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.row .flag{display:inline-block}
.row .cta{margin:0;padding:10px 16px;white-space:nowrap}
/* genre tiles */
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}
.tile{background:var(--card);border-radius:14px;box-shadow:var(--shadow);padding:16px;display:flex;align-items:center;gap:12px;font-weight:700;transition:.15s}
.tile:hover{transform:translateY(-2px)}.tile .ico{font-size:1.8rem;width:48px;height:48px;border-radius:12px;background:#fff0f2;display:grid;place-items:center}
.tile small{display:block;color:var(--sub);font-weight:500;font-size:.72rem}
/* footer */
footer{background:#1d1d1f;color:#a1a1a6;font-size:.78rem;padding:32px 0 40px;margin-top:20px}
footer a{color:#e5e5ea;text-decoration:underline}footer p{margin:.5em 0}
.about{background:var(--card);border-radius:16px;box-shadow:var(--shadow);padding:8px 24px 16px;margin-top:28px;font-size:.92rem}
.about h2{font-size:1.1rem}
.demo{background:#fde68a;color:#1d1d1f;text-align:center;padding:6px;font-weight:700;font-size:.85rem}
@media (max-width:760px){
 .podium{grid-template-columns:1fr}.podium .card{display:grid;grid-template-columns:42% 1fr}
 .podium .thumb{aspect-ratio:auto;border-bottom:0;border-right:1px solid #f0ede7}.podium .nm{-webkit-line-clamp:3;min-height:0}.podium .yen{font-size:1.3rem}
 .row{grid-template-columns:30px 76px 1fr;padding:12px;gap:10px;align-items:start}.rnum{padding-top:24px}.row .pic{width:76px;height:76px}.row .cta{grid-column:1/-1}
 .rnum{font-size:1.1rem}.grid{grid-template-columns:repeat(2,1fr);gap:10px}.body{padding:10px}.nm{font-size:.8rem}.yen{font-size:1.15rem}
 .cta{font-size:.8rem;padding:9px}.prtag{display:none}
}
"""


def stars(it):
    if not it["reviews"]:
        return '<div class="rv">レビューなし</div>'
    w = max(0, min(100, it["rating"] / 5 * 100))
    return (f'<div class="rv"><span class="stars" aria-hidden="true"><i style="width:{w:.0f}%"></i></span>'
            f'<b>{it["rating"]:.2f}</b>（{it["reviews"]:,}件）</div>')


def flags(it):
    out = []
    mv = it.get("move")
    if mv == "new":
        out.append('<span class="flag f-new">NEW</span>')
    elif isinstance(mv, int) and mv > 0:
        out.append(f'<span class="flag f-up">▲{mv}位UP</span>')
    elif isinstance(mv, int) and mv < 0:
        out.append(f'<span class="flag f-down">▼{-mv}</span>')
    if it["point_rate"] > 1:
        out.append(f'<span class="flag f-pt">P{it["point_rate"]}倍</span>')
    return "".join(out)


def thumb(it):
    if it["image"]:
        return f'<img src="{e(it["image"])}" alt="{e(it["name"][:40])}" loading="lazy" width="200" height="200">'
    return '<span class="noimg">no image</span>'


def price(it):
    save = f'<span class="save">前回比 {-it["price_diff"]:,}円↓</span>' if it.get("price_diff", 0) < 0 else ""
    return f'<div class="price"><span class="yen">{it["price"]:,}<small>円</small></span>{save}</div>'


def link_attrs(it):
    return f'href="{e(it["url"])}" rel="sponsored noopener" target="_blank"'


def card(it, genre=None, cta="楽天で詳細を見る"):
    rk = it["rank"]
    chip = f'<span class="chip">{e(genre["icon"])} {e(genre["title"])}</span>' if genre else ""
    return f"""<article class="card"><a class="thumb" {link_attrs(it)}>{thumb(it)}
<span class="rk rk{rk if rk <= 3 else 'x'}">{rk}<small>位</small></span><span class="flags">{flags(it)}</span></a>
<div class="body">{chip}<h3 class="nm"><a {link_attrs(it)}>{e(it['name'])}</a></h3>{stars(it)}{price(it)}
<div class="shop">{e(it['shop'])}</div><a class="cta" {link_attrs(it)}>{cta}</a></div></article>"""


def row(it):
    return f"""<article class="row"><div class="rnum">{it['rank']}<small>位</small></div>
<a class="pic" {link_attrs(it)}>{thumb(it)}</a>
<div class="body" style="padding:0"><h3 class="nm"><a {link_attrs(it)}>{e(it['name'])}</a></h3>
<div class="meta">{stars(it)}{flags(it)}</div>{price(it)}<div class="shop">{e(it['shop'])}</div></div>
<a class="cta" {link_attrs(it)}>楽天で見る</a></article>"""


def section(title, icon, note, inner, more=""):
    return (f'<section class="sec"><div class="sec-h"><div><h2><span class="ico">{icon}</span>{e(title)}</h2>'
            f'<p>{e(note)}</p></div>{more}</div>{inner}</section>')


def page(cfg, title, body, path, demo, updated, active=None, hero="", extra_css=""):
    tabs = '<a href="index.html" class="{}">{}</a>'.format("on" if active is None else "", e(cfg.get("home_label", "🏠 総合")))
    for href, label, key in cfg.get("extra_tabs", []):
        tabs += f'<a href="{href}" class="{"on" if active == key else ""}">{e(label)}</a>'
    if cfg.get("budget"):
        tabs += '<a href="{}.html" class="{}">💰 1000円台</a>'.format(cfg["budget"]["slug"], "on" if active == "budget" else "")
    tabs += "".join(f'<a href="{g["slug"]}.html" class="{"on" if active == g["slug"] else ""}">{e(g["icon"])} {e(g["title"])}</a>'
                    for g in cfg["genres"])
    canonical = cfg["base_url"].rstrip("/") + "/" + path
    full_title = title if title == cfg["site_name"] else f"{title} | {cfg['site_name']}"
    gsv = cfg.get("google_site_verification", "")
    verify = f'<meta name="google-site-verification" content="{e(gsv)}">' if gsv and not demo else ""
    banner = '<div class="demo">デモデータ表示中（公開しないでください）</div>' if demo else ""
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(full_title)}</title><meta name="description" content="{e(cfg['site_description'])}">
<link rel="canonical" href="{e(canonical)}"><meta name="theme-color" content="#bf0000">{verify}
<meta property="og:title" content="{e(full_title)}"><meta property="og:description" content="{e(cfg['site_description'])}">
<meta property="og:type" content="website"><meta property="og:url" content="{e(canonical)}">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Crect width='24' height='24' rx='6' fill='%23bf0000'/%3E%3Cpath fill='white' d='M4 8l4 3.5L12 5l4 6.5L20 8l-1.6 10H5.6z'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>{CSS}{extra_css}</style></head><body>{banner}
<header class="top"><div class="wrap bar"><a class="logo" href="index.html"><span class="mark">{CROWN}</span>{e(cfg['site_name'])}</a>
<span class="prtag">PR・楽天アフィリエイト参加中</span></div><nav class="tabs">{tabs}</nav></header>
{hero}<main class="wrap">{body}</main>
<footer><div class="wrap"><p>{e(cfg.get("footer_note", "掲載している価格・在庫・ポイント倍率・レビューは{updated}時点の情報です。ご購入前に必ず販売ページでご確認ください。").format(updated=updated))}</p>
<p>当サイトは楽天アフィリエイトを利用しており、リンク経由のご購入で運営者に紹介料が支払われる場合があります。</p>
<p><a href="about.html">運営者情報・免責事項</a> ／ Supported by <a href="https://webservice.rakuten.co.jp/" rel="noopener">Rakuten Developers</a></p></div></footer>
</body></html>"""


def render(cfg, results, demo, day, updated, out_dir, budget=None, series=None, descs=None):
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    def write(name, content):
        (out_dir / name).write_text(content, encoding="utf-8")

    genres = [g for g in cfg["genres"] if results.get(g["slug"])]
    total = sum(len(results[g["slug"]]) for g in genres)
    m, d = int(day[5:7]), int(day[8:10])

    # ジャンル別ページ
    for g in genres:
        items = results[g["slug"]]
        hero = f"""<section class="hero sm"><div class="wrap"><div class="crumb"><a href="index.html">総合</a> › {e(g['title'])}</div>
<h1>{e(g['icon'])} {e(g['title'])}<br>売れ筋ランキング TOP{len(items)}</h1>
<p>{m}月{d}日時点、楽天市場で今いちばん売れている{e(g['title'])}を、順位変動つきでチェック。</p></div></section>"""
        top3 = "".join(card(it) for it in items[:3])
        body = section("TOP3", "👑", f"{m}月{d}日時点で最も売れている3商品", f'<div class="podium">{top3}</div>')
        if len(items) > 3:
            body += section(f"4位〜{len(items)}位", "📋", "▲▼は前日からの順位変動です",
                            f'<div class="rows">{"".join(row(it) for it in items[3:])}</div>')
        others = "".join(f'<a class="tile" href="{o["slug"]}.html"><span class="ico">{e(o["icon"])}</span><span>{e(o["title"])}<small>TOP{len(results[o["slug"]])}を見る</small></span></a>'
                         for o in genres if o is not g)
        body += section("ほかのジャンル", "🗂", "気になるジャンルのランキングもチェック", f'<div class="tiles">{others}</div>')
        write(f"{g['slug']}.html", page(cfg, f"{g['title']}売れ筋ランキング {day}", body, f"{g['slug']}.html",
                                        demo, updated, active=g["slug"], hero=hero))

    # トップページ
    all_items = [(g, it) for g in genres for it in results[g["slug"]]]
    risers = sorted((x for x in all_items if isinstance(x[1].get("move"), int) and x[1]["move"] > 0),
                    key=lambda x: -x[1]["move"])[:8]
    cheaper = sorted((x for x in all_items if x[1].get("price_diff", 0) < 0),
                     key=lambda x: x[1]["price_diff"])[:8]
    rated = sorted((x for x in all_items if x[1]["reviews"] >= 100 and x[1]["rating"] >= 4.5),
                   key=lambda x: (-x[1]["rating"], -x[1]["reviews"]))[:8]

    def grid(rows):
        return f'<div class="grid">{"".join(card(it, genre=g) for g, it in rows)}</div>'

    hero = f"""<section class="hero"><div class="wrap"><span class="kicker">{m}月{d}日のランキング</span>
<h1>今日、楽天で<br>本当に売れているもの。</h1>
<p>{e(cfg['site_description'])}</p>
<div class="stats"><div><b>{len(genres)}</b>ジャンル</div><div><b>{total}</b>商品を掲載</div><div><b>毎日</b>更新</div></div></div></section>"""
    body = ""
    extra_css, extra_paths = "", []
    if budget:
        import articles
        extra_css = articles.CSS
        extra_paths = articles.render_budget(cfg, budget, series or {}, descs or {}, demo, day, updated, write)
        body += articles.banner(cfg, budget)
    body += ('<a class="banner" href="furusato/" style="margin-top:16px;background:linear-gradient(135deg,#e8f6ef,#fff7e6);border-color:#bfe6cf">'
             '<span style="font-size:2.6rem">🎁</span><div><b>ふるさと納税の人気返礼品ランキング</b>'
             '<small>肉・海鮮・お米・フルーツなど、レビューの多い定番を寄付金額別にチェック</small></div>'
             '<span class="cta" style="background:#0b7a4b">見てみる</span></a>')
    if not (risers or cheaper):
        body += '<div class="notice"{}>'.format(' style="margin-top:16px"' if budget else '') + '📈 順位の急上昇・値下がり情報は、明日から掲載します。</div>'
    champs = "".join(card(results[g["slug"]][0], genre=g, cta="ランキングを見る").replace(
        f'class="cta" {link_attrs(results[g["slug"]][0])}', f'class="cta ghost" href="{g["slug"]}.html"', 1) for g in genres)
    body += section("ジャンル別 いまの1位", "🏆", "各ジャンルで今日いちばん売れている商品", f'<div class="grid">{champs}</div>')
    if risers:
        body += section("今日の急上昇", "🚀", "前日から大きく順位を上げた注目商品", grid(risers))
    if cheaper:
        body += section("値下がり中", "💸", "前日より価格が下がった商品", grid(cheaper))
    if rated:
        body += section("高評価の売れ筋", "⭐", "レビュー100件以上・平均★4.5以上の安心アイテム", grid(rated))
    tiles = "".join(f'<a class="tile" href="{g["slug"]}.html"><span class="ico">{e(g["icon"])}</span><span>{e(g["title"])}<small>TOP{len(results[g["slug"]])}を見る</small></span></a>'
                    for g in genres)
    body += section("ジャンルから探す", "🗂", "ジャンルごとの売れ筋TOP30", f'<div class="tiles">{tiles}</div>')
    write("index.html", page(cfg, cfg["site_name"], body, "", demo, updated, hero=hero, extra_css=extra_css))

    about = """<div class="about"><h2>運営者情報・免責事項</h2>
<p>当サイトは、楽天市場で今売れている商品をジャンル別にご紹介するサイトです。ランキング情報は楽天ウェブサービスの提供データをもとに掲載しています。</p>
<p>当サイトは楽天アフィリエイトに参加しており、掲載リンクから商品が購入されると運営者に紹介料が支払われる場合があります（広告／PR）。</p>
<p>価格・在庫・ポイント倍率・レビュー等は取得時点の情報であり、正確性を保証するものではありません。最新情報は必ずリンク先の販売ページでご確認ください。</p>
<p>当サイトはアクセス解析ツール等による個人情報の収集を行っていません。</p></div>"""
    write("about.html", page(cfg, "運営者情報・免責事項", about, "about.html", demo, updated, active="about"))

    base = cfg["base_url"].rstrip("/")
    urls = ["", "about.html"] + [f"{g['slug']}.html" for g in genres] + extra_paths
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          + "".join(f"<url><loc>{e(base)}/{u}</loc><lastmod>{day}</lastmod></url>" for u in urls) + "</urlset>\n")
    write("robots.txt", ("User-agent: *\nDisallow: /\n" if demo else f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"))
    write(".nojekyll", "")
    # 検索エンジンの所有権確認ファイルなど、そのまま置くファイル
    static = Path(__file__).resolve().parent / "static"
    if static.exists():
        for f in static.iterdir():
            if f.is_file():
                shutil.copy(f, out_dir / f.name)
    # X投稿用の画像（Buffer が投稿時に読みに来るので、作り直しても消えないようにする）
    social_img = Path(__file__).resolve().parent / "data" / "social_img"
    if social_img.exists():
        (out_dir / "social").mkdir(exist_ok=True)
        for f in social_img.glob("*.png"):
            shutil.copy(f, out_dir / "social" / f.name)
