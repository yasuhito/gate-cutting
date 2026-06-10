---
theme: default
title: ゲートカッティングの仕組み(ポンチ絵)
colorSchema: light
canvasWidth: 1280
aspectRatio: 16/9
exportFilename: gate-cutting-ponchie
drawings:
  persist: false
layout: full
---

<div class="board">
  <div class="slide-head">
    <span class="kicker">GATE CUTTING ─ 概要</span>
    <h2>課題:大きな量子回路は、いまの量子コンピュータで<br><span class="accent">そのまま動かすと精度が出ない</span></h2>
  </div>
  <div class="slide-body s1-body">
    <div class="s1-visual">
      <svg viewBox="0 0 545 370" width="545" height="370" role="img" aria-label="量子回路の模式図">
        <g stroke="#475569" stroke-width="2">
          <line x1="62" y1="60"  x2="470" y2="60" />
          <line x1="62" y1="150" x2="470" y2="150" />
          <line x1="62" y1="240" x2="470" y2="240" />
          <line x1="62" y1="330" x2="470" y2="330" />
        </g>
        <g style="font-size:17px" fill="#334155">
          <text x="20" y="66">q0</text>
          <text x="20" y="156">q1</text>
          <text x="20" y="246">q2</text>
          <text x="20" y="336">q3</text>
        </g>
        <g>
          <rect x="84" y="42" width="36" height="36" rx="8" fill="#fff" stroke="#475569" stroke-width="2"/>
          <text x="102" y="68" style="font-size:18px" text-anchor="middle" fill="#475569" font-weight="700">H</text>
          <rect x="84" y="132" width="36" height="36" rx="8" fill="#fff" stroke="#475569" stroke-width="2"/>
          <text x="102" y="158" style="font-size:18px" text-anchor="middle" fill="#475569" font-weight="700">H</text>
          <rect x="84" y="222" width="36" height="36" rx="8" fill="#fff" stroke="#475569" stroke-width="2"/>
          <text x="102" y="248" style="font-size:18px" text-anchor="middle" fill="#475569" font-weight="700">H</text>
          <rect x="84" y="312" width="36" height="36" rx="8" fill="#fff" stroke="#475569" stroke-width="2"/>
          <text x="102" y="338" style="font-size:18px" text-anchor="middle" fill="#475569" font-weight="700">H</text>
          <rect x="216" y="42" width="36" height="36" rx="8" fill="#fff" stroke="#475569" stroke-width="2"/>
          <text x="234" y="68" style="font-size:18px" text-anchor="middle" fill="#475569" font-weight="700">S</text>
          <rect x="330" y="312" width="36" height="36" rx="8" fill="#fff" stroke="#475569" stroke-width="2"/>
          <text x="348" y="338" style="font-size:18px" text-anchor="middle" fill="#475569" font-weight="700">S</text>
        </g>
        <g stroke="#475569" stroke-width="2.5">
          <line x1="166" y1="60" x2="166" y2="150"/>
        </g>
        <circle cx="166" cy="60" r="7" fill="#475569"/>
        <circle cx="166" cy="150" r="13" fill="none" stroke="#475569" stroke-width="2.5"/>
        <line x1="166" y1="137" x2="166" y2="163" stroke="#475569" stroke-width="2.5"/>
        <line x1="153" y1="150" x2="179" y2="150" stroke="#475569" stroke-width="2.5"/>
        <g stroke="#475569" stroke-width="2.5">
          <line x1="234" y1="240" x2="234" y2="330"/>
        </g>
        <circle cx="234" cy="240" r="7" fill="#475569"/>
        <circle cx="234" cy="330" r="13" fill="none" stroke="#475569" stroke-width="2.5"/>
        <line x1="234" y1="317" x2="234" y2="343" stroke="#475569" stroke-width="2.5"/>
        <line x1="221" y1="330" x2="247" y2="330" stroke="#475569" stroke-width="2.5"/>
        <rect x="276" y="118" width="60" height="156" rx="12" fill="#fef2f2" stroke="#fca5a5" stroke-width="1.5"/>
        <g stroke="#dc2626" stroke-width="3">
          <line x1="306" y1="150" x2="306" y2="240"/>
        </g>
        <circle cx="306" cy="150" r="7" fill="#dc2626"/>
        <circle cx="306" cy="240" r="13" fill="none" stroke="#dc2626" stroke-width="3"/>
        <line x1="306" y1="227" x2="306" y2="253" stroke="#dc2626" stroke-width="3"/>
        <line x1="293" y1="240" x2="319" y2="240" stroke="#dc2626" stroke-width="3"/>
        <path d="M 352 108 Q 330 112 314 128" fill="none" stroke="#dc2626" stroke-width="2" marker-end="url(#arrow-red)"/>
        <text x="358" y="100" style="font-size:16.5px" fill="#dc2626" font-weight="700">エラーの大きい CX</text>
        <text x="358" y="121" style="font-size:15px" fill="#dc2626">(フィデリティ 0.93)</text>
        <defs>
          <marker id="arrow-red" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">
            <path d="M0,0 L9,4.5 L0,9 z" fill="#dc2626"/>
          </marker>
        </defs>
        <g>
          <g transform="translate(420,42)">
            <rect width="40" height="36" rx="8" fill="#fff" stroke="#475569" stroke-width="2"/>
            <path d="M 8 26 A 12 12 0 0 1 32 26" fill="none" stroke="#475569" stroke-width="2"/>
            <line x1="20" y1="26" x2="29" y2="13" stroke="#475569" stroke-width="2"/>
          </g>
          <g transform="translate(420,132)">
            <rect width="40" height="36" rx="8" fill="#fff" stroke="#475569" stroke-width="2"/>
            <path d="M 8 26 A 12 12 0 0 1 32 26" fill="none" stroke="#475569" stroke-width="2"/>
            <line x1="20" y1="26" x2="29" y2="13" stroke="#475569" stroke-width="2"/>
          </g>
          <g transform="translate(420,222)">
            <rect width="40" height="36" rx="8" fill="#fff" stroke="#475569" stroke-width="2"/>
            <path d="M 8 26 A 12 12 0 0 1 32 26" fill="none" stroke="#475569" stroke-width="2"/>
            <line x1="20" y1="26" x2="29" y2="13" stroke="#475569" stroke-width="2"/>
          </g>
          <g transform="translate(420,312)">
            <rect width="40" height="36" rx="8" fill="#fff" stroke="#475569" stroke-width="2"/>
            <path d="M 8 26 A 12 12 0 0 1 32 26" fill="none" stroke="#475569" stroke-width="2"/>
            <line x1="20" y1="26" x2="29" y2="13" stroke="#475569" stroke-width="2"/>
          </g>
        </g>
      </svg>
      <p class="caption"><b>横線</b> = 量子ビット / <b>箱</b> = 1量子ビットゲート / <b>●─⊕</b> = 2量子ビットゲート(CX)<br><b>右端の計器</b> = 測定 / ゲートは左から右の順に適用される</p>
    </div>
    <div class="s1-right">
      <div class="card">
        <h3><span class="num-chip">1</span>2量子ビットゲート(CX)はエラーが大きい</h3>
        <p>1量子ビットゲートの成功率(フィデリティ)が 99.9% 程度なのに対し、CX は 9 割台(箇所によってはさらに低い)。回路全体の精度をほぼ CX が決める。</p>
      </div>
      <div class="card">
        <h3><span class="num-chip">2</span>チップ上の場所によって品質にムラがある</h3>
        <p>同じ機械でも「この量子ビットペアの CX だけ特に悪い」ことがある。品質は定期的な較正(キャリブレーション)で実測されている。</p>
      </div>
      <div class="card">
        <h3><span class="num-chip">3</span>この研究の視点:回路切断を「エラー抑制」に使う</h3>
        <p>回路切断はもともと「大きな回路を小さなマシンに載せる」ための技術。ここではそれを「品質の悪い CX を回避して精度を上げる」目的に転用する。</p>
      </div>
      <div class="idea-band">
        <b>発想 ─ ゲートカッティング:</b>
        品質の悪い CX ゲートを回路から<b>「切除」</b>し、CX を含まない複数の小さな回路を実行。
        その結果を古典コンピュータで合成して、<b>元の回路と同じ答え(期待値)を復元</b>する。
      </div>
    </div>
  </div>
  <div class="slide-foot">
    <span>ゲートカッティングの仕組み</span>
    <span><SlideCurrentNo /> / <SlidesTotal /></span>
  </div>
