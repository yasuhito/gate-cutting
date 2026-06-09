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

import matplotlib.pyplot as plt
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

# External Library (Optional)
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
    trials: int = 1    # 可視化のため1回で設定
    shots: int = 10000
    device_file: str = "device.json"
    max_cuts: int = 3
    cut_fidelity_threshold: float = 0.96 # これを下回ると強制カット
    optimization_level: int = 2

# ==========================================
# 1. Device Manager (from b2.py)
# ==========================================

class DeviceManager:
    def __init__(self, json_path: str = None):
        self.json_path = Path(json_path) if json_path else None
        if self.json_path and self.json_path.exists():
            self.raw_data = self._load_json()
        else:
            logger.info("Device file not found or not specified. Generating random device.")
            self.raw_data = self.generate_qubit_json_corrected()
            
        self.cx_fidelities = {}
        self.one_q_fidelities = {}
        self.qubit_coords = {}
        self.error_params = self._parse_device_data()
        
    def _load_json(self) -> Dict[str, Any]:
        return json.loads(self.json_path.read_text(encoding="utf-8"))

    def _parse_device_data(self) -> ErrorParams:
        parsed = parse_device(self.raw_data)
        self.cx_fidelities = parsed.cx_fidelities
        self.one_q_fidelities = parsed.one_q_fidelities
        self.qubit_coords = parsed.qubit_coords
        return parsed.error_params

    def generate_qubit_json_corrected(self, width: int = 4, height: int = 4) -> dict:
        """デバイスデータがない場合のランダム生成ロジック"""
        def get_qubit_id(x, y):
            block_x = x // 2; block_y = y // 2
            local_x = x % 2; local_y = y % 2
            blocks_per_row = width // 2
            block_start_id = (block_y * blocks_per_row + block_x) * 4
            offset = local_y * 2 + local_x
            return block_start_id + offset

        def get_random_fidelity():
            # 稀に悪い量子ビットを生成
            if random.random() < 0.01: return round(random.uniform(0.50, 0.70), 4)
            return round(min(random.uniform(0.998, 1.0), 1.0), 4)

        qubits_data = []
        for y in range(height):
            for x in range(width):
                q_id = get_qubit_id(x, y)
                qubits_data.append({
                    "id": q_id,
                    "position": {"x": x, "y": y},
                    "fidelity": get_random_fidelity(),
                    "meas_error": {"readout_assignment_error": 0.01}
                })
        qubits_data.sort(key=lambda q: q["id"])

        couplings_data = []
        # Horizontal & Vertical couplings
        for y in range(height):
            for x in range(width - 1):
                src, dst = get_qubit_id(x, y), get_qubit_id(x + 1, y)
                couplings_data.append({"control": src, "target": dst, "fidelity": 0.99})
                couplings_data.append({"control": dst, "target": src, "fidelity": 0.99})
        for x in range(width):
            for y in range(height - 1):
                src, dst = get_qubit_id(x, y), get_qubit_id(x, y + 1)
                couplings_data.append({"control": src, "target": dst, "fidelity": 0.99})
                couplings_data.append({"control": dst, "target": src, "fidelity": 0.99})

        # 一部ランダムにFidelityを下げる（切断テスト用）
        if couplings_data:
             bad_idx = random.randint(0, len(couplings_data)-1)
             couplings_data[bad_idx]["fidelity"] = 0.85
             print(f"DEBUG: Injecting bad edge at {couplings_data[bad_idx]}")

        return {"qubits": qubits_data, "couplings": couplings_data}


# ==========================================
# 2. Circuit Generator (from b2.py)
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
# 3. MIP Solver (from b2.py)
# ==========================================

