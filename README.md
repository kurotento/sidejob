# 楽天ランキング速報サイト（自動更新アフィリエイト）

楽天市場のジャンル別ランキングを毎朝7時に自動取得し、
「急上昇」「値下がり中」「高評価の売れ筋」を付けた静的サイトを GitHub Pages に公開します。
リンクは楽天アフィリエイトリンクなので、そこから購入されると紹介料が入ります。

運用コスト：0円（GitHub Pages・GitHub Actions・楽天API はすべて無料枠）

## あなたがやること（初回のみ・約30分）

アカウント登録やキー発行は本人が行う必要があります。

1. **楽天アフィリエイト** に楽天会員でログインし、アフィリエイトIDを確認
   https://affiliate.rakuten.co.jp/
2. **楽天ウェブサービス** でアプリを新規登録 → `applicationId` と `accessKey` を控える
   https://webservice.rakuten.co.jp/
   - アプリの「WebサイトURL」には公開先URL（例 `https://<GitHubユーザー名>.github.io/sidejob`）を登録
3. **GitHub** で `sidejob` という公開リポジトリを作成
4. リポジトリの Settings → Secrets and variables → Actions に3つ登録
   - `RAKUTEN_APP_ID` / `RAKUTEN_ACCESS_KEY` / `RAKUTEN_AFFILIATE_ID`
5. Settings → Pages → Source を **GitHub Actions** に変更
6. `config.json` の `base_url` を公開先URLに書き換え

ここまで終わったら Claude Code に「pushして初回ビルドして」と頼めば残りは自動です。

## ローカルで確認

```bash
python build.py --demo
```

`public/index.html` をブラウザで開くと見た目を確認できます（デモ表示はダミーデータ）。

## 仕組み

- `build.py` … 楽天ランキングAPIを取得 → `data/history/日付/` に保存 → 前日と比較 → `public/` にHTML生成
- `.github/workflows/daily.yml` … 毎日 7:00 JST に上記を実行し、履歴をコミットして Pages に公開
- `config.json` … サイト名・ジャンル（genreId）の設定。ジャンルを増やすとページが増えます

## 収益を伸ばすために（任意）

- Google Search Console にサイトを登録し `sitemap.xml` を送信（検索からの流入の入口）
- X(Twitter) などで「今日の急上昇」を発信（流入がないと売上はほぼ0です）
- ジャンルを絞り込む（例：「ふるさと納税」「ガジェット」）と検索で上位を取りやすくなります
