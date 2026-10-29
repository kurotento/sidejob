"""Instagram ストーリー（リンクスタンプ付き）を手で出すための素材ページ（public/story.html、検索除外）を毎日作る.

公式API ではリンクスタンプを付けられないので、投稿は手で行う。
手間を減らすため「①画像を保存 → ②リンクをコピー → ③Instagram を開く」のボタンだけにする。
リンクは商品ページへ直接（ROOM を挟むと買うまでの手順が1つ増えるため）。
"""
import datetime as dt
import html
import json
from pathlib import Path

from articles import short_name

DATA = Path(__file__).resolve().parent / "data"
HISTORY = DATA / "story_history.json"  # 出した商品（同じ商品を続けて出さない）
PER_DAY = 3
REPEAT_DAYS = 30
W, H = 1080, 1920
e = html.escape


def pick(budget, results, day):
    hist = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else {}
    cutoff = (dt.date.fromisoformat(day) - dt.timedelta(days=REPEAT_DAYS)).isoformat()
    hist = {k: v for k, v in hist.items() if k >= cutoff}
    used = {c for k, codes in hist.items() if k != day for c in codes}
    import room  # 本・CD・たばこは ROOM と同じく出さない
    ok = lambda it: (it["code"] not in used and it.get("image") and it["reviews"] >= 50  # noqa: E731
                     and it["code"].split(":")[0] not in room.SKIP_SHOPS and not room.SKIP_NAME.search(it["name"]))
    out = []
    pools = [budget or []] + [(results or {}).get(g, []) for g in room.NICHE_GENRES + room.MORE_GENRES]
    for pool in pools:  # 1000円台から1つ、あとはジャンルを順に
        it = next((x for x in pool if ok(x) and x not in out), None)
        if it:
            out.append(it)
        if len(out) >= PER_DAY:
            break
    hist[day] = [it["code"] for it in out]
    HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=0), encoding="utf-8")
    return out


