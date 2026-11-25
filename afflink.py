"""楽天アフィリエイトのリンクに「計測ID」を付けて、どのSNSから売れたかをレポートで分けられるようにする（2026-11-25〜）.

計測IDは楽天アフィリエイトの「サイト情報の登録・変更」で登録したもの（20個まで）。
リンクの形は楽天のリンク作成画面と同じ：hb.afl.rakuten.co.jp/ichiba/<ID>/_RTLink<番号>?pc=<商品ページ>
楽天の「SNSリンク」（a.r10.to の短縮）は商品ごとに画面で作る仕組みで自動では作れないため、こちらを使う。
"""
import urllib.parse

ICHIBA_ID = "59f8cdbc.19b6dd93.59f8cdbd.627f207f"  # 自分のアフィリエイトID（リンク作成画面の形。公開リンクに出るもの）
TRACK = {"threads": 159536, "igstory": 159537, "x": 159538, "youtube": 159539, "pinterest": 159540}


def tag(url, channel):
    """楽天の商品リンク（API の hgc 形式でも、商品ページのURLでも）を計測ID付きにする。分からない形はそのまま返す."""
    code = TRACK.get(channel)
    if not (url and code):
        return url
    u = urllib.parse.urlparse(url)
    if u.netloc == "hb.afl.rakuten.co.jp":
        pc = urllib.parse.parse_qs(u.query).get("pc", [""])[0]
    elif u.netloc.endswith("rakuten.co.jp") and u.netloc.startswith(("item.", "www.")):
        pc = url
    else:
        return url
    if not pc:
        return url
    return (f"https://hb.afl.rakuten.co.jp/ichiba/{ICHIBA_ID}/_RTLink{code}"
            f"?pc={urllib.parse.quote(pc, safe='')}&link_type=hybrid_url")
