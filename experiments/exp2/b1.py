import json
import logging
import random
import sys
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Any

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
from gate_cutting.cut_selection import collect_cx_edges, cut_targets_from_edges
from gate_cutting.device import parse_device
from gate_cutting.gate_cutting import CutTarget, find_cx_cut_targets, run_gate_cut
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
    max_cuts: int = 2
    cut_fidelity_threshold: float = 0.96 # これを下回ると強制カット
    optimization_level: int = 2

# ==========================================
# 1. Device Manager (a1.py base + e5.py adaptation)
# ==========================================

class DeviceManager:
    def __init__(self, json_path: str):
        self.json_path = Path(json_path)
        self.raw_data = self._load_json()
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

class MIPCutFinder:
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
        cx_edges = collect_cx_edges(circuit, self.dm.cx_fidelities)
        G.graph["cx_edges"] = cx_edges
        for edge in cx_edges:
            c_idx, t_idx = edge.qubits
            # Fidelityと元の命令位置を属性として保持
            G.add_edge(
                c_idx,
                t_idx,
                gate="cx",
                fidelity=edge.fidelity,
                instruction_index=edge.instruction_index,
                source_instruction_index=edge.source_instruction_index,
                edge_index=edge.edge_index,
            )
        return G

    def _cut_targets_from_edge_indices(self, G: nx.MultiDiGraph, edges, selected_edge_indices) -> List[CutTarget]:
        cx_edges = G.graph.get("cx_edges")
        if cx_edges is not None:
            return cut_targets_from_edges(cx_edges, selected_edge_indices=selected_edge_indices)

        cut_targets = []
        for edge_index in selected_edge_indices:
            u, v, _, attr = edges[edge_index]
            cut_targets.append(CutTarget(
                instruction_index=attr.get("instruction_index", edge_index),
                qubits=(u, v),
            ))
        return cut_targets

    def solve(self, G: nx.MultiDiGraph, max_cuts: int = 3, cut_fidelity_threshold: float = 0.96) -> List[CutTarget]:
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
            fallback_edge_indices = [
                edge[3].get('edge_index', k)
                for k, edge in enumerate(edges)
                if edge[3].get('fidelity', 1.0) < cut_fidelity_threshold
            ]
            return self._cut_targets_from_edge_indices(G, edges, fallback_edge_indices)

        selected_edge_indices = []
        for k in range(n_edges):
            if res.x[n_nodes + k] > 0.5:
                selected_edge_indices.append(edges[k][3].get('edge_index', k))
        return self._cut_targets_from_edge_indices(G, edges, selected_edge_indices)

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
    def run_cut(cls, original_stim: stim.Circuit, cut_pairs: List[Tuple[int, int]] | List[CutTarget], 
                error_params: ErrorParams, shots=10000) -> float:
        """Gate Cuttingシミュレーション (Stim版)"""
        if cut_pairs and isinstance(cut_pairs[0], CutTarget):
            cut_targets = list(cut_pairs)
        else:
            cut_targets = find_cx_cut_targets(original_stim, cut_pairs=cut_pairs)
        return run_gate_cut(original_stim, cut_targets, error_params, shots=shots)

# ==========================================
# 5. Experiment Runner
# ==========================================

class ExperimentRunner:
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.dm = DeviceManager(config.device_file)
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
