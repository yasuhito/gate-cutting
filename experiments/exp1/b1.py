import logging
import random
import numpy as np
import matplotlib.pyplot as plt
from itertools import product
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass
from tqdm import tqdm

import stim
from qiskit import QuantumCircuit
from qiskit.circuit.library import HGate, SGate, XGate, YGate, ZGate, CXGate

# ==========================================
# 0. 設定とデータ構造
# ==========================================

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

@dataclass
class ErrorParams:
    one_qubit: Dict[int, float]
    two_qubit: Dict[Tuple[int, int], float]
    readout: Dict[int, float]

# ==========================================
# 1. Qiskit -> Stim 変換 (e5.py準拠)
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
            # e5.pyのロジック: CXの後にIを入れて融合を防ぐ（ノイズを正確に入れるため）
            stim_circ.append("I", qs)
        elif op == 'measure': 
            stim_circ.append("M", qs)
    return stim_circ

# ==========================================
# 2. ノイズ付与ロジック (e5.py準拠)
# ==========================================

IGNORE_OPS = {"TICK", "SHIFT_COORDS", "QUBIT_COORDS", "DETECTOR", "OBSERVABLE_INCLUDE", "I"}
MEASURE_OPS = {"M", "MR", "MX", "MY", "MZ"}

def append_operation_with_noise(
    circuit: stim.Circuit, 
    op_name: str, 
    targets: List[int], 
    error_params: ErrorParams
):
    # 測定エラー
    if op_name in MEASURE_OPS:
        for q in targets:
            p = error_params.readout.get(q, 0.0)
            if p > 0:
                circuit.append("X_ERROR", [q], p)
        circuit.append(op_name, targets)
        return

    # 無視する操作
    if op_name in IGNORE_OPS:
        circuit.append(op_name, targets)
        return

    # ゲート操作追加
    circuit.append(op_name, targets)

    # 脱分極エラー追加
    if len(targets) == 2:
        u, v = targets[0], targets[1]
        # (u, v) の順序で登録されている前提
        p_cx = error_params.two_qubit.get((u, v), 0.0)
        # 逆方向もチェック
        if p_cx == 0.0:
            p_cx = error_params.two_qubit.get((v, u), 0.0)
            
        if p_cx > 0 and op_name == "CX":
            circuit.append("DEPOLARIZE2", [u, v], p_cx)
            
    elif len(targets) == 1:
        u = targets[0]
        p_1q = error_params.one_qubit.get(u, 0.0)
        if p_1q > 0:
            circuit.append("DEPOLARIZE1", [u], p_1q)

def get_active_qubits(circuit: stim.Circuit) -> List[int]:
    active_qubits = set()
    for instruction in circuit:
        for t in instruction.targets_copy():
            if t.is_qubit_target:
                active_qubits.add(t.value)
    return sorted(list(active_qubits))

def calculate_expectation(samples: np.ndarray) -> float:
    # パリティ計測: 1の数が奇数なら-1, 偶数なら+1
    parities = np.sum(samples, axis=1) % 2
    eigenvalues = 1 - 2 * parities
    return np.mean(eigenvalues)

# ==========================================
# 3. Gate Cutting Simulator for Stim
# ==========================================

class GateCutStimSimulator:
    # Gate Cutting Decomposition for CX
    # 0.5 * (II + ZI + IX - ZX)
    # (Coeff, Op_Control, Op_Target)
    DECOMPOSITION = [
        (0.5,  'I', 'I'),
        (0.5,  'Z', 'I'),
        (0.5,  'I', 'X'),
        (-0.5, 'Z', 'X')
    ]

    @staticmethod
    def run_unmitigated(stim_circuit: stim.Circuit, error_params: ErrorParams, shots: int) -> float:
        """切断なし（通常のノイズあり実行）"""
        noisy_circuit = stim.Circuit()
        for instruction in stim_circuit:
            targets = [t.value for t in instruction.targets_copy() if t.is_qubit_target]
            append_operation_with_noise(noisy_circuit, instruction.name, targets, error_params)
        
        # 測定がない場合は追加
        if noisy_circuit.num_measurements == 0:
            active = get_active_qubits(noisy_circuit)
            noisy_circuit.append("M", active)
            
        sampler = noisy_circuit.compile_sampler()
        samples = sampler.sample(shots=shots)
        return calculate_expectation(samples)

    @staticmethod
    def run_mitigated(
        stim_circuit: stim.Circuit, 
        cut_indices: List[int], 
        error_params: ErrorParams, 
        shots: int
    ) -> float:
        """Gate Cuttingによるエラー緩和実行"""
        
        total_expectation = 0.0
        instructions = list(stim_circuit)
        
        # 4^k loop
        for combination in product(GateCutStimSimulator.DECOMPOSITION, repeat=len(cut_indices)):
            current_coeff = 1.0
            term_map = {}
            for c_idx, term in zip(cut_indices, combination):
                coeff, op_c, op_t = term
                current_coeff *= coeff
                term_map[c_idx] = (op_c, op_t)

            sub_circuit = stim.Circuit()
            
            for idx, instruction in enumerate(instructions):
                targets = [t.value for t in instruction.targets_copy() if t.is_qubit_target]
                
                if idx in cut_indices:
                    # CXゲートをローカルゲートに置換
                    op_c_name, op_t_name = term_map[idx]
                    
                    # Control Qubitへの操作
                    if op_c_name != 'I':
                        append_operation_with_noise(sub_circuit, op_c_name, [targets[0]], error_params)
                    
                    # Target Qubitへの操作
                    if op_t_name != 'I':
                        append_operation_with_noise(sub_circuit, op_t_name, [targets[1]], error_params)
                        
                    # 注意: ここでCXは追加しない（切断されているため）
                else:
                    # 通常の命令追加
                    append_operation_with_noise(sub_circuit, instruction.name, targets, error_params)

            if sub_circuit.num_measurements == 0:
                active = get_active_qubits(sub_circuit)
                sub_circuit.append("M", active)

            sampler = sub_circuit.compile_sampler()
            samples = sampler.sample(shots=shots)
            exp_val = calculate_expectation(samples)
            
            total_expectation += current_coeff * exp_val

        return total_expectation

