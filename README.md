# OQTOPUS 向けゲートカッティングコンポーネント

[![CI](https://github.com/yasuhito/gate-cutting/actions/workflows/ci.yml/badge.svg)](https://github.com/yasuhito/gate-cutting/actions/workflows/ci.yml)

このリポジトリは、論文著者が研究用に作成したゲートカッティング / ワイヤーカッティング実験スクリプトを整理し、OQTOPUS の一部として実際に動かせる品質まで高めるためのリファクタリングプロジェクトです。

現在は、実験スクリプトに散らばっていた Stim 変換、デバイス情報の読み込み、MIP による切断対象選択、ゲートカッティング実行処理を `src/gate_cutting/` にコンポーネント化しています。`experiments/` と `legacy/` は、元論文の再現・比較・現状仕様確認のために残しています。

## クイックスタート

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

`.[dev]` には Ruff、pytest、pytest-cov、mypy、build を含めています。

検証:

```bash
python -m unittest discover -v
python -m py_compile src/gate_cutting/*.py tests/*.py experiments/exp2/b2.py
ruff check src tests
```

## 最小利用例

```python
from gate_cutting.circuits import random_clifford_circuit
from gate_cutting.device import load_device
from gate_cutting.mip import MIPCutFinder
from gate_cutting.stim_backend import qiskit_to_stim, run_standard
from gate_cutting.gate_cutting import run_gate_cut

# デバイス情報とノイズモデルを読み込む。
device = load_device("experiments/exp2/device.json")

# Qiskit 回路を生成する。
qc = random_clifford_circuit(num_qubits=10, depth=4, seed=1)

# MIP で具体的な CX 切断対象を選ぶ。
finder = MIPCutFinder(device)
cut_graph = finder.build_cut_graph(qc)
cuts = finder.solve_cut_graph(cut_graph, max_cuts=2, cut_fidelity_threshold=0.96)

# Stim へ変換して、通常実行とゲートカッティング実行を比較する。
stim_circuit = qiskit_to_stim(qc)
standard_value = run_standard(stim_circuit, shots=1000, error_params=device.error_params)
cut_value = run_gate_cut(stim_circuit, cuts, device.error_params, shots=1000)
```

## API 概要

| モジュール | 役割 |
| --- | --- |
| `gate_cutting.circuits` | ランダム Clifford 回路生成。 |
| `gate_cutting.device` | `device.json` をフィデリティ、量子ビット座標、`ErrorParams` へ変換する処理。 |
| `gate_cutting.stim_backend` | Qiskit から Stim への変換、`TICK` 区切り、ノイズ挿入、測定処理、パリティ期待値サンプリング。 |
| `gate_cutting.cut_selection` | Qiskit の CX 命令を具体的な `CircuitEdge` / `CutTarget` へ対応付ける処理。 |
| `gate_cutting.mip` | SciPy MILP による切断対象選択。命令番号とフィデリティを保持した `CutTarget` を返す。 |
| `gate_cutting.gate_cutting` | ゲートカッティングの分解と、重み付きサブ回路実行。 |

主なデータ構造:

- `ErrorParams(one_qubit, two_qubit, readout)` — デバイスフィデリティから導出した Stim ノイズ確率。
- `CircuitEdge(edge_index, instruction_index, qubits, fidelity, source_instruction_index)` — MIP 選択対象になる CX 候補。
- `CutTarget(instruction_index, qubits, fidelity=None)` — 切断対象として選ばれた具体的な CX 命令。

## リポジトリ構成

```text
src/gate_cutting/ OQTOPUS 統合に向けた再利用可能コンポーネント
tests/            単体テストと現状仕様確認テスト
experiments/      論文実験を共通コンポーネント利用へ移行したコード
legacy/           参考用に残す元実装・試作コード
docs/             実装メモ、リファクタリング計画、原論文資料
```

## ドキュメント

- `docs/ponchie-slidev/` — 量子計算の予備知識がない人向けの仕組み解説ポンチ絵(Slidev、16:9 ボード 5 枚)。書き出し済み PDF は `docs/ponchie/gate-cutting-ponchie.pdf`。
- `docs/implementation-notes.html` — 実装メモとモジュールの流れを視覚的にまとめた資料。
- `docs/stim-refactor-plan.html` — Stim リファクタリング計画と完了状況。
- `docs/qCxT.pdf` — 元論文。
- `docs/qCxT-hpc203-qs17-slides.pdf` — 発表スライド。

## 現在の状態

完了済み:

- 共通 Stim バックエンド、デバイスパーサー、ゲートカッティング補助機能、MIP 切断対象選択機能、回路生成補助機能の追加。
- 主要な `experiments/exp1` / `experiments/exp2` スクリプトの共通コンポーネント利用への移行。
- SciPy MILP による切断対象選択。
- デバイス解析、Stim 変換、ノイズ挿入、ゲートカッティング展開、MIP 選択、実験スクリプトの共通化、実 Stim 簡易動作をテストで固定。

今後の作業:

- OQTOPUS へ直接統合するためのパッケージ / API 形状の整理。
- ワイヤーカッティングのコンポーネント化。
- Tranqu / OQTOPUS アダプターの整理。
- QASM ベンチマーク対応。
