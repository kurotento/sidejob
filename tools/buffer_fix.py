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


if __name__ == "__main__":
    try:
        {"schema": schema}[sys.argv[1]]()
    except Exception as ex:  # noqa: BLE001
        out.append(f"エラー: {ex}")
    LOG.write_text("\n".join(out) + "\n", encoding="utf-8")
