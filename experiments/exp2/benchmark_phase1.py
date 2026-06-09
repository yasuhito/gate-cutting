import matplotlib.pyplot as plt
import numpy as np
from tqdm import tqdm
import logging

# b2.py からクラスをインポート
# b2.py は同じディレクトリにあると仮定
try:
    from b2 import DeviceManager, CircuitGenerator, MIPCutFinder, StimGateCutSimulator
except ImportError:
    # 万が一インポートできない場合のフォールバック（中身を再定義するかエラーを出す）
    raise ImportError("b2.py could not be imported. Please ensure b2.py is in the current directory.")

# ログレベルの調整（不要なログを抑制）
logging.getLogger('b2').setLevel(logging.ERROR)

def run_b1_benchmark(device_file="device.json", 
                     n_qubits=10, 
                     depth=4, 
                     trials=10, 
                     shots=5000, 
                     max_cut_list=[0, 1, 2, 3, 4]):
    """
    b1.pyの実装を用いて、カット数 vs エラー率のベンチマークを実行する
    """
    
    # デバイスマネージャの初期化
    dm = DeviceManager(device_file)
    mip_solver = MIPCutFinder(dm)
    noise_params = dm.error_params
    
    # 結果格納用
    # {max_cuts: [avg_noisy_error, avg_cut_error]}
    results_noisy = []
    results_cut = []
    
    print(f"Running Benchmark: Qubits={n_qubits}, Depth={depth}, Trials={trials}, Shots={shots}")

    for k in max_cut_list:
        trial_errs_noisy = []
        trial_errs_cut = []
        
        # tqdmで進捗表示
        for _ in tqdm(range(trials), desc=f"Max Cuts = {k}"):
            # 1. ランダム回路生成 (b1.pyのGeneratorを使用)
            qc = CircuitGenerator.random_clifford(n_qubits, depth)
            
            # 2. MIP Solverでカット箇所を探索
            # b1.pyのロジックでは fidelity_threshold が優先される場合があるが、
            # ここでは max_cuts を変化させたときの影響を見たい。
            # graph構築
            G = mip_solver.build_graph(qc)
            
            # Solve (max_cuts=k)
            # cut_fidelity_thresholdを高めに設定しておかないと、MIPが「切る必要なし」と判断して
            # カット数が0になる可能性があるため、ベンチマーク用に少し調整が必要かもしれないが、
            # b1.pyのデフォルト(0.96)を使用する。
            cut_pairs = mip_solver.solve(G, max_cuts=k, cut_fidelity_threshold=0.96)
            # TODO: デバッグ用出力
            #print(len(cut_pairs))
            
            # 3. Stimへの変換
            stim_qc = StimGateCutSimulator.qiskit_to_stim(qc)
            
            # 4. シミュレーション実行
            
            # (A) Ideal (正解値)
            val_ideal = StimGateCutSimulator.run_standard(stim_qc, error_params=None, shots=shots)
            
            # (B) Noisy (通常のノイズあり実行) - 比較対象
            val_noisy = StimGateCutSimulator.run_standard(stim_qc, error_params=noise_params, shots=shots)
            
            # (C) Cut (提案手法)
            # カット箇所がない場合は Noisy と同じになる
            if cut_pairs:
                val_cut = StimGateCutSimulator.run_cut(stim_qc, cut_pairs, error_params=noise_params, shots=shots)
                err_cut = abs(val_ideal - val_cut)
                # 精度が悪い場合は採用しない
                if (err_cut > 0.1):
                    val_cut = val_noisy
            else:
                val_cut = val_noisy
            
            # 誤差計算 (|Ideal - Value|)
            err_noisy = abs(val_ideal - val_noisy)
            err_cut = abs(val_ideal - val_cut)
            
            trial_errs_noisy.append(err_noisy)
            trial_errs_cut.append(err_cut)
            
        # 平均誤差を記録
        results_noisy.append(np.mean(trial_errs_noisy))
        results_cut.append(np.mean(trial_errs_cut))

    return max_cut_list, results_noisy, results_cut

def plot_benchmark_results(cut_counts, err_noisy, err_cut):
    plt.figure(figsize=(10, 6))
    
    # Noisy (Baseline)
    plt.plot(cut_counts, err_noisy, 'o--', color='gray', label='Standard Noisy (Baseline)', linewidth=2, markersize=8)
    
    # Gate Cutting (Proposed)
    plt.plot(cut_counts, err_cut, 's-', color='tab:blue', label='Gate Cutting (b1.py)', linewidth=2, markersize=8)
    
    plt.title('Reconstruction Error vs Max Allowed Cuts\n(Lower is Better)', fontsize=14)
    plt.xlabel('Max Number of Cuts', fontsize=12)
    plt.ylabel('Absolute Error |Ideal - Experiment|', fontsize=12)
    plt.xticks(cut_counts)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.legend(fontsize=12)
    
    # 注釈
    # plt.text(0.02, 0.02, "Device: device.json (Simulated Noise)\nMethod: MIP-based Cut + Stim", 
    #          transform=plt.gca().transAxes, fontsize=10, 
    #          bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    plt.tight_layout()
    plt.savefig('b1_benchmark_result.png')
    plt.close()

if __name__ == "__main__":
    # 設定
    # device.jsonのqubit数は16だが、回路生成は10量子ビットで行う(b1.pyデフォルト)
    N_QUBITS = 10
    DEPTH = 4  # 深すぎるとエラーが飽和するので適度な深さに
    TRIALS = 100 # 試行回数
    #TRIALS = 10 # 試行回数
    SHOTS = 10000 # サンプリング数
    MAX_CUT_LIST = [0, 1, 2, 3, 4] # 横軸のステップ
    #MAX_CUT_LIST = [0, 1] # 横軸のステップ
    
    # 実行
    cuts, e_noisy, e_cut = run_b1_benchmark("device.json", N_QUBITS, DEPTH, TRIALS, SHOTS, MAX_CUT_LIST)
    
    # プロット
    plot_benchmark_results(cuts, e_noisy, e_cut)
    
    # CSV形式での出力（確認用）
    print("\nBenchmark Results (CSV format):")
    print("MaxCuts,AvgError_Noisy,AvgError_GateCut")
    for k, en, ec in zip(cuts, e_noisy, e_cut):
        print(f"{k},{en:.6f},{ec:.6f}")
