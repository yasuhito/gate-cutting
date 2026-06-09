# Gate Cutting / qCxT 実験コード

量子クラウド環境を想定した **量子回路の Gate Cutting / Wire Cutting** と、デバイスの Fidelity 情報を使った **MIP による切断箇所最適化** の実験コードです。

原稿PDFは `docs/qCxT.pdf`、研究会スライドは `docs/qCxT-hpc203-qs17-slides.pdf` にあります。

## ディレクトリ構成

```text
.
├── README.md
├── AGENTS.md                            # 作業ルール
├── gate_cutting/                        # 共通化した実装コード
│   ├── __init__.py
│   ├── cut_selection.py                 # Qiskit CX命令→CutTarget変換
│   ├── device.py                        # device.jsonパース・ErrorParams抽出
│   ├── gate_cutting.py                  # Gate Cutting 展開・実行
│   └── stim_backend.py                  # Qiskit→Stim変換・ノイズ挿入
├── tests/                               # TDD用テスト
│   ├── test_cut_selection.py
│   ├── test_device.py
│   ├── test_experiment_refactors.py
│   ├── test_gate_cutting.py
│   └── test_stim_backend.py
├── docs/
│   ├── qCxT.pdf                         # 原稿PDF
│   ├── qCxT-hpc203-qs17-slides.pdf      # 研究会スライド
│   ├── implementation-notes.md          # 実装メモ・作者コメント整理
│   └── stim-refactor-plan.html          # Stim リファクタリング作業計画
├── experiments/
│   ├── exp1/                     # 原稿の第1段階実験
│   │   ├── b1.py
│   │   └── benchmark_phase1.py
│   └── exp2/                     # 原稿の第2段階実験
│       ├── b1.py
│       ├── b2.py
│       ├── benchmark_phase1.py
│       ├── benchmark_phase2.py
│       ├── check.py
│       └── device.json
├── legacy/
│   └── ex2/                      # 試作・参考コードと実験ログ
│       ├── e4.py
│       ├── e5.py
│       ├── ev1.py
│       ├── device.json
│       ├── device.good.json
│       ├── good.txt
│       ├── bad.txt
│       └── bad2.txt
└── archive/
    └── original/                 # 元zipと重複PDFの保管
```

## 資料

- `docs/qCxT.pdf` — 原稿PDF（7ページ）
- `docs/qCxT-hpc203-qs17-slides.pdf` — 第203回HPC・第17回QS合同研究発表会の発表スライド（36ページ）
- `docs/implementation-notes.md` — 実装メモ・作者コメント整理
- `docs/stim-refactor-plan.html` — Stim 周辺を再利用可能にするためのリファクタリング計画

## 各実験の位置づけ

### `experiments/exp1/`

原稿の実験コードです。主に **Gate Cutting と Wire Cutting の基礎比較** を行います。

- `benchmark_phase1.py`
  - Qiskit Aer を使った Gate Cutting / Wire Cutting の比較。
  - 切断数に対する復元誤差とサンプリングオーバーヘッドを評価します。
- `b1.py`
  - Stim を使った Gate Cutting のノイズスイープ実験。

### `experiments/exp2/`

原稿の実験コードです。主に **実機を想定したエラー情報 + MIP + Gate Cutting** の評価です。

- `device.json`
  - 実機を想定した量子ビット Fidelity、2量子ビットゲート Fidelity、readout error を含むデバイスデータ。
- `b1.py`
  - MIPで低FidelityなCXゲートを選び、StimでGate Cuttingの効果を評価する統合版。
- `b2.py`
  - `b1.py` の改良版。`max_cuts` を守る処理やランダムデバイス生成機能があります。
- `benchmark_phase1.py`
  - 固定 `device.json` を使った、最大切断数ごとのエラー比較。
- `benchmark_phase2.py`
  - 試行ごとにランダムデバイスを生成するベンチマーク。
- `check.py`
  - デバイスグラフ上で使用ゲート・切断ゲートを可視化する確認用スクリプト。

### `legacy/ex2/`

試作・参考コードです。原稿本体の実験は `experiments/exp1/` と `experiments/exp2/` を参照してください。

ただし `legacy/ex2/ev1.py` には、以下のような再利用価値のある Stim 関連処理があります。

- `load_device_data()`
  - `device.json` から `cx_fidelities`、1Q Fidelity、量子ビット座標、`ErrorParams` を取り出します。
- `qiskit_to_stim()`
  - Qiskit の回路を Stim の回路へ変換します。
- `append_operation_with_noise()`
  - `ErrorParams` を渡すと、通常ゲートの直後に `DEPOLARIZE1` / `DEPOLARIZE2` / readout error などのノイズ命令を挿入します。

