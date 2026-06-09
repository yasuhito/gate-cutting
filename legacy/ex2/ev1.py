import sys
import json
import logging
import random
import time
import csv

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from itertools import product
from typing import Dict, List, Tuple, Any
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import stim
from qiskit import QuantumCircuit
from qiskit.circuit.library import HGate, SGate, XGate, YGate, ZGate, CXGate
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix

from tranqu import Tranqu


# ログ設定
#logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logging.basicConfig(level=logging.FATAL, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ==========================================
# 1. データ構造
# ==========================================

@dataclass
class ErrorParams:
    one_qubit: Dict[int, float]              # {qubit_index: error_rate}
    two_qubit: Dict[Tuple[int, int], float]  # {(ctrl, tgt): error_rate}
    readout: Dict[int, float]                # {qubit_index: error_rate}

@dataclass
class ExperimentResult:
    case_name: str
    num_qubits: int
    depth: int
    num_cuts: int
    ideal_exp: float
    noisy_exp: float
    cut_exp: float
    error_noisy: float
    error_cut: float
    improvement_rate: float
    runtime: float

# ==========================================
# 2. チップ生成ロジック (from g.py)
# ==========================================

def generate_qubit_json_corrected(width: int = 4, height: int = 4) -> dict:
    """g.py のロジックに基づくデバイスJSON生成"""
    
    # --- Helper Functions from g.py ---
    def get_qubit_id(x, y):
        block_x = x // 2
        block_y = y // 2
        local_x = x % 2
        local_y = y % 2
        blocks_per_row = width // 2
        block_start_id = (block_y * blocks_per_row + block_x) * 4
        offset = local_y * 2 + local_x
        return block_start_id + offset

    def _maybe_bad(bad_prob: float) -> bool:
        return random.random() < max(0.0, min(1.0, bad_prob))

    def get_random_fidelity(*, base: float = 0.999, variance: float = 0.001, bad_prob: float = 0.0) -> float:
        if _maybe_bad(bad_prob):
            return round(random.uniform(0.50, 0.70), 4)
        val = random.uniform(base - variance, base + variance / 2)
        return round(min(val, 1.0), 4)

    def get_random_meas_error(*, bad_prob: float = 0.0) -> Dict[str, float]:
        if _maybe_bad(bad_prob):
            return {
                "prob_meas1_prep0": round(random.uniform(0.10, 0.30), 4),
                "prob_meas0_prep1": round(random.uniform(0.20, 0.40), 4),
                "readout_assignment_error": round(random.uniform(0.50, 0.90), 4)
            }
        return {
            "prob_meas1_prep0": round(random.uniform(0.0010, 0.0050), 4),
            "prob_meas0_prep1": round(random.uniform(0.0100, 0.0300), 4),
            "readout_assignment_error": round(random.uniform(0.0100, 0.0200), 4)
        }

    # --- Generation ---
    qubits_data = []
    for y in range(height):
        for x in range(width):
            q_id = get_qubit_id(x, y)
            qubit_info = {
                "id": q_id,
                "position": {"x": x, "y": y},
                "fidelity": get_random_fidelity(bad_prob=0.01),
                "meas_error": get_random_meas_error(bad_prob=0.01),
            }
            qubits_data.append(qubit_info)
    qubits_data.sort(key=lambda q: q["id"])

    couplings_data = []
    # Horizontal
    for y in range(height):
        for x in range(width - 1):
            id_left = get_qubit_id(x, y)
            id_right = get_qubit_id(x + 1, y)
            if (x % 2) == (y % 2): src, dst = id_left, id_right
            else: src, dst = id_right, id_left
            couplings_data.append({
                "control": src, "target": dst,
                "fidelity": get_random_fidelity(base=0.965, variance=0.1, bad_prob=0.4)
            })
    # Vertical
    for x in range(width):
        for y in range(height - 1):
            id_top = get_qubit_id(x, y)
            id_bottom = get_qubit_id(x, y + 1)
            if (x % 2) == (y % 2): src, dst = id_top, id_bottom
            else: src, dst = id_bottom, id_top
            couplings_data.append({
                "control": src, "target": dst,
                "fidelity": get_random_fidelity(base=0.965, variance=0.02)
            })

    #return {"qubits": qubits_data, "couplings": couplings_data}
    jst = timezone(timedelta(hours=9))
    timestamp = datetime.now(jst).isoformat(timespec='seconds')

    final_json = {
        "name": "A",
        "device_id": "A",
        "qubits": qubits_data,
        "couplings": couplings_data,
        "calibrated_at": timestamp
    }

    return final_json


def convert_json_to_graph_and_params(json_data: dict) -> Tuple[nx.DiGraph, ErrorParams]:
    """JSONデータをNetworkXグラフとErrorParamsに変換"""
    G = nx.DiGraph()
    one_q_err = {}
    readout_err = {}
    two_q_err = {}
    
    # Nodes
    for q in json_data["qubits"]:
        qid = int(q["id"])
        G.add_node(qid, pos=(q["position"]["x"], q["position"]["y"]))
        # Error calculation for Stim
        one_q_err[qid] = max(0.0, 1.0 - float(q["fidelity"]))
        readout_err[qid] = max(0.0, float(q["meas_error"]["readout_assignment_error"]))
        
    # Edges (Couplings)
    for c in json_data["couplings"]:
        u, v = int(c["control"]), int(c["target"])
        fid = float(c["fidelity"])
        err = max(0.0, 1.0 - fid)
        
        # Add directed edge with fidelity info
        G.add_edge(u, v, fidelity=fid, weight=fid) # Weight for MIP (higher fidelity = harder to cut? No, min-cut minimizes sum of weights)
        # 通常Min-Cutは「カットする辺の重みの和」を最小化する。
        # Fidelityが高い場所は切りたくない -> Weightを大きくするべき？
        # しかしMIPソルバの実装では単純にエッジ変数の和を最小化している(c=1)。
        # グラフ作成時に重みを調整するならここで。
        # 今回は単純にトポロジーとして使用。
        
        two_q_err[(u, v)] = err

    return G, ErrorParams(one_q_err, two_q_err, readout_err)

def load_device(json_path: str):
    path = Path(json_path)
    return json.loads(path.read_text(encoding="utf-8"))


def load_device_data(data: str):
    cx_fidelities = {}
    for c in data.get("couplings", []):
        u, v = int(c["control"]), int(c["target"])
        fid = float(c["fidelity"])
        cx_fidelities[(u, v)] = fid
        if "reverse_fidelity" in c:
            cx_fidelities[(v, u)] = float(c["reverse_fidelity"])

    one_q_fidelities = {}
    qubit_coords = {}
    one_qubit_errors = {}
    readout_errors = {}

    for q in data.get("qubits", []):
        qid = int(q["id"])
        fid = float(q.get("fidelity", 1.0))
        one_q_fidelities[qid] = fid
        
        position = q.get("position", {})
        if isinstance(position, dict) and "x" in position and "y" in position:
            qubit_coords[qid] = (float(position["x"]), float(position["y"]))
        elif "x" in q and "y" in q:
            qubit_coords[qid] = (float(q["x"]), float(q["y"]))
        else:
            qubit_coords[qid] = (qid, 0)

        one_qubit_errors[qid] = max(0.0, 1.0 - fid)
        meas = q.get("meas_error", {})
        readout_errors[qid] = max(0.0, meas.get("readout_assignment_error", 0.0))

    two_qubit_errors = {}
    for c in data.get("couplings", []):
        u, v = int(c["control"]), int(c["target"])
        p = max(0.0, 1.0 - c.get("fidelity", 1.0))
        two_qubit_errors[(u, v)] = p

    error_params = ErrorParams(one_qubit_errors, two_qubit_errors, readout_errors)
    return data, cx_fidelities, one_q_fidelities, qubit_coords, error_params