class MIPCutFinder:
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
        n_vars = n_nodes + n_edges 
        
        c = np.zeros(n_vars)
        lower_bounds = np.zeros(n_vars)
        upper_bounds = np.ones(n_vars)
        
        # 悪いエッジを特定
        bad_edges = []
        for k in range(n_edges):
            _, _, _, attr = edges[k]
            fid = attr.get('fidelity', 1.0)
            if fid < cut_fidelity_threshold:
                bad_edges.append((k, fid))
        
        bad_edges.sort(key=lambda x: x[1])
        
        force_cut_indices = set()
        if len(bad_edges) > max_cuts:
            logger.warning(f"Low fidelity edges ({len(bad_edges)}) exceed max_cuts ({max_cuts}). Enforcing strictly worst {max_cuts} cuts.")
            force_cut_indices = {k for k, _ in bad_edges[:max_cuts]}
        else:
            force_cut_indices = {k for k, _ in bad_edges}

        for k in range(n_edges):
            fid = edges[k][3].get('fidelity', 1.0)
            z_idx = n_nodes + k
            
            if k in force_cut_indices:
                c[z_idx] = 0.0 
                lower_bounds[z_idx] = 1.0 
            else:
                error_rate = max(1.0 - fid, 1e-9)
                weight = fid / error_rate
                c[z_idx] = weight

        # 制約
        rows, cols, vals = [], [], []
        b_l, b_u = [], []
        constraint_idx = 0
        
        # 1. 切断の論理制約
        for k in range(n_edges):
            u, v, _, _ = edges[k]
            u_idx = node_to_idx[u]; v_idx = node_to_idx[v]; z_idx = n_nodes + k
            rows.extend([constraint_idx]*3); cols.extend([u_idx, v_idx, z_idx]); vals.extend([-1, 1, 1])
            b_l.append(0); b_u.append(np.inf); constraint_idx += 1
            rows.extend([constraint_idx]*3); cols.extend([u_idx, v_idx, z_idx]); vals.extend([1, -1, 1])
            b_l.append(0); b_u.append(np.inf); constraint_idx += 1

        # 2. カット数上限
        for k in range(n_edges):
            z_idx = n_nodes + k
            rows.append(constraint_idx); cols.append(z_idx); vals.append(1)
        b_l.append(0); b_u.append(max_cuts); constraint_idx += 1

        # 3. バランス制約 (緩和)
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
            logger.warning("MIP Solver failed. Fallback to greedy bad edge cut.")
            fallback_edge_indices = [
                edge[3].get('edge_index', k)
                for k, edge in enumerate(edges)
                if edge[3].get('fidelity', 1.0) < cut_fidelity_threshold
            ][:max_cuts]
            return self._cut_targets_from_edge_indices(G, edges, fallback_edge_indices)

        selected_edge_indices = []
        for k in range(n_edges):
            if res.x[n_nodes + k] > 0.5:
                selected_edge_indices.append(edges[k][3].get('edge_index', k))
                
        return self._cut_targets_from_edge_indices(G, edges, selected_edge_indices)

# ==========================================
# 4. Stim Simulator (from b2.py)
# ==========================================

class StimGateCutSimulator:
    DECOMPOSITION = [
        (0.5,  'I', 'I'), (0.5,  'Z', 'I'),
        (0.5,  'I', 'X'), (-0.5, 'Z', 'X')
    ]

    @staticmethod
    def qiskit_to_stim(qc: QuantumCircuit) -> stim.Circuit:
        return convert_qiskit_to_stim(qc)

    @staticmethod
    def _append_op_with_noise(circuit, op_name, targets, error_params):
        append_stim_operation_with_noise(circuit, op_name, targets, error_params)

    @staticmethod
    def get_expectation(samples: np.ndarray) -> float:
        return stim_parity_expectation(samples)

    @classmethod
    def run_standard(cls, circuit: stim.Circuit, error_params: ErrorParams = None, shots=10000) -> float:
        return run_stim_standard(circuit, shots=shots, error_params=error_params)

    @classmethod
    def run_cut(cls, original_stim: stim.Circuit, cut_pairs: List[Tuple[int, int]] | List[CutTarget], 
                error_params: ErrorParams, shots=10000) -> float:
        if cut_pairs and isinstance(cut_pairs[0], CutTarget):
            cut_targets = list(cut_pairs)
        else:
            cut_targets = find_cx_cut_targets(original_stim, cut_pairs=cut_pairs)
        return run_gate_cut(original_stim, cut_targets, error_params, shots=shots)

