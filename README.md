# メシウマ — Google Maps保存リストビューア

Google Mapsから書き出したCSVを、ジャンル・都道府県・市区町村などで検索・絞り込みできるReact/Viteサイトです。GitHub Pagesへ自動デプロイできます。

## まずローカルで確認

Node.js が入っているMacで:

```bash
npm install
npm run dev
```

ターミナルに出る `http://localhost:5173/` をブラウザで開きます。

---

## Google Places APIキーを設定

初回だけ、プロジェクト直下で:

```bash
cp .env.example .env
```

`.env` を開いてGoogle Places API (New) のキーを設定します。

```env
GOOGLE_MAPS_API_KEY=AIzaSyxxxxxxxxxxxxxxxx
```

`.env` は `.gitignore` に入っているためGitHubにはアップロードされません。

---

## 普段の更新方法

### 1. Google Mapsから最新CSVを書き出す

最新のCSVを、このプロジェクト直下の:

```text
メシウマ.csv
```

に上書きします。

### 2. この1コマンドを実行

```bash
./update_data.sh
```

これだけです。

`update_data.sh` は内部で:

```bash
python3 scripts/incremental_update.py メシウマ.csv
```

を実行します。

### 差分更新の仕組み

前回のCSVは自動的に:

```text
csv/prev_メシウマ.csv
```

へ保存されます。

次回 `./update_data.sh` を実行すると、最新の `メシウマ.csv` と `csv/prev_メシウマ.csv` を比較します。

- **新しく追加された店** → Google Places APIで住所・都道府県・市区町村を取得
- **以前からある店** → APIを呼ばず、前回取得した住所情報を再利用
- **最新CSVから消えた店** → `restaurants.json` からも削除
- **メモ・タグ・ジャンル等が変更された既存店** → 最新CSVの内容に更新

したがって、毎月2,000件以上を再度APIに送る必要はありません。

比較には原則として **Google MapsのURL** を使用します。URLがない場合だけ店名を使います。

---

## 初回実行について

`csv/prev_メシウマ.csv` がまだ存在しない最初の1回だけは、全店舗を「新規」とみなします。

```bash
./update_data.sh
```

を実行すると、全件について住所補完を行い、完了後に:

```text
csv/prev_メシウマ.csv
```

が自動生成されます。

以降は差分のみAPIへ送られます。

---

## 差分だけ確認したい

APIを呼ばず、追加・削除された店だけ確認できます。

```bash
./update_data.sh メシウマ.csv --dry-run
```

---

## 新規店のうち20件だけテストしたい

```bash
./update_data.sh メシウマ.csv --limit 20
```

この場合、未処理の新規店が残っている間は `csv/prev_メシウマ.csv` を更新しません。

そのため、次回:

```bash
./update_data.sh
```

を実行すれば、キャッシュ済みの店を飛ばしながら残りを続けて処理できます。

---

## 直接Pythonを実行する場合

通常は `./update_data.sh` だけで十分ですが、直接実行することもできます。

```bash
python3 scripts/incremental_update.py メシウマ.csv
```

主なオプション:

```bash
# 差分確認だけ
python3 scripts/incremental_update.py メシウマ.csv --dry-run

# API問い合わせを20件までに制限
python3 scripts/incremental_update.py メシウマ.csv --limit 20

# 前回CSVを別ファイルにする
python3 scripts/incremental_update.py メシウマ.csv --prev csv/prev_メシウマ.csv
```

---

## データ生成の内部構成

### `scripts/convert_google_maps_csv.py`

Google Maps/Takeout CSVを読み込み、サイトで使うデータ形式へ変換します。

店名・メモ・タグ・コメントから以下のようなジャンルを一次推定します。

- ラーメン
- 寿司
- 焼肉
- 中華
- イタリアン
- カフェ
- カレー
- 和食
- など

判定できない店は `未分類` です。

### `scripts/enrich_places.py`

Google Places API (New) を使って:

- 住所
- 国
- 都道府県
- 市区町村
- Place ID

を補完します。

取得結果は:

```text
.cache/places-cache.json
```

にも保存されます。

### `scripts/incremental_update.py`

今回の通常更新で使うメインスクリプトです。

`convert_google_maps_csv.py` と `enrich_places.py` を組み合わせ、前回CSVとの差分だけをPlaces APIへ送ります。

---

## 生成される店舗データ

サイトが読むファイルは:

```text
public/data/restaurants.json
```

です。

店舗ごとに概ね以下の情報を持ちます。

```json
{
  "name": "○○食堂",
  "memo": "ランチがおすすめ",
  "url": "https://www.google.com/maps/place/...",
  "tags": ["行きたい"],
  "comment": "",
  "genre": "和食",
  "address": "東京都渋谷区...",
  "country": "日本",
  "prefecture": "東京都",
  "city": "渋谷区",
  "placeId": "ChIJ..."
}
```

Web画面では店名だけでなく、`東京都`、`渋谷区`、住所なども検索対象になります。

---

## すでに住所補完済みの `restaurants.json` がある場合

以前の版ですでに全店舗の住所補完を済ませている場合は、もう一度全件APIにかける必要はありません。補完済みの `public/data/restaurants.json` をこのプロジェクトへ入れたうえで、現在のCSVを前回基準として一度だけコピーします。

```bash
mkdir -p csv
cp メシウマ.csv csv/prev_メシウマ.csv
```

その後からは通常どおり:

```bash
./update_data.sh
```

で、新しく追加された店舗だけがPlaces APIの対象になります。

---

## GitHub Pagesへ公開

1. GitHubで新しいリポジトリを作る
2. このフォルダ一式をpushする
3. GitHubのリポジトリで `Settings` → `Pages`
4. `Build and deployment` の `Source` を **GitHub Actions** にする
5. `main` ブランチへpushする

`.github/workflows/deploy.yml` が自動的にViteをビルドして公開します。

その後はデータ更新後に:

```bash
git add .
git commit -m "Update restaurant list"
git push
```

でサイトへ反映できます。

### 注意

`.env` と `.cache/` はGitへコミットしないでください。

一方、`csv/prev_メシウマ.csv` は差分比較に必要なので、複数PCで同じリポジトリを使う場合はコミットしておくと前回状態を共有できます。


## Webフィルター

Web画面では、都道府県・市区町村・ジャンル・タグで絞り込みできます。検索欄は店名、都道府県、市区町村、住所、メモ、タグを対象にします。都道府県を選ぶと、市区町村の候補はその都道府県内だけに絞られます。
