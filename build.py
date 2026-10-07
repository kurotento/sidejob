"""楽天ランキング速報サイトの生成スクリプト.

使い方:
    python build.py            # 楽天APIから取得してサイトを生成(環境変数が必要)
    python build.py --demo     # ダミーデータで見た目だけ確認

必要な環境変数:
    RAKUTEN_APP_ID        楽天ウェブサービスのアプリID (applicationId)
    RAKUTEN_ACCESS_KEY    楽天ウェブサービスのアクセスキー (accessKey)
    RAKUTEN_AFFILIATE_ID  楽天アフィリエイトID (無いと報酬が発生しません)
"""
import argparse
import datetime as dt
import html
import json
import os
import random
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HISTORY_DIR = ROOT / "data" / "history"
OUT_DIR = ROOT / "public"
RANKING_ENDPOINT = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
JST = dt.timezone(dt.timedelta(hours=9))


def load_config():
    with open(ROOT / "config.json", encoding="utf-8") as f:
        return json.load(f)


# ---------- 取得 ----------

def fetch_ranking(genre_id, base_url):
    params = {
        "applicationId": os.environ["RAKUTEN_APP_ID"],
        "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
        "genreId": genre_id,
        "formatVersion": 2,
    }
    if os.environ.get("RAKUTEN_AFFILIATE_ID"):
        params["affiliateId"] = os.environ["RAKUTEN_AFFILIATE_ID"]
    url = RANKING_ENDPOINT + "?" + urllib.parse.urlencode(params)
    # 2026年仕様ではアプリに登録したサイトURLと一致する Referer/Origin が求められる
    req = urllib.request.Request(url, headers={
        "Referer": base_url.rstrip("/") + "/",
        "Origin": urllib.parse.urlsplit(base_url)._replace(path="").geturl(),
        "User-Agent": "rakuten-ranking-site/1.0",
    })
    with urllib.request.urlopen(req, timeout=30) as res:
        data = json.load(res)
    items = []
    for raw in data.get("Items", []):
        it = raw.get("Item", raw)  # formatVersion 1/2 両対応
        items.append(normalize_item(it))
    # 2026年版APIは下位から返ってくることがあるため順位で並べ直す
    return sorted(items, key=lambda x: x["rank"])


def normalize_item(it):
    images = it.get("mediumImageUrls") or []
    img = images[0] if images else ""
    if isinstance(img, dict):
        img = img.get("imageUrl", "")
    img = re.sub(r"_ex=\d+x\d+", "_ex=200x200", img)
    return {
        "rank": int(it.get("rank", 0)),
        "code": it.get("itemCode", ""),
        "name": it.get("itemName", ""),
        "price": int(it.get("itemPrice", 0) or 0),
        "url": it.get("affiliateUrl") or it.get("itemUrl", ""),
        "shop": it.get("shopName", ""),
        "image": img,
        "reviews": int(it.get("reviewCount", 0) or 0),
        "rating": float(it.get("reviewAverage", 0) or 0),
        "point_rate": int(it.get("pointRate", 1) or 1),
    }


def demo_items(genre, n):
    rnd = random.Random(f"{genre['slug']}-{dt.date.today()}")
    items = []
    for i in range(n):
        code = f"demo:{genre['slug']}-{rnd.randint(1, n + 10)}"
        items.append({
            "rank": i + 1, "code": code,
            "name": f"【デモ】{genre['title']}の人気商品 {code.split('-')[-1]} 送料無料 まとめ買い",
            "price": rnd.randrange(980, 29800, 10), "url": "#", "shop": "デモショップ",
            "image": "", "reviews": rnd.randint(0, 5000),
            "rating": round(rnd.uniform(3.2, 4.9), 2), "point_rate": rnd.choice([1, 1, 2, 5, 10]),
        })
    # 同じコードの重複を除去して順位を振り直す
    seen, uniq = set(), []
    for it in items:
        if it["code"] not in seen:
            seen.add(it["code"])
            uniq.append(it)
    for i, it in enumerate(uniq):
        it["rank"] = i + 1
    return uniq


# ---------- 履歴 ----------