# ==========================================
# 5. Visualization (from e5.py)
# ==========================================

def plot_result(raw_data, qubit_coords, one_q_fidelities, G_circuit, cut_pairs):
    """
    デバイスの結合マップ上に、使用された回路とカットされた箇所を描画する
    """
    print("\n--- Visualizing Graph ---")
    fig, ax = plt.subplots(figsize=(10, 10))

    # 1. デバイス全体のグラフ
    G_device = nx.DiGraph()
    device_pos = {}
    node_labels = {}
    edge_labels = {}
    node_fidelities = {}

    # ノード
    if 'qubits' in raw_data:
        for q in raw_data['qubits']:
            qid = int(q['id'])
            device_pos[qid] = qubit_coords.get(qid, (qid, 0))
            fid = one_q_fidelities.get(qid, 0.0)
            G_device.add_node(qid, fidelity=fid)
            node_fidelities[qid] = fid
            node_labels[qid] = f"{qid}\n{fid:.4f}"

    # エッジ（デバイス結合）
    if 'couplings' in raw_data:
        for c in raw_data['couplings']:
            u, v = int(c['control']), int(c['target'])
            fid = float(c['fidelity'])
            G_device.add_edge(u, v)
            edge_labels[(u, v)] = f"{fid:.4f}"

    # 2. 回路で使用されたエッジとカット箇所
    used_edges_set = set()
    # G_circuitはMultiDiGraphなのでkeys=Trueで回すが、u,vだけ必要
    for u, v, _ in G_circuit.edges(keys=True):
        used_edges_set.add((u, v))
    
    cut_edges_set = {
        cut.qubits if isinstance(cut, CutTarget) else tuple(cut)
        for cut in cut_pairs
    }
    
    normal_edges_to_draw = []
    cut_edges_to_draw = []

    for u, v in used_edges_set:
        if G_device.has_edge(u, v):
            if (u, v) in cut_edges_set:
                cut_edges_to_draw.append((u, v))
            else:
                normal_edges_to_draw.append((u, v))

    # 3. 描画
    node_size = 1500
    
    # ノード色（Fidelityベース）
    if node_fidelities:
        fidelity_values = list(node_fidelities.values())
        vmin, vmax = min(fidelity_values), max(fidelity_values)
        sm = plt.cm.ScalarMappable(cmap="viridis", norm=plt.Normalize(vmin=vmin, vmax=vmax))
        node_colors = [sm.to_rgba(f) for f in fidelity_values]
        nx.draw_networkx_nodes(G_device, device_pos, node_size=node_size, node_color=node_colors, edgecolors='black', ax=ax)
        cbar = plt.colorbar(sm, ax=ax, label="Qubit Fidelity", fraction=0.046, pad=0.04)
    else:
        nx.draw_networkx_nodes(G_device, device_pos, node_size=node_size, node_color='lightgreen', edgecolors='black', ax=ax)

    nx.draw_networkx_labels(G_device, device_pos, labels=node_labels, font_size=9, font_weight='bold', ax=ax)

    # 全エッジ（背景・グレー）
    nx.draw_networkx_edges(G_device, device_pos, node_size=node_size, arrowstyle='-|>', arrowsize=15, 
                           edge_color='dimgray', width=1.0, connectionstyle='arc3,rad=0', ax=ax)

    # 使用エッジ（青）
    if normal_edges_to_draw:
        nx.draw_networkx_edges(G_device, device_pos, edgelist=normal_edges_to_draw, node_size=node_size, 
                               arrowstyle='-|>', arrowsize=20, edge_color='blue', width=2.5, connectionstyle='arc3,rad=0', ax=ax)

    # カットエッジ（赤・破線）
    if cut_edges_to_draw:
        nx.draw_networkx_edges(G_device, device_pos, edgelist=cut_edges_to_draw, node_size=node_size, 
                               arrowstyle='-|>', arrowsize=20, edge_color='red', width=3.5, style='dashed', connectionstyle='arc3,rad=0', ax=ax)

    # エッジラベル
    nx.draw_networkx_edge_labels(G_device, device_pos, edge_labels=edge_labels, font_color='darkblue', font_size=8, label_pos=0.6, ax=ax)

    ax.set_title(f"Circuit Cutting Result\nRed Dashed = Cut Gates (MIP Selected)", fontsize=14, fontweight="bold")
    ax.axis('off')
    ax.invert_yaxis()
    plt.tight_layout()
    plt.show()

