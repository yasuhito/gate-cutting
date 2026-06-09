import logging
import random
import numpy as np
import matplotlib.pyplot as plt
from itertools import product, combinations
from typing import List, Tuple, Dict, Any
from tqdm import tqdm

# Qiskit Imports
from qiskit import QuantumCircuit, ClassicalRegister
from qiskit.circuit.library import HGate, SGate, XGate, YGate, ZGate, CXGate, TGate, RXGate, RYGate
from qiskit_aer import AerSimulator

# Logging setup
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ==========================================
# 1. Universal Circuit Generator
# ==========================================

class UniversalCircuitGenerator:
    """Clifford + T + Rotation を含むランダム回路生成"""
    
    # Non-Cliffordを含むゲートセット
    SINGLE_QUBIT_GATES = [
        ("h", HGate()), ("s", SGate()), ("t", TGate()), 
        ("x", XGate()), ("y", YGate()), ("z", ZGate()),
        ("rx", lambda: RXGate(random.uniform(0, 2*np.pi))),
        ("ry", lambda: RYGate(random.uniform(0, 2*np.pi)))
    ]

    @staticmethod
    def generate(num_qubits: int, depth: int, seed: int = None) -> QuantumCircuit:
        rng = random.Random(seed)
        qc = QuantumCircuit(num_qubits)
        qubits = list(range(num_qubits))

        for _ in range(depth):
            # 1. Single Qubit Gates
            for q in qubits:
                if rng.random() < 0.7:
                    name, gate_obj = rng.choice(UniversalCircuitGenerator.SINGLE_QUBIT_GATES)
                    # パラメータ付きゲート(RX, RY)の処理
                    if callable(gate_obj):
                        qc.append(gate_obj(), [q])
                    else:
                        qc.append(gate_obj, [q])

            # 2. CX Gates (Entanglement)
            rng.shuffle(qubits)
            for i in range(0, len(qubits)-1, 2):
                if rng.random() < 0.8:
                    qc.append(CXGate(), [qubits[i], qubits[i+1]])

        return qc

# ==========================================
# 2. Simulators (Gate Cut & Wire Cut)
# ==========================================

class BaseSimulator:
    @staticmethod
    def get_expectation(counts: Dict[str, int]) -> float:
        """<ZZ...Z> 期待値計算"""
        total_shots = sum(counts.values())
        if total_shots == 0: return 0.0
        sum_val = 0
        for bitstring, count in counts.items():
            # スペース除去
            clean = bitstring.replace(" ", "")
            # パリティ計算 (1の数が奇数なら -1, 偶数なら +1)
            parity = clean.count('1') % 2
            sum_val += (1 if parity == 0 else -1) * count
        return sum_val / total_shots

class GateCutSimulator(BaseSimulator):
    DECOMPOSITION = [
        (0.5,  'I', 'I'), (0.5,  'Z', 'I'),
        (0.5,  'I', 'X'), (-0.5, 'Z', 'X')
    ]

    @staticmethod
    def run(original_circuit: QuantumCircuit, cut_indices: List[int], shots: int) -> float:
        backend = AerSimulator(max_parallel_threads=1)
        total_expectation = 0.0
        
        # 4^k loop
        for combination in product(GateCutSimulator.DECOMPOSITION, repeat=len(cut_indices)):
            current_coeff = 1.0
            term_map = {}
            for idx_in_list, term in zip(cut_indices, combination):
                coeff, op_c, op_t = term
                current_coeff *= coeff
                term_map[idx_in_list] = (op_c, op_t)
            
            # Reconstruct
            qs = original_circuit.qubits
            if original_circuit.clbits:
                sub_circuit = QuantumCircuit(qs, *original_circuit.cregs)
            else:
                sub_circuit = QuantumCircuit(qs)
                
            for i, instruction in enumerate(original_circuit.data):
                if i in cut_indices:
                    op_c, op_t = term_map[i]
                    # Apply Local Ops
                    for q, op in [(instruction.qubits[0], op_c), (instruction.qubits[1], op_t)]:
                        if op == 'X': sub_circuit.x(q)
                        elif op == 'Z': sub_circuit.z(q)
                else:
                    sub_circuit.append(instruction)

            if not any(inst.operation.name == 'measure' for inst in sub_circuit.data):
                sub_circuit.measure_all()
            
            # Run
            result = backend.run(sub_circuit, shots=shots).result()
            term_exp = BaseSimulator.get_expectation(result.get_counts())
            total_expectation += current_coeff * term_exp

        return total_expectation