# ==========================================
# 3. 回路生成ロジック (from create_random_clifford_circuit.py)
# ==========================================

single_qubit_cliffords = [
    ("h", HGate()), ("s", SGate()), ("sdg", SGate().inverse()),
    ("x", XGate()), ("y", YGate()), ("z", ZGate())
]

def random_clifford_circuit(num_qubits: int, depth: int, seed: int | None = None) -> QuantumCircuit:
    """Cliffordゲートのみからなるランダム回路を生成"""
    rng = random.Random(seed)
    qc = QuantumCircuit(num_qubits)
    
    # 論理量子ビットID (0 ~ N-1)
    qubits = list(range(num_qubits))

    for layer in range(depth):
        # 1. Single Qubit Gates
        for q in qubits:
            if rng.random() < 0.6:
                name, gate = rng.choice(single_qubit_cliffords)
                qc.append(gate, [q])

        # 2. CX Gates
        rng.shuffle(qubits)
        for i in range(0, len(qubits)-1, 2):
            if rng.random() < 2.0:
                qc.append(CXGate(), [qubits[i], qubits[i+1]])

    return qc

# ==========================================
# 4. MIP Solver & Analysis (Adapted)
# ==========================================

def circuit_to_networkx(
    circuit: QuantumCircuit,
    cx_fidelities: Dict[Tuple[int, int], float],
    one_q_fidelities: Dict[int, float],
    qubit_coords: Dict[int, Tuple[float, float]],
    default_cx_fid: float = 1.0,
    default_1q_fid: float = 1.0
) -> nx.MultiDiGraph:
    """
    回路をグラフ化。ノードとエッジにFidelity情報を付与する。
    """
    G = nx.MultiDiGraph()
    for i in range(circuit.num_qubits):
        pos = qubit_coords.get(i, (i, 0))
        # 1Q Fidelityをノードの重みとして保持
        fid_1q = one_q_fidelities.get(i, default_1q_fid)
        G.add_node(i, pos=pos, fidelity=fid_1q)

    for instruction in circuit.data:
        if instruction.operation.name != "cx":
            continue
        c_idx = circuit.find_bit(instruction.qubits[0]).index
        t_idx = circuit.find_bit(instruction.qubits[1]).index
        
        fid_cx = cx_fidelities.get((c_idx, t_idx), default_cx_fid)
        
        # MIPでの重み付け用: Fidelityそのものを属性に入れる
        # (solve_mip_cutでこの値を使って目的関数を作る)
        G.add_edge(c_idx, t_idx, gate="cx", fidelity=fid_cx)
            
    return G


# def solve_mip_cut(G: nx.MultiDiGraph, min_partition_ratio=0.1, cut_fidelity_threshold=0.98) -> List[Tuple[int, int]]:
#     """
#     MIPソルバを用いて最適なカットを探索する。
#     修正: エラー率に基づいて重みを劇的に変化させるロジックに変更
#     """
#     nodes = list(G.nodes(data=True))
#     # keys=True, data=True なので (u, v, key, data) の4要素タプルが返る
#     edges = list(G.edges(keys=True, data=True))
    
#     n_nodes = len(nodes)
#     n_edges = len(edges)
    
#     if n_edges == 0: return []

#     node_to_idx = {n[0]: i for i, n in enumerate(nodes)}
    
#     # 変数: [x_0, ..., x_n-1, z_0, ..., z_m-1]
#     n_vars = n_nodes + n_edges
    
#     # === 目的関数 (Objective) ===
#     # Minimize sum( Cost_k * z_k )
#     # z_k = 1 ならカットされる。つまり Cost_k が小さいほどカットされやすい。
#     c = np.zeros(n_vars)
    
#     for k in range(n_edges):
#         u, v, key, attr = edges[k]
        
#         fid = attr.get('fidelity', 1.0)
        
#         # --- 修正箇所: 重み付けロジックの変更 ---
#         # エラー率を分母に置くことで、Fidelityが高いほどコストが急激に高くなるようにする
#         # (良いエッジは切りたくない = コスト大 / 悪いエッジは切りたい = コスト小)
        
#         error_rate = max(1.0 - fid, 1e-9) # 0除算防止
#         weight = fid / error_rate
        
#         # さらに、明示的な閾値を下回る場合は、ボーナスとして極端にコストを下げる
#         if fid < cut_fidelity_threshold:
#              weight *= 0.01 # 強制的にカット候補にする

#         c[n_nodes + k] = weight
#         # -------------------------------------

#     # === 制約 (Constraints) ===
#     rows, cols, vals = [], [], []
#     b_l, b_u = [], []
#     constraint_idx = 0
    
#     # 1. 切断の論理制約: z_k >= |x_u - x_v|
#     for k in range(n_edges):
#         u, v, key, attr = edges[k]
#         u_idx = node_to_idx[u]
#         v_idx = node_to_idx[v]
#         z_idx = n_nodes + k
        
#         # -x_u + x_v + z_k >= 0
#         rows.extend([constraint_idx]*3); cols.extend([u_idx, v_idx, z_idx]); vals.extend([-1, 1, 1])
#         b_l.append(0); b_u.append(np.inf); constraint_idx += 1
#         # x_u - x_v + z_k >= 0
#         rows.extend([constraint_idx]*3); cols.extend([u_idx, v_idx, z_idx]); vals.extend([1, -1, 1])
#         b_l.append(0); b_u.append(np.inf); constraint_idx += 1

#     # 2. バランス制約 (Fidelity Weighted Balance)
#     # ノードのFidelityの総和を計算
#     total_node_fidelity = sum(d.get('fidelity', 1.0) for _, d in nodes)
    
#     # バランス制約がきつすぎると、悪いエッジを切りたくても切れない場合があるため
#     # 引数 min_partition_ratio を調整可能にしておく
#     min_fid = total_node_fidelity * min_partition_ratio
#     max_fid = total_node_fidelity * (1.0 - min_partition_ratio)
    
#     for i in range(n_nodes):
#         weight = nodes[i][1].get('fidelity', 1.0)
#         rows.append(constraint_idx); cols.append(i); vals.append(weight)
    
#     b_l.append(min_fid); b_u.append(max_fid); constraint_idx += 1
    
#     # === ソルバ実行 ===
#     A = coo_matrix((vals, (rows, cols)), shape=(constraint_idx, n_vars))
#     res = milp(c=c, constraints=LinearConstraint(A, b_l, b_u), integrality=np.ones(n_vars), bounds=Bounds(0, 1))
    
#     if not res.success:
#         #logger.warning("MIP Solver failed to find a balanced cut.")
#         print("MIP Solver failed to find a balanced cut.")
#         return []

#     # === 結果解析 ===
#     selected_cut_indices = [k for k in range(n_edges) if res.x[n_nodes + k] > 0.5]
    
#     if not selected_cut_indices:
#         return []