## 作者コメント整理

- **`exp1` と `exp2` が原稿の実験コード**です。
- `ex2/ev1.py` などに、`qiskit_to_stim()` や `append_operation_with_noise()` といった Stim 変換・ノイズ挿入処理があります。
- `qiskit_to_stim()` では、CX の後に `I` を入れている箇所があります。
  - コメント上は「同じ命令の場合まとめられるので、CXのあとにはIを入れてまとめられないようにする」という意図です。
  - 作者メモとしては「本来はバリア等を使うべき」という TODO です。
- `device.json` には、実機を想定したエラー/Fidelity 情報が入っています。
- `legacy/ex2/ev1.py` の `load_device_data()` でエラーパラメータを取得できます。
- その `ErrorParams` を `append_operation_with_noise()` に渡すと、通常ゲートの後に対応するノイズゲートが挿入されます。

詳細は `docs/implementation-notes.md` も参照してください。

## 共通モジュール

Stim / device まわりの再利用可能な最小実装を `gate_cutting/` に追加しました。

現在の主なAPI:

- `gate_cutting.cut_selection.CircuitEdge`
- `gate_cutting.cut_selection.collect_cx_edges()` — Qiskit風回路からCX候補を集め、Stim変換後の instruction index を保持。
- `gate_cutting.cut_selection.cut_targets_from_edges()` — MIPで選ばれたedge indexを `CutTarget` に変換。
- `gate_cutting.device.DeviceData`
- `gate_cutting.device.parse_device()` — device JSON から Fidelity / 座標 / `ErrorParams` を抽出。
- `gate_cutting.device.load_device()` — device JSON ファイルを読み込んで `DeviceData` を返す。
- `gate_cutting.stim_backend.ErrorParams`
- `gate_cutting.stim_backend.qiskit_to_stim()` — Qiskit風回路をStim回路へ変換。CX後の区切りは `I` ではなく `TICK`。
- `gate_cutting.stim_backend.append_operation_with_noise()` — `ErrorParams` に基づき `DEPOLARIZE1` / `DEPOLARIZE2` / readout `X_ERROR` を挿入。
- `gate_cutting.stim_backend.run_standard()` — ideal/noisy Stim回路を実行してパリティ期待値を返す。
- `gate_cutting.gate_cutting.CutTarget`
- `gate_cutting.gate_cutting.find_cx_cut_targets()` — `(control, target)` または instruction index から具体的なCX切断対象を探す。
- `gate_cutting.gate_cutting.iter_gate_cut_terms()` — Gate Cutting の各項の係数とサブ回路を生成する。
- `gate_cutting.gate_cutting.run_gate_cut()` — Gate Cutting 展開を実行して重み付き期待値を合成する。

`experiments/exp1/b1.py`, `experiments/exp2/b1.py`, `experiments/exp2/b2.py`, `experiments/exp2/check.py` は、これらの共通モジュールを使う形に移行し始めています。

## 実行環境

主な依存ライブラリ:

```text
numpy
matplotlib
tqdm
qiskit
qiskit-aer
stim
networkx
scipy
```

一部スクリプトでは `tranqu` を optional に使います。未インストールの場合はトランスパイル処理がスキップされる実装があります。

## テスト

実装は TDD で進めます。現在の軽量テストは外部の `stim` / `qiskit` が未インストールでも fake を使って実行できます。`device.json` のパース、Stim変換、Gate Cutting 展開、MIP選択結果の `CutTarget` 化、実験スクリプトの共通モジュール利用を unit test で固定しています。

```bash
python -m unittest discover -v
python -m py_compile gate_cutting/*.py tests/*.py experiments/exp2/b2.py
```

## 実行例

相対パスや同一ディレクトリ import を使っているため、基本的には各実験ディレクトリに移動して実行してください。

```bash
cd experiments/exp1
python benchmark_phase1.py

cd ../exp2
python benchmark_phase1.py
python benchmark_phase2.py
python check.py
```

生成される図の例:

- `experiments/exp1/benchmark_phase1.png`
- `experiments/exp2/b1_benchmark_result.png`
- `experiments/exp2/phase2_benchmark_result.png`

## 整理メモ

- 元の `qCxT.zip` は `archive/original/qCxT.zip` に保管しました。
- `qCxT (1).pdf` は `qCxT.pdf` と同一内容だったため、重複PDFとして `archive/original/qCxT-duplicate.pdf` に移動しました。
- zip 内の macOS メタデータ（`.DS_Store`, `__MACOSX/`）は展開対象から除外しました。