def save_snapshot(day, slug, items):
    d = HISTORY_DIR / day
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{slug}.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, separators=(",", ":"))


def load_previous(day, slug):
    if not HISTORY_DIR.exists():
        return None
    for d in sorted((p for p in HISTORY_DIR.iterdir() if p.name < day), reverse=True):
        f = d / f"{slug}.json"
        if f.exists():
            with open(f, encoding="utf-8") as fp:
                return json.load(fp)
    return None


def annotate(items, prev):
    prev_map = {it["code"]: it for it in (prev or [])}
    for it in items:
        p = prev_map.get(it["code"])
        if prev is None:
            it["move"], it["price_diff"] = None, 0
        elif p is None:
            it["move"], it["price_diff"] = "new", 0
        else:
            it["move"] = p["rank"] - it["rank"]
            it["price_diff"] = it["price"] - p["price"]
    return items


def prune_history(keep_days=60):
    if not HISTORY_DIR.exists():
        return
    dirs = sorted(p for p in HISTORY_DIR.iterdir() if p.is_dir())
    for d in dirs[:-keep_days]:
        shutil.rmtree(d)


# ---------- 描画 ----------

e = html.escape

CSS = """
:root{--bg:#fafaf7;--fg:#1f2328;--muted:#6b7280;--card:#fff;--line:#e5e7eb;--accent:#bf0000;--up:#c2410c;--down:#2563eb;--good:#15803d}
@media (prefers-color-scheme:dark){:root{--bg:#16181d;--fg:#e6e6e6;--muted:#9ca3af;--card:#1f2228;--line:#2f333b;--accent:#ff5c5c;--up:#fb923c;--down:#60a5fa;--good:#4ade80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;line-height:1.6}
a{color:inherit}header,main,footer{max-width:960px;margin:0 auto;padding:16px}
header h1{font-size:1.4rem;margin:.2em 0}header h1 a{text-decoration:none}.desc,.muted{color:var(--muted);font-size:.9rem}
nav{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}nav a{font-size:.85rem;padding:4px 10px;border:1px solid var(--line);border-radius:999px;text-decoration:none;background:var(--card)}
.pr{font-size:.75rem;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:2px 6px;display:inline-block}
.list{list-style:none;padding:0;display:grid;gap:10px}
.item{display:grid;grid-template-columns:44px 96px 1fr;gap:12px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
.rank{font-weight:700;font-size:1.3rem;text-align:center}.item img,.noimg{width:96px;height:96px;object-fit:contain;border-radius:6px;background:#fff}
.noimg{display:flex;align-items:center;justify-content:center;color:#999;font-size:.75rem;border:1px dashed var(--line)}
.name{font-size:.92rem;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.meta{font-size:.82rem;color:var(--muted);display:flex;flex-wrap:wrap;gap:4px 12px}.price{font-weight:700;color:var(--fg);font-size:1rem}
.badge{font-size:.72rem;font-weight:700;padding:1px 6px;border-radius:4px;border:1px solid currentColor}
.up{color:var(--up)}.down{color:var(--down)}.new{color:var(--accent)}.cheaper{color:var(--good)}
.btn{display:inline-block;margin-top:4px;font-size:.82rem;background:var(--accent);color:#fff;text-decoration:none;padding:4px 12px;border-radius:6px}
h2{font-size:1.15rem;border-left:4px solid var(--accent);padding-left:8px;margin-top:28px}
.demo{background:#fde68a;color:#1f2328;text-align:center;padding:6px;font-weight:700}
@media (max-width:520px){.item{grid-template-columns:32px 72px 1fr}.item img,.noimg{width:72px;height:72px}.rank{font-size:1.05rem}}
"""