#     # カットされたエッジのFidelity平均
#     cut_fidelities = [edges[k][3].get('fidelity', 1.0) for k in selected_cut_indices]
#     avg_cut_fidelity = sum(cut_fidelities) / len(cut_fidelities)

#     logger.info(f"MIP Selected {len(selected_cut_indices)} cuts. Avg Fidelity: {avg_cut_fidelity:.4f}")
#     return [(edges[k][0], edges[k][1]) for k in selected_cut_indices]

# def solve_mip_cut(G: nx.MultiDiGraph, min_partition_ratio=0.01, cut_fidelity_threshold=0.98) -> List[Tuple[int, int]]:
#     """
#     MIPソルバを用いて最適なカットを探索する。
#     修正: バランス制約を緩和し、悪いエッジを極端に切りやすくしたバージョン
#     """
#     nodes = list(G.nodes(data=True))
#     edges = list(G.edges(keys=True, data=True)) # (u, v, key, data)
    
#     n_nodes = len(nodes)
#     n_edges = len(edges)
    
#     if n_edges == 0: return []

#     # TODO: デバッグ
#     # --- デバッグ: 候補エッジの確認 ---
#     # 回路グラフに含まれているエッジの中に、3->9 があるか確認します
#     print(f"--- MIP Edges Check (Total {n_edges}) ---")
#     target_edge_found = False
#     for u, v, k, d in edges:
#         fid = d.get('fidelity', 1.0)
#         if fid < cut_fidelity_threshold:
#             print(f"Low Fidelity Edge Found: {u} -> {v} (Fid: {fid:.4f})")
#         if u == 3 and v == 9:
#             target_edge_found = True
#             print(f"TARGET EDGE (3->9) EXISTS in Graph. Fidelity: {fid:.4f}")
    
#     if not target_edge_found:
#         print("Target edge (3->9) was NOT found in the transpiled circuit graph! The transpiler might have avoided it or swapped qubits.")
#     # --------------------------------

#     node_to_idx = {n[0]: i for i, n in enumerate(nodes)}
    
#     # 変数: [x_0, ..., x_n-1, z_0, ..., z_m-1]
#     n_vars = n_nodes + n_edges
    
#     # === 目的関数 (Objective) ===
#     # Minimize sum( Cost_k * z_k )
#     c = np.zeros(n_vars)
    
#     for k in range(n_edges):
#         u, v, key, attr = edges[k]
#         fid = attr.get('fidelity', 1.0)
        
#         # --- 修正: 二極化コスト ---
#         # 閾値を下回るエッジはコストを極小(0.001)にし、
#         # それ以外はコストを大(10.0)にする。
#         # これにより「悪いエッジがあるなら、バランスが悪くても絶対にそこを切る」動きになる。
#         if fid < cut_fidelity_threshold:
#             c[n_nodes + k] = 0.001 
#         else:
#             c[n_nodes + k] = 10.0

#     # === 制約 (Constraints) ===
#     rows, cols, vals = [], [], []
#     b_l, b_u = [], []
#     constraint_idx = 0
    
#     # 1. 切断の論理制約: z_k >= |x_u - x_v|
#     for k in range(n_edges):
#         u, v, key, attr = edges[k]
#         u_idx = node_to_idx[u]
#         v_idx = node_to_idx[v]
#         z_idx = n_nodes + k
        
#         rows.extend([constraint_idx]*3); cols.extend([u_idx, v_idx, z_idx]); vals.extend([-1, 1, 1])
#         b_l.append(0); b_u.append(np.inf); constraint_idx += 1
        
#         rows.extend([constraint_idx]*3); cols.extend([u_idx, v_idx, z_idx]); vals.extend([1, -1, 1])
#         b_l.append(0); b_u.append(np.inf); constraint_idx += 1

#     # 2. バランス制約 (緩和版)
#     # min_partition_ratio を極端に小さく (0.01) 設定することで、
#     # 「1量子ビットだけ切り離す」ことを許可する。
#     total_node_fidelity = sum(d.get('fidelity', 1.0) for _, d in nodes)
    
#     # 最低でも1ノード分(重み概算1.0)程度は許容するように安全マージンをとる
#     min_fid = 0.0 # 完全に0にすると解なしになる場合があるので、実質下限なし
#     # ただし、全員0 または 全員1 (カットなし) を防ぐため、少しだけ幅を持たせる
#     # ここではソルバ任せにするが、min_partition_ratio引数が効くように計算
    
#     min_limit = total_node_fidelity * min_partition_ratio
#     max_limit = total_node_fidelity * (1.0 - min_partition_ratio)
    
#     for i in range(n_nodes):
#         weight = nodes[i][1].get('fidelity', 1.0)
#         rows.append(constraint_idx); cols.append(i); vals.append(weight)
    
#     b_l.append(min_limit); b_u.append(max_limit); constraint_idx += 1
    
#     # === ソルバ実行 ===
#     A = coo_matrix((vals, (rows, cols)), shape=(constraint_idx, n_vars))
#     res = milp(c=c, constraints=LinearConstraint(A, b_l, b_u), integrality=np.ones(n_vars), bounds=Bounds(0, 1))
    
#     if not res.success:
#         logger.warning("MIP Solver failed to find a cut.")
#         return []

#     # === 結果解析 ===
#     selected_cut_indices = [k for k in range(n_edges) if res.x[n_nodes + k] > 0.5]
    
#     if not selected_cut_indices:
#         logger.info("MIP found optimal solution, but NO cuts were selected (Cost was too high?).")
#         return []

#     cut_fidelities = [edges[k][3].get('fidelity', 1.0) for k in selected_cut_indices]
#     avg_cut_fidelity = sum(cut_fidelities) / len(cut_fidelities)

#     logger.info(f"MIP Selected {len(selected_cut_indices)} cuts. Avg Fidelity: {avg_cut_fidelity:.4f}")
#     return [(edges[k][0], edges[k][1]) for k in selected_cut_indices]

# def solve_mip_cut(G: nx.MultiDiGraph, min_partition_ratio=0.0, cut_fidelity_threshold=0.98) -> List[Tuple[int, int]]:
#     """
#     MIPソルバを用いて最適なカットを探索する。
#     修正: 悪いエッジはコスト操作ではなく、変数の境界値(Bounds)で強制的にカットさせる。
#     """
#     nodes = list(G.nodes(data=True))
#     edges = list(G.edges(keys=True, data=True))
    
#     n_nodes = len(nodes)
#     n_edges = len(edges)
    
#     if n_edges == 0: return []
    
#     # ----------------------------------------------------
#     # デバッグ: 強制カット対象の確認
#     # ----------------------------------------------------
#     forced_cuts_count = 0
#     for u, v, k, d in edges:
#         fid = d.get('fidelity', 1.0)
#         if fid < cut_fidelity_threshold:
#             logger.info(f"-> Force Cut Constraint: {u} -> {v} (Fid: {fid:.4f})")
#             forced_cuts_count += 1
            
#     if forced_cuts_count == 0:
#         logger.info("No edges below threshold. MIP will run normally.")
#     # ----------------------------------------------------

#     node_to_idx = {n[0]: i for i, n in enumerate(nodes)}
#     n_vars = n_nodes + n_edges # [x_0...x_n, z_0...z_m]
    
