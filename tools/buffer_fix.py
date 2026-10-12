"""一回限りの手直し用：Buffer の予約済み投稿を調べたり置き換えたりする（GitHub Actions の buffer-fix で動かす）.

python tools/buffer_fix.py schema  … Buffer API の項目を data/buffer_fix_log.txt に書く
python tools/buffer_fix.py singles … 今日の残りの1商品投稿を、こちらで置いた画像で予約し直す
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import social  # noqa: E402

LOG = ROOT / "data" / "buffer_fix_log.txt"
key = os.environ["BUFFER_API_KEY"]
out = []


def schema():
    t = '{ name args { name type { name kind ofType { name kind ofType { name kind } } } } }'
    q = "{ __schema { queryType { fields %s } mutationType { fields %s } } }" % (t, t)
    d = social.gql(key, q)["__schema"]
    for kind in ("queryType", "mutationType"):
        for f in d[kind]["fields"]:
            out.append(f"{kind} {f['name']}: {json.dumps(f['args'], ensure_ascii=False)}")
    for name in ("PostsInput", "PostsFiltersInput", "DeletePostInput", "Post", "PostsResults", "PostEdge"):
        try:
            ty = social.gql(key, '{ __type(name: "%s") { kind fields { name type { name kind ofType { name kind } } } '
                                 'inputFields { name type { name kind ofType { name kind } } } } }' % name)["__type"]
            out.append(f"TYPE {name}: {json.dumps(ty, ensure_ascii=False)}")
        except Exception as ex:  # noqa: BLE001
            out.append(f"TYPE {name}: {ex}")


def singles():
    """data/buffer_fix.json の投稿を、画像だけ差し替えて予約し直す（古い予約は消す）."""
    fix = json.loads((ROOT / "data" / "buffer_fix.json").read_text(encoding="utf-8"))
    channel = social.find_channel(key)
    org = social.gql(key, "query { account { organizations { id } } }")["account"]["organizations"][0]["id"]
    q = ('{ posts(first: 100, input: {organizationId: %s, filter: {channelIds: [%s]}}) '
         '{ edges { node { id status dueAt text assets { __typename } } } } }') % (json.dumps(org), json.dumps(channel))
    nodes = [e["node"] for e in social.gql(key, q)["posts"]["edges"]]
    for f in fix:
        due = f["due"][:16]
        hits = [n for n in nodes if (n.get("dueAt") or "")[:16] == due and n["text"][:30] == f["text"][:30]]
        out.append(f"{f['time']}: 予約 {len(hits)}件 状態 {[h['status'] for h in hits]}")
        hits = [h for h in hits if h["status"] not in ("sent", "error")]
        if len(hits) != 1:
            out.append("  → 1件に決まらないので触らない")
            continue
        r = social.create(key, {"text": f["text"], "due": f["due"], "image": f["image"]}, channel)
        if not r.get("id") and not (r.get("post") or {}).get("id"):
            out.append(f"  → 新しい予約に失敗: {json.dumps(r, ensure_ascii=False)[:200]}")
            continue
        d = social.gql(key, 'mutation { deletePost(input: {id: %s}) { __typename } }' % json.dumps(hits[0]["id"]))
        out.append(f"  → 予約し直し・古い予約を削除 {json.dumps(d, ensure_ascii=False)[:120]}")


if __name__ == "__main__":
    try:
        {"schema": schema, "singles": singles}[sys.argv[1]]()
    except Exception as ex:  # noqa: BLE001
        out.append(f"エラー: {ex}")
    LOG.write_text("\n".join(out) + "\n", encoding="utf-8")
