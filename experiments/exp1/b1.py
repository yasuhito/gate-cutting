import logging
import random
import sys
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import numpy as np
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import stim
from qiskit import QuantumCircuit
from qiskit.circuit.library import HGate, SGate, XGate, YGate, ZGate, CXGate

from gate_cutting.gate_cutting import CutTarget, run_gate_cut
from gate_cutting.stim_backend import (
    ErrorParams,
    qiskit_to_stim,
    run_standard as run_stim_standard,
)

# ==========================================
# 0. 設定
# ==========================================

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ==========================================
# 1. Gate Cutting Simulator for Stim
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
        return run_stim_standard(stim_circuit, shots=shots, error_params=error_params)

    @staticmethod
    def run_mitigated(
        stim_circuit: stim.Circuit, 
        cut_indices: List[int], 
        error_params: ErrorParams, 
        shots: int
    ) -> float:
        """Gate Cuttingによるエラー緩和実行"""
        instructions = list(stim_circuit)
        cut_targets = []
        for idx in cut_indices:
            instruction = instructions[idx]
            if instruction.name != "CX":
                raise ValueError(f"Cut index {idx} does not point to a CX instruction")
            targets = [t.value for t in instruction.targets_copy() if t.is_qubit_target]
            if len(targets) != 2:
                raise ValueError(f"Cut index {idx} does not point to a two-qubit CX instruction")
            cut_targets.append(CutTarget(instruction_index=idx, qubits=(targets[0], targets[1])))
        return run_gate_cut(stim_circuit, cut_targets, error_params, shots=shots)

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