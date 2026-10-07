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
    render(cfg, results, args.demo, day, updated, OUT_DIR)
    print(f"生成完了: {OUT_DIR}（失敗ジャンル {errors}件）")


if __name__ == "__main__":
    main()
