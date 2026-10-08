"""自分用のポータル（public/my.html、検索除外）を毎日作る.

手で行う作業のチェックリスト・自動投稿の状態・よく開く管理画面を1ページにまとめる。
自動投稿の状態は、ページを開いたときに GitHub の記録（data/*.txt）を読みに行くので、いつ開いても最新になる。
秘密の情報（キー・パスワード・メール）はこのページに載せない。
"""
import datetime as dt
import html

e = html.escape
RAW = "https://raw.githubusercontent.com/kurotento/sidejob/main/data/"


def tasks(day, videos):
    """今日やること（時間の目安つき）. 返り値は [(時間, 作業, URL, 補足)]."""
    d = dt.date.fromisoformat(day)
    out = []
    if videos:
        out.append(("朝〜昼", f"YouTube にショート動画を投稿（{len(videos)}本）", "shorts.html", "保存 → YouTube アプリで投稿"))
    out.append(("昼〜夜", "X で困っている人に返信（5〜10件）", "replies.html", "検索 → 返信例をコピーして少し直す"))
    out.append(("20〜22時", "楽天ROOM に投稿", "room.html", "新しい会員でログインしているか確認してから"))
    out.append(("20〜22時", "ROOM のいいね・フォロー回り", "room-engage.html", "フォロー20人・いいね50件まで"))
    if d.weekday() == 0:
        out.append(("週1（月曜）", "楽天アフィリエイトの成果レポートを見る", "https://affiliate.rakuten.co.jp/report/",
                    "クリック数と売れた商品をチェック"))
        out.append(("週1（月曜）", "Search Console で検索からの表示回数を見る", "https://search.google.com/search-console", ""))
    if dt.date(2027, 1, 8) <= d <= dt.date(2027, 2, 28) and d.weekday() == 0:
        out.append(("期限つき", "26tyama で Facebook 登録 → Meta 開発者アプリの持ち主を移す", "https://developers.facebook.com/apps/",
                    "仮のアカウントで作ったアプリを 26tyama に移す（accounts.md 参照）"))
    if dt.date(2027, 9, 1) <= d <= dt.date(2027, 10, 8) and d.weekday() == 0:
        out.append(("期限つき", "楽天ウェブサービスのアプリの有効期限を延長（10/8まで）", "https://webservice.rakuten.co.jp/app/list", ""))
    if d.day == 1:
        out.append(("月1（1日）", "ROOM のランク更新のお知らせを見る", "https://room.rakuten.co.jp/", "オリジナル写真の条件を確認"))
    return out


LINKS = [
    ("投稿・予約", [
        ("Buffer（予約の一覧）", "https://publish.buffer.com/"),
        ("YouTube Studio", "https://studio.youtube.com/"),
        ("楽天ROOM（自分のページ）", "{room}"),
        ("Threads 投稿リスト（手で投稿したいとき）", "threads.html"),
    ]),
    ("自分のアカウント", [
        ("X @rankumasidejob", "https://x.com/rankumasidejob"),
        ("Instagram @rankumasidejob", "https://www.instagram.com/rankumasidejob/"),
        ("Threads @rankumasidejob", "https://www.threads.com/@rankumasidejob"),
        ("YouTube @rankumasidejob", "https://www.youtube.com/@rankumasidejob"),
    ]),
    ("成果・数字", [
        ("楽天アフィリエイト 成果レポート", "https://affiliate.rakuten.co.jp/report/"),
        ("Search Console", "https://search.google.com/search-console"),
        ("Instagram のインサイト（アプリから）", "https://www.instagram.com/rankumasidejob/"),
    ]),
    ("サイト", [
        ("楽天ランキング速報", "./"),
        ("1000円台の買い回り", "{budget}"),
        ("ふるさと納税 人気返礼品", "furusato/"),
    ]),
    ("仕組みの管理（たまに）", [
        ("GitHub の自動更新の結果", "https://github.com/kurotento/sidejob/actions"),
        ("GitHub のキー（Secrets）", "https://github.com/kurotento/sidejob/settings/secrets/actions"),
        ("楽天ウェブサービス（期限 2027/10/8）", "https://webservice.rakuten.co.jp/app/list"),
        ("Google AI Studio（Gemini）", "https://aistudio.google.com/api-keys"),
    ]),
]


def build(cfg, day, videos, out_dir):
    m, d = int(day[5:7]), int(day[8:10])
    week = "月火水木金土日"[dt.date.fromisoformat(day).weekday()]
    rows = "".join(f"""<li><label><input type="checkbox" data-k="{n}"><span class="t">{e(t)}</span>
<a href="{e(u)}" target="_blank" rel="noopener">{e(w)}</a>{f'<small>{e(note)}</small>' if note else ''}</label></li>"""
                   for n, (t, w, u, note) in enumerate(tasks(day, videos)))
    fill = {"room": cfg.get("room_url", "https://room.rakuten.co.jp/"), "budget": f"{cfg['budget']['slug']}.html"}
    groups = "".join(
        f"<section><h2>{e(g)}</h2><div class='ls'>" + "".join(
            f'<a href="{e(u.format(**fill))}" target="_blank" rel="noopener">{e(name)}</a>' for name, u in items)
        + "</div></section>" for g, items in LINKS)
    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>らんくま ポータル</title><style>