class WireCutSimulator(BaseSimulator):
    # Wire Cutting Decomposition: 8 terms
    DECOMPOSITION = [
        (0.5,  'M_Z', 'P_0'), (-0.5, 'M_Z', 'P_1'),
        (0.5,  'M_X', 'P_X+'), (-0.5, 'M_X', 'P_X-'),
        (0.5,  'M_Y', 'P_Y+'), (-0.5, 'M_Y', 'P_Y-'),
        (0.5,  'M_I', 'P_0'), (0.5,  'M_I', 'P_1')
    ]

    @staticmethod
    def _append_cut_ops(qc, op_code, qubit, creg, c_idx):
        # Measure
        if op_code == 'M_Z': qc.measure(qubit, creg[c_idx])
        elif op_code == 'M_X': qc.h(qubit); qc.measure(qubit, creg[c_idx])
        elif op_code == 'M_Y': qc.sdg(qubit); qc.h(qubit); qc.measure(qubit, creg[c_idx])
        elif op_code == 'M_I': qc.reset(qubit); qc.measure(qubit, creg[c_idx]) # Identity emulation
        # Prepare
        if op_code == 'P_0': qc.reset(qubit)
        elif op_code == 'P_1': qc.reset(qubit); qc.x(qubit)
        elif op_code == 'P_X+': qc.reset(qubit); qc.h(qubit)
        elif op_code == 'P_X-': qc.reset(qubit); qc.x(qubit); qc.h(qubit)
        elif op_code == 'P_Y+': qc.reset(qubit); qc.h(qubit); qc.s(qubit)
        elif op_code == 'P_Y-': qc.reset(qubit); qc.h(qubit); qc.sdg(qubit)

    @staticmethod
    def run(original_circuit: QuantumCircuit, cut_indices: List[int], shots: int) -> float:
        backend = AerSimulator(max_parallel_threads=1)
        total_expectation = 0.0
        
        # 8^k loop
        for combination in product(WireCutSimulator.DECOMPOSITION, repeat=len(cut_indices)):
            current_coeff = 1.0
            term_map = {}
            for idx_in_list, term in zip(cut_indices, combination):
                coeff, op_measure, op_prepare = term
                current_coeff *= coeff
                term_map[idx_in_list] = (op_measure, op_prepare)
            
            qs = original_circuit.qubits
            cr_cut = ClassicalRegister(len(cut_indices), name="cut_meas")
            cr_final = ClassicalRegister(len(qs), name="final_meas")
            sub_circuit = QuantumCircuit(qs, cr_final, cr_cut)

            cut_counter = 0
            for i, instruction in enumerate(original_circuit.data):
                if i in cut_indices:
                    q_ctrl = instruction.qubits[0]
                    op_meas, op_prep = term_map[i]
                    WireCutSimulator._append_cut_ops(sub_circuit, op_meas, q_ctrl, cr_cut, cut_counter)
                    WireCutSimulator._append_cut_ops(sub_circuit, op_prep, q_ctrl, cr_cut, cut_counter)
                    cut_counter += 1
                else:
                    sub_circuit.append(instruction)

            sub_circuit.measure(qs, cr_final)
            
            result = backend.run(sub_circuit, shots=shots).result()
            counts = result.get_counts()
            
            term_exp = 0.0
            total_counts_term = 0
            n_qubits = len(qs)

            for bitstring, count in counts.items():
                clean_bits = bitstring.replace(" ", "")
                # Qiskit order: [cut_part][final_part] or vice versa depending on reg order.
                # Here we added cr_final then cr_cut, so cr_cut is MSB (left), cr_final is LSB (right)
                # clean_bits = cut...cut final...final
                final_part = clean_bits[-n_qubits:]
                cut_part = clean_bits[:-n_qubits]

                val_final = 1 if (final_part.count('1') % 2 == 0) else -1
                
                # Sign flip based on cut measurement
                # M_I never flips (it measures 0 post-reset). Others flip if 1.
                sign_cut = 1 if (cut_part.count('1') % 2 == 0) else -1
                
                term_exp += (sign_cut * val_final) * count
                total_counts_term += count
            
            if total_counts_term > 0:
                term_exp /= total_counts_term
                total_expectation += current_coeff * term_exp
                
        return total_expectation

