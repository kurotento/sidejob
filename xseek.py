"""X の返信ネタ帳用：季節ごとに「X でよく聞かれる物」の候補商品を楽天の商品検索で集める（毎朝1回）.

ランキングの商品から返信を作ると、聞かれている物（ハンドクリームなど）が入っていないことが多いので、
聞かれている言葉から出発して、レビューの多い商品を集める。返信文は、相手の条件に合う特徴を選んで組み立てる。
"""
import datetime as dt
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "data" / "xseek.json"
SEARCH = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
PER_WORD = 4
# X で「おすすめ教えて」と聞かれやすい物（季節ごと）。2026-10 に実際の検索で質問が出ることを確認したものから
SEASONS = {
    (10, 11, 12, 1, 2): ["加湿器", "ハンドクリーム", "ボディクリーム", "毛布", "電気毛布", "湯たんぽ", "パジャマ",
                         "敷きパッド", "リップクリーム", "電気ケトル", "鍋", "ルームシューズ"],
    (3, 4, 5): ["日焼け止め", "花粉 マスク", "収納ボックス", "掃除機", "化粧水", "ルームウェア"],
    (6, 7, 8, 9): ["日焼け止め", "扇風機", "ハンディファン", "冷感 敷きパッド", "制汗剤", "麦茶"],
}
ASK = "(おすすめ教えて OR オススメ教えて OR 何使ってる OR どれがいい OR おすすめある OR おすすめあったら OR おすすめありますか)"
NOISE = " lang:ja -filter:links -filter:retweets -PR -ROOM -プレゼント -キャンペーン -応募"


def words_for(day):
    m = dt.date.fromisoformat(day).month
    return next(w for months, w in SEASONS.items() if m in months)


def search_urls(words, size=6):
    """まとめて探す X の検索（言葉が多いと検索が長すぎるので、いくつかに分ける）."""
    out = []
    for i in range(0, len(words), size):
        group = words[i:i + size]
        q = "(" + " OR ".join(group) + ") " + ASK + NOISE
        out.append(("・".join(group), f"https://x.com/search?q={urllib.parse.quote(q)}&f=live"))
    return out


def fetch(word, base_url):
    params = {"applicationId": os.environ["RAKUTEN_APP_ID"], "accessKey": os.environ.get("RAKUTEN_ACCESS_KEY", ""),
              "keyword": word, "sort": "-reviewCount", "hits": 15, "availability": 1,
              "minPrice": 500, "maxPrice": 20000, "formatVersion": 2}
    req = urllib.request.Request(SEARCH + "?" + urllib.parse.urlencode(params), headers={
        "Referer": base_url.rstrip("/") + "/", "User-Agent": "rakuten-ranking-site/1.0",
        "Origin": urllib.parse.urlsplit(base_url)._replace(path="").geturl()})
    with urllib.request.urlopen(req, timeout=30) as res:
        return [x.get("Item", x) for x in json.load(res).get("Items", [])]


def pick(raws, word):
    from articles import short_name
    from build import normalize_item
    import room
    out = []
    for raw in raws:
        it = normalize_item({**raw, "rank": 0})
        head = short_name(it["name"], 40)[:6]
        if (it["code"].split(":")[0] in room.SKIP_SHOPS or room.SKIP_NAME.search(it["name"])
                or any(short_name(x["name"], 40)[:6] == head for x in out)):  # 色違い・サイズ違いは1つに
            continue
        # 検索の言葉と関係の薄い物（「鍋」で鍋つゆ以外の物など）を除く
        if not all(w in it["name"] for w in word.split()):
            continue
        out.append(it)
        if len(out) >= PER_WORD:
            break
    return out


def chips(it, desc):
    """返信に入れる特徴の候補（Gemini の紹介文の特徴、なければキャッチコピーから）."""
    feats = list((desc or {}).get("features") or [])
    if not feats:
        feats = [x.strip() for x in re.split(r"[【】\[\]★☆◆■●♪！!／/|｜、。\s]+", it.get("catch", "")) if 4 <= len(x.strip()) <= 25][:3]
    return [re.sub(r"[。\s]+$", "", f) for f in feats][:3]


def build(cfg, day):
    """返り値: {"urls": [(ラベル, URL)], "words": [(言葉, [{name, price, reviews, rating, url, chips}])]}."""
    from articles import short_name
    import writer
    words = words_for(day)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    if cache.get("day") != day and os.environ.get("RAKUTEN_APP_ID"):
        found = {}
        for w in words:
            try:
                found[w] = pick(fetch(w, cfg["base_url"]), w)
            except Exception as ex:  # noqa: BLE001
                print(f"[xseek] {w}: 検索に失敗 {str(ex)[:120]}")
            time.sleep(1.1)  # 商品検索の毎秒の上限を避ける
        items = [it for v in found.values() for it in v]
        descs = writer.describe(items, day, limit=cfg.get("xseek_describe_per_day", 30)) if os.environ.get("GEMINI_API_KEY") else {}
        cache = {"day": day, "words": [
            (w, [{"name": short_name(it["name"], 34), "price": it["price"], "reviews": it["reviews"], "rating": it["rating"],
                  "url": it["url"], "chips": chips(it, descs.get(it["code"]))} for it in v]) for w, v in found.items() if v]}
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    return {"urls": search_urls(words), "words": cache.get("words", []) if cache.get("day") == day else []}