#     # === 目的関数 (Objective) ===
#     c = np.zeros(n_vars)
    
#     # === 変数の境界値 (Bounds) ===
#     # ここが修正の肝です。
#     # 通常は 0 <= var <= 1 ですが、悪いエッジに対応する z_k は 1 <= z_k <= 1 (つまり必ず1) にします。
#     lower_bounds = np.zeros(n_vars)
#     upper_bounds = np.ones(n_vars)
    
#     for k in range(n_edges):
#         u, v, key, attr = edges[k]
#         fid = attr.get('fidelity', 1.0)
        
#         # コスト設定（強制カット以外の場所を切る際の基準）
#         if fid < cut_fidelity_threshold:
#             # 閾値未満は「強制カット」なのでコストはどうでもいいが、念のため0
#             c[n_nodes + k] = 0.0 
#             # 【重要】下限を1.0にする = 「必ず切れ」という制約
#             lower_bounds[n_nodes + k] = 1.0 
#         else:
#             # 良いエッジは切りたくないのでコスト高く
#             # Fidelityが高いほど切りたくない重み付け
#             error_rate = max(1.0 - fid, 1e-9)
#             weight = fid / error_rate
#             c[n_nodes + k] = weight

#     # === 制約 (Constraints) ===
#     rows, cols, vals = [], [], []
#     b_l, b_u = [], []
#     constraint_idx = 0
    
#     # 1. 切断の論理制約: z_k >= |x_u - x_v|
#     for k in range(n_edges):
#         u, v, key, attr = edges[k]
#         u_idx = node_to_idx[u]
#         v_idx = node_to_idx[v]
#         z_idx = n_nodes + k
        
#         rows.extend([constraint_idx]*3); cols.extend([u_idx, v_idx, z_idx]); vals.extend([-1, 1, 1])
#         b_l.append(0); b_u.append(np.inf); constraint_idx += 1
        
#         rows.extend([constraint_idx]*3); cols.extend([u_idx, v_idx, z_idx]); vals.extend([1, -1, 1])
#         b_l.append(0); b_u.append(np.inf); constraint_idx += 1

#     # 2. バランス制約
#     # 特定の悪い箇所を切り抜くために 0.0 (制約なし) を許容する
#     total_node_fidelity = sum(d.get('fidelity', 1.0) for _, d in nodes)
#     min_limit = total_node_fidelity * min_partition_ratio
#     max_limit = total_node_fidelity * (1.0 - min_partition_ratio)
    
#     for i in range(n_nodes):
#         weight = nodes[i][1].get('fidelity', 1.0)
#         rows.append(constraint_idx); cols.append(i); vals.append(weight)
    
#     b_l.append(min_limit); b_u.append(max_limit); constraint_idx += 1
    
#     # === ソルバ実行 ===
#     A = coo_matrix((vals, (rows, cols)), shape=(constraint_idx, n_vars))
    
#     # bounds引数に、作成した lower_bounds, upper_bounds を渡す
#     res = milp(
#         c=c, 
#         constraints=LinearConstraint(A, b_l, b_u), 
#         integrality=np.ones(n_vars), 
#         bounds=Bounds(lower_bounds, upper_bounds)
#     )
    
#     if not res.success:
#         # 強制カットのせいでグラフ分割が不可能になった場合（稀ですがトポロジー次第でありえる）
#         logger.warning("MIP Solver failed. Constraints might be too strict (e.g., forcing a cut that isolates a node violating strict balance).")
#         # フォールバック: とりあえず閾値以下のエッジだけをリストアップして返す（Wire Cut用途ならこれで十分）
#         logger.info("Fallback: Returning all low-fidelity edges directly.")
#         fallback_cuts = []
#         for u, v, k, d in edges:
#             if d.get('fidelity', 1.0) < cut_fidelity_threshold:
#                 fallback_cuts.append((u, v))
#         return fallback_cuts

#     # === 結果解析 ===
#     selected_cut_indices = [k for k in range(n_edges) if res.x[n_nodes + k] > 0.5]
    
#     cut_fidelities = [edges[k][3].get('fidelity', 1.0) for k in selected_cut_indices]
#     if cut_fidelities:
#         avg_cut_fidelity = sum(cut_fidelities) / len(cut_fidelities)
#         logger.info(f"MIP Selected {len(selected_cut_indices)} cuts. Avg Fidelity: {avg_cut_fidelity:.4f}")
#     else:
#         logger.info("MIP selected 0 cuts.")

#     return [(edges[k][0], edges[k][1]) for k in selected_cut_indices]

def solve_mip_cut(G: nx.MultiDiGraph, max_cuts=3, cut_fidelity_threshold=0.98) -> List[Tuple[int, int]]:
    """
    MIPソルバを用いて最適なカットを探索する。
    修正: カット数に上限(max_cuts)を設け、Fidelityが低い箇所を優先的にカットする。
    """
    nodes = list(G.nodes(data=True))
    edges = list(G.edges(keys=True, data=True)) # (u, v, key, data)
    
    n_nodes = len(nodes)
    n_edges = len(edges)
    
    if n_edges == 0: return []

    logger.info(f"--- MIP Strategy: Max {max_cuts} cuts. Prioritize Fidelity < {cut_fidelity_threshold} ---")

    node_to_idx = {n[0]: i for i, n in enumerate(nodes)}
    n_vars = n_nodes + n_edges # [x_0...x_n-1, z_0...z_m-1]
    
    # === 目的関数 (Objective) ===
    # Minimize sum( Cost_k * z_k )
    # ここで「悪いエッジ」のコストをマイナスに設定することで、
    # ソルバは目的関数を最小化するために、そのエッジを「1 (カット)」にしようとします。
    c = np.zeros(n_vars)
    
    priority_edges = []

    for k in range(n_edges):
        u, v, key, attr = edges[k]
        fid = attr.get('fidelity', 1.0)
        
        if fid < cut_fidelity_threshold:
            # 悪いエッジ: カットすると -10.0 のボーナス（最小化問題なのでマイナスが嬉しい）
            # さらにFidelityが低いほど、より強いインセンティブを与える
            weight = -10.0 + fid 
            priority_edges.append((u, v, fid))
        else:
            # 良いエッジ: カットすると +1.0 のペナルティ
            # 巻き添えカットを最小限にするため
            weight = 1.0
            
        c[n_nodes + k] = weight

    # 優先度順にログ出力
    priority_edges.sort(key=lambda x: x[2])
    if priority_edges:
        logger.info(f"Candidates (Bad Edges): {priority_edges}")
    else:
        logger.info("No bad edges found below threshold. Will minimize cuts purely by count.")

    # === 制約 (Constraints) ===
    rows, cols, vals = [], [], []
    b_l, b_u = [], []
    constraint_idx = 0
    
    # 1. 切断の論理制約: z_k >= |x_u - x_v|
    for k in range(n_edges):
        u, v, key, attr = edges[k]
        u_idx = node_to_idx[u]
        v_idx = node_to_idx[v]
        z_idx = n_nodes + k
        
        # -x_u + x_v + z_k >= 0
        rows.extend([constraint_idx]*3); cols.extend([u_idx, v_idx, z_idx]); vals.extend([-1, 1, 1])
        b_l.append(0); b_u.append(np.inf); constraint_idx += 1
        
        # x_u - x_v + z_k >= 0
        rows.extend([constraint_idx]*3); cols.extend([u_idx, v_idx, z_idx]); vals.extend([1, -1, 1])
        b_l.append(0); b_u.append(np.inf); constraint_idx += 1

    # 2. 【重要】カット数上限制約 (sum(z_k) <= max_cuts)
    for k in range(n_edges):
        z_idx = n_nodes + k
        rows.append(constraint_idx); cols.append(z_idx); vals.append(1)
    
    b_l.append(0); b_u.append(max_cuts); constraint_idx += 1

    # 3. 自明な解(カットなし)の回避（オプション）
    # 悪いエッジがあるのに「カット数0」が選ばれるのを防ぐため、
    # 少なくとも悪いエッジがある場合は、目的関数がマイナスになる方向へ進むはずなので、
    # バランス制約は撤廃してOK。
    # ただし、グラフとして連結成分を分けるための「x」の固定は必要ない（MIPが自動探索する）。

    # === ソルバ実行 ===
    A = coo_matrix((vals, (rows, cols)), shape=(constraint_idx, n_vars))
    
    # 緩和などは行わず、単純に解く
    res = milp(
        c=c, 
        constraints=LinearConstraint(A, b_l, b_u), 
        integrality=np.ones(n_vars), 
        bounds=Bounds(0, 1)
    )
    
    if not res.success:
        logger.warning("MIP Solver failed. Maybe max_cuts is too strict for the topology.")
        return []

    # === 結果解析 ===
    selected_cut_indices = [k for k in range(n_edges) if res.x[n_nodes + k] > 0.5]
    
    result_cuts = []
    for k in selected_cut_indices:
        u, v, key, attr = edges[k]
        fid = attr.get('fidelity', 1.0)
        result_cuts.append(((u, v), fid))

    # 優先度（Fidelityが低い順）に並べ替えて出力
    result_cuts.sort(key=lambda x: x[1])
    
    logger.info(f"MIP Selected {len(result_cuts)} cuts (Max {max_cuts}).")
    for (u, v), fid in result_cuts:
        logger.info(f"  -> CUT: {u}->{v} (Fid: {fid:.4f})")

    # 戻り値は座標のみ
    return [rc[0] for rc in result_cuts]

