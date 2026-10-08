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

import furusato
import room
import social
import writer
from render import render

ROOT = Path(__file__).resolve().parent
HISTORY_DIR = ROOT / "data" / "history"
OUT_DIR = ROOT / "public"
RANKING_ENDPOINT = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
JST = dt.timezone(dt.timedelta(hours=9))


def load_config():
    with open(ROOT / "config.json", encoding="utf-8") as f:
        return json.load(f)


# ---------- 取得 ----------

def fetch_ranking(genre_id, base_url, page=1):
    """genre_id が None なら総合ランキング。page は 1〜34（1ページ30件）."""
    params = {
        "applicationId": os.environ["RAKUTEN_APP_ID"],
        "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
        "formatVersion": 2,
        "page": page,
    }
    if genre_id:
        params["genreId"] = genre_id
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
        "postage_free": str(it.get("postageFlag", "")) == "0",
        "in_stock": str(it.get("availability", "1")) == "1",
        "has_range": bool(it.get("hasPriceRange")),
        "catch": (it.get("catchcopy") or "")[:120],
        "caption": clean_caption(it.get("itemCaption") or ""),
        "caption_long": clean_caption(it.get("itemCaption") or "", 1500),
    }


def clean_caption(text, limit=400):
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


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
            "postage_free": rnd.random() < .7, "in_stock": True, "has_range": rnd.random() < .2,
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


def fetch_budget(cfg, demo):
    """総合ランキング上位から、価格帯・送料無料・在庫ありで絞り込む."""
    b = cfg["budget"]
    pool = []
    if demo:
        pool = demo_items({"slug": "budget", "title": "総合"}, 300)
        for it in pool:
            it["price"] = 700 + (it["price"] % 1600)
    else:
        for page in range(1, b["pages"] + 1):
            try:
                items = fetch_ranking(None, cfg["base_url"], page=page)
            except urllib.error.HTTPError as ex:
                print(f"[budget] page {page}: HTTP {ex.code}", file=sys.stderr)
                break
            time.sleep(1.1)
            if not items:
                break
            pool += items
    seen, picked = set(), []
    for it in sorted(pool, key=lambda x: x["rank"]):
        if (b["min_price"] <= it["price"] <= b["max_price"] and it.get("postage_free") and it.get("in_stock")
                and it["code"] not in seen):
            seen.add(it["code"])
            picked.append(it)
    print(f"[budget] 総合{len(pool)}件中 {len(picked)}件が条件に一致")
    return picked[: b["max_items"]]


# ---------- 履歴 ----------

def save_snapshot(day, slug, items):
    d = HISTORY_DIR / day
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{slug}.json", "w", encoding="utf-8") as f:
        # 説明文は容量が大きいので履歴には残さない
        slim = [{k: v for k, v in it.items() if k not in ("caption", "caption_long", "catch")} for it in items]
        json.dump(slim, f, ensure_ascii=False, separators=(",", ":"))


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


def load_series(slug, codes, days=30):
    """商品ごとの [(日付, 順位, 価格), ...] を古い順に返す."""
    series = {c: [] for c in codes}
    if not HISTORY_DIR.exists():
        return series
    for d in sorted(p for p in HISTORY_DIR.iterdir() if p.is_dir())[-days:]:
        f = d / f"{slug}.json"
        if not f.exists():
            continue
        with open(f, encoding="utf-8") as fp:
            for it in json.load(fp):
                if it["code"] in series:
                    series[it["code"]].append((d.name, it["rank"], it["price"]))
    return series


def prune_history(keep_days=60):
    if not HISTORY_DIR.exists():
        return
    dirs = sorted(p for p in HISTORY_DIR.iterdir() if p.is_dir())
    for d in dirs[:-keep_days]:
        shutil.rmtree(d)