</div>

---
layout: full
---

<div class="board">
  <div class="slide-head">
    <span class="kicker">GATE CUTTING ─ 概要</span>
    <h2>原理:CX ゲートは「1量子ビットゲートだけの回路」<br><span class="accent">4 つの足し算</span>に置き換えられる</h2>
  </div>
  <div class="slide-body">
    <div class="s2-main">
      <div class="s2-before">
        <svg viewBox="0 0 360 215" width="355" height="212" role="img" aria-label="切断前のCX">
          <g stroke="#475569" stroke-width="2">
            <line x1="50" y1="75"  x2="330" y2="75" />
            <line x1="50" y1="160" x2="330" y2="160" />
          </g>
          <text x="12" y="81"  style="font-size:16px" fill="#334155">q0</text>
          <text x="12" y="166" style="font-size:16px" fill="#334155">q1</text>
          <rect x="72" y="57" width="34" height="36" rx="8" fill="#f1f5f9" stroke="#94a3b8" stroke-width="1.5"/>
          <rect x="72" y="142" width="34" height="36" rx="8" fill="#f1f5f9" stroke="#94a3b8" stroke-width="1.5"/>
          <rect x="262" y="57" width="34" height="36" rx="8" fill="#f1f5f9" stroke="#94a3b8" stroke-width="1.5"/>
          <rect x="262" y="142" width="34" height="36" rx="8" fill="#f1f5f9" stroke="#94a3b8" stroke-width="1.5"/>
          <text x="89" y="80" style="font-size:13px" fill="#94a3b8" text-anchor="middle">…</text>
          <text x="89" y="165" style="font-size:13px" fill="#94a3b8" text-anchor="middle">…</text>
          <text x="279" y="80" style="font-size:13px" fill="#94a3b8" text-anchor="middle">…</text>
          <text x="279" y="165" style="font-size:13px" fill="#94a3b8" text-anchor="middle">…</text>
          <line x1="184" y1="75" x2="184" y2="160" stroke="#dc2626" stroke-width="3"/>
          <circle cx="184" cy="75" r="7" fill="#dc2626"/>
          <circle cx="184" cy="160" r="13" fill="none" stroke="#dc2626" stroke-width="3"/>
          <line x1="184" y1="147" x2="184" y2="173" stroke="#dc2626" stroke-width="3"/>
          <line x1="171" y1="160" x2="197" y2="160" stroke="#dc2626" stroke-width="3"/>
          <line x1="214" y1="30" x2="154" y2="200" stroke="#dc2626" stroke-width="2.5" stroke-dasharray="7 6"/>
          <text x="216" y="26" style="font-size:26px" fill="#dc2626">✂</text>
        </svg>
        <p class="caption">切りたい CX(制御 q0 ─ 標的 q1)</p>
      </div>
      <div class="s2-eq">=</div>
      <div class="s2-terms">
        <div class="term">
          <div class="coef">+½</div>
          <div>
            <p class="caption">① なにも置かない</p>
            <svg viewBox="0 0 240 96" width="240" height="96">
              <line x1="14" y1="28" x2="226" y2="28" stroke="#475569" stroke-width="2"/>
              <line x1="14" y1="68" x2="226" y2="68" stroke="#475569" stroke-width="2"/>
              <rect x="102" y="10" width="36" height="36" rx="8" fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4 4"/>
              <rect x="102" y="50" width="36" height="36" rx="8" fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4 4"/>
              <text x="120" y="33" style="font-size:14px" fill="#94a3b8" text-anchor="middle">－</text>
              <text x="120" y="73" style="font-size:14px" fill="#94a3b8" text-anchor="middle">－</text>
            </svg>
          </div>
        </div>
        <div class="term">
          <div class="coef">+½</div>
          <div>
            <p class="caption">② 制御側に Z</p>
            <svg viewBox="0 0 240 96" width="240" height="96">
              <line x1="14" y1="28" x2="226" y2="28" stroke="#475569" stroke-width="2"/>
              <line x1="14" y1="68" x2="226" y2="68" stroke="#475569" stroke-width="2"/>
              <rect x="102" y="10" width="36" height="36" rx="8" fill="#fff" stroke="#475569" stroke-width="2.5"/>
              <text x="120" y="36" style="font-size:19px" fill="#475569" font-weight="700" text-anchor="middle">Z</text>
              <rect x="102" y="50" width="36" height="36" rx="8" fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4 4"/>
              <text x="120" y="73" style="font-size:14px" fill="#94a3b8" text-anchor="middle">－</text>
            </svg>
          </div>
        </div>
        <div class="term">
          <div class="coef">+½</div>
          <div>
            <p class="caption">③ 標的側に X</p>
            <svg viewBox="0 0 240 96" width="240" height="96">
              <line x1="14" y1="28" x2="226" y2="28" stroke="#475569" stroke-width="2"/>
              <line x1="14" y1="68" x2="226" y2="68" stroke="#475569" stroke-width="2"/>
              <rect x="102" y="10" width="36" height="36" rx="8" fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4 4"/>
              <text x="120" y="33" style="font-size:14px" fill="#94a3b8" text-anchor="middle">－</text>
              <rect x="102" y="50" width="36" height="36" rx="8" fill="#fff" stroke="#475569" stroke-width="2.5"/>
              <text x="120" y="76" style="font-size:19px" fill="#475569" font-weight="700" text-anchor="middle">X</text>
            </svg>
          </div>
        </div>
        <div class="term minus">
          <div class="coef">−½</div>
          <div>
            <p class="caption">④ 両方に置く(符号はマイナス)</p>
            <svg viewBox="0 0 240 96" width="240" height="96">
              <line x1="14" y1="28" x2="226" y2="28" stroke="#475569" stroke-width="2"/>
              <line x1="14" y1="68" x2="226" y2="68" stroke="#475569" stroke-width="2"/>
              <rect x="102" y="10" width="36" height="36" rx="8" fill="#fff" stroke="#dc2626" stroke-width="2.5"/>
              <text x="120" y="36" style="font-size:19px" fill="#dc2626" font-weight="700" text-anchor="middle">Z</text>
              <rect x="102" y="50" width="36" height="36" rx="8" fill="#fff" stroke="#dc2626" stroke-width="2.5"/>
              <text x="120" y="76" style="font-size:19px" fill="#dc2626" font-weight="700" text-anchor="middle">X</text>
            </svg>
          </div>
        </div>
      </div>
    </div>
    <div class="s2-notes">
      <div class="formula-band">
        どの置き換え後の回路にも <b>2量子ビットゲートがない</b> → q0 側と q1 側は完全に独立。
        4 つの回路を別々に実行して測定し、結果(期待値)を係数付きで足し合わせると元の回路の答えになる:
        <div class="formula">⟨元の回路⟩ = ½⟨①⟩ + ½⟨②⟩ + ½⟨③⟩ − ½⟨④⟩</div>
      </div>
      <div class="cost-band">
        <b>代償:実行する回路の数が増える。</b><br>
        1 箇所切ると 4 通り、k 箇所切ると <b>4<sup>k</sup> 通り</b>(2 箇所で 16、3 箇所で 64)。
        切る場所は厳選が必要 → 次ページ。類似手法の Wire Cutting(配線を切る)は
        16<sup>k</sup> かかるため、4<sup>k</sup> で済む Gate Cutting の方が実用的。
      </div>
    </div>
  </div>
  <div class="slide-foot">
    <span>ゲートカッティングの仕組み ─ CX = ½(I⊗I) + ½(Z⊗I) + ½(I⊗X) − ½(Z⊗X)</span>
    <span><SlideCurrentNo /> / <SlidesTotal /></span>
  </div>
