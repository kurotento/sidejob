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
# X で「おすすめ教えて」と聞かれやすい物（季節ごと）。実際に検索して、聞いている投稿が毎日出るものだけ
# 2026-11-07 の見直し：パジャマ・敷きパッド・リップ・電気ケトル・ルームシューズは質問が週1件ほどしかなく、
# 「鍋」は食べる鍋の投稿ばかりになるので外し、毎日質問が出る化粧水・ヒーターを足した
SEASONS = {
    (10, 11, 12, 1, 2): ["加湿器", "ハンドクリーム", "ボディクリーム", "化粧水", "毛布", "電気毛布", "湯たんぽ", "ヒーター"],
    (3, 4, 5): ["日焼け止め", "花粉 マスク", "収納ボックス", "掃除機", "化粧水", "ルームウェア"],
    (6, 7, 8, 9): ["日焼け止め", "扇風機", "ハンディファン", "冷感 敷きパッド", "制汗剤", "麦茶"],
}
# 楽天の商品検索で使うジャンル（キーワードを商品名に詰め込んだ別の物を除く。例：「電気毛布」でモバイルバッテリー）
GENRES = {"加湿器": 204549, "ハンドクリーム": 304759, "ボディクリーム": 216671, "化粧水": 216307, "毛布": 205611,
          "電気毛布": 208397, "湯たんぽ": 208202, "ヒーター": 100188, "日焼け止め": 100939, "掃除機": 562637,
          "扇風機": 562637, "ハンディファン": 562637, "制汗剤": 100939}
# おまけ付き・福袋など、その物を買う人に返す候補にならない物
NG = re.compile(r"福袋|おまけ|訳あり|アウトレット|詰め替え用のみ|サンプル")
ASK = "(おすすめ教えて OR オススメ教えて OR 何使ってる OR どれがいい OR おすすめある OR おすすめあったら OR おすすめありますか)"
NOISE = " lang:ja -filter:links -filter:retweets -PR -ROOM -プレゼント -キャンペーン -応募"


def words_for(day):
    m = dt.date.fromisoformat(day).month
    return next(w for months, w in SEASONS.items() if m in months)


def search_urls(words, size=4):
    """まとめて探す X の検索（言葉が多いと検索が長すぎるので、いくつかに分ける）."""
    out = []
    for i in range(0, len(words), size):
        group = words[i:i + size]
        q = "(" + " OR ".join(group) + ") " + ASK + NOISE
        out.append(("・".join(group), f"https://x.com/search?q={urllib.parse.quote(q)}&f=live"))
    return out


def fetch(word, base_url):
    params = {"applicationId": os.environ["RAKUTEN_APP_ID"], "accessKey": os.environ.get("RAKUTEN_ACCESS_KEY", ""),
              "keyword": word, "sort": "-reviewCount", "hits": 30, "availability": 1,
              "minPrice": 500, "maxPrice": 20000, "formatVersion": 2}
    if word in GENRES:
        params["genreId"] = GENRES[word]
    req = urllib.request.Request(SEARCH + "?" + urllib.parse.urlencode(params), headers={
        "Referer": base_url.rstrip("/") + "/", "User-Agent": "rakuten-ranking-site/1.0",
        "Origin": urllib.parse.urlsplit(base_url)._replace(path="").geturl()})
    with urllib.request.urlopen(req, timeout=30) as res:
        return [x.get("Item", x) for x in json.load(res).get("Items", [])]


def pick(raws, word):
    from articles import short_name
    from build import normalize_item
    from itemfilter import excluded  # 本・CD・たばこは ROOM と同じく出さない（同じ種類の候補を並べる場所なので、似た商品の判定は使わない）
    out = []
    for raw in raws:
        it = normalize_item({**raw, "rank": 0})
        short = short_name(it["name"], 40)
        if (excluded(it) or NG.search(it["name"])
                or any(short_name(x["name"], 40)[:6] == short[:6] for x in out)):  # 色違い・サイズ違いは1つに
            continue
        # 返信に出す名前に、聞かれている物の言葉が入っていない物（宣伝文だけの名前・別の物）は使わない
        if not all(w in short for w in word.split()):
            continue
        out.append(it)
        if len(out) >= PER_WORD:
            break
    return out


def tidy(name, n=26):
    """返信に入れる名前：同じ言葉のくり返し（「電気ブランケット … ブランケット」）を除き、単語の区切りで短くする."""
    keep = []
    for w in name.rstrip("…").split():
        if any(w in k or k in w for k in keep):
            continue
        if keep and len(" ".join(keep + [w])) > n:
            break
        keep.append(w)
    return " ".join(keep) or name[:n]


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
        from build import normalize_item
        raws = {}
        for w in words:
            try:
                raws[w] = fetch(w, cfg["base_url"])
            except Exception as ex:  # noqa: BLE001
                print(f"[xseek] {w}: 検索に失敗 {str(ex)[:120]}")
            time.sleep(1.1)  # 商品検索の毎秒の上限を避ける
        try:  # 宣伝文の多い商品名を、先に Gemini で短い名前にしておく（「更に〜おまけ付」のような名前を出さない）
            import names
            names.prepare([normalize_item({**r, "rank": 0}) for v in raws.values() for r in v], day)
        except Exception as ex:  # noqa: BLE001
            print(f"[xseek] 短い名前: 失敗 {str(ex)[:120]}")
        found = {w: pick(v, w) for w, v in raws.items()}
        items = [it for v in found.values() for it in v]
        descs = writer.describe(items, day, limit=cfg.get("xseek_describe_per_day", 30)) if os.environ.get("GEMINI_API_KEY") else {}
        cache = {"day": day, "words": [
            (w, [{"name": tidy(short_name(it["name"], 80)), "price": it["price"], "reviews": it["reviews"], "rating": it["rating"],
                  "url": it["url"], "chips": chips(it, descs.get(it["code"]))} for it in v]) for w, v in found.items() if v]}
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    return {"urls": search_urls(words), "words": cache.get("words", []) if cache.get("day") == day else []}