def page(cfg, title, body, path, demo, updated):
    nav = "".join(f'<a href="{g["slug"]}.html">{e(g["title"])}</a>' for g in cfg["genres"])
    canonical = cfg["base_url"].rstrip("/") + "/" + path
    full_title = title if title == cfg["site_name"] else f"{title} | {cfg['site_name']}"
    banner = '<div class="demo">デモデータ表示中（公開しないでください）</div>' if demo else ""
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(full_title)}</title><meta name="description" content="{e(cfg['site_description'])}">
<link rel="canonical" href="{e(canonical)}"><style>{CSS}</style></head><body>{banner}
<header><h1><a href="index.html">{e(cfg['site_name'])}</a></h1><p class="desc">{e(cfg['site_description'])}</p>
<span class="pr">PR：当サイトは楽天アフィリエイトを利用しています</span><nav>{nav}</nav></header>
<main>{body}</main>
<footer class="muted"><p>最終更新：{e(updated)}（JST）／価格・在庫・ポイント倍率は取得時点のものです。購入前に必ず販売ページでご確認ください。</p>
<p><a href="about.html">運営者情報・免責事項</a></p>
<p>Supported by <a href="https://webservice.rakuten.co.jp/" rel="noopener">Rakuten Developers</a></p></footer>
</body></html>"""


def item_html(it):
    if it.get("move") == "new":
        move = '<span class="badge new">NEW</span>'
    elif isinstance(it.get("move"), int) and it["move"] > 0:
        move = f'<span class="badge up">▲{it["move"]}</span>'
    elif isinstance(it.get("move"), int) and it["move"] < 0:
        move = f'<span class="badge down">▼{-it["move"]}</span>'
    else:
        move = ""
    price_note = ""
    if it.get("price_diff", 0) < 0:
        price_note = f'<span class="cheaper">前回より{-it["price_diff"]:,}円安</span>'
    img = (f'<img src="{e(it["image"])}" alt="" loading="lazy">' if it["image"]
           else '<div class="noimg">no image</div>')
    stars = f'★{it["rating"]:.2f}（{it["reviews"]:,}件）' if it["reviews"] else "レビューなし"
    point = f'<span>ポイント{it["point_rate"]}倍</span>' if it["point_rate"] > 1 else ""
    return f"""<li class="item"><div class="rank">{it['rank']}</div>{img}
<div><div class="name">{e(it['name'])}</div>
<div class="meta"><span class="price">{it['price']:,}円</span>{move}{price_note}<span>{stars}</span>{point}<span>{e(it['shop'])}</span></div>
<a class="btn" href="{e(it['url'])}" rel="sponsored noopener" target="_blank">楽天で見る</a></div></li>"""


def render(cfg, results, demo, day, updated):
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    def write(name, content):
        (OUT_DIR / name).write_text(content, encoding="utf-8")

    # ジャンル別ページ
    for g in cfg["genres"]:
        items = results.get(g["slug"])
        if not items:
            continue
        body = (f"<h2>{e(g['title'])} 売れ筋ランキング（{day}）</h2>"
                f'<p class="muted">▲▼は前回取得時からの順位変動です。</p>'
                f'<ul class="list">{"".join(item_html(it) for it in items)}</ul>')
        write(f"{g['slug']}.html", page(cfg, f"{g['title']}ランキング {day}", body, f"{g['slug']}.html", demo, updated))

    # トップ：急上昇・値下がり・高評価
    all_items = [(g, it) for g in cfg["genres"] for it in results.get(g["slug"], [])]
    risers = sorted((x for x in all_items if isinstance(x[1].get("move"), int) and x[1]["move"] > 0),
                    key=lambda x: -x[1]["move"])[:10]
    cheaper = sorted((x for x in all_items if x[1].get("price_diff", 0) < 0),
                     key=lambda x: x[1]["price_diff"])[:10]
    rated = sorted((x for x in all_items if x[1]["reviews"] >= 100 and x[1]["rating"] >= 4.5),
                   key=lambda x: (-x[1]["rating"], -x[1]["reviews"]))[:10]

    def section(title, rows, note):
        if not rows:
            return ""
        lis = "".join(item_html({**it, "rank": it["rank"]}).replace(
            '<div class="name">', f'<div class="muted">{e(g["title"])} {it["rank"]}位</div><div class="name">', 1)
            for g, it in rows)
        return f'<h2>{e(title)}</h2><p class="muted">{e(note)}</p><ul class="list">{lis}</ul>'

    body = (section("今日の急上昇", risers, "前回から最も順位を上げた商品")
            + section("値下がり中", cheaper, "前回取得時より価格が下がった商品")
            + section("高評価の売れ筋", rated, "レビュー100件以上・平均4.5以上")
            + "<h2>ジャンル別ランキング</h2><ul>"
            + "".join(f'<li><a href="{g["slug"]}.html">{e(g["title"])}</a>（1位：{e(results[g["slug"]][0]["name"][:40])}…）</li>'
                      for g in cfg["genres"] if results.get(g["slug"]))
            + "</ul>")
    if not (risers or cheaper):
        body = '<p class="muted">順位変動・値下がり情報は2日目以降の更新から表示されます。</p>' + body
    write("index.html", page(cfg, cfg["site_name"], body, "", demo, updated))

    about = """<h2>運営者情報・免責事項</h2>