# ==========================================
# 3. Experiment Runner
# ==========================================

def run_benchmark(n_qubits=10, depth=4, max_cuts=3, trials=5, shots_per_circ=1024):
    
    cut_counts = list(range(max_cuts + 1))
    
    # Storage for results
    # {num_cuts: [errors_gate, errors_wire]}
    data_gate_error = {k: [] for k in cut_counts}
    data_wire_error = {k: [] for k in cut_counts}
    
    # Theoretical overhead (gamma^2)
    # Gate Cut: gamma = 2 per cut -> gamma^2 = 4 per cut
    # Wire Cut: gamma = 4 per cut -> gamma^2 = 16 per cut
    overhead_gate = [4**k for k in cut_counts]
    overhead_wire = [16**k for k in cut_counts]

    print(f"Running Benchmark: Qubits={n_qubits}, Depth={depth}, Trials={trials}, MaxCuts={max_cuts}")

    for _ in tqdm(range(trials)):
        # 1. Generate Circuit
        qc = UniversalCircuitGenerator.generate(n_qubits, depth)
        
        # Calculate Ideal Value (Statevector)
        qc_ideal = qc.copy()
        qc_ideal.measure_all()
        # Use statevector for exact reference
        backend_sv = AerSimulator(method='statevector', max_parallel_threads=1)
        result_ideal = backend_sv.run(qc_ideal).result()
        exact_val = BaseSimulator.get_expectation(result_ideal.get_counts())

        # Identify all CX gates
        cx_indices = [i for i, inst in enumerate(qc.data) if inst.operation.name == 'cx']
        
        if len(cx_indices) < max_cuts:
            # Skip if not enough CX gates to cut
            continue

        for k in cut_counts:
            if k == 0:
                # No cut: standard run with finite shots
                val_gate = GateCutSimulator.run(qc, [], shots_per_circ)
                val_wire = val_gate # same for 0 cuts
                data_gate_error[k].append(abs(exact_val - val_gate))
                data_wire_error[k].append(abs(exact_val - val_wire))
                continue

            # Randomly select k gates to cut
            target_indices = sorted(random.sample(cx_indices, k))

            # Run Gate Cut
            val_gate = GateCutSimulator.run(qc, target_indices, shots_per_circ)
            data_gate_error[k].append(abs(exact_val - val_gate))

            # Run Wire Cut
            val_wire = WireCutSimulator.run(qc, target_indices, shots_per_circ)
            data_wire_error[k].append(abs(exact_val - val_wire))

    return cut_counts, data_gate_error, data_wire_error, overhead_gate, overhead_wire

# ==========================================
# 4. Visualization
# ==========================================

def plot_results(cut_counts, gate_err, wire_err, ov_gate, ov_wire):
    # Average errors
    avg_gate_err = [np.mean(gate_err[k]) if gate_err[k] else 0 for k in cut_counts]
    avg_wire_err = [np.mean(wire_err[k]) if wire_err[k] else 0 for k in cut_counts]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Plot 1: Reconstruction Error
    ax1.plot(cut_counts, avg_gate_err, 'o-', label='Gate Cutting', linewidth=2, markersize=8)
    ax1.plot(cut_counts, avg_wire_err, 's-', label='Wire Cutting', linewidth=2, markersize=8)
    ax1.set_title('Reconstruction Error vs Number of Cuts\n(Lower is Better)', fontsize=14)
    ax1.set_xlabel('Number of Cuts', fontsize=12)
    ax1.set_ylabel('Absolute Error |Ideal - Cut|', fontsize=12)
    ax1.set_xticks(cut_counts)
    ax1.grid(True, linestyle='--', alpha=0.7)
    ax1.legend(fontsize=12)
    
    # Note for Plot 1
    ax1.text(0.05, 0.95, "Fixed Shots per Sub-circuit", transform=ax1.transAxes, 
             fontsize=10, verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.5))

    # Plot 2: Sampling Overhead (Theoretical)
    ax2.plot(cut_counts, ov_gate, 'o--', label='Gate Cutting ($4^k$)', color='tab:blue')
    ax2.plot(cut_counts, ov_wire, 's--', label='Wire Cutting ($16^k$)', color='tab:orange')
    ax2.set_yscale('log')
    ax2.set_title('Sampling Overhead (Variance Factor $\gamma^2$)\n(Lower is Better)', fontsize=14)
    ax2.set_xlabel('Number of Cuts', fontsize=12)
    ax2.set_ylabel('Overhead Factor (Log Scale)', fontsize=12)
    ax2.set_xticks(cut_counts)
    ax2.grid(True, linestyle='--', alpha=0.7)
    ax2.legend(fontsize=12)

    plt.tight_layout()
    #plt.show()
    plt.savefig('benchmark_phase1.png')
    plt.close()

