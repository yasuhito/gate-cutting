import json
import logging
import random
import time
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
            if rng.random() < 0.05:
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

def solve_mip_cut(G: nx.MultiDiGraph, min_partition_ratio=0.3, cut_fidelity_threshold=0.98) -> List[Tuple[int, int]]:
    """
    MIPソルバを用いて最適なカットを探索する。
    
    修正: MultiDiGraphのedges(keys=True, data=True)の戻り値 (u, v, key, data) に対応
    """
    nodes = list(G.nodes(data=True))
    # keys=True, data=True なので (u, v, key, data) の4要素タプルが返る
    edges = list(G.edges(keys=True, data=True))
    
    n_nodes = len(nodes)
    n_edges = len(edges)
    
    if n_edges == 0: return []

    node_to_idx = {n[0]: i for i, n in enumerate(nodes)}
    
    # 変数: [x_0, ..., x_n-1, z_0, ..., z_m-1]
    n_vars = n_nodes + n_edges
    
    # === 目的関数 (Objective) ===
    # Minimize sum( Cost_k * z_k )
    c = np.zeros(n_vars)
    
    for k in range(n_edges):
        # 修正箇所: 4要素タプルからアンパック
        u, v, key, attr = edges[k]
        
        fid = attr.get('fidelity', 1.0)
        # 低Fidelity(エラーが高い)ほど係数を小さくして、カットに選ばれやすくする
        c[n_nodes + k] = fid + 0.1

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

    # TODO: デバッグ
    # 2. バランス制約 (Fidelity Weighted Balance)
    # ノードのFidelityの総和を計算
    total_node_fidelity = sum(d.get('fidelity', 1.0) for _, d in nodes)
    
    min_fid = total_node_fidelity * min_partition_ratio
    max_fid = total_node_fidelity * (1.0 - min_partition_ratio)
    
    for i in range(n_nodes):
        # nodes[i] は (node_id, attr_dict)
        weight = nodes[i][1].get('fidelity', 1.0)
        rows.append(constraint_idx); cols.append(i); vals.append(weight)
    
    b_l.append(min_fid); b_u.append(max_fid); constraint_idx += 1
    
    # === ソルバ実行 ===
    A = coo_matrix((vals, (rows, cols)), shape=(constraint_idx, n_vars))
    res = milp(c=c, constraints=LinearConstraint(A, b_l, b_u), integrality=np.ones(n_vars), bounds=Bounds(0, 1))
    
    if not res.success:
        logger.warning("MIP Solver failed to find a balanced cut.")
        return []

    # === 結果解析 ===
    selected_cut_indices = [k for k in range(n_edges) if res.x[n_nodes + k] > 0.5]
    
    if not selected_cut_indices:
        return []

    # カットされたエッジのFidelity平均を計算 (修正: attrへのアクセス)
    cut_fidelities = [edges[k][3].get('fidelity', 1.0) for k in selected_cut_indices]
    avg_cut_fidelity = sum(cut_fidelities) / len(cut_fidelities)

    # # TODO: デバッグ    
    # if avg_cut_fidelity > cut_fidelity_threshold:
    #     logger.info(f"Optimization Found cuts, but rejected: Avg Cut Fidelity {avg_cut_fidelity:.4f} > Threshold {cut_fidelity_threshold}")
    #     return []

    logger.info(f"MIP Selected {len(selected_cut_indices)} cuts. Avg Fidelity: {avg_cut_fidelity:.4f}")
    return [(edges[k][0], edges[k][1]) for k in selected_cut_indices]

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

def append_noise_op(circuit, op, targets, params):
    if op == 'M':
        for q in targets:
            if params.readout.get(q, 0) > 0: circuit.append("X_ERROR", [q], params.readout[q])
        circuit.append("M", targets)
    else:
        circuit.append(op, targets)
        # Apply depol noise
        if len(targets) == 1:
            if params.one_qubit.get(targets[0], 0) > 0:
                circuit.append("DEPOLARIZE1", targets, params.one_qubit[targets[0]])
        elif len(targets) == 2 and op == 'CX':
            # Directed error lookup
            err = params.two_qubit.get(tuple(targets), 0)
            if err > 0:
                circuit.append("DEPOLARIZE2", targets, err)