</div>

---
layout: full
---

<div class="board">
  <div class="slide-head">
    <span class="kicker">GATE CUTTING ─ 概要</span>
    <h2>どこを切るか:実機の較正データ + <span class="accent">数理最適化(MILP)</span>で自動選択</h2>
  </div>
  <div class="slide-body s3-body">
    <div class="s3-col">
      <div class="card card-blue">
        <span class="pill pill-blue">入力 ①</span>
        <h3>実機の較正データ <code>device.json</code></h3>
        <p>量子ビットごと・CX ペアごとの実測フィデリティ(成功率)。</p>
      </div>
      <div class="json-card">{<br>&nbsp;&nbsp;<span class="k">"qubits"</span>: [{id: 0, fidelity: 0.999}, …],<br>&nbsp;&nbsp;<span class="k">"couplings"</span>: [<br>&nbsp;&nbsp;&nbsp;&nbsp;{control: 0, target: 1, fidelity: 0.99},<br>&nbsp;&nbsp;&nbsp;&nbsp;{control: 1, target: 4, <span class="bad">fidelity: 0.93</span>},<br>&nbsp;&nbsp;&nbsp;&nbsp;…<br>&nbsp;&nbsp;]<br>}</div>
      <div class="s3-graph">
        <svg viewBox="0 0 340 205" width="290" height="175" role="img" aria-label="チップのトポロジー">
          <g stroke="#94a3b8" stroke-width="2.5">
            <line x1="60" y1="55" x2="170" y2="55"/>
            <line x1="170" y1="55" x2="280" y2="55"/>
            <line x1="60" y1="150" x2="170" y2="150"/>
            <line x1="170" y1="150" x2="280" y2="150"/>
            <line x1="60" y1="55" x2="60" y2="150"/>
            <line x1="280" y1="55" x2="280" y2="150"/>
          </g>
          <line x1="170" y1="55" x2="170" y2="150" stroke="#dc2626" stroke-width="4"/>
          <text x="195" y="95" style="font-size:15px" fill="#dc2626" font-weight="700">0.93</text>
          <text x="178" y="118" style="font-size:22px" fill="#dc2626">✂</text>
          <g style="font-size:12.5px" fill="#64748b">
            <text x="103" y="46">0.99</text>
            <text x="213" y="46">0.98</text>
            <text x="103" y="172">0.97</text>
            <text x="213" y="172">0.99</text>
            <text x="22" y="106">0.98</text>
            <text x="288" y="106">0.97</text>
          </g>
          <g>
            <circle cx="60"  cy="55"  r="17" fill="#fff" stroke="#475569" stroke-width="2.5"/>
            <circle cx="170" cy="55"  r="17" fill="#fff" stroke="#475569" stroke-width="2.5"/>
            <circle cx="280" cy="55"  r="17" fill="#fff" stroke="#475569" stroke-width="2.5"/>
            <circle cx="60"  cy="150" r="17" fill="#fff" stroke="#475569" stroke-width="2.5"/>
            <circle cx="170" cy="150" r="17" fill="#fff" stroke="#475569" stroke-width="2.5"/>
            <circle cx="280" cy="150" r="17" fill="#fff" stroke="#475569" stroke-width="2.5"/>
          </g>
          <g style="font-size:15px" fill="#1e293b" text-anchor="middle" font-weight="700">
            <text x="60"  y="60">0</text>
            <text x="170" y="60">1</text>
            <text x="280" y="60">2</text>
            <text x="60"  y="155">3</text>
            <text x="170" y="155">4</text>
            <text x="280" y="155">5</text>
          </g>
          <text x="170" y="198" style="font-size:14px" fill="#64748b" text-anchor="middle">○ = 量子ビット / 線 = CX とそのフィデリティ</text>
        </svg>
      </div>
    </div>
    <div class="s3-arrow">▶</div>
    <div class="s3-col">
      <div class="card card-purple fill-col">
        <span class="pill pill-purple">最適化</span>
        <h3>整数計画ソルバー(SciPy MILP)で切断対象を決める</h3>
        <p class="lead-in">「回路中のどの CX 命令を切るか」を 0/1 変数にして、次のルールで最適化:</p>
        <ul class="rule-list">
          <li>フィデリティが<b>しきい値(例 0.96)を下回る CX</b> ほど「切ると得」と評価する</li>
          <li>切れるのは最大 <code>max_cuts</code> 本まで(4<sup>k</sup> の実行コスト爆発を抑える)</li>
          <li>「<b>2 グループ分け</b>をまたぐ CX は必ず切る」という形で回路の分割も表現できる(完全な分離は強制しない)</li>
        </ul>
      </div>
      <div class="card card-purple-line">
        <p class="fine"><b>ポイント:</b>回路は「量子ビット = 点、CX = 線」のグラフとして扱う。同じ量子ビットペアに CX が複数あっても、<b>命令番号で 1 個ずつ区別</b>して狙い撃ちできる。</p>
      </div>
    </div>
    <div class="s3-arrow">▶</div>
    <div class="s3-col">
      <div class="card card-blue">
        <span class="pill pill-blue">入力 ②</span>
        <h3>実行したい量子回路</h3>
        <p>Qiskit で書いた回路(実験ではランダム Clifford 回路を使用)。</p>
      </div>
      <div class="out-card fill-col">
        <span class="pill pill-green">出力</span>
        <h3>切断対象リスト <code>CutTarget</code></h3>
        「回路の何番目の命令の CX(どの量子ビットペア)を切るか」の具体的なリスト。
        <div class="code-line">CutTarget(instruction_index=12,<br>&nbsp;&nbsp;qubits=(1, 4), fidelity=0.93)</div>
        <p class="hand-off">これを次ページの「展開・実行」エンジンに渡す。</p>
      </div>
    </div>
  </div>
  <div class="slide-foot">
    <span>ゲートカッティングの仕組み ─ mip.py / cut_selection.py / device.py</span>
    <span><SlideCurrentNo /> / <SlidesTotal /></span>
  </div>
