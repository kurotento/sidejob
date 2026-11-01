"""振り返りレポート（public/report.html、検索除外）を毎日作る。毎週日曜にその週の判断をする用.

- 毎朝、数字を data/metrics.json に1日1行で残す（楽天ROOM・Threads のフォロワー、YouTube ショートの再生数）
- テーマ（曜日の枠・1000円台・ふるさと納税）ごとに、この7日のショートの再生数を並べる
- Google アナリティクス・楽天のクリック数は、それぞれの画面へのリンク（ログインが要るため）
"""
import datetime as dt
import html
import json
import re
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
METRICS = DATA / "metrics.json"
CHANNEL_SHORTS = "https://www.youtube.com/@rankumasidejob/shorts"
THREADS = "https://www.threads.com/@rankumasidejob"
e = html.escape

# ショートの題名に入る言葉 → テーマ（曜日の枠と、毎日の2本）
THEME_WORDS = [("推し活グッズ", "推し活"), ("安い vs 高い", "VSバトル"), ("なんでこれが", "謎解き"), ("猫グッズ", "猫"),
               ("犬グッズ", "犬"), ("ふるさと納税クイズ", "ふるさと納税クイズ"), ("買う前に", "選び方チェック"),
               ("電気代", "冬の節約"), ("一人暮らし", "一人暮らし"), ("あったか", "あったかグッズ"),
               ("1000円台", "1000円台"), ("ふるさと納税", "ふるさと納税"), ("急上昇", "急上昇（旧）")]


