import json
import logging
import random
import sys
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Any
from datetime import datetime, timezone, timedelta

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import networkx as nx
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix

# Qiskit Imports
from qiskit import QuantumCircuit
from qiskit.circuit.library import HGate, SGate, XGate, YGate, ZGate, CXGate

# Stim Imports
import stim
from gate_cutting.device import parse_device
from gate_cutting.gate_cutting import find_cx_cut_targets, run_gate_cut
from gate_cutting.stim_backend import (
    ErrorParams,
    append_operation_with_noise as append_stim_operation_with_noise,
    parity_expectation as stim_parity_expectation,
    qiskit_to_stim as convert_qiskit_to_stim,
    run_standard as run_stim_standard,
)

# External Library
try:
    from tranqu import Tranqu
except ImportError:
    Tranqu = None

# ==========================================
# 0. 設定とデータ構造
# ==========================================

logging.basicConfig(level=logging.FATAL, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

@dataclass
class SimulationConfig:
    n_qubits: int = 10
    depth: int = 2
    trials: int = 10
    shots: int = 50000
    device_file: str = "device.json"
    device: Any = None
    max_cuts: int = 2
    cut_fidelity_threshold: float = 0.96 # これを下回ると強制カット
    optimization_level: int = 2

# ==========================================
# 1. Device Manager (a1.py base + e5.py adaptation)
# ==========================================

class DeviceManager:
    def __init__(self, json_path: str):
        if json_path:
            self.json_path = Path(json_path)
            self.raw_data = self._load_json()
        else:
            self.json_path = None
            self.raw_data = self.generate_qubit_json_corrected()
        self.cx_fidelities = {}
        self.one_q_fidelities = {}
        self.qubit_coords = {}
        self.error_params = self._parse_device_data()
        
    def _load_json(self) -> Dict[str, Any]:
        if not self.json_path.exists():
            raise FileNotFoundError(f"Device file not found: {self.json_path}")
        return json.loads(self.json_path.read_text(encoding="utf-8"))

    def _parse_device_data(self) -> ErrorParams:
        parsed = parse_device(self.raw_data)
        self.cx_fidelities = parsed.cx_fidelities
        self.one_q_fidelities = parsed.one_q_fidelities
        self.qubit_coords = parsed.qubit_coords
        return parsed.error_params

    def generate_qubit_json_corrected(self, width: int = 4, height: int = 4) -> dict:
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


# ==========================================
# 2. Circuit Generator (a1.py)
# ==========================================

class CircuitGenerator:
    SINGLE_QUBIT_CLIFFORDS = [
        ("h", HGate()), ("s", SGate()), ("sdg", SGate().inverse()),
        ("x", XGate()), ("y", YGate()), ("z", ZGate())
    ]

    @staticmethod
    def random_clifford(num_qubits: int, depth: int, seed: int | None = None) -> QuantumCircuit:
        rng = random.Random(seed)
        qc = QuantumCircuit(num_qubits)
        qubits = list(range(num_qubits))

        for _ in range(depth):
            for q in qubits:
                if rng.random() < 0.6:
                    _, gate = rng.choice(CircuitGenerator.SINGLE_QUBIT_CLIFFORDS)
                    qc.append(gate, [q])
            rng.shuffle(qubits)
            for i in range(0, len(qubits)-1, 2):
                if rng.random() < 2.0:
                    qc.append(CXGate(), [qubits[i], qubits[i+1]])
        return qc

# ==========================================
# 3. MIP Solver (e5.py Logic Adapted)
# ==========================================

#class MIPCutFinder:
    """MIPを用いて最適なカット箇所(CXゲート)を探索する。e5.pyのBoundsロジックを採用"""
    def __init__(self, device_manager: DeviceManager):
        self.dm = device_manager

    def build_graph(self, circuit: QuantumCircuit) -> nx.MultiDiGraph:
        G = nx.MultiDiGraph()
        # ノード追加
        for i in range(circuit.num_qubits):
            pos = self.dm.qubit_coords.get(i, (i, 0))
            fid_1q = self.dm.one_q_fidelities.get(i, 1.0)
            G.add_node(i, pos=pos, fidelity=fid_1q)
            
        # エッジ追加
        for instruction in circuit.data:
            if instruction.operation.name != "cx":
                continue
            c_idx = circuit.find_bit(instruction.qubits[0]).index
            t_idx = circuit.find_bit(instruction.qubits[1]).index
            fid_cx = self.dm.cx_fidelities.get((c_idx, t_idx), 1.0)
            
            # Fidelityを属性として保持
            G.add_edge(c_idx, t_idx, gate="cx", fidelity=fid_cx)
        return G

    def solve(self, G: nx.MultiDiGraph, max_cuts: int = 3, cut_fidelity_threshold: float = 0.96) -> List[Tuple[int, int]]:
        nodes = list(G.nodes(data=True))
        edges = list(G.edges(keys=True, data=True))
        n_nodes = len(nodes)
        n_edges = len(edges)
        if n_edges == 0: return []

        node_to_idx = {n[0]: i for i, n in enumerate(nodes)}
        n_vars = n_nodes + n_edges # [x_0...x_n, z_0...z_m]
        
        # === 目的関数 (Objective) ===
        c = np.zeros(n_vars)
        
        # === 変数の境界値 (Bounds) ===
        # e5.py logic: 悪いエッジに対応する z_k は lower_bound=1.0 (必ず切る) に設定
        lower_bounds = np.zeros(n_vars)
        upper_bounds = np.ones(n_vars)
        
        forced_cuts_count = 0
        
        for k in range(n_edges):
            u, v, _, attr = edges[k]
            fid = attr.get('fidelity', 1.0)
            
            if fid < cut_fidelity_threshold:
                # 強制カット
                c[n_nodes + k] = 0.0 
                lower_bounds[n_nodes + k] = 1.0
                forced_cuts_count += 1
            else:
                # 良いエッジは切りたくない (Fidelityが高いほどコスト増)
                error_rate = max(1.0 - fid, 1e-9)
                weight = fid / error_rate
                c[n_nodes + k] = weight

        # === 制約 (Constraints) ===
        rows, cols, vals = [], [], []
        b_l, b_u = [], []
        constraint_idx = 0
        
        # 1. 切断の論理制約: z_k >= |x_u - x_v|
        for k in range(n_edges):
            u, v, _, _ = edges[k]
            u_idx = node_to_idx[u]
            v_idx = node_to_idx[v]
            z_idx = n_nodes + k
            
            # -x_u + x_v + z_k >= 0
            rows.extend([constraint_idx]*3); cols.extend([u_idx, v_idx, z_idx]); vals.extend([-1, 1, 1])
            b_l.append(0); b_u.append(np.inf); constraint_idx += 1
            # x_u - x_v + z_k >= 0
            rows.extend([constraint_idx]*3); cols.extend([u_idx, v_idx, z_idx]); vals.extend([1, -1, 1])
            b_l.append(0); b_u.append(np.inf); constraint_idx += 1

        # 2. カット数上限 (強制カット分はカウントされるが、上限を超えてもBounds優先で解なしになるのを防ぐため考慮が必要)
        # ここでは e5.py の緩和されたバランス制約を採用する代わりに、単純な個数制限は一旦外すか、緩める。
        # 今回は a1.py の max_cuts を尊重しつつ、強制カットが多い場合は警告を出す運用にする。
        
        # カット数制限（zの総和 <= max_cuts）
        if forced_cuts_count <= max_cuts:
            for k in range(n_edges):
                z_idx = n_nodes + k
                rows.append(constraint_idx); cols.append(z_idx); vals.append(1)
            b_l.append(0); b_u.append(max_cuts); constraint_idx += 1
        else:
            logger.warning(f"Forced cuts ({forced_cuts_count}) exceed max_cuts ({max_cuts}). Ignoring max_cuts constraint.")

        # 3. バランス制約 (Min Partition Ratio) - e5.py からの移植
        # 極端な断片化を許容するため 0.0 に設定 (a1.pyにはなかったが導入)
        min_partition_ratio = 0.0
        total_node_fidelity = sum(d.get('fidelity', 1.0) for _, d in nodes)
        min_limit = total_node_fidelity * min_partition_ratio
        max_limit = total_node_fidelity * (1.0 - min_partition_ratio)
        
        for i in range(n_nodes):
            weight = nodes[i][1].get('fidelity', 1.0)
            rows.append(constraint_idx); cols.append(i); vals.append(weight)
        b_l.append(min_limit); b_u.append(max_limit); constraint_idx += 1

        # ソルバ実行
        A = coo_matrix((vals, (rows, cols)), shape=(constraint_idx, n_vars))
        res = milp(
            c=c, 
            constraints=LinearConstraint(A, b_l, b_u), 
            integrality=np.ones(n_vars), 
            bounds=Bounds(lower_bounds, upper_bounds)
        )
        
        if not res.success:
            logger.warning("MIP Solver failed. Returning strictly low fidelity edges as fallback.")
            return [(u, v) for u, v, _, d in edges if d.get('fidelity', 1.0) < cut_fidelity_threshold]

        selected_cuts = []
        for k in range(n_edges):
            if res.x[n_nodes + k] > 0.5:
                u, v, _, _ = edges[k]
                selected_cuts.append((u, v))
        return selected_cuts

class MIPCutFinder:
    """MIPを用いて最適なカット箇所(CXゲート)を探索する。max_cutsを厳守するように修正"""
    def __init__(self, device_manager):
        self.dm = device_manager

    def build_graph(self, circuit) -> nx.MultiDiGraph:
        G = nx.MultiDiGraph()
        # ノード追加
        for i in range(circuit.num_qubits):
            pos = self.dm.qubit_coords.get(i, (i, 0))
            fid_1q = self.dm.one_q_fidelities.get(i, 1.0)
            G.add_node(i, pos=pos, fidelity=fid_1q)
            
        # エッジ追加
        for instruction in circuit.data:
            if instruction.operation.name != "cx":
                continue
            c_idx = circuit.find_bit(instruction.qubits[0]).index
            t_idx = circuit.find_bit(instruction.qubits[1]).index
            fid_cx = self.dm.cx_fidelities.get((c_idx, t_idx), 1.0)
            
            # Fidelityを属性として保持
            G.add_edge(c_idx, t_idx, gate="cx", fidelity=fid_cx)
        return G

    def solve(self, G: nx.MultiDiGraph, max_cuts: int = 3, cut_fidelity_threshold: float = 0.96) -> List[Tuple[int, int]]:
        nodes = list(G.nodes(data=True))
        edges = list(G.edges(keys=True, data=True))
        n_nodes = len(nodes)
        n_edges = len(edges)
        if n_edges == 0: return []

        node_to_idx = {n[0]: i for i, n in enumerate(nodes)}
        n_vars = n_nodes + n_edges # [x_0...x_n, z_0...z_m]
        
        # === 変数の境界値 (Bounds) と 目的関数 (Objective) の準備 ===
        c = np.zeros(n_vars)
        lower_bounds = np.zeros(n_vars)
        upper_bounds = np.ones(n_vars)
        
        # --- 修正点1: 強制カット候補を事前に特定し、max_cutsを超えないように調整 ---
        # 低Fidelityのエッジ（インデックスとFidelity）をリストアップ
        bad_edges = []
        for k in range(n_edges):
            _, _, _, attr = edges[k]
            fid = attr.get('fidelity', 1.0)
            if fid < cut_fidelity_threshold:
                bad_edges.append((k, fid))
        
        # Fidelityが低い順（悪い順）にソート
        bad_edges.sort(key=lambda x: x[1])
        
        # 強制的に切断するエッジのインデックスセットを作成
        # max_cutsを超える場合は、より悪いエッジを優先し、残りは強制しない（コストで判断させる）
        force_cut_indices = set()
        if len(bad_edges) > max_cuts:
            logger.warning(f"Low fidelity edges ({len(bad_edges)}) exceed max_cuts ({max_cuts}). Enforcing strictly worst {max_cuts} cuts.")
            force_cut_indices = {k for k, _ in bad_edges[:max_cuts]}
        else:
            force_cut_indices = {k for k, _ in bad_edges}

        # コストとBoundsの設定
        for k in range(n_edges):
            u, v, _, attr = edges[k]
            fid = attr.get('fidelity', 1.0)
            z_idx = n_nodes + k
            
            if k in force_cut_indices:
                # 強制カット対象
                c[z_idx] = 0.0 
                lower_bounds[z_idx] = 1.0 # ここで強制的に1にする
            else:
                # 通常のエッジ（またはmax_cuts溢れで強制から漏れた低Fidelityエッジ）
                # 切りたくない度合いをコストにする
                error_rate = max(1.0 - fid, 1e-9)
                weight = fid / error_rate
                
                # 低Fidelityだが強制リストに入らなかったものは、
                # コストを低く設定してソルバに「切るならこれ」と推奨する（weightは小さくなる）
                c[z_idx] = weight

        # === 制約 (Constraints) ===
        rows, cols, vals = [], [], []
        b_l, b_u = [], []
        constraint_idx = 0
        
        # 1. 切断の論理制約: z_k >= |x_u - x_v|
        for k in range(n_edges):
            u, v, _, _ = edges[k]
            u_idx = node_to_idx[u]
            v_idx = node_to_idx[v]
            z_idx = n_nodes + k
            
            # -x_u + x_v + z_k >= 0
            rows.extend([constraint_idx]*3); cols.extend([u_idx, v_idx, z_idx]); vals.extend([-1, 1, 1])
            b_l.append(0); b_u.append(np.inf); constraint_idx += 1
            # x_u - x_v + z_k >= 0
            rows.extend([constraint_idx]*3); cols.extend([u_idx, v_idx, z_idx]); vals.extend([1, -1, 1])
            b_l.append(0); b_u.append(np.inf); constraint_idx += 1

        # 2. カット数上限 (max_cuts)
        # --- 修正点2: 条件分岐を削除し、必ず制約を追加 ---
        for k in range(n_edges):
            z_idx = n_nodes + k
            rows.append(constraint_idx); cols.append(z_idx); vals.append(1)
        b_l.append(0); b_u.append(max_cuts); constraint_idx += 1

        # 3. バランス制約 (Min Partition Ratio)
        min_partition_ratio = 0.0 # 0.0 = 任意の分割サイズを許容
        total_node_fidelity = sum(d.get('fidelity', 1.0) for _, d in nodes)
        min_limit = total_node_fidelity * min_partition_ratio
        max_limit = total_node_fidelity * (1.0 - min_partition_ratio)
        
        for i in range(n_nodes):
            weight = nodes[i][1].get('fidelity', 1.0)
            rows.append(constraint_idx); cols.append(i); vals.append(weight)
        b_l.append(min_limit); b_u.append(max_limit); constraint_idx += 1

        # ソルバ実行
        A = coo_matrix((vals, (rows, cols)), shape=(constraint_idx, n_vars))
        res = milp(
            c=c, 
            constraints=LinearConstraint(A, b_l, b_u), 
            integrality=np.ones(n_vars), 
            bounds=Bounds(lower_bounds, upper_bounds)
        )
        
        if not res.success:
            logger.warning("MIP Solver failed. Returning worst edges strictly within max_cuts as fallback.")
            # --- 修正点3: Fallback時もmax_cutsを守る ---
            # 全ての低Fidelityエッジを取得
            fallback_candidates = []
            for k in range(n_edges):
                _, _, _, attr = edges[k]
                if attr.get('fidelity', 1.0) < cut_fidelity_threshold:
                    fallback_candidates.append(edges[k])
            
            # Fidelityが低い順にソートして、max_cuts個だけ返す
            fallback_candidates.sort(key=lambda x: x[3].get('fidelity', 1.0))
            return [(u, v) for u, v, _, _ in fallback_candidates[:max_cuts]]

        selected_cuts = []
        for k in range(n_edges):
            # z_k が 1 (に近い値) ならカット
            if res.x[n_nodes + k] > 0.5:
                u, v, _, _ = edges[k]
                selected_cuts.append((u, v))
                
        # 念のための安全策: 万が一数値誤差等でmax_cutsを超えていたら、fidelityの低い順に絞る
        if len(selected_cuts) > max_cuts:
             logger.warning(f"Solver result {len(selected_cuts)} > max_cuts. Trimming result.")
             # エッジ情報を取り出し直してソートする必要があるため、少し手間だが厳密に行う
             cut_details = []
             for u, v in selected_cuts:
                 # 元のグラフから属性を取得
                 fid = G[u][v][0].get('fidelity', 1.0)
                 cut_details.append(((u, v), fid))
             cut_details.sort(key=lambda x: x[1]) # 低い順
             selected_cuts = [item[0] for item in cut_details[:max_cuts]]

        return selected_cuts
    
# ==========================================
# 4. Stim Simulator (New: Replaces GateCutSimulator)
# ==========================================

class StimGateCutSimulator:
    """Stimを使用したGate Cuttingシミュレーション"""

    # Gate Cutting Decomposition for CNOT (Control-Z / Target-X basis)
    # CX = 0.5(II + ZI + IX - ZX)
    # (Coeff, Control_Op, Target_Op)
    DECOMPOSITION = [
        (0.5,  'I', 'I'),
        (0.5,  'Z', 'I'),
        (0.5,  'I', 'X'),
        (-0.5, 'Z', 'X')
    ]

    IGNORE_OPS = {"TICK", "SHIFT_COORDS", "QUBIT_COORDS", "DETECTOR", "OBSERVABLE_INCLUDE", "BARRIER"}
    MEASURE_OPS = {"M", "MR", "MX", "MY", "MZ"}

    @staticmethod
    def qiskit_to_stim(qc: QuantumCircuit) -> stim.Circuit:
        return convert_qiskit_to_stim(qc)

    @classmethod
    def _append_op_with_noise(cls, circuit: stim.Circuit, op_name: str, targets: List[int], error_params: ErrorParams):
        append_stim_operation_with_noise(circuit, op_name, targets, error_params)

    @staticmethod
    def get_expectation(samples: np.ndarray) -> float:
        """<ZZ...Z> 期待値計算"""
        return stim_parity_expectation(samples)

    @classmethod
    def run_standard(cls, circuit: stim.Circuit, error_params: ErrorParams = None, shots=10000) -> float:
        """通常のStimシミュレーション (Ideal or Noisy)"""
        return run_stim_standard(circuit, shots=shots, error_params=error_params)

    @classmethod
    def run_cut(cls, original_stim: stim.Circuit, cut_pairs: List[Tuple[int, int]], 
                error_params: ErrorParams, shots=10000) -> float:
        """Gate Cuttingシミュレーション (Stim版)"""
        cut_targets = find_cx_cut_targets(original_stim, cut_pairs=cut_pairs)
        return run_gate_cut(original_stim, cut_targets, error_params, shots=shots)

# ==========================================
# 5. Experiment Runner
# ==========================================

class ExperimentRunner:
    def __init__(self, config: SimulationConfig):
        self.config = config
        if config.device_file:
            self.dm = DeviceManager(config.device_file)
        else:
            self.dm = DeviceManager()
        self.mip_solver = MIPCutFinder(self.dm)
        # エラーなしパラメータ (Ideal用)
        self.ideal_params = ErrorParams({}, {}, {})
        # 実機ノイズパラメータ
        self.noise_params = self.dm.error_params
        
        self.tranqu = Tranqu() if Tranqu else None
        if self.tranqu is None:
            logger.warning("Tranqu not found. Skipping transpilation step.")

    def run(self):
        results = []
        logger.info(f"Starting Stim-based Evaluation with config: {self.config}")

        exec_counter = 0
        while exec_counter < self.config.trials:
            # 1. Circuit Generation (Qiskit)
            qc = CircuitGenerator.random_clifford(
                self.config.n_qubits, 
                self.config.depth
            )

            # 2. Transpilation (Tranqu -> Qiskit)
            if self.tranqu:
                try:
                    result = self.tranqu.transpile(
                        program=qc,
                        program_lib="qiskit",
                        transpiler_lib="qiskit",
                        transpiler_options={
                            "basis_gates": ["id", "x", "y", "z", "h", "s", "sdg", "cx"], 
                            "optimization_level": self.config.optimization_level
                        },
                        device=self.dm.raw_data,
                        device_lib="oqtopus",
                    )
                    transpiled_qc = result.transpiled_program
                except Exception as e:
                    logger.error(f"Transpilation failed: {e}")
                    continue
            else:
                transpiled_qc = qc 

            # 3. MIP Cut Finding
            G_circuit = self.mip_solver.build_graph(transpiled_qc)
            cut_pairs = self.mip_solver.solve(
                G_circuit, 
                max_cuts=self.config.max_cuts, 
                cut_fidelity_threshold=self.config.cut_fidelity_threshold
            )
            
            if cut_pairs:
                logger.info(f"Trial {exec_counter+1}: Cutting CX gates at {cut_pairs}")
            else:
                logger.info(f"Trial {exec_counter+1}: No cuts needed or found.")

            # 4. Convert to Stim
            try:
                stim_qc = StimGateCutSimulator.qiskit_to_stim(transpiled_qc)
                # 元の回路(比較用)
                stim_org = StimGateCutSimulator.qiskit_to_stim(qc)
            except Exception as e:
                logger.error(f"Stim conversion failed: {e}")
                continue

            # 5. Simulation (Stim)
            
            # (A) Ideal (No Noise, No Cut) - Reference
            val_ideal = StimGateCutSimulator.run_standard(stim_qc, error_params=None, shots=self.config.shots)
            
            # (B) Noisy (Standard Execution) - Baseline
            val_noisy = StimGateCutSimulator.run_standard(stim_qc, error_params=self.noise_params, shots=self.config.shots)
            
            # (C) Cut (Noisy) - Proposed Method
            val_cut_noisy = 0.0
            if cut_pairs:
                val_cut_noisy = StimGateCutSimulator.run_cut(
                    stim_qc, cut_pairs, error_params=self.noise_params, shots=self.config.shots
                )
            else:
                val_cut_noisy = val_noisy

            res_entry = {
                'trial': exec_counter + 1,
                'cuts': len(cut_pairs),
                'ideal': val_ideal,
                'noisy': val_noisy,
                'cut_noisy': val_cut_noisy,
                'err_std': abs(val_ideal - val_noisy),
                'err_cut': abs(val_ideal - val_cut_noisy),
                'improvement': abs(val_ideal - val_noisy) - abs(val_ideal - val_cut_noisy)
            }
            results.append(res_entry)
            print(res_entry) 

            exec_counter += 1

        return results

    def write_results(self, results: List[Dict], output_format: str = "csv"):
        if not results: return
        if output_format.lower() == "csv":
            fieldnames = list(results[0].keys())
            writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
            writer.writeheader()
            for row in results:
                writer.writerow(row)

# ==========================================
# 6. Main Entry Point
# ==========================================

if __name__ == "__main__":
    # Device file check
    if not Path("device.json").exists():
        logger.error("device.json not found. Please provide the device file.")
        sys.exit(1)

    config = SimulationConfig(
        n_qubits=10,
        depth=2,
        trials=5,
        shots=10000,
        max_cuts=2,
        cut_fidelity_threshold=0.96 # e5.pyのロジックで強制的にカットする閾値
    )
    
    runner = ExperimentRunner(config)
    try:
        final_results = runner.run()
        runner.write_results(final_results, output_format="csv")
    except Exception as e:
        logger.fatal(f"Execution failed: {e}", exc_info=True)