</div>

---
layout: full
---

<div class="board">
  <div class="slide-head">
    <span class="kicker">GATE CUTTING ─ 概要</span>
    <h2>全体パイプライン:<span class="accent">このリポジトリ(src/gate_cutting/)の構成</span></h2>
  </div>
  <div class="slide-body">
    <div class="s4-inputs">
      <div class="input-card">
        <b>入力 ① 量子回路</b> ─ Qiskit 回路(実験用にはランダム Clifford 回路を生成)
        <span class="mod">circuits.py</span>
      </div>
      <div class="input-card">
        <b>入力 ② device.json</b> ─ 実機の較正データを読み込み、フィデリティをノイズ確率(<code>ErrorParams</code>)へ変換
        <span class="mod">device.py</span>
      </div>
    </div>
    <div class="s4-flow">
      <div class="step">
        <span class="step-no">STEP 1</span>
        <h3>切る CX を選ぶ</h3>
        <p>較正データをもとに SciPy MILP で切断対象(<code>CutTarget</code>)を自動選択。</p>
        <span class="mod">mip.py / cut_selection.py</span>
      </div>
      <div class="s4-arrow">▶</div>
      <div class="step">
        <span class="step-no">STEP 2</span>
        <h3>4<sup>k</sup> 個のサブ回路に展開</h3>
        <p>切る CX を「なし / Z / X / Z&amp;X」の 4 パターン(係数 ±½)に置き換えた回路を生成。</p>
        <span class="mod">gate_cutting.py</span>
      </div>
      <div class="s4-arrow">▶</div>
      <div class="step">
        <span class="step-no">STEP 3</span>
        <h3>ノイズ付きシミュレーション</h3>
        <p>Stim 形式に変換し、各ゲートの後ろに実機由来のノイズを挿入して高速にサンプリング実行。「切っても結果を復元できるか」の事前評価にも使う。</p>
        <span class="mod">stim_backend.py</span>
      </div>
      <div class="s4-arrow">▶</div>
      <div class="step">
        <span class="step-no">STEP 4</span>
        <h3>古典後処理で答えを復元</h3>
        <p>各サブ回路の測定から期待値(全ビットのパリティ)を計算し、係数を掛けて合算 → 元の回路の期待値。</p>
        <span class="mod">gate_cutting.py: run_gate_cut()</span>
      </div>
    </div>
    <div class="s4-compare">
      <div class="compare-band">
        <b>検証方法:</b>同じ回路を切らずに実行(<code>run_standard</code>)した期待値と、
        ゲートカッティング経由(<code>run_gate_cut</code>)の期待値を比較し、切る数を増やすほど
        理想値との誤差が減る(= エラー抑制が効く)ことを確認する。
      </div>
      <div class="goal-band">
        <b>ゴール:</b>論文用の実験スクリプトを再利用可能なコンポーネントに整理し、
        量子計算プラットフォーム <b>OQTOPUS</b> に組み込めるようにする(ワイヤーカッティング対応などは今後)。
      </div>
    </div>
  </div>
  <div class="slide-foot">
    <span>ゲートカッティングの仕組み ─ リポジトリ: gate-cutting</span>
    <span><SlideCurrentNo /> / <SlidesTotal /></span>
  </div>
