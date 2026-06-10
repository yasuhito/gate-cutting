# ゲートカッティングの仕組み(ポンチ絵)

量子計算の予備知識がほとんどない読者向けに、本リポジトリのゲートカッティングの仕組みを説明する 16:9 ボード 5 枚(本編 4 枚 + 補足「Stim を使う理由」)。[Slidev](https://sli.dev/) で記述している。

内容は元論文 `docs/qCxT.pdf` と発表スライド `docs/qCxT-hpc203-qs17-slides.pdf`、および `src/gate_cutting/` の実装に基づく。

## 使い方

```bash
npm install

# ブラウザでプレビュー(ホットリロード付き)
npm run dev

# PDF を docs/ponchie/gate-cutting-ponchie.pdf へ書き出し
npm run export
```

書き出した PDF は 1 ページ = 1 ボード(16:9)。PowerPoint に使うときは、PDF のページをスクリーンショットしてスライドに貼る。

## 編集時の注意

- 図版はインライン SVG。SVG の `font-size` 属性は UnoCSS の attributify モードに解釈されてしまうため、**必ず `style="font-size:Npx"` で指定する**こと。
- クラス名は UnoCSS のユーティリティ名と衝突しないものを選ぶこと。`c-purple`(= `color:` 指定)、`mt4` / `mt10`(= margin)、`grow`(= flex-grow)などは衝突して意図しないスタイルが当たる。
- Vue がテンプレート内の改行を空白に潰すため、整形済みテキスト(JSON 例など)は `white-space: pre` ではなく `<br>` + `&nbsp;` で組むこと。
- 各スライドの HTML 内に空行を入れない(markdown のパースが割り込んでレイアウトが壊れる)。
