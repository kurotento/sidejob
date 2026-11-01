"""商品の判定（ROOM・ショート・ストーリーで共通）.

- excluded: 出さない商品（本・CD・たばこ など）
- similar: 同じような商品（簡易トイレが3つ並ぶ、など）
- pick_varied: 候補の上から、似た商品を飛ばして選ぶ
"""
import re

# 本・CD・DVD など（好みが分かれて「1000円台だから載せた」ようにしか見えない／ROOM の投稿画面で写真が出ないことが多い）と
# たばこ関連は出さない
SKIP_SHOPS = {"book", "ploom"}
SKIP_NAME = re.compile(r"CD|DVD|Blu-?ray|ブルーレイ|アルバム|写真集|月号|ムック|コミック|文庫|単行本|書籍|"
                       r"VOLUME|カレンダー|トレカ|たばこ|タバコ", re.I)
# 商品名の宣伝の言葉（似た商品かどうかを比べるときは除く）
AD_WORD = re.compile(r"位|OFF|オフ|[%％]|クーポン|送料|ポイント|楽天|限定|SALE|セール|公式|倍|円|獲得|ランキング|累計|人気|お試し|あす楽|即納")


def excluded(it):
    return it["code"].split(":")[0] in SKIP_SHOPS or bool(SKIP_NAME.search(it["name"]))


def name_words(name):
    """似た商品かどうかを比べるための、商品名の主な言葉（【】などの宣伝文と記号を除く）."""
    name = re.sub(r"【[^】]*】|\[[^\]]*\]|［[^］]*］|＼[^／]*／|「[^」]*」|<[^>]*>", " ", name)
    words = re.split(r"[\s　/／|｜・,，、。!！?？()（）『』★☆◆◇■□●○※+＋]+", name)
    return [w for w in words if len(w) >= 2 and not AD_WORD.search(w)]


def similar(a, b):
    """同じような商品なら True。最初のほうの主な言葉（3文字以上）が、相手の名前の最初のほうに含まれていれば似た商品とみなす."""
    if a["code"] == b["code"]:
        return True
    wa, wb = name_words(a["name"])[:4], name_words(b["name"])[:4]
    ja, jb = "".join(wa), "".join(wb)
    return any(len(w) >= 3 and w in jb for w in wa) or any(len(w) >= 3 and w in ja for w in wb)


def pick_varied(cands, n, chosen=()):
    """候補の上から、すでに選んだ物（chosen を含む）と似ていない商品を n 件まで選ぶ."""
    out = []
    for it in cands:
        if len(out) >= n:
            break
        if not any(similar(it, o) for o in [*chosen, *out]):
            out.append(it)
    return out