# ==========================================
# 6. Experiment Runner (Integration)
# ==========================================

class ExperimentRunner:
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.dm = DeviceManager(config.device_file)
        self.mip_solver = MIPCutFinder(self.dm)
        self.noise_params = self.dm.error_params
        self.tranqu = Tranqu() if Tranqu else None

    def run(self):
        results = []
        logger.info(f"Starting Evaluation with config: {self.config}")

        qc = QuantumCircuit(self.config.n_qubits)
        qc.h(0)
        for i in range(self.config.n_qubits - 1):
            qc.cx(i, i + 1)

        for i in range(self.config.trials):
            # 1. Circuit Generation
            #qc = CircuitGenerator.random_clifford(self.config.n_qubits, self.config.depth)

            # 2. Transpilation
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
                    logger.info("Transpilation successful using Tranqu/Qiskit.")
                except Exception as e:
                    logger.warning(f"Transpilation failed: {e}. Using raw circuit (might not map to device topology).")
                    transpiled_qc = qc
            else:
                logger.warning("Tranqu not found. Using raw circuit.")
                transpiled_qc = qc

            # 3. MIP Cut Finding
            G_circuit = self.mip_solver.build_graph(transpiled_qc)
            cut_pairs = self.mip_solver.solve(
                G_circuit, 
                max_cuts=self.config.max_cuts, 
                cut_fidelity_threshold=self.config.cut_fidelity_threshold
            )
            
            logger.info(f"Trial {i+1}: Cuts found: {cut_pairs}")

            # # 4. Visualization (e5.py integration)
            # plot_result(self.dm.raw_data, self.dm.qubit_coords, self.dm.one_q_fidelities, G_circuit, cut_pairs)

            # 5. Simulation
            stim_qc = StimGateCutSimulator.qiskit_to_stim(transpiled_qc)
            val_ideal = StimGateCutSimulator.run_standard(stim_qc, error_params=None, shots=self.config.shots)
            val_noisy = StimGateCutSimulator.run_standard(stim_qc, error_params=self.noise_params, shots=self.config.shots)
            
            val_cut_noisy = 0.0
            if cut_pairs:
                val_cut_noisy = StimGateCutSimulator.run_cut(
                    stim_qc, cut_pairs, error_params=self.noise_params, shots=self.config.shots
                )
            else:
                val_cut_noisy = val_noisy

            print(f"Trial {i+1} Result:")
            print(f"  Ideal: {val_ideal:.4f}")
            print(f"  Noisy: {val_noisy:.4f}")
            print(f"  Cut+Noisy: {val_cut_noisy:.4f}")
            
            # 4. Visualization (e5.py integration)
            plot_result(self.dm.raw_data, self.dm.qubit_coords, self.dm.one_q_fidelities, G_circuit, cut_pairs)

            results.append({'trial': i+1, 'cuts': len(cut_pairs), 'ideal': val_ideal, 'noisy': val_noisy, 'cut_noisy': val_cut_noisy})

        return results

# ==========================================
# 7. Main Entry Point
# ==========================================

if __name__ == "__main__":
    # 設定: 低いFidelityの閾値を設定して、強制カットが発生しやすいようにする
    config = SimulationConfig(
        n_qubits=11,
        depth=3,
        trials=1,
        shots=10000,
        max_cuts=2,
        cut_fidelity_threshold=0.96 
    )
    
    runner = ExperimentRunner(config)
    runner.run()