def add_to_sitemap(cfg, paths, day):
    sm = OUT_DIR / "sitemap.xml"
    base = cfg["base_url"].rstrip("/")
    extra = "".join(f"<url><loc>{base}/{p}</loc><lastmod>{day}</lastmod></url>" for p in paths)
    sm.write_text(sm.read_text(encoding="utf-8").replace("</urlset>", extra + "</urlset>"), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="APIを使わずダミーデータで生成")
    args = ap.parse_args()
    cfg = load_config()
    now = dt.datetime.now(JST)
    day, updated = now.strftime("%Y-%m-%d"), f"{now.year}年{now.month}月{now.day}日"

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

    budget = None
    if cfg.get("budget"):
        try:
            budget = fetch_budget(cfg, args.demo)
        except Exception as ex:  # noqa: BLE001
            print(f"[budget] 取得失敗: {ex}", file=sys.stderr)
        if budget:
            prev = None if args.demo else load_previous(day, "budget")
            if not args.demo:
                save_snapshot(day, "budget", budget)
            annotate(budget, prev)
    descs = {}
    if budget and not args.demo:
        try:
            descs = writer.describe(budget, day, limit=cfg["budget"].get("describe_per_day", 40))
        except Exception as ex:  # noqa: BLE001 - 紹介文が作れなくてもサイトは出す
            print(f"[describe] 失敗: {ex}", file=sys.stderr)
    series = load_series("budget", [it["code"] for it in budget]) if budget and not args.demo else {}
    if not args.demo:
        prune_history()
    render(cfg, results, args.demo, day, updated, OUT_DIR, budget=budget, series=series, descs=descs)
    cats, fdescs = [], {}
    try:  # ふるさと納税サイト（/furusato/）
        cats = furusato.demo_cats() if args.demo else furusato.fetch_all(cfg)
        fdescs = {}
        if not args.demo:
            top = [it for c in cats for it in c["items"][:10]]
            fdescs = writer.describe(top, day, limit=cfg.get("furusato_describe_per_day", 30))
        fpaths = furusato.render_site(cfg, cats, fdescs, args.demo, day, updated, OUT_DIR)
        add_to_sitemap(cfg, fpaths, day)
        print(f"[furusato] {len(fpaths)}ページ")
    except Exception as ex:  # noqa: BLE001 - ふるさと納税側の失敗でメインサイトは止めない
        print(f"[furusato] 失敗: {ex}", file=sys.stderr)
    if budget:
        try:
            n = room.build(cfg, budget, descs, day, OUT_DIR, save=not args.demo, fcats=cats, fdescs=fdescs, results=results)
            print(f"[room] 投稿リスト {n}件")
        except Exception as ex:  # noqa: BLE001
            print(f"[room] 失敗: {ex}", file=sys.stderr)
    try:  # X の返信用ネタ帳
        import replies
        print(f"[replies] 質問 {replies.build(cfg, budget, cats, day, OUT_DIR)}件")
    except Exception as ex:  # noqa: BLE001
        print(f"[replies] 失敗: {ex}", file=sys.stderr)
    if not args.demo:
        try:  # Threads 用の投稿（悩み別・3案から採点で選ぶ）
            import threads
            print(f"[threads] 投稿 {threads.build(cfg, results, budget, cats, {**descs, **fdescs}, day, OUT_DIR)}本")
        except Exception as ex:  # noqa: BLE001
            print(f"[threads] 失敗: {ex}", file=sys.stderr)
    print(f"生成完了: {OUT_DIR}（失敗ジャンル {errors}件）")
    if not args.demo:
        videos = []
        try:  # YouTube ショート動画（YouTube へのアップロードは手動。X には Buffer 経由で投稿）
            import shorts
            slog = []
            videos = shorts.build(cfg, results, budget, cats, day, OUT_DIR, slog)
            for line in slog:
                print(line)
            print(f"[shorts] 動画 {len(videos)}本")
        except Exception as ex:  # noqa: BLE001
            print(f"[shorts] 失敗: {ex}", file=sys.stderr)
        try:
            social.plan(cfg, results, budget, {**descs, **fdescs}, day, OUT_DIR, cats, videos)
        except Exception as ex:  # noqa: BLE001 - 投稿の失敗でサイト更新は止めない
            print(f"[social] 失敗: {ex}", file=sys.stderr)


if __name__ == "__main__":
    main()