def run_shot_scaling_benchmark(n_qubits=10, depth=4, fixed_cuts=2, trials=5):
    """
    カット数を固定し、ショット数を増やしていったときの精度の変化を見る
    """
    # ショット数のリスト (対数スケールで増やす)
    shot_scales = [100, 500, 1000, 5000, 10000, 50000]
    
    avg_gate_errors = []
    avg_wire_errors = []

    print(f"\n--- Running Shot Scaling Benchmark (Fixed Cuts={fixed_cuts}) ---")

    # 共通の回路セットを先に生成しておく（ショット数条件だけ変えて同じ回路を回すため）
    test_circuits = []
    for _ in range(trials):
        qc = UniversalCircuitGenerator.generate(n_qubits, depth)
        cx_indices = [i for i, inst in enumerate(qc.data) if inst.operation.name == 'cx']
        if len(cx_indices) >= fixed_cuts:
            # ランダムにカット箇所を固定
            cut_indices = sorted(random.sample(cx_indices, fixed_cuts))
            
            # 正解値計算
            qc_ideal = qc.copy()
            qc_ideal.measure_all()
            backend_sv = AerSimulator(method='statevector')
            res = backend_sv.run(qc_ideal).result()
            exact = BaseSimulator.get_expectation(res.get_counts())
            
            test_circuits.append((qc, cut_indices, exact))

    # ショット数ごとに評価
    for shots in shot_scales:
        print(f"Testing shots = {shots} ...")
        g_errs = []
        w_errs = []
        
        for qc, cuts, exact in test_circuits:
            # Gate Cut
            val_g = GateCutSimulator.run(qc, cuts, shots)
            g_errs.append(abs(exact - val_g))
            
            # Wire Cut
            val_w = WireCutSimulator.run(qc, cuts, shots)
            w_errs.append(abs(exact - val_w))
            
        avg_gate_errors.append(np.mean(g_errs))
        avg_wire_errors.append(np.mean(w_errs))

    return shot_scales, avg_gate_errors, avg_wire_errors

def plot_shot_scaling(shots, g_err, w_err, fixed_cuts):
    plt.figure(figsize=(8, 6))
    plt.plot(shots, g_err, 'o-', label=f'Gate Cutting', linewidth=2)
    plt.plot(shots, w_err, 's-', label=f'Wire Cutting', linewidth=2)
    
    plt.xscale('log')
    plt.yscale('log')
    
    plt.title(f'Convergence Rate (Fixed Cuts = {fixed_cuts})\n(Lower is Better)', fontsize=14)
    plt.xlabel('Shots per Sub-circuit (Log Scale)', fontsize=12)
    plt.ylabel('Reconstruction Error (Log Scale)', fontsize=12)
    plt.grid(True, which="both", ls="--", alpha=0.7)
    plt.legend(fontsize=12)
    plt.tight_layout()
    plt.show()

# ==========================================
# Main Execution
# ==========================================

if __name__ == "__main__":
    # Settings for quick demo
    N_QUBITS = 8
    DEPTH = 4
    MAX_CUTS = 3   # Warning: Wire Cut with 4 cuts = 8^4 = 4096 circuits. Keep small for demo.
    #TRIALS = 10     # Number of random circuits to average
    TRIALS = 100
    SHOTS = 2000   # Shots per sub-circuit

    cuts, d_gate, d_wire, o_gate, o_wire = run_benchmark(N_QUBITS, DEPTH, MAX_CUTS, TRIALS, SHOTS)
    plot_results(cuts, d_gate, d_wire, o_gate, o_wire)

    # # ★追加: ショット数依存性の確認
    # # カット数は「2」または「3」あたりが差が出やすくておすすめです
    # shots, g_err, w_err = run_shot_scaling_benchmark(n_qubits=10, depth=4, fixed_cuts=2, trials=10)
    # plot_shot_scaling(shots, g_err, w_err, fixed_cuts=2)
