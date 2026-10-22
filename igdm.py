"""リールに「リスト」とコメントしてくれた人へ、動画の商品リンクを DM で返す（GitHub Actions で15分ごと、igpost.py のあと）.

Instagram の公式API の「プライベート返信」を使う（コメント1件につき1回、コメントから7日以内）。
こちらから話しかけるのではなく、コメントをくれた人にだけ返す。いいね・フォローの自動化はしない。
config.json の "ig_dm": true で動く。鍵（IG_TOKEN）に instagram_business_manage_comments と
instagram_business_manage_messages の権限が必要。
"""
import datetime as dt
import json
import os
import re

import igpost

ROOT = igpost.ROOT
DM = ROOT / "data" / "instagram_dm.json"        # 動画URL → 送る文（sns.py が毎朝作る）
DONE = ROOT / "data" / "instagram_dm_done.json"  # 返信済みのコメント
JST = igpost.JST
KEYWORD = re.compile(r"リスト|りすと|ﾘｽﾄ|list", re.I)
DAYS = 7


def run():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    token = os.environ.get("IG_TOKEN")
    if not (cfg.get("ig_dm") and token):
        print("ig_dm が off か IG_TOKEN がないためスキップ")
        return
    now = dt.datetime.now(JST)
    media = json.loads(igpost.MEDIA.read_text(encoding="utf-8")) if igpost.MEDIA.exists() else {}
    texts = json.loads(DM.read_text(encoding="utf-8")) if DM.exists() else {}
    done = json.loads(DONE.read_text(encoding="utf-8")) if DONE.exists() else {}
    log = igpost.LOG.read_text(encoding="utf-8").splitlines()[-300:] if igpost.LOG.exists() else []
    me = igpost.call("GET", "me", token, fields="user_id,username")
    sent = 0
    for mid, info in media.items():
        if now - dt.datetime.fromisoformat(info["at"]) > dt.timedelta(days=DAYS):
            continue
        entry = texts.get(info["url"])
        if not entry:
            continue
        try:
            comments = igpost.call("GET", f"{mid}/comments", token, fields="id,text,username", limit=50).get("data", [])
        except RuntimeError as ex:
            log.append(f"{now:%m/%d %H:%M} DM: コメント取得エラー {mid} {str(ex)[:150]}")
            continue
        for c in comments:
            if c["id"] in done or c.get("username") == me.get("username") or not KEYWORD.search(c.get("text", "")):
                continue
            try:
                igpost.call("POST", f"{me['user_id']}/messages", token,
                            recipient=json.dumps({"comment_id": c["id"]}), message=json.dumps({"text": entry["text"]}))
                done[c["id"]] = now.isoformat()
                sent += 1
                log.append(f"{now:%m/%d %H:%M} DM: @{c.get('username', '?')} に商品リンクを送信")
            except RuntimeError as ex:
                done[c["id"]] = "error"  # 同じコメントに何度も失敗し続けないように
                log.append(f"{now:%m/%d %H:%M} DM: 送信エラー @{c.get('username', '?')} {str(ex)[:150]}")
    keep = (now - dt.timedelta(days=30)).isoformat()
    done = {k: v for k, v in done.items() if v == "error" or v >= keep}
    DONE.write_text(json.dumps(done, ensure_ascii=False, indent=0), encoding="utf-8")
    igpost.LOG.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"DM 送信 {sent}件")


if __name__ == "__main__":
    run()