</div>

---
layout: full
---

<div class="board">
  <div class="slide-head">
    <span class="kicker">GATE CUTTING ─ 補足</span>
    <h2>補足:シミュレータに <span class="accent">Stim</span> を使う理由</h2>
  </div>
  <div class="slide-body">
    <p class="s5-lead">Stim はクリフォード回路専用の高速シミュレータ。状態ベクトルを持たず「スタビライザー形式」で計算するため、量子ビット数が増えても多項式時間で動く。この実験の性質と 3 点で噛み合う。</p>
    <div class="s5-grid">
      <div class="card">
        <h3><span class="num-chip">1</span>4<sup>k</sup> × ショットの物量に耐える</h3>
        <p>k 箇所切ると 4<sup>k</sup> 個のサブ回路 × 各 10,000 ショット(+ 切らない基準実行との比較)。状態ベクトル方式はコストが量子ビット数 n に対して 2<sup>n</sup> で増えるが、Stim は多項式時間で、ショットもまとめて高速にサンプリングできる。</p>
      </div>
      <div class="card">
        <h3><span class="num-chip">2</span>ノイズモデルがそのまま載る</h3>
        <p>挿入するノイズはパウリノイズのみ(ゲート後の DEPOLARIZE、測定前の読み出し反転)。パウリノイズはクリフォードの世界を壊さない。CX 分解の置き換えゲートも Z / X(パウリ)なので、<b>切った後のサブ回路もすべて Stim で扱える形のまま</b>。</p>
      </div>
      <div class="card">
        <h3><span class="num-chip">3</span>「切って大丈夫か」の事前評価</h3>
        <p>切り方によっては期待値が消えて復元に失敗する(奇数分割問題)。実行前にシミュレータで検査し、ダメなら切らない、という安全弁を入れている。8×8 = 64 量子ビットの実機規模でこの事前検査ができるのはスタビライザー方式だからこそ。</p>
      </div>
    </div>
    <div class="cost-band s5-tradeoff">
      <b>代償:クリフォードゲート(X/Y/Z/H/S/Sdg/CX など)しか扱えない。</b>
      実験はクリフォード回路に限定し、回転ゲートは S 等に置き換える。目的は「エラー抑制が効くか」のノイズ検証なのでこの構成で十分。
      ノイズなし・小規模での手法比較には Qiskit Aer を併用している。
    </div>
  </div>
  <div class="slide-foot">
    <span>ゲートカッティングの仕組み ─ stim_backend.py</span>
    <span><SlideCurrentNo /> / <SlidesTotal /></span>
  </div>
