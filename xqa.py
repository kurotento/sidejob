"""X の返信ネタ帳用：ROOM・動画で紹介している商品ごとに「検索する言葉・よくある質問・返信例」を作る.

ふつうの人が X でつぶやく言葉（「加湿器 迷う」「毛布 おすすめ」など）で探せるように、
商品名やブランド名ではなく、一般的な呼び方を Gemini に決めてもらう（使えないときは商品名から作る）。
"""
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from articles import short_name
import writer

CACHE = Path(__file__).resolve().parent / "data" / "xqa.json"
MAX_ITEMS = 12
# 買う前に迷っている人の言い回し（言葉は短く、引用符で囲まない方が日本語の投稿に当たりやすい）
ASK = "(おすすめ OR どれがいい OR 何がいい OR 迷う OR 迷って OR 悩む OR 悩んで OR 買おうかな OR 欲しい OR 探してる OR 買い替え)"

SYSTEM = """あなたは X（旧Twitter）で、買い物に迷っている人へ返信する文例を作る担当です。
商品ごとに、次の3つを作ってください。

1. word: その商品を探している人が X でつぶやくときに使う、いちばん一般的な呼び方（普通名詞を1〜2語、10字以内）。
   ブランド名・型番・「楽天」は入れない。細かすぎる言葉（「二枚合わせ毛布」）より、みんなが使う言葉（「毛布」）を選ぶ。
   例：加湿器 / 電気毛布 / ペットカメラ / 味噌汁 フリーズドライ / 収納ボックス / 洗顔 / 抱っこ紐
2. question: その word を含めて、X で誰かが実際につぶやきそうな、買う前の迷いや質問（口語、20〜40字）。
3. answer: その question への返信例（50〜100字、1〜2文）。友だちに教えるような短い返事にする。
   「楽天だと『商品名（短く）』（価格）が○○ですよ」のように、商品名・価格と、与えられた情報にある具体的な事実1つ（容量・サイズ・洗える・機能など）で答える。
   一般論のアドバイス（「まずは〜を測っておくと」「〜を選ぶのがコツです」）、前置き、共感の決まり文句（「わかります！」「迷いますよね」）は書かない。
   自分が使った・買ったような体験談は書かない。効果を断定しない。「No.1」「最安」「人気」などは書かない。リンクは入れない。
   最後に必ず「 #PR」を付ける。口調は「〜ですよ」「〜みたいです」くらいのくだけた丁寧語。
   良い例：「楽天だと『アイリスオーヤマ 上から給水 加湿器』（4,980円）が上から水を入れられるタイプですよ #PR」

入力の順番どおりに、次のJSONだけを出力してください:
{"items": [{"code": "...", "word": "...", "question": "...", "answer": "..."}]}"""


def search_query(word):
    return f"{word} {ASK}"


def fallback(it):
    from social import product_tag
    word = (product_tag(it["name"]) or "").lstrip("#")[:10]
    if not word or re.fullmatch(r"[\x00-\x7f]+", word) or word in ("コラボ", "シャツ"):
        return None  # 探す言葉が作れない商品は出さない（Gemini が使えない日だけ）
    reviews = f"レビュー{it['reviews']:,}件で★{it['rating']:.1f}と評価も多めです" if it.get("reviews") else "楽天で今よく売れています"
    return {"word": word, "question": f"{word}、どれがいいか迷う…おすすめある？",
            "answer": f"楽天だと「{short_name(it['name'], 24)}」（{it['price']:,}円）が{reviews}。選ぶときの候補にどうぞ #PR"}


def ok(d):
    text = f"{d.get('question', '')} {d.get('answer', '')}"
    return (d.get("word") and len(d["word"]) <= 12 and d.get("answer", "").rstrip().endswith("#PR")
            and 30 <= len(d["answer"]) <= 130 and not writer.BANNED.search(text) and "http" not in text
            and not re.search(r"コツです|わかります|迷いますよね|悩みますよね|まずは", d.get("answer", "")))


def ask_model(items, descs, key, model):
    lines = []
    for it in items:
        d = descs.get(it["code"]) or {}
        facts = " / ".join([d.get("intro", ""), *d.get("features", [])]) or it.get("caption", "")[:300]
        lines.append(f"code: {it['code']}\n商品名: {it['name'][:120]}\n価格: {it['price']:,}円\n情報: {facts[:500]}")
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": "\n\n".join(lines)}]}],
        "generationConfig": {"temperature": 0.5, "maxOutputTokens": 4096, "responseMimeType": "application/json"},
    }).encode()
    req = urllib.request.Request(writer.ENDPOINT.format(model=model), data=body,
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=120) as res:
        raw = json.loads(res.read().decode("utf-8", "replace"))
    content = "".join(p.get("text", "") for p in raw["candidates"][0]["content"]["parts"] if not p.get("thought"))
    m = re.search(r"\{.*\}", content, re.S)
    return {x.get("code"): x for x in json.loads(m.group(0)).get("items", [])} if m else {}


def build(items, descs, day):
    """items: その日に ROOM・動画で紹介する商品（重複なし）. 返り値は [(item, {word, question, answer})]."""
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    descs = {**writer.load_cache(), **descs}  # ROOM 用にほかのジャンルで作った紹介文も使う
    items = items[:MAX_ITEMS]
    todo = [it for it in items if it["code"] not in cache]
    key = os.environ.get("GEMINI_API_KEY")
    if todo and key:
        for model in writer.MODELS:
            try:
                got = ask_model(todo, descs, key, model)
                for it in todo:
                    d = got.get(it["code"]) or {}
                    if ok(d):
                        cache[it["code"]] = {k: str(d[k]).strip() for k in ("word", "question", "answer")} | {"day": day}
                break
            except (urllib.error.URLError, ValueError, KeyError, IndexError, TimeoutError) as ex:
                print(f"[xqa] {model} 失敗: {str(ex)[:150]}")
    for it in items:  # 今日も使ったものは残す
        if it["code"] in cache:
            cache[it["code"]]["day"] = day
    keep = (dt.date.fromisoformat(day) - dt.timedelta(days=30)).isoformat()
    cache = {k: v for k, v in cache.items() if v.get("day", day) >= keep}
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    out = [(it, cache.get(it["code"]) or fallback(it)) for it in items]
    return [(it, x) for it, x in out if x]