# ==========================================
# 5. Simulation Logic (Stim)
# ==========================================

def qiskit_to_stim(qc: QuantumCircuit) -> stim.Circuit:
    stim_circ = stim.Circuit()
    for instruction in qc.data:
        op = instruction.operation.name.lower()
        qs = [qc.find_bit(q).index for q in instruction.qubits]
        if op == 'id': stim_circ.append("I", qs)
        elif op == 'x': stim_circ.append("X", qs)
        elif op == 'y': stim_circ.append("Y", qs)
        elif op == 'z': stim_circ.append("Z", qs)
        elif op == 'h': stim_circ.append("H", qs)
        elif op == 's': stim_circ.append("S", qs)
        elif op == 'sdg': stim_circ.append("S_DAG", qs)
        elif op in ('cx', 'cnot'):
            stim_circ.append("CX", qs)
            # 同じ命令の場合、まとめられるのでCXのあとにはIを入れてまとめられないようにする
            stim_circ.append("I", qs)
        elif op == 'measure': stim_circ.append("M", qs)
    return stim_circ

def get_active_qubits(circuit: stim.Circuit) -> List[int]:
    """回路内で使用されている量子ビットのIDリストを取得（ソート済み）"""
    active_qubits = set()
    for instruction in circuit:
        # targetにはqubit_target以外(meas_targetなど)も含まれるが、
        # 基本的にqubit valueを見ればOK
        for t in instruction.targets_copy():
            if t.is_qubit_target:
                active_qubits.add(t.value)
    return sorted(list(active_qubits))


# ==========================================
# 3. シミュレーション用ヘルパー関数
# ==========================================

IGNORE_OPS = {"TICK", "SHIFT_COORDS", "QUBIT_COORDS", "DETECTOR", "OBSERVABLE_INCLUDE"}
MEASURE_OPS = {"M", "MR", "MX", "MY", "MZ"}

def append_operation_with_noise(
    circuit: stim.Circuit, 
    op_name: str, 
    targets: List[int], 
    error_params: ErrorParams
):
    if op_name in MEASURE_OPS:
        for q in targets:
            p = error_params.readout.get(q, 0.0)
            if p > 0:
                circuit.append("X_ERROR", [q], p)
        circuit.append(op_name, targets)
        return

    if op_name in IGNORE_OPS:
        circuit.append(op_name, targets)
        return

    circuit.append(op_name, targets)

    if len(targets) == 2:
        u, v = targets[0], targets[1]
        p_cx = error_params.two_qubit.get((u, v), 0.0)
        if p_cx > 0 and op_name == "CX":
            circuit.append("DEPOLARIZE2", [u, v], p_cx)
    elif len(targets) == 1:
        u = targets[0]
        p_1q = error_params.one_qubit.get(u, 0.0)
        if p_1q > 0:
            circuit.append("DEPOLARIZE1", [u], p_1q)

def calculate_expectation(samples: np.ndarray) -> float:
    parities = np.sum(samples, axis=1) % 2
    eigenvalues = 1 - 2 * parities
    return np.mean(eigenvalues)

def append_wire_cut_ops(circuit: stim.Circuit, op_code: str, qubit: int, error_params: ErrorParams):
    """Wire Cutting用の操作（測定または準備）を追加する"""
    if op_code == 'M_Z':
        append_operation_with_noise(circuit, 'M', [qubit], error_params)
    elif op_code == 'M_X':
        append_operation_with_noise(circuit, 'H', [qubit], error_params)
        append_operation_with_noise(circuit, 'M', [qubit], error_params)
    elif op_code == 'M_Y':
        append_operation_with_noise(circuit, 'S_DAG', [qubit], error_params)
        append_operation_with_noise(circuit, 'H', [qubit], error_params)
        append_operation_with_noise(circuit, 'M', [qubit], error_params)
    elif op_code == 'M_I':
        append_operation_with_noise(circuit, 'R', [qubit], error_params)

    elif op_code == 'P_0':
        append_operation_with_noise(circuit, 'R', [qubit], error_params)
    elif op_code == 'P_1':
        append_operation_with_noise(circuit, 'R', [qubit], error_params)
        append_operation_with_noise(circuit, 'X', [qubit], error_params)
    elif op_code == 'P_X+': 
        append_operation_with_noise(circuit, 'R', [qubit], error_params)
        append_operation_with_noise(circuit, 'H', [qubit], error_params)
    elif op_code == 'P_X-': 
        append_operation_with_noise(circuit, 'R', [qubit], error_params)
        append_operation_with_noise(circuit, 'X', [qubit], error_params)
        append_operation_with_noise(circuit, 'H', [qubit], error_params)
    elif op_code == 'P_Y+': 
        append_operation_with_noise(circuit, 'R', [qubit], error_params)
        append_operation_with_noise(circuit, 'H', [qubit], error_params)
        append_operation_with_noise(circuit, 'S', [qubit], error_params)
    elif op_code == 'P_Y-': 
        append_operation_with_noise(circuit, 'R', [qubit], error_params)
        append_operation_with_noise(circuit, 'H', [qubit], error_params)
        append_operation_with_noise(circuit, 'S_DAG', [qubit], error_params)


