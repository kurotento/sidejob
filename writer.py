"""Gemini API（無料枠）で商品ごとの紹介文を作り、data/descriptions.json に保存する.

APIキーは環境変数 GEMINI_API_KEY（GitHub の Secrets）から読む。
紹介文はショップの商品説明に書かれた事実だけから作る。体験談・効果の断定は禁止。
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# 新規プロジェクト向けの推奨モデル。前者が使えない場合は後者を試す
MODELS = [m for m in os.environ.get("DESC_MODEL", "gemini-3.5-flash-lite,gemini-3.8-flash").split(",") if m]
CACHE = Path(__file__).resolve().parent / "data" / "descriptions.json"
LOG = Path(__file__).resolve().parent / "data" / "descriptions_log.txt"

SYSTEM = """あなたは楽天市場の商品紹介サイトのライターです。与えられた「商品名」「キャッチコピー」「ショップの商品説明」に書かれている事実だけを使い、日本語で商品を紹介します。

必ず守るルール:
- 情報にないことは書かない（素材・容量・産地・機能などを推測で補わない）
- 自分が使った・食べた・買ったような体験談は絶対に書かない（「使ってみた」「実際に」「私も」などは禁止）
- 健康・美容・医薬的な効果を断定しない（「治る」「痩せる」「シミが消える」などは禁止）
- 「No.1」「最安」「日本一」「ランキング1位」などの順位・最上級の表現は書かない
- 「驚異的」「話題」「大人気」「完璧」などの大げさな言葉は使わない
- あいさつ（こんにちは等）や自己紹介、「紹介するよ」「紹介するね」は書かず、いきなり商品の説明から始める
- 紹介文の中で同じ評価の言葉（便利・重宝・魅力・おすすめ・安心 など）を2回以上使わない
- セール・クーポン・ポイント・送料・期間限定の話は書かない（日によって変わるため）
- 商品名のキーワードの羅列をそのまま書き写さず、自然な文章にする

