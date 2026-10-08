"""楽天ROOM 用のコメント本文を Gemini で書く（data/room_comments.json にキャッシュ）.

商品ごとに「書き方の型」を変えて、リストに同じ形の文が並ばないようにする。
材料はサイト用の紹介文（descriptions.json）と商品データだけ。体験談は書かせない。
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from writer import BANNED, ENDPOINT, MODELS

CACHE = Path(__file__).resolve().parent / "data" / "room_comments.json"

STYLES = [
    ("問いかけ", "読む人の困りごとや季節の場面を問いかける1文から始める（例：『〜な朝、つらくないですか？』）。続けてこの商品がどう役立つかを2〜3文で"),
    ("場面", "この商品を使う具体的な場面（時間帯・場所・家族構成など）を描くところから始め、その場面での良さを2〜3文で"),
    ("推し3つ", "短い前置き1文のあと、推しポイントを3つ、行頭に絵文字（毎回ちがう絵文字）を付けて1行ずつ書く"),
    ("選び方", "この種類の商品を選ぶときに見るべき点を1つ挙げ、この商品がその点でどうかを説明する。最後に注意点か選び方のコツを1文"),
    ("数字", "容量・個数・サイズ・レビュー件数などの数字を最初に出して興味を引き、そのあと中身を2〜3文で"),
    ("ひとこと", "2〜3行の短い文だけで、テンポよく。くだけた口調で、体言止めも使ってよい"),
]

SYSTEM = """あなたは楽天ROOMに商品を投稿している、暮らしや買い物が好きな30代の投稿者です。
与えられた商品情報だけを使って、ROOMの投稿コメントの本文を書きます。

必ず守るルール:
- 情報にないことは書かない（素材・容量・産地・機能などを推測で補わない）
- 自分が使った・食べた・買ったような体験談は絶対に書かない（「使ってみた」「リピ」「愛用」「届いた」「私も」などは禁止）。「気になる」「〜な人によさそう」のような書き方はOK
- 効果を断定しない。No.1・最安・大人気・話題・完璧などの言葉は使わない
- 価格・送料・ポイント・セール・ハッシュタグは書かない（あとで別に付ける）
- 「〜だよ」「〜だね」を続けて使わない。語尾は「です・ます」「〜かも」「〜な人に」「体言止め」などを混ぜる
- AIっぽい定型（『いかがでしょうか』『〜してみてはいかが』『魅力』『おすすめです』の連発）は避ける
- 改行を使って読みやすく。全体で70〜160字
- 絵文字は0〜3個まで

出力は次のJSONだけ: {"text": "本文"}"""


def load():
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def style_for(code):
    return sum(map(ord, code)) % len(STYLES)


def call(prompt, key, model):
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9, "maxOutputTokens": 1024, "responseMimeType": "application/json"},
    }).encode()
    req = urllib.request.Request(ENDPOINT.format(model=model), data=body, headers={
        "Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=90) as res:
        raw = json.loads(res.read().decode("utf-8", "replace"))
    parts = raw["candidates"][0]["content"]["parts"]
    content = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    m = re.search(r"\{.*\}", content, re.S)
    return json.loads(m.group(0))["text"].strip() if m else ""


def ok(text):
    t = re.sub(r"\s+", "", text)
    return 50 <= len(t) <= 220 and not BANNED.search(text) and "#" not in text and not re.search(r"\d+円|送料|ポイント|届いた|リピ", text)


def write(items, descs, day, kinds, limit=40):
    """items の ROOM コメント本文を用意する。返り値は {code: 本文}。キーがなければキャッシュだけ使う."""
    cache = load()
    key = os.environ.get("GEMINI_API_KEY")
    model = MODELS[0]
    made = fails = 0
    for it in items:
        code = it["code"]
        if code in cache or not key or made >= limit or fails >= 3:
            continue
        d = descs.get(code) or {}
        name, how = STYLES[style_for(code)]
        prompt = (f"書き方の型: {name} — {how}\n"
                  f"商品の種類: {kinds.get(code, '')}\n商品名: {it['name']}\n"
                  f"紹介文: {d.get('intro', '')}\n特徴: {' / '.join(d.get('features', []))}\n"
                  f"向いている人: {d.get('for_whom', '')}\n注意点: {d.get('check', '')}\n"
                  f"レビュー: {it.get('reviews', 0)}件 平均{it.get('rating', 0)}")
        text = ""
        for _ in range(2):  # ルール違反なら1回だけ書き直させる
            try:
                text = call(prompt, key, model)
            except urllib.error.HTTPError as ex:
                if ex.code == 404 and model != MODELS[-1]:
                    model = MODELS[MODELS.index(model) + 1]
                    continue
                fails += 1
                if ex.code == 429:
                    fails = 3
                break
            except Exception:  # noqa: BLE001
                fails += 1
                break
            time.sleep(7)  # 無料枠の毎分上限を避ける
            if ok(text):
                break
            text = ""
        if text:
            cache[code] = {"text": text, "style": name, "created": day}
            made += 1
    keep = {it["code"] for it in items}
    cache = {k: v for k, v in cache.items() if k in keep or v.get("created", day) >= day[:8]}  # 当月分は残す
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    return {k: v["text"] for k, v in cache.items() if k in keep}