# ==========================================
# 4. シミュレーション実行関数
# ==========================================
def set_measurements_if_absent(circuit: stim.Circuit, error_params: ErrorParams):
    if circuit.num_measurements == 0:
        active_qubits = get_active_qubits(circuit)
        # TODO: 測定エラーの追加
        # for q in active_qubits:
        #     p = error_params.readout.get(q, 0.0)
        #     if p > 0:
        #         circuit.append("X_ERROR", [q], p)
        circuit.append("M", active_qubits)


def simulate_ideal(circuit: stim.Circuit, shots=10000) -> float:
    sim_circ = circuit.copy()
    error_params_ideal = ErrorParams({}, {}, {}) # 空のエラーパラメータ
    set_measurements_if_absent(sim_circ, error_params_ideal)
    sampler = sim_circ.compile_sampler()
    samples = sampler.sample(shots=shots)
    return calculate_expectation(samples)

def simulate_noisy(circuit: stim.Circuit, error_params: ErrorParams, shots=10000) -> float:
    noisy_circuit = stim.Circuit()
    for instruction in circuit:
        targets = [t.value for t in instruction.targets_copy() if t.is_qubit_target]
        append_operation_with_noise(noisy_circuit, instruction.name, targets, error_params)
    
    set_measurements_if_absent(noisy_circuit, error_params)

    # TODO: デバッグ
    #print(f"noisy_circuit:\n{noisy_circuit}")

    sampler = noisy_circuit.compile_sampler()
    samples = sampler.sample(shots=shots)
    return calculate_expectation(samples)

def simulate_cut_circuit(
    original_circuit: stim.Circuit,
    cut_pairs: List[Tuple[int, int]], 
    error_params: ErrorParams,
    shots=10000,
    decomposition=None
) -> float:
    cut_indices = []
    target_set = set(cut_pairs)
    
    for i, instruction in enumerate(original_circuit):
        if instruction.name == "CX":
            targets = [t.value for t in instruction.targets_copy() if t.is_qubit_target]
            if len(targets) == 2:
                u, v = targets[0], targets[1]
                if (u, v) in target_set:
                    cut_indices.append(i)

    #active_qubits = get_active_qubits(original_circuit)

    if not cut_indices:
        print("[Cut] Warning: No matching CX gates found in Stim circuit for the MIP cut.")
        return 0.0
    
    #print(f"[Cut] Identified Stim indices to cut: {cut_indices}")

    # # Wire Cutting Decomposition (Identity Channel Decomposition)
    # decomposition = [
    #     (0.5,  'M_Z', 'P_0'), (-0.5, 'M_Z', 'P_1'),
    #     (0.5,  'M_X', 'P_X+'), (-0.5, 'M_X', 'P_X-'),
    #     (0.5,  'M_Y', 'P_Y+'), (-0.5, 'M_Y', 'P_Y-'),
    #     (0.5,  'M_I', 'P_0'), (0.5,  'M_I', 'P_1')
    # ]
    
    # # Gate Cutting Decomposition (CX Gate Decomposition)
    # decomposition = [
    #     (0.5,  'I', 'I'), (0.5,  'Z', 'I'),
    #     (0.5,  'I', 'X'), (-0.5, 'Z', 'X')
    # ]

    total_expectation = 0.0
    instructions = list(original_circuit)
    #num_qubits = original_circuit.num_qubits
    
    for combination in product(decomposition, repeat=len(cut_indices)):
        current_coeff = 1.0
        term_map = {}
        for c_idx, term in zip(cut_indices, combination):
            coeff, op_measure, op_prepare = term
            current_coeff *= coeff
            term_map[c_idx] = (op_measure, op_prepare)

        sub_circuit = stim.Circuit()
        
        for idx, instruction in enumerate(instructions):
            targets = [t.value for t in instruction.targets_copy() if t.is_qubit_target]
            
            if idx in cut_indices:
                # wire cutting case
                ctrl_qubit = targets[0]
                op_meas, op_prep = term_map[idx]
                # Wire Cutting Sequence
                append_wire_cut_ops(sub_circuit, op_meas, ctrl_qubit, error_params)
                append_wire_cut_ops(sub_circuit, op_prep, ctrl_qubit, error_params)

                # # gate cutting case
                # op_c, op_t = term_map[idx]
                # op_name_c = "Z" if op_c == "Z" else "I"
                # append_operation_with_noise(sub_circuit, op_name_c, [targets[0]], error_params)
                # op_name_t = "X" if op_t == "X" else "I"
                # append_operation_with_noise(sub_circuit, op_name_t, [targets[1]], error_params)
            else:
                append_operation_with_noise(sub_circuit, instruction.name, targets, error_params)

        set_measurements_if_absent(sub_circuit, error_params)

        # TODO: デバッグ
        #print(f"sub_circuit:\n{sub_circuit}")
        
        sampler = sub_circuit.compile_sampler()
        samples = sampler.sample(shots=shots)
        exp_val = calculate_expectation(samples)
        
        total_expectation += current_coeff * exp_val

    return total_expectation