def get(url):
    req = urllib.request.Request(url, headers={"Accept-Language": "ja", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def fetch_counts(cfg):
    """今日の数字（取れなかったものは入れない）."""
    out = {}
    try:
        m = re.search(r'"followers":(\d+)', get(cfg["room_url"]))
        if m:
            out["room_followers"] = int(m.group(1))
    except Exception:  # noqa: BLE001
        pass
    try:
        page = html.unescape(get(THREADS))  # 文字が &#x...; の形で入っているので戻してから読む
        m = re.search(r"([\d,.]+K?) Followers", page) or re.search(r"フォロワー\s*([\d,.]+万?)\s*人", page)
        if m:
            n = m.group(1).replace(",", "")
            out["threads_followers"] = (int(float(n[:-1]) * 1000) if n.endswith("K") else
                                        int(float(n[:-1]) * 10000) if n.endswith("万") else int(float(n)))
    except Exception:  # noqa: BLE001
        pass
    try:
        page = get(CHANNEL_SHORTS)
        shorts = []
        for m in re.finditer(r'"accessibilityText":"([^"]{0,200}?)、?,? ?([\d,]+) ?回視聴', page):
            shorts.append([m.group(1).strip(" ,、"), int(m.group(2).replace(",", ""))])
        if shorts:
            out["shorts"] = shorts
    except Exception:  # noqa: BLE001
        pass
    return out


def theme_of(title):
    return next((name for word, name in THEME_WORDS if word in title), "その他")


def short_day(title, year):
    m = re.search(r"【(\d+)/(\d+)】", title)
    return dt.date(year, int(m.group(1)), int(m.group(2))) if m else None


def build(cfg, day, out_dir):
    d = dt.date.fromisoformat(day)
    metrics = json.loads(METRICS.read_text(encoding="utf-8")) if METRICS.exists() else {}
    metrics[day] = {**metrics.get(day, {}), **fetch_counts(cfg)}
    keep = (d - dt.timedelta(days=120)).isoformat()
    metrics = {k: v for k, v in sorted(metrics.items()) if k >= keep}
    METRICS.write_text(json.dumps(metrics, ensure_ascii=False, indent=0), encoding="utf-8")

    # テーマごとの再生数（この7日に出したショート。再生数は今日見た数）
    week = {d - dt.timedelta(days=k) for k in range(1, 8)}
    by_theme = {}
    for title, n in metrics[day].get("shorts", []):
        sd = short_day(title, d.year)
        if sd in week:
            by_theme.setdefault(theme_of(title), []).append((sd, n, title))
    rows = sorted(by_theme.items(), key=lambda kv: -max(n for _, n, _ in kv[1]))
    theme_html = "".join(
        f"<tr><td>{e(name)}</td><td class='n'>{max(n for _, n, _ in v):,}</td><td class='n'>{sum(n for _, n, _ in v) // len(v):,}</td>"
        f"<td class='n'>{len(v)}</td></tr>" for name, v in rows) or "<tr><td colspan='4'>まだショートの数字がありません</td></tr>"

    def change(key):
        """フォロワーの今の数と、7日前・28日前からの増え方."""
        now = metrics[day].get(key)
        if now is None:
            return "取れませんでした"
        parts = [f"{now:,}人"]
        for days in (7, 28):
            past = next((metrics[k][key] for k in sorted(metrics) if k <= (d - dt.timedelta(days=days)).isoformat()
                         and key in metrics[k] and k >= (d - dt.timedelta(days=days + 3)).isoformat()), None)
            if past is not None:
                parts.append(f"{days}日で {now - past:+,}")
        return "（".join(parts[:1]) + ("（" + "・".join(parts[1:]) + "）" if parts[1:] else "")

    m, dd = d.month, d.day
    sunday = d.weekday() == 6
    html_text = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>振り返り {m}/{dd}</title><style>
body{{margin:0;font-family:system-ui,"Hiragino Sans",sans-serif;background:#f6f4f0;color:#1d1d1f}}
header{{background:#1d4ed8;color:#fff;padding:14px 16px}}header h1{{font-size:1.1rem;margin:0}}header p{{margin:4px 0 0;font-size:.8rem;opacity:.9}}
main{{padding:12px;max-width:640px;margin:0 auto}}section{{background:#fff;border-radius:14px;padding:12px 14px;margin-bottom:12px}}
h2{{font-size:.95rem;margin:0 0 8px}}table{{width:100%;border-collapse:collapse;font-size:.85rem}}th,td{{padding:6px 4px;border-bottom:1px solid #eee;text-align:left}}
td.n,th.n{{text-align:right}}.note{{font-size:.78rem;color:#6e6e73}}a{{color:#1d4ed8}}li{{margin:4px 0;font-size:.88rem}}
</style></head><body><header><h1>振り返り（{m}月{dd}日）</h1><p>{'今日は日曜。この1週間の数字で、続けるテーマ・やめるテーマを決める日' if sunday else '毎日更新。判断は日曜にまとめて'}</p></header><main>
<section><h2>テーマごとのショートの再生数（この7日）</h2>
<table><tr><th>テーマ</th><th class="n">いちばん</th><th class="n">平均</th><th class="n">本数</th></tr>{theme_html}</table>
<p class="note">YouTube のショート一覧から、今日の時点の再生数。出した日が新しいほど、まだ伸びる途中です。</p></section>
<section><h2>フォロワー</h2><ul>
<li>楽天ROOM：{e(change("room_followers"))}</li>
<li>Threads：{e(change("threads_followers"))}</li></ul></section>
<section><h2>クリックと売上（ログインして見る）</h2><ul>
<li><a href="https://analytics.google.com/analytics/web/" target="_blank" rel="noopener">Google アナリティクス</a>：「集客」で X・Threads からの人数、「イベント」の rakuten_click で楽天リンクのクリック</li>
<li><a href="https://affiliate.rakuten.co.jp/report/" target="_blank" rel="noopener">楽天アフィリエイトの成果レポート</a>：毎日のクリック数と売上（ROOM・Threads 経由もここ）</li></ul></section>
<section><h2>日曜に決めること</h2><ul>
<li>再生数が上の2〜3テーマ：来週も続ける（ほかの曜日に増やすのもあり）</li>
<li>下のテーマ：2週続けて下なら、別のテーマに入れ替える</li>
<li>ROOM のフォロワーとクリックが増えていなければ、ROOM での見せ方を見直す</li></ul></section>
</main></body></html>"""
    (out_dir / "report.html").write_text(html_text, encoding="utf-8")
    return len(rows)