:root{{--bg:#f6f4f0;--card:#fff;--ink:#1d1d1f;--sub:#6e6e73;--red:#bf0000;--ok:#1f8a4c;--ng:#b42318;--line:#e6e2da}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151515;--card:#222;--ink:#f2f2f2;--sub:#a0a0a0;--line:#333}}}}
body{{margin:0;font-family:system-ui,"Hiragino Sans",sans-serif;background:var(--bg);color:var(--ink)}}
header{{background:var(--red);color:#fff;padding:14px 16px}}header h1{{font-size:1.1rem;margin:0}}header p{{margin:4px 0 0;font-size:.8rem;opacity:.9}}
main{{padding:12px 16px 40px;max-width:720px;margin:0 auto}}section{{background:var(--card);border-radius:14px;padding:12px 14px;margin-bottom:12px}}
h2{{font-size:.98rem;margin:0 0 8px}}ul{{list-style:none;padding:0;margin:0}}li{{border-top:1px solid var(--line);padding:8px 0}}li:first-child{{border-top:0}}
label{{display:grid;grid-template-columns:22px 86px 1fr;gap:4px 8px;align-items:center}}label small{{grid-column:3;color:var(--sub);font-size:.75rem}}
.t{{font-size:.78rem;color:var(--sub)}}li.done a{{text-decoration:line-through;opacity:.5}}a{{color:#2563eb}}
.ls{{display:flex;flex-wrap:wrap;gap:8px}}.ls a{{padding:8px 12px;border-radius:999px;border:1px solid var(--line);text-decoration:none;color:var(--ink);font-size:.85rem}}
.st{{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;font-size:.85rem}}.st b{{font-weight:600}}.ok{{color:var(--ok)}}.ng{{color:var(--ng)}}
.bar{{height:6px;background:var(--line);border-radius:3px;margin:6px 0 2px}}.bar i{{display:block;height:100%;background:var(--ok);border-radius:3px;width:0}}</style></head><body>
<header><h1>🧸 らんくま ポータル</h1><p>{m}月{d}日（{week}）のやること・自動投稿の状態・管理画面のリンク</p></header>
<main>
<section><h2>✅ 今日のやること</h2><div class="bar"><i id="pg"></i></div><ul id="todo">{rows}</ul></section>
<section><h2>🤖 自動投稿の状態</h2><div class="st" id="st"><span>読み込み中…</span></div>
<p style="font-size:.75rem;color:var(--sub);margin:8px 0 0">GitHub の記録から読んでいます。失敗があれば赤く出ます。</p></section>
{groups}
</main>
<script>
const K='portal-{day}';let s={{}};try{{s=JSON.parse(localStorage.getItem(K)||'{{}}')}}catch(e){{}}
const boxes=[...document.querySelectorAll('#todo input')];
function show(){{let n=0;boxes.forEach(b=>{{b.checked=!!s[b.dataset.k];b.closest('li').classList.toggle('done',b.checked);if(b.checked)n++}});
document.getElementById('pg').style.width=(boxes.length?n/boxes.length*100:0)+'%'}}
boxes.forEach(b=>b.addEventListener('change',()=>{{s[b.dataset.k]=b.checked;try{{localStorage.setItem(K,JSON.stringify(s))}}catch(e){{}}show()}}));show();
async function txt(f){{try{{const r=await fetch('{RAW}'+f+'?t='+Date.now());return r.ok?await r.text():''}}catch(e){{return ''}}}}
function row(k,v,cls){{return '<b>'+k+'</b><span class="'+(cls||'')+'">'+v+'</span>'}}
(async()=>{{
 const [b,so]=await Promise.all([txt('build_log.txt'),txt('social_log.txt')]);const out=[];
 const done=b.match(/生成完了.*（失敗ジャンル (\\d+)件）/);out.push(row('サイト更新',done?(done[1]==='0'?'OK':'一部失敗 '+done[1]+'件'):'記録なし',done&&done[1]==='0'?'ok':'ng'));
 const g=b.match(/\\[gemini\\] キーの確認: (.*)/);if(g)out.push(row('Gemini',g[1],g[1].startsWith('OK')?'ok':'ng'));
 const v=b.match(/\\[shorts\\] 動画 (\\d+)本/);if(v)out.push(row('ショート動画',v[1]+'本'));
 for(const [sv,label] of [['x','X'],['threads','Threads'],['instagram','Instagram']]){{
  let ok=0,ng=0,notify=0;
  const sec=so.split(/--- \\d\\d:\\d\\d 予約処理/);
  const want=sv==='x'?/^(\\[x\\])?:/:new RegExp('^\\\\['+sv+'\\\\]');
  const last={{}};  // 同じ投稿を何度か試した場合は、最後の結果だけを数える
  for(const part of sec){{if(!want.test(part))continue;for(const l of part.split('\\n').slice(1)){{const m=l.match(/^(.+?): (予約|失敗)/);if(m)last[m[1]]=l}}}}
  for(const l of Object.values(last)){{if(/: 予約/.test(l)){{ok++;if(/通知/.test(l))notify++}}else ng++}}
  out.push(row(label,'予約 '+ok+'件'+(notify?'（うち通知 '+notify+'）':'')+(ng?' / 失敗 '+ng+'件':''),ng?'ng':(ok?'ok':'')));
 }}
 document.getElementById('st').innerHTML=out.join('');
}})();
</script></body></html>"""
    (out_dir / "my.html").write_text(page, encoding="utf-8")
