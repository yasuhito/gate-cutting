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

- `gate_cutting/stim_backend.py`
  - `ErrorParams`
  - `qiskit_to_stim()`
  - `append_operation_with_noise()`
  - `run_standard()`

参考になる既存実装:

- `legacy/ex2/ev1.py`
  - `load_device_data()`
  - `qiskit_to_stim()`
  - `append_operation_with_noise()`
- `experiments/exp1/b1.py`
  - `qiskit_to_stim()`
  - `append_operation_with_noise()`
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

### `load_device_data()`

`legacy/ex2/ev1.py` の `load_device_data(data)` は、デバイスJSONから次を取り出します。

- `cx_fidelities`
- `one_q_fidelities`
- `qubit_coords`
- `ErrorParams(one_qubit, two_qubit, readout)`

`ErrorParams` は Stim でノイズを挿入するためのエラーレート集合です。

### `append_operation_with_noise()`

`append_operation_with_noise()` に `ErrorParams` を渡すと、通常ゲートの後にノイズ命令を追加します。

代表例:

- 1量子ビットゲート後: `DEPOLARIZE1`
- CX 後: `DEPOLARIZE2`
- 測定前/測定時: readout error 用の `X_ERROR` など

この処理により、`device.json` の Fidelity / error 情報を使ったノイズ付き Stim 回路を作れます。

## MIP まわり

`experiments/exp2/` の `MIPCutFinder` は、回路中の CX をグラフのエッジとして扱い、Fidelity が低いエッジを優先して切断対象にします。

大まかな流れ:

1. Qiskit 回路を作る。
2. 必要なら Tranqu / Qiskit で対象デバイスへトランスパイルする。
3. 回路中の CX とデバイス Fidelity からグラフを作る。
4. MIP で切断対象の CX を選ぶ。
5. Stim 回路へ変換する。
6. 通常ノイズあり実行と Gate Cutting あり実行を比較する。

## 注意点 / TODO

- `I` を使った CX 後の区切りは暫定実装です。バリア相当の処理に置き換える余地があります。
- スクリプトは研究用の実験コードで、相対パスや同一ディレクトリ import に依存しています。実行時は対象ディレクトリへ移動してください。
- `legacy/ex2/` は実験過程のコードを含むため、最終的な原稿実験の再現には `experiments/exp1/` と `experiments/exp2/` を優先してください。