def append_wire_cut(circuit, op_code, q, params):
    ops_map = {
        'M_Z': [('M', [q])], 'M_X': [('H', [q]), ('M', [q])], 'M_Y': [('S_DAG', [q]), ('H', [q]), ('M', [q])],
        'M_I': [('R', [q])], 'P_0': [('R', [q])], 'P_1': [('R', [q]), ('X', [q])],
        'P_X+': [('R', [q]), ('H', [q])], 'P_X-': [('R', [q]), ('X', [q]), ('H', [q])],
        'P_Y+': [('R', [q]), ('H', [q]), ('S', [q])], 'P_Y-': [('R', [q]), ('H', [q]), ('S_DAG', [q])]
    }
    for op, tgts in ops_map[op_code]:
        append_noise_op(circuit, op, tgts, params)


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

def simulate_ideal(circuit: stim.Circuit, shots=10000) -> float:
    sim_circ = circuit.copy()
    if sim_circ.num_measurements == 0:
        active_qubits = get_active_qubits(sim_circ)
        sim_circ.append("M", active_qubits)
    sampler = sim_circ.compile_sampler()
    samples = sampler.sample(shots=shots)
    return calculate_expectation(samples)

def simulate_noisy(circuit: stim.Circuit, error_params: ErrorParams, shots=10000) -> float:
    noisy_circuit = stim.Circuit()
    for instruction in circuit:
        targets = [t.value for t in instruction.targets_copy() if t.is_qubit_target]
        append_operation_with_noise(noisy_circuit, instruction.name, targets, error_params)
    
    if noisy_circuit.num_measurements == 0:
        active_qubits = get_active_qubits(noisy_circuit)
        noisy_circuit.append("M", active_qubits)

    # TODO: デバッグ
    #print(f"noisy_circuit:\n{noisy_circuit}")

    sampler = noisy_circuit.compile_sampler()
    samples = sampler.sample(shots=shots)
    return calculate_expectation(samples)