def evaluate_suite():

    results = []
    tranqu = Tranqu()
    
    # --- Parameters ---
    WIDTH, HEIGHT = 4, 4  # 8 Qubits (g.py logic)
    # Note: g.py generates IDs based on 2x2 blocks.
    # 4x2 grid -> IDs: [0,1,2,3] (Block 0,0), [4,5,6,7] (Block 1,0). Total 8 contiguous IDs. Good.
    
    #N_QUBITS = WIDTH * HEIGHT 
    N_QUBITS = 10
    DEPTH = 2
    TRIALS = 30
    #SHOTS = 10000
    shots = 50000
    
    print(f"Starting Evaluation (W={WIDTH}, H={HEIGHT}, N_QUBITS={N_QUBITS}, Depth={DEPTH})...")

    # === Case 1: 固定チップ x ランダム回路 ===
    #print("--- Case 1: Fixed Chip x Random Circuits ---")
    
    #device_json = generate_qubit_json_corrected(WIDTH, HEIGHT)
    
    # # TODO: デバッグ
    # #json_path = "device.good.json"
    json_path = "device.json"
    device_json = load_device(json_path)
    
    # デバッグ: チップの保存
    # json_str = json.dumps(device_json, indent=2)
    
    # #filename = "device_C_64.json"
    # filename = "../json/device.json"
    # with open(filename, "w") as f:
    #     f.write(json_str)
    
    # print(f"Successfully generated '{filename}'.")

    oqtopus_device, cx_fidelities, one_q_fidelities, qubit_coords, error_params = load_device_data(device_json)
    #print(f"error_params good: {error_params}")

    #print(f"Loaded device with {len(oqtopus_device['qubits'])} qubits and {len(oqtopus_device['couplings'])} couplings.")

    exec_counter = 1
    skip_counter = 0
    for i in range(TRIALS*10):
        qc = random_clifford_circuit(N_QUBITS, DEPTH, seed=None) # Seed None for random
        #qc.measure_all()

        # # # # TODO: デバッグ用に回路保存
        # import pickle
        # with open(f"qc.pkl", "wb") as f:
        #     pickle.dump(qc, f)  

        try:
            result = tranqu.transpile(
                program=qc,
                program_lib="qiskit",
                transpiler_lib="qiskit",
                transpiler_options={
                    "basis_gates": ["id", "x", "y", "z", "h", "s", "sdg", "cx"], 
                    "optimization_level": 2},
                device=oqtopus_device,
                device_lib="oqtopus",
            )
            transpiled_qc = result.transpiled_program
        except Exception as e:
            # トランスパイルに失敗したら次にいく
            continue
        
        # print(f"Original QC:\n{qc}")
        # print(f"Transpiled QC:\n{transpiled_qc}")

        # 3. グラフ解析とMIPによるカット
        G_circuit = circuit_to_networkx(
            transpiled_qc, 
            cx_fidelities, 
            one_q_fidelities, 
            qubit_coords
        )
        
        # MIPソルバ実行
        # # min_partition_ratio=0.01 に緩和し、cut_fidelity_threshold=0.95 に設定
        # # これにより、全体の10%程度の小さな断片（1量子ビットなど）でも、Fidelityが悪ければカットを許容する
        # cut_pairs = solve_mip_cut(G_circuit, min_partition_ratio=0.01, cut_fidelity_threshold=0.95)

        # MIPソルバ実行
        # min_partition_ratio=0.0 で、どんな小さな断片化も許可する
        #cut_pairs = solve_mip_cut(G_circuit, min_partition_ratio=0.1, cut_fidelity_threshold=0.9)
        # MIPソルバ実行
        # max_cuts=2 に制限し、閾値以下のエッジを優先的に狙わせる
        cut_pairs = solve_mip_cut(G_circuit, max_cuts=2, cut_fidelity_threshold=0.96)

        #cut_pairs = [(4,5), (15,14)]
        #cut_pairs = [(3,9)]
        logger.info(f"MIP Result Cut pairs: {cut_pairs}")
        
        # 4. Stim変換とシミュレーション
        stim_qc = qiskit_to_stim(transpiled_qc)

        # (A) 理想的なシミュレーション
        val_ideal = simulate_ideal(stim_qc, shots)
        #print(f"\n[Ideal]       <ZZ..Z>: {val_ideal:.4f}")

        # (B) ノイズあり (カットなし)
        val_noisy = simulate_noisy(stim_qc, error_params, shots)
        #print(f"[Noisy]       <ZZ..Z>: {val_noisy:.4f}")

        if cut_pairs:
            
            # Gate Cutting Decomposition (CX Gate Decomposition)
            decomposition = [
                (0.5,  'I', 'I'), (0.5,  'Z', 'I'),
                (0.5,  'I', 'X'), (-0.5, 'Z', 'X')
            ]

            # (C) ノイズなし + カットあり (Wire Cutの理論検証用)
            error_params_ideal = ErrorParams({}, {}, {}) # 空のエラーパラメータ
            val_cut_ideal = simulate_cut_circuit(stim_qc, cut_pairs, error_params_ideal, shots, decomposition)
            #print(f"[Cut(Ideal)]  <ZZ..Z>: {val_cut_ideal:.4f}")
            if abs(val_cut_ideal-val_ideal) > 0.1 or (val_cut_ideal * val_ideal < 0): # 符号が逆の場合もNG
                #print("[Warning] Significant deviation in ideal cut simulation!")
                # Wire Cutting Decomposition (Identity Channel Decomposition)
                decomposition = [
                    (0.5,  'M_Z', 'P_0'), (-0.5, 'M_Z', 'P_1'),
                    (0.5,  'M_X', 'P_X+'), (-0.5, 'M_X', 'P_X-'),
                    (0.5,  'M_Y', 'P_Y+'), (-0.5, 'M_Y', 'P_Y-'),
                    (0.5,  'M_I', 'P_0'), (0.5,  'M_I', 'P_1')
                ]
                val_cut_ideal = simulate_cut_circuit(stim_qc, cut_pairs, error_params_ideal, shots, decomposition)
                if abs(val_cut_ideal-val_ideal) > 0.1 or (val_cut_ideal * val_ideal < 0): # 符号が逆の場合もNG
                    #print("[Warning] Significant deviation in ideal cut simulation!")
                    #cut_pairs = []  # カットを無効化
                    skip_counter += 1
                    continue  # この試行をスキップして次へ

            # (D) ノイズあり + カットあり (実機想定)
            val_cut_noisy = simulate_cut_circuit(stim_qc, cut_pairs, error_params, shots, decomposition)

            # === 結果 ===

            def mae(x, y):    return np.mean(np.abs(x - y))
            def rmse(x, y):   return np.sqrt(np.mean((x - y)**2))
            # 基本誤差
            mae_noisy     = mae(val_noisy, val_ideal)
            mae_cut       = mae(val_cut_noisy, val_ideal)

            rmse_noisy    = rmse(val_noisy, val_ideal)
            rmse_cut      = rmse(val_cut_noisy, val_ideal)
            # 改善率
            IR_mae   = (mae_noisy - mae_cut) / mae_noisy
            IR_rmse  = (rmse_noisy - rmse_cut) / rmse_noisy

            # 相対RMSE減衰
            RRR = 1 - rmse_cut / rmse_noisy

            # # SNR 向上量（dB）
            # def snr(x, y):
            #     return 10*np.log10(np.sum(y**2) / np.sum((x-y)**2))

            # snr_noisy = snr(val_noisy, val_ideal)
            # snr_cut   = snr(val_cut_noisy, val_ideal)
            #delta_snr = snr_cut - snr_noisy

            result = {
                'ideal': val_ideal,
                'noisy': val_noisy,
                'cut_noisy': val_cut_noisy,
                'mae_noisy': mae_noisy,
                'mae_cut': mae_cut,
                'rmse_noisy': rmse_noisy,
                'rmse_cut': rmse_cut,
                'IR_mae': IR_mae,
                'IR_rmse': IR_rmse,
                'RRR': RRR,
                #'delta_snr': delta_snr,
                'cut_size': len(cut_pairs)
            }
            results.append(result)
            print(result)

            #print(f"{{'ideal': {val_ideal:.4f}, 'noisy': {val_noisy:.4f}, 'cut_noisy': {val_cut_noisy:.4f}}}", )
            #print(f"exec_counter: {exec_counter}")
            if exec_counter >= TRIALS:
                break
            exec_counter += 1
    
    print(f"Evaluation completed. Executed: {exec_counter}, Skipped: {skip_counter}")
    return results


