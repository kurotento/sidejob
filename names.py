"""商品名から宣伝文句を除いた短い名前を Gemini に作ってもらう（articles.short_name が優先して使う）.

楽天の商品名は「【本気で最安値挑戦中】」「訳あり 最短賞味期限：〜」のように、毎日ちがう形の宣伝文が頭に付く。
言葉の決まりで外すだけでは追いつかないので、まとめて Gemini に頼む。
元の商品名にない言葉が入った答えは使わない（名前をでっち上げないように）。
"""
import datetime as dt
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "data" / "names.json"  # {元の商品名: {"name": 短い名前, "day": 最後に使った日}}
BATCH = 40
KEEP_DAYS = 60

SYSTEM = """楽天市場の商品名から、宣伝文句を取り除いた「商品そのものの名前」を作ってください。

- 残すもの：ブランド名・メーカー名、商品の種類（パックご飯、ヘアミスト、電気ケトルなど）、容量・枚数・サイズなど商品を見分ける言葉
- 取り除くもの：セール・クーポン・ポイント・期間・時刻、ランキング・受賞・販売数・レビュー数、「最安値挑戦」「なくなり次第終了」「訳あり 賞味期限〜」のような売り文句、送料、ショップ名・「公式」「公認ショップ」、検索用のキーワードの羅列
- 元の商品名に書かれている言葉だけを使う（言い換え・補足・翻訳はしない）。語順は自然に並べ替えてよい
- 12〜32字程度

入力の順番どおりに、次のJSONだけを出力してください:
{"names": ["短い名前", ...]}"""


def norm(s):
    return unicodedata.normalize("NFKC", s).lower()


def faithful(orig, short):
    """短い名前の言葉が、すべて元の商品名に入っているか."""
    o = norm(orig)
    words = [w for w in re.split(r"[\s・/／,、×()（）]+", norm(short)) if w]
    return bool(words) and all(w in o for w in words) and 6 <= len(short) <= 40


_cache = None


def load():
    global _cache
    if _cache is None:
        _cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    return _cache


def lookup(name):
    v = load().get(name)
    return v["name"] if v else None


def ask(names, key, model):
    import writer
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": "\n".join(f"{i + 1}. {n}" for i, n in enumerate(names))}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096, "responseMimeType": "application/json"},
    }).encode()
    req = urllib.request.Request(writer.ENDPOINT.format(model=model), data=body,
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=120) as res:
        raw = json.loads(res.read().decode("utf-8", "replace"))
    content = "".join(p.get("text", "") for p in raw["candidates"][0]["content"]["parts"] if not p.get("thought"))
    m = re.search(r"\{.*\}", content, re.S)
    return json.loads(m.group(0)).get("names", []) if m else []


def prepare(items, day):
    """まだ短い名前がない商品名をまとめて作る（毎朝のビルドで1回）. 返り値は新しく作れた件数."""
    import writer
    cache = load()
    for it in items:
        if it["name"] in cache:
            cache[it["name"]]["day"] = day
    todo = list(dict.fromkeys(it["name"] for it in items if it["name"] not in cache))
    key = os.environ.get("GEMINI_API_KEY")
    made = 0
    if todo and key:
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            for model in writer.MODELS:
                try:
                    got = ask(chunk, key, model)
                    for orig, short in zip(chunk, got):
                        short = re.sub(r"\s+", " ", str(short)).strip()
                        if faithful(orig, short):
                            cache[orig] = {"name": short, "day": day}
                            made += 1
                    break
                except (urllib.error.URLError, ValueError, KeyError, IndexError, TimeoutError) as ex:
                    print(f"[names] {model} 失敗: {str(ex)[:150]}")
    keep = (dt.date.fromisoformat(day) - dt.timedelta(days=KEEP_DAYS)).isoformat()
    for k in [k for k, v in cache.items() if v.get("day", day) < keep]:
        del cache[k]
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"[names] 短い名前 新規{made}件 / 対象{len(todo)}件")
    return made