def make_image(it, path, theme):
    from PIL import Image, ImageDraw

    import design
    from social import fetch_image, wrap
    bg, accent = theme
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    d.text((W // 2, 230), "楽天でいま売れてる", font=design.font("sans", 64), fill=accent, anchor="mm")
    d.rounded_rectangle((110, 330, W - 110, 1110), 48, fill="white")
    pic = fetch_image(it["image"], 600)
    if pic:
        pic.thumbnail((700, 700))
        im.paste(pic, ((W - pic.width) // 2, 720 - pic.height // 2))
    y = 1170
    for line in wrap(d, short_name(it["name"], 40), design.font("sans", 54), W - 200, 2):
        d.text((W // 2, y), line, font=design.font("sans", 54), fill="#222", anchor="mm")
        y += 72
    price = f"{it['price']:,}円" + ("・送料無料" if it.get("postage_free") else "")
    d.text((W // 2, y + 40), price, font=design.font("sans", 76), fill=accent, anchor="mm")
    if it.get("reviews"):
        d.text((W // 2, y + 130), f"★{it['rating']:.1f}（レビュー{it['reviews']:,}件）", font=design.font("sans", 44),
               fill="#555", anchor="mm")
    # この文字のすぐ下（空いている所）にリンクスタンプを置く
    d.text((W // 2, 1560), "▼ 商品ページはこちら ▼", font=design.font("sans", 48), fill=accent, anchor="mm")
    d.text((W - 60, H - 60), "PR", font=design.font("sans", 36), fill="#888", anchor="rd")
    im.save(path, quality=90)


THEMES = [("#fff4e8", "#e2541b"), ("#eef6ff", "#1f6fd1"), ("#f3fbef", "#2f8f3a")]


def build_muse_page(cfg, items, day, out_dir):
    """Muse が読む用のページ。みくすろいど側の today.html と同じ形にそろえてある。

    人が見る story.html とは別に出す。Muse への指示を両方で同じ文面にできるようにするため。
    """
    base = cfg["base_url"].rstrip("/")
    rows = ""
    for n, it in enumerate(items, 1):
        url = f"{base}/story/{day}-{n}.jpg"
        rows += (f'<li><h2>{n}. {e(short_name(it["name"], 40))}</h2>'
                 f'<p>素材URL: <a href="{e(url)}">{e(url)}</a>（画像）</p>'
                 f'<p class="link">リンクスタンプ: <b>商品を見る</b><br>'
                 f'<a href="{e(it["url"])}">{e(it["url"])}</a></p></li>')
    page = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="robots" content="noindex,nofollow">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>今日のストーリー {day}</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:24px;line-height:1.7}}
 li{{margin-bottom:28px}} h2{{font-size:1.05rem;margin:0 0 6px}}
 .link b{{color:#0a7}}
</style></head><body>
<h1>今日のストーリー（{day}）</h1>
<p>全{len(items)}件。上から順に投稿してください。テキストは入れず、リンクスタンプの指定があるものだけ付けてください。</p>
<ol>{rows}</ol>
</body></html>"""
    (out_dir / "story-muse.html").write_text(page, encoding="utf-8")


def build(cfg, budget, results, day, out_dir):
    items = pick(budget, results, day)
    (out_dir / "story").mkdir(parents=True, exist_ok=True)
    cards = ""
    for n, it in enumerate(items):
        name = f"story/{day}-{n + 1}.jpg"
        make_image(it, out_dir / name, THEMES[n % len(THEMES)])
        cards += f"""<article class="c"><img src="{e(name)}" alt="">
<h2>{n + 1}. {e(short_name(it['name'], 40))}</h2>
<a class="b" href="{e(name)}" download="story-{day}-{n + 1}.jpg">① 画像を保存</a>
<button class="b" data-u="{e(it['url'])}">② リンクをコピー</button>
<a class="b" href="instagram://story-camera">③ Instagram を開く</a></article>"""
    m, d = int(day[5:7]), int(day[8:10])
    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>ストーリー素材 {m}/{d}</title><style>
body{{font-family:sans-serif;margin:0;background:#fafafa;color:#222}}header{{background:#c13584;color:#fff;padding:12px 16px}}
h1{{font-size:1.05rem;margin:0}}header p{{margin:4px 0 0;font-size:.8rem}}main{{padding:12px 16px;max-width:560px;margin:auto}}
.c{{background:#fff;border-radius:12px;padding:12px;margin:0 0 16px;box-shadow:0 1px 3px #0002}}.c img{{width:100%;border-radius:8px}}
h2{{font-size:.9rem;margin:8px 0}}.b{{display:block;width:100%;box-sizing:border-box;text-align:center;padding:12px;margin:6px 0;border-radius:8px;
border:0;background:#c13584;color:#fff;font-size:.95rem;text-decoration:none;font-family:inherit}}.b.ok{{background:#2f8f3a}}
ol{{font-size:.85rem;padding-left:20px}}</style></head><body>
<header><h1>📷 Instagram ストーリー素材（{m}月{d}日）</h1><p>1日1〜3本。リンク付きストーリーで、見た人が商品ページへ直接行けます</p></header><main>
<div id="pc" style="display:none;background:#fff3cd;border-radius:8px;padding:12px;margin:0 0 12px;font-size:.9rem">
⚠ ストーリーはスマホの Instagram アプリでしか投稿できません。<b>スマホのカメラでこのQRコードを読んで</b>、スマホでこのページを開いてください。
<div id="qr" style="margin:10px auto 0;width:180px"></div></div>
<ol><li>①で画像を保存（スマホは長押し→「写真に保存」でもOK）</li><li>②でリンクをコピー</li>
<li>③でInstagramを開き、保存した画像を選ぶ → 上のスタンプ → 「リンク」に貼り付け</li>
<li>スタンプは「▼ 商品ページはこちら ▼」のすぐ下に置き、表示する文字を「商品を見る」に変える</li></ol>
{cards or '<p>今日の素材はありません</p>'}</main>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
<script>if(!/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)){{document.getElementById("pc").style.display="block";
try{{new QRCode(document.getElementById("qr"),{{text:location.href,width:180,height:180}})}}catch(e){{}}}}
document.querySelectorAll("button[data-u]").forEach(b=>b.onclick=async()=>{{
try{{await navigator.clipboard.writeText(b.dataset.u);b.textContent="✓ コピーしました";b.classList.add("ok")}}catch(e){{prompt("コピーしてください",b.dataset.u)}}}});</script>
</body></html>"""
    (out_dir / "story.html").write_text(page, encoding="utf-8")
    build_muse_page(cfg, items, day, out_dir)
    return len(items)