def simulate_cut_circuit(
    original_circuit: stim.Circuit,
    cut_pairs: List[Tuple[int, int]], 
    error_params: ErrorParams,
    shots=10000
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

    active_qubits = get_active_qubits(original_circuit)

    if not cut_indices:
        print("[Cut] Warning: No matching CX gates found in Stim circuit for the MIP cut.")
        return 0.0
    
    print(f"[Cut] Identified Stim indices to cut: {cut_indices}")

    # # Wire Cutting Decomposition (Identity Channel Decomposition)
    decomposition = [
        (0.5,  'M_Z', 'P_0'), (-0.5, 'M_Z', 'P_1'),
        (0.5,  'M_X', 'P_X+'), (-0.5, 'M_X', 'P_X-'),
        (0.5,  'M_Y', 'P_Y+'), (-0.5, 'M_Y', 'P_Y-'),
        (0.5,  'M_I', 'P_0'), (0.5,  'M_I', 'P_1')
    ]
    
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

        if sub_circuit.num_measurements == 0:
            sub_circuit.append("M", active_qubits)
        else:
            sub_circuit.append("M", active_qubits)

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
    #TRIALS = 3
    #SHOTS = 10000
    shots = 50000
    
    print(f"Starting Evaluation (W={WIDTH}, H={HEIGHT}, Depth={DEPTH})...")

    # === Case 1: 固定チップ x ランダム回路 ===
    print("--- Case 1: Fixed Chip x Random Circuits ---")
    
    #device_json = generate_qubit_json_corrected(WIDTH, HEIGHT)
    
    # TODO: デバッグ
    #json_path = "device.good.json"
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

    # qc = random_clifford_circuit(N_QUBITS, DEPTH, seed=None) # Seed None for random
    # print(qc)

    # # # # TODO: デバッグ用に回路保存
    # import pickle
    # with open(f"qc.pkl", "wb") as f:
    #     pickle.dump(qc, f)  

    # import pickle
    # with open(f"qc.pkl", "rb") as f:
    #     qc = pickle.load(f)
    # #print(qc)

    qc = QuantumCircuit(N_QUBITS)
    qc.h(0)
    for i in range(N_QUBITS - 1):
        qc.cx(i, i + 1)

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
    
    logger.info(f"Mapping: {result.virtual_physical_mapping.qubit_mapping}")

    print(f"Original QC:\n{qc}")
    print(f"Transpiled QC:\n{transpiled_qc}")

    # # # TODO: デバッグ実際のエラーを悪くしてみる
    # json_path = "device.json"
    # device_json = load_device(json_path)
    # oqtopus_device, cx_fidelities, one_q_fidelities, qubit_coords, error_params = load_device_data(device_json)
    # print(f"error_params bad: {error_params}")

    # 3. グラフ解析とMIPによるカット
    G_circuit = circuit_to_networkx(
        transpiled_qc, 
        cx_fidelities, 
        one_q_fidelities, 
        qubit_coords
    )
    
    # MIPソルバ実行
    cut_pairs = solve_mip_cut(G_circuit, min_partition_ratio=0.3, cut_fidelity_threshold=0.95)

    #cut_pairs = [(4,5), (15,14)]
    #cut_pairs = [(3,9)]
    logger.info(f"MIP Result Cut pairs: {cut_pairs}")
    
    # 4. Stim変換とシミュレーション
    stim_qc = qiskit_to_stim(transpiled_qc)

    # (A) 理想的なシミュレーション
    val_ideal = simulate_ideal(stim_qc, shots)
    print(f"\n[Ideal]       <ZZ..Z>: {val_ideal:.4f}")

    # (B) ノイズあり (カットなし)
    val_noisy = simulate_noisy(stim_qc, error_params, shots)
    print(f"[Noisy]       <ZZ..Z>: {val_noisy:.4f}")

    if cut_pairs:
        # (C) ノイズなし + カットあり (Wire Cutの理論検証用)
        error_params_ideal = ErrorParams({}, {}, {}) # 空のエラーパラメータ
        val_cut_ideal = simulate_cut_circuit(stim_qc, cut_pairs, error_params_ideal, shots)
        print(f"[Cut(Ideal)]  <ZZ..Z>: {val_cut_ideal:.4f}")

        # (D) ノイズあり + カットあり (実機想定)
        val_cut_noisy = simulate_cut_circuit(stim_qc, cut_pairs, error_params, shots)
        print(f"[Cut(Noisy)]  <ZZ..Z>: {val_cut_noisy:.4f}")
    else:
        print("[Cut] Skipped (No cuts found)")

    # === 可視化 ===
    plot_result(oqtopus_device, qubit_coords, one_q_fidelities, G_circuit, cut_pairs)


    return results

# ==========================================
# 7. Visualization
# ==========================================

def plot_result(raw_data, qubit_coords, one_q_fidelities, G_circuit, cut_pairs):
    # === 可視化 ===
    print("\n--- Visualizing Graph ---")
    fig, ax = plt.subplots(figsize=(8, 8)) # axを取得するために修正

    # -----------------------------
    # (1) デバイス全体のグラフ構築とデータ収集
    # -----------------------------
    G_device = nx.DiGraph()
    device_pos = {}
    node_labels = {}
    edge_labels = {}
    node_fidelities = {} # Fidelityデータを収集する辞書

    # ノード追加 (全量子ビット)
    if 'qubits' in raw_data:
        for q in raw_data['qubits']:
            qid = int(q['id'])
            # 座標取得 (load_device_dataで処理済み)
            device_pos[qid] = qubit_coords.get(qid, (qid, 0))
            
            # Fidelity情報を取得
            fid = one_q_fidelities.get(qid, 0.0)
            G_device.add_node(qid, fidelity=fid) # ノードにfidelity属性を追加
            node_fidelities[qid] = fid
            
            # ラベル (ID + Fidelity)
            node_labels[qid] = f"{qid}\n{fid:.4f}"

    # エッジ追加 (全結合)
    if 'couplings' in raw_data:
        for c in raw_data['couplings']:
            u, v = int(c['control']), int(c['target'])
            fid = float(c['fidelity'])
            G_device.add_edge(u, v)
            edge_labels[(u, v)] = f"{fid:.4f}"

    qubit_number = len(G_device.nodes)
    coupling_number = len(G_device.edges)
    
    # -----------------------------
    # (2) 回路で使用されたエッジとカット箇所を特定
    # -----------------------------
    used_edges_set = set(G_circuit.edges())
    cut_edges_set = set(cut_pairs)
    
    normal_edges_to_draw = []
    cut_edges_to_draw = []

    for u, v in used_edges_set:
        if G_device.has_edge(u, v):
            if (u, v) in cut_edges_set:
                cut_edges_to_draw.append((u, v))
            else:
                normal_edges_to_draw.append((u, v))
    
    # -----------------------------
    # (3) 描画 - カラーコード適用
    # -----------------------------
    node_size = 1500 
    
    # カラーコードの設定
    if node_fidelities:
        fidelity_values = list(node_fidelities.values())
        if fidelity_values:
            vmin = min(fidelity_values)
            vmax = max(fidelity_values)
        else:
            vmin = 0.0
            vmax = 1.0

        sm = plt.cm.ScalarMappable(
            cmap="viridis",
            norm=plt.Normalize(vmin=vmin, vmax=vmax)
        )
        # 各ノードの忠実度に基づいて色を決定
        node_colors = [sm.to_rgba(f) for f in fidelity_values] 
        
        # A. 全ノード (カラーコード適用)
        nx.draw_networkx_nodes(G_device, device_pos, 
                            node_size=node_size, 
                            node_color=node_colors, # カラーコード適用
                            edgecolors='black',
                            ax=ax) 

        # カラーバーの追加
        cbar = plt.colorbar(sm, ax=ax, label="Qubit Fidelity", fraction=0.046, pad=0.04)
        cbar.ax.tick_params(labelsize=10)
        
    else:
        # ノードがない場合のデフォルト描画
        nx.draw_networkx_nodes(G_device, device_pos, 
                            node_size=node_size, 
                            node_color='lightgreen', 
                            edgecolors='black',
                            ax=ax)


    # B. ノードラベル
    nx.draw_networkx_labels(G_device, device_pos, 
                            labels=node_labels,
                            font_size=9, 
                            font_family='sans-serif',
                            font_weight='bold',
                            ax=ax)

    # C. 全エッジ (グレー, 通常)
    nx.draw_networkx_edges(G_device, device_pos, 
                           node_size=node_size,
                           arrowstyle='-|>', 
                           arrowsize=15, 
                           edge_color='dimgray', 
                           width=1.0,
                           connectionstyle='arc3,rad=0',
                           ax=ax)

    # D. 使用エッジ (青, 太線) - カットされなかった部分
    if normal_edges_to_draw:
        nx.draw_networkx_edges(G_device, device_pos, 
                               edgelist=normal_edges_to_draw,
                               node_size=node_size,
                               arrowstyle='-|>', 
                               arrowsize=20, 
                               edge_color='blue', 
                               width=2.5, 
                               connectionstyle='arc3,rad=0',
                               ax=ax)

    # E. カットエッジ (赤, 破線, 太線)
    if cut_edges_to_draw:
        nx.draw_networkx_edges(G_device, device_pos, 
                               edgelist=cut_edges_to_draw,
                               node_size=node_size,
                               arrowstyle='-|>', 
                               arrowsize=20, 
                               edge_color='red', 
                               width=3.5,
                               style='dashed',
                               connectionstyle='arc3,rad=0',
                               ax=ax)

    # F. エッジラベル (Fidelity)
    nx.draw_networkx_edge_labels(G_device, device_pos, 
                                 edge_labels=edge_labels, 
                                 font_color='darkblue',
                                 font_size=8,
                                 label_pos=0.6,
                                 ax=ax)

    # タイトル設定 (量子ビット数と結合数を追加)
    ax.set_title(
        f"Transpiled Circuit (Blue=Used, Red=Cut)\nQubit: {qubit_number}, Coupling: {coupling_number}",
        pad=20, 
        fontsize=14, 
        fontweight="bold"
    )
    
    ax.axis('off')
    
    # 座標系調整: Y軸反転で左上を(0,0)に
    ax.invert_yaxis()
    
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    res = evaluate_suite()
