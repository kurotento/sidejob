"""「リスト」と送ってくれた人へ、動画の商品リンクを DM で返す（GitHub Actions で15分ごと、igpost.py のあと）.

- リールに「リスト」とコメント → 公式API の「プライベート返信」（コメント1件につき1回、7日以内）
- ストーリーを見て DM で「リスト」と送ってきた → その DM に返信（相手のメッセージから24時間以内）
こちらから話しかけるのではなく、送ってくれた人にだけ返す。いいね・フォローの自動化はしない。
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
DONE = ROOT / "data" / "instagram_dm_done.json"  # 返信済みのコメント・メッセージ
JST = igpost.JST
KEYWORD = re.compile(r"リスト|りすと|ﾘｽﾄ|list", re.I)
COMMENT_DAYS = 7
DM_HOURS = 24


def parse(t):
    return dt.datetime.strptime(t, "%Y-%m-%dT%H:%M:%S%z")


def latest_text(media, texts, before, kinds=("story", "post")):
    """その時刻より前に出した動画のうち、いちばん新しいものの商品リンク（ストーリーを優先）."""
    for kind in kinds:
        cands = sorted(((dt.datetime.fromisoformat(v["at"]), v["url"]) for v in media.values()
                        if v.get("kind", "post") == kind and texts.get(v["url"]) and dt.datetime.fromisoformat(v["at"]) <= before),
                       reverse=True)
        if cands:
            return texts[cands[0][1]]["text"]
    return None


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

    def send(key, recipient, text, who):
        nonlocal sent
        try:
            igpost.call("POST", f"{me['user_id']}/messages", token,
                        recipient=json.dumps(recipient), message=json.dumps({"text": text}))
            done[key] = now.isoformat()
            sent += 1
            log.append(f"{now:%m/%d %H:%M} DM: @{who} に商品リンクを送信")
        except RuntimeError as ex:
            done[key] = "error"  # 同じものに何度も失敗し続けないように
            log.append(f"{now:%m/%d %H:%M} DM: 送信エラー @{who} {str(ex)[:150]}")

    # 1) リールへのコメント
    for mid, info in media.items():
        if info.get("kind", "post") != "post" or now - dt.datetime.fromisoformat(info["at"]) > dt.timedelta(days=COMMENT_DAYS):
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
            send(c["id"], {"comment_id": c["id"]}, entry["text"], c.get("username", "?"))

    # 2) DM で「リスト」と送ってきた人（ストーリーからの人）
    try:
        convs = igpost.call("GET", "me/conversations", token, platform="instagram", fields="id,updated_time", limit=20).get("data", [])
    except RuntimeError as ex:
        convs = []
        log.append(f"{now:%m/%d %H:%M} DM: 会話の取得エラー {str(ex)[:150]}")
    for cv in convs:
        if now - parse(cv["updated_time"]) > dt.timedelta(hours=DM_HOURS):
            continue
        try:
            msgs = igpost.call("GET", cv["id"], token, fields="messages{id,message,created_time,from}").get("messages", {}).get("data", [])
        except RuntimeError as ex:
            log.append(f"{now:%m/%d %H:%M} DM: メッセージ取得エラー {str(ex)[:150]}")
            continue
        for msg in msgs:
            frm = msg.get("from") or {}
            if (msg["id"] in done or frm.get("id") == str(me["user_id"]) or frm.get("username") == me.get("username")
                    or not KEYWORD.search(msg.get("message") or "")
                    or now - parse(msg["created_time"]) > dt.timedelta(hours=DM_HOURS)):
                continue
            text = latest_text(media, texts, parse(msg["created_time"]))
            if not text:
                text = ("メッセージありがとうございます！\nおすすめの商品はROOMにまとめています👇\n"
                        f"{cfg.get('room_url', '')}\n※楽天アフィリエイトのリンクです（PR）")
            send(msg["id"], {"id": frm["id"]}, text, frm.get("username", "?"))

    keep = (now - dt.timedelta(days=30)).isoformat()
    done = {k: v for k, v in done.items() if v == "error" or v >= keep}
    DONE.write_text(json.dumps(done, ensure_ascii=False, indent=0), encoding="utf-8")
    igpost.LOG.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"DM 送信 {sent}件")


if __name__ == "__main__":
    run()
