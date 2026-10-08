"""Instagram 投稿の予約表（Google スプレッドシート）の読み書き.

列は別事業のシートと同じ形:
  日付 / 投稿枠 / 種別(post=リール, story, image=フィード画像) / 予約日時 / 動画URL / キャプション / ステータス / 更新日時 / メモ
ステータス: 予約 → 完了 / エラー（手で「キャンセル」にすれば投稿されない）

鍵は GitHub の Secrets「GOOGLE_SA_JSON」（サービスアカウントの JSON）。シートIDは config.json の instagram_sheet_id。
"""
import datetime as dt
import json
import os

HEADER = ["日付", "投稿枠", "種別", "予約日時", "動画URL", "キャプション", "ステータス", "更新日時", "メモ"]
JST = dt.timezone(dt.timedelta(hours=9))


def open_sheet(sheet_id):
    import gspread  # GitHub の実行環境でだけ入れる
    creds = json.loads(os.environ["GOOGLE_SA_JSON"])
    ws = gspread.service_account_from_dict(creds).open_by_key(sheet_id).sheet1
    if ws.row_values(1) != HEADER:  # 空のシートなら見出しを書く
        ws.update(range_name="A1:I1", values=[HEADER])
        ws.freeze(rows=1)
    return ws


def now_text():
    return dt.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")


def add_rows(sheet_id, rows):
    """rows: [{"日付","投稿枠","種別","予約日時","動画URL","キャプション"}]。同じ 予約日時＋種別 がある行は足さない."""
    if not rows or not os.environ.get("GOOGLE_SA_JSON"):
        return 0
    ws = open_sheet(sheet_id)
    have = {(r.get("予約日時"), r.get("種別")) for r in ws.get_all_records(expected_headers=HEADER)}
    new = [[r["日付"], r["投稿枠"], r["種別"], r["予約日時"], r["動画URL"], r["キャプション"], "予約", now_text(), ""]
           for r in rows if (r["予約日時"], r["種別"]) not in have]
    if new:
        ws.append_rows(new, value_input_option="RAW")
    return len(new)
