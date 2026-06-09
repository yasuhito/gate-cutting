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

import numpy as np

# Qiskit Imports
from qiskit import QuantumCircuit

# Stim Imports
import stim
from gate_cutting.circuits import CircuitGenerator
from gate_cutting.device import parse_device
from gate_cutting.gate_cutting import CutTarget, find_cx_cut_targets, run_gate_cut
from gate_cutting.mip import MIPCutFinder
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
# 2. Circuit Generator
# ==========================================
# Shared CircuitGenerator is imported from gate_cutting.circuits.

# ==========================================
# 3. MIP Solver
# ==========================================
# Shared MIPCutFinder is imported from gate_cutting.mip.

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