次のJSONだけを出力してください:
{"intro": "案内役のクマ『らんくま』の口調（〜だよ、〜だね）で、4文・160〜230字の紹介文。起承転結で書く。起＝何の商品か。承＝主な特徴や中身。転＝選ぶときのポイントや、この商品ならではの良さ。結＝この商品が活きる場面や、向いている人を述べて締めくくる（最後の文は必ずこの結論にする）。結びの言い回しは商品に合わせて毎回変える（例：『〜する日の常備用にしておくと安心だね』『〜を始めたい人の最初の1本にいいよ』『〜な家庭なら出番が多そうだね』）。『ちょうどいい』『ぴったり』は使わない",
 "features": ["主な特徴を3つ。各35字以内の普通の文体"],
 "for_whom": "こんな人に向いている、を1文・50字以内",
 "check": "購入前に確認したほうがよい点（サイズ・容量・色の選択、賞味期限、対応機種など）を1文・60字以内。その商品ならではの注意点がなければ空文字にする（『注文内容を確認』のような一般的なことは書かない）"}"""

BANNED = re.compile(r"使ってみ|食べてみ|飲んでみ|試してみ|実際に使|私も|わたしも|僕も|買ってよかった|リピしてる|愛用|"
                    r"No\.?\s*1|ナンバーワン|日本一|世界一|最安|ランキング1位|ちょうどいい|ちょうど良い|ぴったり")
GREETING = re.compile(r"^(こんにちは[^。！!]*[。！!]\s*|(案内役の)?(クマの)?『?らんくま』?だよ[。！!]\s*)+")


def tidy_intro(text):
    """定型のあいさつ・前置きを除く（一覧で同じ書き出しが並ばないように）."""
    text = GREETING.sub("", text.strip())
    text = re.sub(r"^今回は、?", "", text)
    return text.strip()


def load_cache():
    if CACHE.exists():
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache, day, keep_days=60):
    # ランキングから外れて60日以上たった紹介文は消す（容量を抑える）
    cutoff = (dt.date.fromisoformat(day) - dt.timedelta(days=keep_days)).isoformat()
    cache = {k: v for k, v in cache.items() if v.get("last_seen", day) >= cutoff}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=0, sort_keys=True)


def call_model(item, key, model):
    user = (f"商品名: {item['name']}\nキャッチコピー: {item.get('catch', '')}\n"
            f"ショップの商品説明: {item.get('caption_long') or item.get('caption', '')}")
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2048, "responseMimeType": "application/json"},
    }).encode()
    req = urllib.request.Request(ENDPOINT.format(model=model), data=body, headers={
        "Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=90) as res:
        raw = res.read().decode("utf-8", "replace")
    try:
        parts = json.loads(raw)["candidates"][0]["content"]["parts"]
        content = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    except (ValueError, KeyError, IndexError) as ex:
        raise ValueError(f"応答の形式が想定外: {raw[:300]}") from ex
    m = re.search(r"\{.*\}", content, re.S)  # ```json などの囲みを外す
    if not m:
        raise ValueError(f"JSONが見つからない: {content[:300]}")
    return json.loads(m.group(0))


REPEATABLE = ("便利", "重宝", "魅力", "おすすめ", "安心", "手軽", "活躍")


def validate(d):
    if not isinstance(d, dict):
        return None
    intro = tidy_intro(str(d.get("intro", "")))
    feats = [str(x).strip() for x in d.get("features", []) if str(x).strip()][:3]
    out = {"intro": intro, "features": feats,
           "for_whom": str(d.get("for_whom", "")).strip(), "check": str(d.get("check", "")).strip()}
    text = " ".join([intro, out["for_whom"], out["check"], *feats])
    if len(intro) < 100 or len(feats) < 2 or BANNED.search(text):
        return None
    if "紹介する" in intro or any(intro.count(w) >= 2 for w in REPEATABLE):
        return None
    return out


def describe(items, day, limit=40):
    """未作成の商品について紹介文を作る。返り値は {itemCode: 紹介文dict}."""
    cache = load_cache()
    token = os.environ.get("GEMINI_API_KEY")
    model = MODELS[0]
    log = []
    todo = [it for it in items if it["code"] not in cache and (it.get("caption") or it.get("catch"))]
    if token and todo:
        done = fails = 0
        for it in todo[:limit]:
            if fails >= 3 and done == 0:  # 最初から連続で失敗するなら設定の問題。無料枠を無駄にしない
                log.append("連続で失敗したため中断")
                break
            try:
                try:
                    d = validate(call_model(it, token, model))
                except urllib.error.HTTPError as ex:
                    if ex.code not in (500, 503):
                        raise
                    time.sleep(15)  # 一時的な混雑。1回だけ再試行
                    d = validate(call_model(it, token, model))
                if d is None:  # ルール違反なら1回だけ書き直させる
                    time.sleep(7)
                    d = validate(call_model(it, token, model))
            except urllib.error.HTTPError as ex:
                if ex.code == 404 and model != MODELS[-1]:  # モデルが使えなければ次の候補へ
                    model = MODELS[MODELS.index(model) + 1]
                    log.append(f"モデルが見つからないため {model} に切り替え")
                    continue
                log.append(f"{it['code']}: HTTP {ex.code} {ex.read().decode('utf-8', 'replace')[:300]}")
                fails += 1
                if ex.code == 429:  # 無料枠の上限。残りは翌日
                    break
                continue
            except Exception as ex:  # noqa: BLE001
                log.append(f"{it['code']}: {ex}")
                fails += 1
                continue
            if d:
                cache[it["code"]] = {**d, "created": day}
                done += 1
            else:
                log.append(f"{it['code']}: ルール違反または不完全な出力のため不採用")
            time.sleep(7)  # 無料枠の毎分上限を避ける
        log.insert(0, f"{day} model={model} 新規{done}件 / 対象{len(todo)}件")
    elif not token:
        log.append(f"{day} GEMINI_API_KEY がないため紹介文の作成をスキップ")
    for it in items:
        if it["code"] in cache:
            cache[it["code"]]["last_seen"] = day
    save_cache(cache, day)
    LOG.write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log[:5]), file=sys.stderr)
    return {it["code"]: cache[it["code"]] for it in items if it["code"] in cache}