# ==========================================
# 4. 回路生成とメインループ
# ==========================================

def random_clifford_circuit(num_qubits: int, depth: int) -> QuantumCircuit:
    """簡易版ランダムClifford回路"""
    qc = QuantumCircuit(num_qubits)
    for _ in range(depth):
        for i in range(num_qubits):
            if random.random() < 0.5:
                qc.h(i)
        for i in range(0, num_qubits - 1, 2):
            if random.random() < 0.5:
                qc.cx(i, i+1)
    return qc

def run_noise_sweep_benchmark():
    # 設定
    N_QUBITS = 10
    DEPTH = 4
    CUTS = 2             # 固定カット数（多すぎると遅くなるので注意。2 or 3推奨）
    TRIALS = 5           # 各ノイズポイントでの試行回路数
    SHOTS = 20000        # 各サブ回路のショット数
    
    # ノイズスイープ範囲 (CXエラー率: 0.1% 〜 10%)
    noise_levels = [0.001, 0.005, 0.01, 0.02, 0.04, 0.06, 0.08, 0.10]
    
    # 結果格納用
    avg_err_unmitigated = []
    avg_err_mitigated = []
    
    print(f"Running Noise Sweep (Stim): Qubits={N_QUBITS}, Cuts={CUTS}, Shots={SHOTS}")
    
    for noise_rate in tqdm(noise_levels):
        errs_unmit = []
        errs_mit = []
        
        # Noise Params 生成 (1Q/Readoutは小さく固定し、CXエラーをスイープ)
        # 簡易化のため全ペアに同じエラー率を設定
        two_q_errors = {}
        for i in range(N_QUBITS):
            for j in range(N_QUBITS):
                if i != j: two_q_errors[(i, j)] = noise_rate
        
        error_params = ErrorParams(
            one_qubit={i: noise_rate * 0.1 for i in range(N_QUBITS)}, # 1QはCXの1/10
            two_qubit=two_q_errors,
            readout={i: 0.005 for i in range(N_QUBITS)} # Readoutは0.5%固定
        )
        
        for _ in range(TRIALS):
            # 1. 回路生成
            qc = random_clifford_circuit(N_QUBITS, DEPTH)
            stim_circ = qiskit_to_stim(qc)
            
            # 2. 正解値計算 (ノイズなし)
            ideal_val = GateCutStimSimulator.run_unmitigated(
                stim_circ, 
                ErrorParams({}, {}, {}), # No Error
                shots=SHOTS
            )
            
            # 3. カット箇所の選定
            cx_indices = []
            for i, inst in enumerate(stim_circ):
                if inst.name == "CX":
                    cx_indices.append(i)
            
            if len(cx_indices) < CUTS:
                continue # CXが足りない場合はスキップ
                
            cut_indices = sorted(random.sample(cx_indices, CUTS))
            
            # 4. Unmitigated (そのまま実行)
            val_unmit = GateCutStimSimulator.run_unmitigated(stim_circ, error_params, SHOTS)
            errs_unmit.append(abs(ideal_val - val_unmit))
            
            # 5. Mitigated (Gate Cutting)
            val_mit = GateCutStimSimulator.run_mitigated(stim_circ, cut_indices, error_params, SHOTS)
            errs_mit.append(abs(ideal_val - val_mit))
            
        avg_err_unmitigated.append(np.mean(errs_unmit) if errs_unmit else 0)
        avg_err_mitigated.append(np.mean(errs_mit) if errs_mit else 0)

    return noise_levels, avg_err_unmitigated, avg_err_mitigated

# ==========================================
# 5. 可視化
# ==========================================

def plot_noise_sweep(noise_levels, err_unmit, err_mit):
    plt.figure(figsize=(9, 6))
    
    plt.plot(noise_levels, err_unmit, 'ko--', label='Unmitigated (Noisy)', linewidth=2, alpha=0.7)
    plt.plot(noise_levels, err_mit, 'bo-', label='Gate Cutting (Mitigated)', linewidth=3)
    
    plt.xlabel('2-Qubit Gate Error Rate', fontsize=12)
    plt.ylabel('Estimation Error |Ideal - Exp|', fontsize=12)
    plt.title('Error Mitigation Performance: Gate Cutting vs Unmitigated\n(Lower is Better)', fontsize=14)
    
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend(fontsize=12)
    
    # ログスケールにするかどうかは結果次第だが、両対数が見やすい場合が多い
    plt.xscale('log')
    plt.yscale('log')
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    x, y_unmit, y_mit = run_noise_sweep_benchmark()
    plot_noise_sweep(x, y_unmit, y_mit)