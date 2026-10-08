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
