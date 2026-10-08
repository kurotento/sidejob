"""予約表（スプレッドシート）を見て、時間になった Instagram 投稿を公開する（GitHub Actions で15分ごと）.

Instagram の公式API（Instagram ログイン方式）を使う。鍵は Secrets の IG_TOKEN（60日で切れるので、週1回延長する）。
  リール : media_type=REELS, video_url
  ストーリー: media_type=STORIES, video_url
  フィード画像: image_url（JPEGのみ）
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import igsheet

API = "https://graph.instagram.com/v23.0"
ROOT = Path(__file__).resolve().parent
LOG = ROOT / "data" / "instagram_log.txt"
STATE = ROOT / "data" / "instagram_state.json"
JST = igsheet.JST


def call(method, path, token, **params):
    params["access_token"] = token
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(f"{API}/{path}?{data.decode()}")
    else:
        req = urllib.request.Request(f"{API}/{path}", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return json.load(res)
    except urllib.error.HTTPError as ex:
        raise RuntimeError(ex.read().decode("utf-8", "replace")[:300]) from ex


def publish(token, uid, kind, url, caption):
    if kind == "image":
        c = call("POST", f"{uid}/media", token, image_url=url, caption=caption)
    elif kind == "story":
        c = call("POST", f"{uid}/media", token, media_type="STORIES", video_url=url)
    else:  # post = リール
        c = call("POST", f"{uid}/media", token, media_type="REELS", video_url=url, caption=caption, share_to_feed="true")
    cid = c["id"]
    for _ in range(40):  # 動画は Instagram 側の処理が終わるまで待つ（最大10分）
        st = call("GET", cid, token, fields="status_code,status").get("status_code")
        if st == "FINISHED":
            break
        if st == "ERROR":
            raise RuntimeError(f"動画処理エラー: {call('GET', cid, token, fields='status')}")
        time.sleep(15)
    return call("POST", f"{uid}/media_publish", token, creation_id=cid)["id"]


def run():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    token = os.environ.get("IG_TOKEN")
    sheet_id = cfg.get("instagram_sheet_id")
    if not (sheet_id and os.environ.get("GOOGLE_SA_JSON")):
        print("GOOGLE_SA_JSON / instagram_sheet_id がないためスキップ")
        return
    ws = igsheet.open_sheet(sheet_id)  # 見出しがなければここで書く（シートの接続確認も兼ねる）
    print("予約表に接続しました")
    if not token:
        print("IG_TOKEN がないため投稿はスキップ")
        return
    log = LOG.read_text(encoding="utf-8").splitlines()[-300:] if LOG.exists() else []
    rows = ws.get_all_records(expected_headers=igsheet.HEADER)
    now = dt.datetime.now(JST)
    uid = None
    for i, r in enumerate(rows, start=2):  # 2行目からがデータ
        if r["ステータス"] != "予約":
            continue
        try:
            due = dt.datetime.strptime(str(r["予約日時"]), "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)
        except ValueError:
            continue
        if due > now:
            continue
        if now - due > dt.timedelta(hours=6):  # 大きく遅れたものは出さない（夜のストーリーが翌朝に出るなどを防ぐ）
            ws.update(range_name=f"G{i}:I{i}", values=[["キャンセル", igsheet.now_text(), "予約時刻から6時間以上過ぎたため自動キャンセル"]])
            continue
        uid = uid or call("GET", "me", token, fields="user_id")["user_id"]
        ws.update(range_name=f"G{i}:H{i}", values=[["投稿中", igsheet.now_text()]])
        try:
            mid = publish(token, uid, r["種別"], r["動画URL"], r["キャプション"])
            ws.update(range_name=f"G{i}:I{i}", values=[["完了", igsheet.now_text(), f"media_id={mid}"]])
            log.append(f"{now:%m/%d %H:%M} {r['予約日時']} {r['種別']}: 完了 media_id={mid}")
        except Exception as ex:  # noqa: BLE001
            ws.update(range_name=f"G{i}:I{i}", values=[["エラー", igsheet.now_text(), f"投稿処理エラー: {ex}"[:400]]])
            log.append(f"{now:%m/%d %H:%M} {r['予約日時']} {r['種別']}: エラー {str(ex)[:200]}")
    refresh(token, log)
    LOG.write_text("\n".join(log) + "\n", encoding="utf-8")


def refresh(token, log):
    """鍵の期限を延ばす（週1回）。新しい鍵が返ってきたら GitHub の Secrets を差し替える."""
    now = dt.datetime.now(JST)
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    if state.get("refreshed", "") > (now - dt.timedelta(days=7)).isoformat():
        return
    try:
        r = json.load(urllib.request.urlopen(
            f"https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token={token}", timeout=60))
    except Exception as ex:  # noqa: BLE001
        log.append(f"{now:%m/%d %H:%M} 鍵の延長: 失敗 {ex}")
        return
    days = int(r.get("expires_in", 0)) // 86400
    STATE.write_text(json.dumps({"refreshed": now.isoformat(), "expires": (now + dt.timedelta(days=days)).date().isoformat()}),
                     encoding="utf-8")
    new = r.get("access_token", "")
    if new and new != token:
        ok = update_secret("IG_TOKEN", new)
        log.append(f"{now:%m/%d %H:%M} 鍵の延長: 新しい鍵（残り{days}日）" + ("→ Secrets を更新" if ok else "→ Secrets を更新できず（要対応）"))
    else:
        log.append(f"{now:%m/%d %H:%M} 鍵の延長: OK（残り{days}日）")


def update_secret(name, value):
    """GH_PAT（Secrets 書き込み権限のある個人用トークン）があれば、Secrets を差し替える."""
    pat = os.environ.get("GH_PAT")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not (pat and repo):
        return False
    try:
        from base64 import b64encode

        from nacl import encoding, public
        h = {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json"}
        key = json.load(urllib.request.urlopen(urllib.request.Request(
            f"https://api.github.com/repos/{repo}/actions/secrets/public-key", headers=h), timeout=30))
        box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))
        body = json.dumps({"encrypted_value": b64encode(box.encrypt(value.encode())).decode(), "key_id": key["key_id"]}).encode()
        urllib.request.urlopen(urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/secrets/{name}",
                                                      data=body, headers=h, method="PUT"), timeout=30)
        return True
    except Exception as ex:  # noqa: BLE001
        print(f"Secrets の更新に失敗: {ex}", file=sys.stderr)
        return False


if __name__ == "__main__":
    run()