</div>

---
layout: full
---

<div class="board">
  <div class="slide-head">
    <span class="kicker">GATE CUTTING ─ 補足</span>
    <h2>補足:切断対象を選ぶ <span class="accent">MIP の評価関数と制約条件</span></h2>
  </div>
  <div class="slide-body">
    <p class="s6-lead">「どこを切るか」(ボード 3)の中身。実装(<code>mip.py</code>)の定式化をそのまま示す。回路は「量子ビット = 点、CX 命令 = 線(較正フィデリティ付き)」のグラフ。</p>
    <div class="s6-grid">
      <div class="s6-col">
        <div class="card">
          <h3>0/1 変数</h3>
          <ul class="rule-list">
            <li><b><i>u<sub>i</sub></i> ∈ {0, 1}</b> — 量子ビット <i>i</i> の所属グループ(量子ビットごとに 1 個)</li>
            <li><b><i>z<sub>e</sub></i> ∈ {0, 1}</b> — CX 候補 <i>e</i> を切るか(CX 命令ごとに 1 個。同じ量子ビットペアに CX が複数あっても命令番号で別の変数)</li>
          </ul>
        </div>
        <div class="formula-band fill-col">
          <b>評価関数(最小化)</b> ─ フィデリティが低い CX ほど「切ると得」
          <div class="formula">minimize&nbsp;&nbsp;Σ<sub>e</sub> c<sub>e</sub> · z<sub>e</sub></div>
          <div class="s6-cases">
            c<sub>e</sub> = F<sub>e</sub> − 0.96 <span class="s6-dim">(F<sub>e</sub> &lt; しきい値 0.96 → 負: 切るほど目的関数が下がる)</span><br>
            c<sub>e</sub> = F<sub>e</sub> − 0.96 + 10<sup>−6</sup> <span class="s6-dim">(F<sub>e</sub> ≥ しきい値 → 正: 切ると必ず損)</span>
          </div>
          <svg viewBox="0 0 480 96" width="480" height="96" role="img" aria-label="コスト関数の数直線">
            <line x1="30" y1="58" x2="290" y2="58" stroke="#dc2626" stroke-width="5"/>
            <line x1="290" y1="58" x2="450" y2="58" stroke="#94a3b8" stroke-width="5"/>
            <line x1="290" y1="40" x2="290" y2="76" stroke="#1e293b" stroke-width="2"/>
            <circle cx="160" cy="58" r="7" fill="#dc2626"/>
            <text x="160" y="84" style="font-size:13px" fill="#dc2626" text-anchor="middle" font-weight="700">F = 0.93 の CX</text>
            <text x="290" y="92" style="font-size:13px" fill="#1e293b" text-anchor="middle">しきい値 0.96</text>
            <text x="155" y="28" style="font-size:14px" fill="#dc2626" text-anchor="middle" font-weight="700">コスト負 = 切ると得</text>
            <text x="372" y="28" style="font-size:14px" fill="#64748b" text-anchor="middle">コスト正 = 切らない</text>
            <text x="455" y="62" style="font-size:13px" fill="#64748b">F<tspan dy="3" style="font-size:10px">e</tspan></text>
          </svg>
        </div>
      </div>
      <div class="s6-col">
        <div class="card fill-col">
          <h3>制約条件</h3>
          <ul class="rule-list">
            <li><b>切断本数の上限:</b> Σ<sub>e</sub> z<sub>e</sub> ≤ <code>max_cuts</code>(既定 3)。4<sup>k</sup> のショット数爆発を抑える予算制約</li>
            <li><b>グループ整合:</b> z<sub>e</sub> ≥ |u<sub>a</sub> − u<sub>b</sub>| ─ グループをまたぐ CX は必ず切る(回路の 2 分割を表現できる。完全な分離は強制しない)。実装では 2 本の線形不等式 −u<sub>a</sub> + u<sub>b</sub> + z<sub>e</sub> ≥ 0、u<sub>a</sub> − u<sub>b</sub> + z<sub>e</sub> ≥ 0 に展開</li>
            <li><b>整数条件:</b> 全変数が 0/1 の混合整数線形計画。ソルバは SciPy <code>milp</code>(HiGHS)で、実機トポロジー規模でも数秒で解ける</li>
          </ul>
        </div>
        <div class="cost-band">
          <b>性質と限界:</b>
          良い CX は微小ペナルティ 10<sup>−6</sup> のせいで切っても必ず損 → 無駄な切断は自然に 0 本に収束し、
          悪い CX だけがフィデリティの低い順に予算内で選ばれる。
          論文はさらに「バランス制約(部分回路のサイズ・フィデリティの均等化)」を挙げているが、現実装は未対応(今後の課題)。
        </div>
      </div>
    </div>
  </div>
  <div class="slide-foot">
    <span>ゲートカッティングの仕組み ─ mip.py: MIPCutFinder._solve_mip_edge_indices()</span>
    <span><SlideCurrentNo /> / <SlidesTotal /></span>
  </div>
</div>
