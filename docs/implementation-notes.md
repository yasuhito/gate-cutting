# 実装メモ

作者コメントとコード上の重要箇所を整理したメモです。

## 原稿の実験コード

原稿に対応する実験コードは以下です。

- `experiments/exp1/`
  - Gate Cutting と Wire Cutting の基礎比較。
  - サンプリングオーバーヘッド、復元誤差、ショット数依存性を見るコード。
- `experiments/exp2/`
  - 実機想定デバイスの Fidelity / error 情報を使う実験。
  - MIP で切断対象の CX ゲートを選び、Stim で Gate Cutting の効果を評価するコード。

`legacy/ex2/` は試作・参考コードです。

## Stim 変換まわり

共通化した実装:

- `gate_cutting/cut_selection.py`
  - `CircuitEdge`
  - `collect_cx_edges()`
  - `cut_targets_from_edges()`
- `gate_cutting/device.py`
  - `DeviceData`
  - `parse_device()`
  - `load_device()`
- `gate_cutting/stim_backend.py`
  - `ErrorParams`
  - `qiskit_to_stim()`
  - `append_operation_with_noise()`
  - `run_standard()`
- `gate_cutting/gate_cutting.py`
  - `CutTarget`
  - `find_cx_cut_targets()`
  - `iter_gate_cut_terms()`
  - `run_gate_cut()`

参考になる既存実装:

- `legacy/ex2/ev1.py`
  - `load_device_data()`
  - `qiskit_to_stim()`
  - `append_operation_with_noise()`
- `experiments/exp1/b1.py`
  - 旧実装では `qiskit_to_stim()` / `append_operation_with_noise()` をローカル定義していた。
  - 現在は `gate_cutting.stim_backend` と `gate_cutting.gate_cutting` を利用する形へ移行済み。
- `experiments/exp2/b1.py`, `experiments/exp2/b2.py`
  - `StimGateCutSimulator.qiskit_to_stim()`
  - `StimGateCutSimulator._append_op_with_noise()`

### `qiskit_to_stim()`

Qiskit の `QuantumCircuit` を Stim の `stim.Circuit` に変換する処理です。

代表的な変換:

- `x` → `X`
- `y` → `Y`
- `z` → `Z`
- `h` → `H`
- `s` → `S`
- `sdg` → `S_DAG`
- `cx` / `cnot` → `CX`
- `measure` → `M`

旧実装では CX の後に `I` を追加している箇所があります。

```python
stim_circ.append("CX", qs)
stim_circ.append("I", qs)
```

意図は、Stim 側で同種の命令がまとめられる/最適化されることで、後段のノイズ挿入位置がずれるのを避けるためです。

共通モジュール `gate_cutting/stim_backend.py` では、この暫定的な `I` の代わりに `TICK` を使います。

```python
stim_circ.append("CX", qs)
stim_circ.append("TICK")
```

`TICK` は annotation として「ここで区切る」意図が明確で、追加の identity gate を混ぜずに済みます。

## ノイズ挿入まわり

### デバイスデータ

`experiments/exp2/device.json` および `legacy/ex2/device.json` には、実機を想定した以下の情報があります。

- 量子ビットID
- 量子ビット座標
- 1量子ビット Fidelity
- readout error
- coupling / CX Fidelity

### `load_device_data()` / `gate_cutting.device`

`legacy/ex2/ev1.py` の `load_device_data(data)` は、デバイスJSONから次を取り出します。

- `cx_fidelities`
- `one_q_fidelities`
- `qubit_coords`
- `ErrorParams(one_qubit, two_qubit, readout)`

共通モジュールでは、この処理を `gate_cutting/device.py` の `parse_device()` / `load_device()` に切り出しています。

`ErrorParams` は Stim でノイズを挿入するためのエラーレート集合です。

### `append_operation_with_noise()`

`append_operation_with_noise()` に `ErrorParams` を渡すと、通常ゲートの後にノイズ命令を追加します。

代表例:

- 1量子ビットゲート後: `DEPOLARIZE1`
- CX 後: `DEPOLARIZE2`
- 測定前/測定時: readout error 用の `X_ERROR` など

この処理により、`device.json` の Fidelity / error 情報を使ったノイズ付き Stim 回路を作れます。

## Gate Cutting まわり

`gate_cutting/gate_cutting.py` に Gate Cutting 展開を切り出しています。`experiments/exp1/b1.py` と `experiments/exp2/b2.py` の Gate Cutting 実行は、この共通実装へ委譲し始めています。

- `CutTarget` は具体的な CX 命令を `instruction_index` と `qubits` で表します。
- `find_cx_cut_targets()` は、従来の `(control, target)` ペア指定にも対応しつつ、同じペアの CX が複数ある場合に備えて instruction index 指定もできます。
- `iter_gate_cut_terms()` は、`0.5(II + ZI + IX - ZX)` の各項に対応するサブ回路を生成します。
- `run_gate_cut()` は、各サブ回路の期待値を係数付きで合成します。

## MIP まわり

`experiments/exp2/` の `MIPCutFinder` は、回路中の CX をグラフのエッジとして扱い、Fidelity が低いエッジを優先して切断対象にします。

`gate_cutting/cut_selection.py` では、Qiskit風回路の CX 命令を `CircuitEdge` として集め、MIPで選ばれた edge index を `CutTarget` に変換します。`CutTarget.instruction_index` は、`qiskit_to_stim()` で `TICK` を挿入した後の Stim 回路上の CX index です。これにより、同じ `(control, target)` の CX が複数ある場合でも、MIPが選んだ具体的なゲートだけを切断できます。

大まかな流れ:

1. Qiskit 回路を作る。
2. 必要なら Tranqu / Qiskit で対象デバイスへトランスパイルする。
3. 回路中の CX とデバイス Fidelity からグラフを作る。このとき元のCX候補を `CircuitEdge` として保持する。
4. MIP で切断対象の CX edge index を選ぶ。
5. 選ばれた edge index を `CutTarget` に変換する。
6. Stim 回路へ変換する。
7. 通常ノイズあり実行と Gate Cutting あり実行を比較する。

## 注意点 / TODO

- `I` を使った CX 後の区切りは暫定実装です。バリア相当の処理に置き換える余地があります。
- スクリプトは研究用の実験コードで、相対パスや同一ディレクトリ import に依存しています。実行時は対象ディレクトリへ移動してください。
- `legacy/ex2/` は実験過程のコードを含むため、最終的な原稿実験の再現には `experiments/exp1/` と `experiments/exp2/` を優先してください。