def evaluate_random_chip_suite():

    results = []
    tranqu = Tranqu()
    
    # --- Parameters ---
    WIDTH, HEIGHT = 4, 4  # 8 Qubits (g.py logic)
    # Note: g.py generates IDs based on 2x2 blocks.
    # 4x2 grid -> IDs: [0,1,2,3] (Block 0,0), [4,5,6,7] (Block 1,0). Total 8 contiguous IDs. Good.
    
    #N_QUBITS = WIDTH * HEIGHT 
    N_QUBITS = 10
    DEPTH = 2
    TRIALS = 30
    #SHOTS = 10000
    shots = 50000
    
    print(f"Starting Evaluation Randdom Chip (W={WIDTH}, H={HEIGHT}, N_QUBITS={N_QUBITS}, Depth={DEPTH})...")

    exec_counter = 1
    skip_counter = 0
    for i in range(TRIALS*10):
        #print(f"--- Trial {i+1} ---")

        device_json = generate_qubit_json_corrected(WIDTH, HEIGHT)
        
        # # # TODO: デバッグ
        # # #json_path = "device.good.json"
        # json_path = "device.json"
        # device_json = load_device(json_path)
        
        # デバッグ: チップの保存
        # json_str = json.dumps(device_json, indent=2)
        
        # #filename = "device_C_64.json"
        # filename = "../json/device.json"
        # with open(filename, "w") as f:
        #     f.write(json_str)
        
        # print(f"Successfully generated '{filename}'.")

        oqtopus_device, cx_fidelities, one_q_fidelities, qubit_coords, error_params = load_device_data(device_json)

        #qc = random_clifford_circuit(N_QUBITS, DEPTH, seed=None) # Seed None for random
        qc = QuantumCircuit(N_QUBITS)
        qc.h(0)
        for i in range(N_QUBITS-1):
            qc.cx(i, i+1)
        #qc.measure_all()

        try:
            result = tranqu.transpile(
                program=qc,
                program_lib="qiskit",
                transpiler_lib="qiskit",
                transpiler_options={
                    "basis_gates": ["id", "x", "y", "z", "h", "s", "sdg", "cx"], 
                    "optimization_level": 2},
                device=oqtopus_device,
                device_lib="oqtopus",
            )
            transpiled_qc = result.transpiled_program
        except Exception as e:
            #print(f"Transpilation failed: {e}")
            # トランスパイルに失敗したら次にいく
            continue
        
        # print(f"Original QC:\n{qc}")
        # print(f"Transpiled QC:\n{transpiled_qc}")

        # 3. グラフ解析とMIPによるカット
        G_circuit = circuit_to_networkx(
            transpiled_qc, 
            cx_fidelities, 
            one_q_fidelities, 
            qubit_coords
        )
        
        # MIPソルバ実行
        # max_cuts=2 に制限し、閾値以下のエッジを優先的に狙わせる
        cut_pairs = solve_mip_cut(G_circuit, max_cuts=2, cut_fidelity_threshold=0.96)

        if cut_pairs:
            #cut_pairs = [(4,5), (15,14)]
            #cut_pairs = [(3,9)]
            logger.info(f"MIP Result Cut pairs: {cut_pairs}")
            #print(f"MIP Result Cut pairs: {cut_pairs}")
            
            # 4. Stim変換とシミュレーション
            stim_qc = qiskit_to_stim(transpiled_qc)

            # (A) 理想的なシミュレーション
            val_ideal = simulate_ideal(stim_qc, shots)
            #print(f"\n[Ideal]       <ZZ..Z>: {val_ideal:.4f}")

            # (B) ノイズあり (カットなし)
            val_noisy = simulate_noisy(stim_qc, error_params, shots)
            #print(f"[Noisy]       <ZZ..Z>: {val_noisy:.4f}")
            
            # Gate Cutting Decomposition (CX Gate Decomposition)
            decomposition = [
                (0.5,  'I', 'I'), (0.5,  'Z', 'I'),
                (0.5,  'I', 'X'), (-0.5, 'Z', 'X')
            ]

            # (C) ノイズなし + カットあり (Wire Cutの理論検証用)
            error_params_ideal = ErrorParams({}, {}, {}) # 空のエラーパラメータ
            val_cut_ideal = simulate_cut_circuit(stim_qc, cut_pairs, error_params_ideal, shots, decomposition)
            #print(f"[Cut(Ideal)]  <ZZ..Z>: {val_cut_ideal:.4f}")
            if abs(val_cut_ideal-val_ideal) > 0.1 or (val_cut_ideal * val_ideal < 0): # 符号が逆の場合もNG
                #print("[Warning] Significant deviation in ideal cut simulation!")
                # Wire Cutting Decomposition (Identity Channel Decomposition)
                decomposition = [
                    (0.5,  'M_Z', 'P_0'), (-0.5, 'M_Z', 'P_1'),
                    (0.5,  'M_X', 'P_X+'), (-0.5, 'M_X', 'P_X-'),
                    (0.5,  'M_Y', 'P_Y+'), (-0.5, 'M_Y', 'P_Y-'),
                    (0.5,  'M_I', 'P_0'), (0.5,  'M_I', 'P_1')
                ]
                val_cut_ideal = simulate_cut_circuit(stim_qc, cut_pairs, error_params_ideal, shots, decomposition)
                if abs(val_cut_ideal-val_ideal) > 0.1 or (val_cut_ideal * val_ideal < 0): # 符号が逆の場合もNG
                    #print("[Warning] Significant deviation in ideal cut simulation!")
                    #cut_pairs = []  # カットを無効化
                    skip_counter += 1
                    #print(f"Skipping {skip_counter} trials due to ideal cut deviation.")
                    continue  # この試行をスキップして次へ

            # (D) ノイズあり + カットあり (実機想定)
            val_cut_noisy = simulate_cut_circuit(stim_qc, cut_pairs, error_params, shots, decomposition)

            # === 結果 ===

            def mae(x, y):    return np.mean(np.abs(x - y))
            def rmse(x, y):   return np.sqrt(np.mean((x - y)**2))
            # 基本誤差
            mae_noisy     = mae(val_noisy, val_ideal)
            mae_cut       = mae(val_cut_noisy, val_ideal)

            rmse_noisy    = rmse(val_noisy, val_ideal)
            rmse_cut      = rmse(val_cut_noisy, val_ideal)
            # 改善率
            IR_mae   = (mae_noisy - mae_cut) / mae_noisy
            IR_rmse  = (rmse_noisy - rmse_cut) / rmse_noisy

            # 相対RMSE減衰
            RRR = 1 - rmse_cut / rmse_noisy

            # # SNR 向上量（dB）
            # def snr(x, y):
            #     return 10*np.log10(np.sum(y**2) / np.sum((x-y)**2))

            # snr_noisy = snr(val_noisy, val_ideal)
            # snr_cut   = snr(val_cut_noisy, val_ideal)
            # delta_snr = snr_cut - snr_noisy

            result = {
                'ideal': val_ideal,
                'noisy': val_noisy,
                'cut_noisy': val_cut_noisy,
                'mae_noisy': mae_noisy,
                'mae_cut': mae_cut,
                'rmse_noisy': rmse_noisy,
                'rmse_cut': rmse_cut,
                'IR_mae': IR_mae,
                'IR_rmse': IR_rmse,
                'RRR': RRR,
                #'delta_snr': delta_snr,
                'cut_size': len(cut_pairs)
            }
            results.append(result)
            print(result)

            #print(f"{{'ideal': {val_ideal:.4f}, 'noisy': {val_noisy:.4f}, 'cut_noisy': {val_cut_noisy:.4f}}}", )
            #print(f"exec_counter: {exec_counter}")
            if exec_counter >= TRIALS:
                break
            exec_counter += 1
    
    print(f"Evaluation Random Chip completed. Executed: {exec_counter}, Skipped: {skip_counter}")
    return results

def _write_results(results, output_format: str = "jsonl"):
    """Write results to stdout in the specified format (jsonl or csv)."""
    if output_format.lower() == "csv":
        if not results:
            return
        fieldnames = list(results[0].keys())
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)
    else:
        # jsonl
        for row in results:
            sys.stdout.write(json.dumps(row, ensure_ascii=False) + "\n")



if __name__ == "__main__":
    res = evaluate_suite()
    _write_results(res, output_format="csv")
    #res = evaluate_random_chip_suite()