<p>当サイトは楽天ウェブサービスのAPIを利用して楽天市場のランキング情報を自動で集計・掲載しています。</p>
<p>当サイトは楽天アフィリエイトに参加しており、掲載リンクから商品が購入されると運営者に紹介料が支払われる場合があります（広告／PR）。</p>
<p>価格・在庫・ポイント倍率・レビュー等は取得時点の情報であり、正確性を保証するものではありません。最新情報は必ずリンク先の販売ページでご確認ください。</p>
<p>当サイトはアクセス解析ツール等による個人情報の収集を行っていません。</p>"""
    write("about.html", page(cfg, "運営者情報・免責事項", about, "about.html", demo, updated))

    base = cfg["base_url"].rstrip("/")
    urls = ["", "about.html"] + [f"{g['slug']}.html" for g in cfg["genres"] if results.get(g["slug"])]
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          + "".join(f"<url><loc>{e(base)}/{u}</loc><lastmod>{day}</lastmod></url>" for u in urls) + "</urlset>\n")
    write("robots.txt", ("User-agent: *\nDisallow: /\n" if demo else f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"))
    write(".nojekyll", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="APIを使わずダミーデータで生成")
    args = ap.parse_args()
    cfg = load_config()
    now = dt.datetime.now(JST)
    day, updated = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d %H:%M")

    if not args.demo:
        missing = [k for k in ("RAKUTEN_APP_ID", "RAKUTEN_ACCESS_KEY") if not os.environ.get(k)]
        if missing:
            sys.exit(f"環境変数が未設定です: {', '.join(missing)}（見た目の確認だけなら --demo）")
        if not os.environ.get("RAKUTEN_AFFILIATE_ID"):
            print("警告: RAKUTEN_AFFILIATE_ID が未設定のため、リンクから報酬は発生しません", file=sys.stderr)

    results, errors = {}, 0
    for g in cfg["genres"]:
        try:
            if args.demo:
                items = demo_items(g, cfg["items_per_genre"])
            else:
                items = fetch_ranking(g["genreId"], cfg["base_url"])[: cfg["items_per_genre"]]
                time.sleep(1.1)  # 楽天APIの推奨: 1秒に1リクエスト以下
        except urllib.error.HTTPError as ex:
            errors += 1
            print(f"[{g['slug']}] HTTP {ex.code}: {ex.read().decode('utf-8', 'replace')[:300]}", file=sys.stderr)
            continue
        except Exception as ex:  # noqa: BLE001 - 1ジャンルの失敗でサイト全体を止めない
            errors += 1
            print(f"[{g['slug']}] 取得失敗: {ex}", file=sys.stderr)
            continue
        if not args.demo:
            prev = load_previous(day, g["slug"])
            save_snapshot(day, g["slug"], items)
        else:
            prev = demo_items({**g, "slug": g["slug"] + "-prev"}, cfg["items_per_genre"])
            for it in prev:
                it["code"] = it["code"].replace("-prev", "")
        results[g["slug"]] = annotate(items, prev)
        print(f"[{g['slug']}] {len(items)}件")

    if not results:
        sys.exit("全ジャンルの取得に失敗しました")
    if not args.demo:
        prune_history()
    render(cfg, results, args.demo, day, updated)
    print(f"生成完了: {OUT_DIR}（失敗ジャンル {errors}件）")


if __name__ == "__main__":
    main()
