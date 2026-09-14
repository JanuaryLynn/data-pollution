;; =============================================================
;; Data Pollution Governance ABM
;; Version: v1.8-coverage-aligned
;;
;; 本版为正式跑数前冻结候选版。相对 v1.6 / v1.7 的关键修订:
;;
;;   V1.8-1  legal-strength 恢复为论文原始百分比定义：
;;           L = 每次法律干预覆盖的全网账号比例 (%)
;;           sweep = [50, 70, 90], baseline = 70。
;;           因此 L 与 platform-speed 都是 percentage-based capacity，
;;           跨规模实验中无需手工按 N 放大。
;;
;;   V1.8-2  treatment 与 targeting 真正正交：
;;           legal / platform 使用相同 candidate universe（全网节点）
;;           与相同 targeting operator：
;;             random   = 从全网随机抽取；
;;             targeted = 按 degree 从高到低优先选择。
;;
;;   V1.8-3  法律错误率采用与平台可比的二元判断结构：
;;           polluted candidate:
;;             alpha_L 概率正确处置，1-alpha_L 为 false negative；
;;           clean candidate:
;;             1-alpha_L 概率错误处置（false positive）。
;;           制度含义上 alpha_L 表示法律判断/程序准确率，
;;           不等同于平台分类器准确率。
;;
;;   V1.8-4  over-removal-rate:
;;           O(t) = 累计至少遭遇一次错误治理的独立节点数 / N。
;;           这是 population-level collateral governance cost，
;;           严格有界于 [0,100]。
;;
;;   V1.8-5  基础扩散过程为 SI-type、无自发恢复；
;;           legal / platform 治理可将 polluted 节点重置为 clean。
;;
;; 累计整合:
;;   T1.1 符号修正 (p0 / beta0 / amplification)
;;   T1.2 法律错误率 alpha_L
;;   T1.3 Collateral damage 追踪
;;   T1.4 超级传播者按 degree top-k 选取
;;   T1.6 治理主体与 targeting 机制解耦
;;   T1.8 网络拓扑可切换 (BA / ER / WS)
;;   T1.9 platform-speed 改为覆盖率百分比
;;   T1.10 legal-strength 改为覆盖率百分比
;;
;; 符号对照:
;;   p0                初始污染率 (%)                  -> 论文 III.E
;;   beta0             基线传染概率                    -> 论文公式(1)
;;   amplification     超级传播者放大系数 alpha         -> 论文公式(1)
;;   legal-strength    法律干预覆盖率 L (%)             -> 论文 III.E
;;   legal-response-time 法律响应间隔 tau_L (ticks)
;;   legal-accuracy    法律判断/程序准确率 alpha_L (%)
;;   platform-accuracy 平台识别准确率 alpha (%)
;;   platform-speed    平台审核覆盖率 n_p (% / tick)
;;
;; 重要: setup 不使用 clear-all，BehaviorSpace 每个 experiment
;;       必须显式列出完整参数，避免跨实验参数残留。
;; =============================================================

extensions [nw]

globals [
  ;; ---------- 网络拓扑 ----------
  network-type          ; "BA" / "ER" / "WS"        默认 "BA"
  num-nodes             ; 节点数 N                   默认 1000
  ba-m                  ; BA 的最小连边数 m          默认 2
  ws-rewire-prob        ; WS 的重连概率              默认 0.1

  ;; ---------- 传播参数 ----------
  p0                    ; 初始污染率 (%)             扫参 [10, 30, 50]
  beta0                 ; 基线传染概率               默认 0.10
  amplification         ; 超级传播者放大系数 alpha    默认 0.5
  super-ratio           ; 超级传播者比例 (%)         默认 1

  ;; ---------- 治理参数 ----------
  treatment             ; "none" / "legal" / "platform"
  targeting-mode        ; "default" / "targeted" / "random"
  legal-strength        ; 法律干预覆盖率 L (%)          扫参 [50, 70, 90]
  legal-response-time   ; 法律响应间隔 (tick)         扫参 [1, 5, 10]
  legal-accuracy        ; 法律准确率 alpha_L (%)      扫参 [90, 95, 100]
  platform-accuracy     ; 平台准确率 alpha (%)        扫参 [70, 80, 90]
  platform-speed        ; 平台审核覆盖率 (%)          扫参 [50, 75, 100]

  ;; ---------- 评估参数 ----------
  lambda-weight         ; 复合指标中误删的惩罚权重    默认 1.0
  max-ticks             ; 单次运行时长                默认 50

  ;; ---------- 统计量 ----------
  pollution-count
  initial-polluted-count
  legal-deleted-count
  platform-deleted-count
  deleted-count
  legal-false-deleted
  platform-false-deleted
  false-deleted
  over-removal-count

  ;; ---------- 运行控制 ----------
  ticks-started?
  params-initialized?
]

turtles-own [
  polluted?
  super-spreader?
  wrongly-removed?
]


;; =============================================================
;; 初始化
;; =============================================================

to setup
  clear-turtles
  clear-patches
  clear-drawing
  clear-all-plots
  clear-output
  set ticks-started? false

  fill-missing-parameters
  reset-counters
  report-parameters

  build-network
  assign-super-spreaders
  seed-initial-pollution

  set pollution-count count turtles with [polluted?]
  set initial-polluted-count pollution-count

  layout-circle turtles 10

  reset-ticks
  set ticks-started? true
end


;; 交互式调试用: 强制清空所有参数后重填默认值。BehaviorSpace 请勿调用。
to setup-fresh
  set params-initialized? false
  set network-type 0
  set num-nodes 0
  set ba-m 0
  set ws-rewire-prob 0
  set p0 0
  set beta0 0
  set amplification 0
  set super-ratio 0
  set treatment 0
  set targeting-mode 0
  set legal-strength 0
  set legal-response-time 0
  set legal-accuracy 0
  set platform-accuracy 0
  set platform-speed 0
  set lambda-weight 0
  set max-ticks 0
  setup
end


to fill-missing-parameters
  if num-nodes           = 0 [ set num-nodes           1000 ]
  if ba-m                = 0 [ set ba-m                2    ]
  if ws-rewire-prob      = 0 [ set ws-rewire-prob      0.1  ]
  if super-ratio         = 0 [ set super-ratio         1    ]

  if p0                  = 0 [ set p0                  50   ]
  if beta0               = 0 [ set beta0               0.10 ]
  if amplification       = 0 [ set amplification       0.5  ]

  if legal-strength      = 0 [ set legal-strength      70   ]
  if legal-response-time = 0 [ set legal-response-time 5    ]
  if legal-accuracy      = 0 [ set legal-accuracy      95   ]
  if platform-accuracy   = 0 [ set platform-accuracy   80   ]
  if platform-speed      = 0 [ set platform-speed      75   ]

  if lambda-weight       = 0 [ set lambda-weight       1.0  ]
  if max-ticks           = 0 [ set max-ticks           50   ]

  if treatment      = 0 or treatment      = "" [ set treatment      "none"    ]
  if network-type   = 0 or network-type   = "" [ set network-type   "BA"      ]
  if targeting-mode = 0 or targeting-mode = "" [ set targeting-mode "default" ]

  set params-initialized? true
end


to reset-counters
  set legal-deleted-count    0
  set platform-deleted-count 0
  set deleted-count          0
  set legal-false-deleted    0
  set platform-false-deleted 0
  set false-deleted          0
  set over-removal-count     0
  set initial-polluted-count 0
  set pollution-count        0
end


to report-parameters
  print "------- 参数设置 -------"
  print (word "network-type         = " network-type)
  print (word "num-nodes N          = " num-nodes)
  print (word "treatment            = " treatment)
  print (word "targeting-mode       = " targeting-mode
              "  (生效为: " effective-targeting ")")
  print (word "p0 (初始污染率)      = " p0 " %")
  print (word "beta0 (基线传染率)   = " beta0)
  print (word "amplification alpha  = " amplification
              "  -> 超级传播者传染率 = " (beta0 * (1 + amplification)))
  print (word "super-ratio          = " super-ratio " %")
  print (word "legal-strength L     = " legal-strength " %  -> 每次法律干预审查 "
              (round (num-nodes * legal-strength / 100)) " 个候选节点")
  print (word "legal-response-time  = " legal-response-time)
  print (word "legal-accuracy aL    = " legal-accuracy " %")
  print (word "platform-accuracy a  = " platform-accuracy " %")
  print (word "platform-speed       = " platform-speed " %  -> 每 tick 审核 "
              (round (num-nodes * platform-speed / 100)) " 个节点")
  print (word "lambda-weight        = " lambda-weight)
  print "------------------------"
end


;; =============================================================
;; 网络生成 (BA / ER / WS), 均校准到相同平均度数 2 * ba-m
;; =============================================================
to build-network
  if network-type = "BA" [ build-barabasi-albert ]
  if network-type = "ER" [ build-erdos-renyi ]
  if network-type = "WS" [ build-watts-strogatz ]

  if not any? turtles [
    error (word "未知的 network-type: " network-type " (应为 BA / ER / WS)")
  ]

  ask turtles [
    set shape "person"
    set color blue
    set size 0.5
    set polluted? false
    set super-spreader? false
    set wrongly-removed? false
  ]
end


to build-barabasi-albert
  nw:generate-preferential-attachment turtles links num-nodes ba-m
end


to build-erdos-renyi
  let er-prob (2 * ba-m) / (num-nodes - 1)
  nw:generate-random turtles links num-nodes er-prob
end


;; 手工实现 Watts-Strogatz: 环形晶格 + 随机重连
;; 手工实现是为避免依赖特定版本 nw 扩展的 WS 生成原语。
to build-watts-strogatz
  create-turtles num-nodes
  let ordered sort turtles

  foreach (range num-nodes) [ i ->
    let a item i ordered
    foreach (range 1 (ba-m + 1)) [ j ->
      let b item ((i + j) mod num-nodes) ordered
      if a != b [
        ask a [ if not link-neighbor? b [ create-link-with b ] ]
      ]
    ]
  ]

  let to-rewire []
  ask links [
    if random-float 1.0 < ws-rewire-prob [
      set to-rewire lput (list end1 end2) to-rewire
    ]
  ]

  foreach to-rewire [ pair ->
    let a item 0 pair
    let b item 1 pair
    if a != nobody and b != nobody [
      if [link-neighbor? b] of a [
        let pool turtles with [self != a and not link-neighbor? a]
        if any? pool [
          let c one-of pool
          ask a [
            ask link-with b [ die ]
            create-link-with c
          ]
        ]
      ]
    ]
  ]
end


;; -------------------------------------------------------------
;; Select top 1% nodes by degree centrality as superspreaders.
;; 在 ER / WS 下度数分布近似泊松, "前 1%" 的度数优势远小于 BA,
;; 这正是跨拓扑对比要观察的现象。
;; -------------------------------------------------------------
to assign-super-spreaders
  let n-super max list 1 (round (count turtles * super-ratio / 100))
  if n-super > count turtles [ set n-super count turtles ]

  let ranked sort-on [(- count link-neighbors)] turtles

  ask turtle-set (sublist ranked 0 n-super) [
    set super-spreader? true
    set size 1
  ]
end


to seed-initial-pollution
  let n-seed max list 1 (round (count turtles * p0 / 100))
  if n-seed > count turtles [ set n-seed count turtles ]

  ask n-of n-seed turtles [
    set polluted? true
    set color red
  ]
end


;; =============================================================
;; 干预机制解耦: targeting-mode 与 treatment 正交
;; "default" 沿用论文原设定 (legal->targeted, platform->random)
;; =============================================================
to-report effective-targeting
  if targeting-mode = "targeted" [ report "targeted" ]
  if targeting-mode = "random"   [ report "random" ]
  ifelse treatment = "legal" [ report "targeted" ][ report "random" ]
end


;; =============================================================
;; 主循环
;; =============================================================
to go
  if not ticks-started? [ setup ]
  if ticks >= max-ticks [ stop ]

  spread-pollution

  if treatment = "legal"    [ do-legal-intervention ]
  if treatment = "platform" [ do-platform-moderation ]

  update-visuals

  set pollution-count count turtles with [polluted?]
  set deleted-count (legal-deleted-count + platform-deleted-count)
  set false-deleted (legal-false-deleted + platform-false-deleted)

  tick
end


to update-visuals
  ask turtles [
    ifelse polluted?
    [ set color red ]
    [ ifelse wrongly-removed?
      [ set color gray ]
      [ set color blue ] ]
  ]
end


;; 论文 公式(1):  p_infect = beta0 * (1 + amplification * s_i) * z_it
to spread-pollution
  ask turtles with [polluted?] [
    let spread-chance beta0
    if super-spreader? [
      set spread-chance beta0 * (1 + amplification)
    ]

    ask link-neighbors with [not polluted?] [
      if random-float 1.0 < spread-chance [
        set polluted? true
      ]
    ]
  ]
end


;; -------------------------------------------------------------
;; 法律干预 (每 legal-response-time 个 tick 一次)
;;
;; legal-strength = L (%):
;;   每次法律干预从全网选择 L% 的候选账号进行审查/处置。
;;   例如 N=1000, L=70 -> 每次审查 700 个候选账号；
;;        N=5000, L=70 -> 每次审查 3500 个候选账号。
;;
;; 与 platform 使用相同 targeting 语义与相同 candidate universe：
;;   random   : 从全网随机选择候选账号；
;;   targeted : 按 degree 从高到低优先选择候选账号。
;;
;; 对每个候选账号：
;;   polluted? = true:
;;      legal-accuracy 概率正确处置 -> polluted? = false
;;      1-legal-accuracy 概率 false negative -> 不处置
;;   polluted? = false:
;;      1-legal-accuracy 概率 false positive -> 计入 wrongful removal
;;      legal-accuracy 概率正确不处置
;; -------------------------------------------------------------
to do-legal-intervention
  if legal-response-time <= 0 [ stop ]
  if ticks mod legal-response-time != 0 [ stop ]

  let nodes-to-process min list
      (round (count turtles * legal-strength / 100))
      (count turtles)

  if nodes-to-process <= 0 [ stop ]

  let targets nobody
  ifelse effective-targeting = "targeted" [
    set targets max-n-of nodes-to-process turtles [count link-neighbors]
  ]
  [
    set targets n-of nodes-to-process turtles
  ]

  ask targets [
    ifelse polluted? [
      ;; true positive / false negative
      if random-float 100 < legal-accuracy [
        set polluted? false
        set legal-deleted-count legal-deleted-count + 1
      ]
    ]
    [
      ;; true negative / false positive
      if random-float 100 < (100 - legal-accuracy) [
        set legal-false-deleted legal-false-deleted + 1
        mark-wrongly-removed
      ]
    ]
  ]
end


;; -------------------------------------------------------------
;; 平台自律审核
;; platform-speed 是覆盖率百分比: 每 tick 审核全网的 platform-speed %。
;; 该定义随 N 自动缩放, 因此跨规模实验无需手工调整。
;; 与 legal 共用相同 candidate universe（全网节点）和 targeting 语义：
;; random: 从全网随机抽样; targeted: 按 degree 从高到低优先审核。
;; 注意: platform-speed = 100 时全量覆盖, 两种模式等价。
;; -------------------------------------------------------------
to do-platform-moderation
  let sample-size min list (round (count turtles * platform-speed / 100))
                           (count turtles)
  if sample-size <= 0 [ stop ]

  let audited nobody
  ifelse effective-targeting = "targeted" [
    set audited max-n-of sample-size turtles [count link-neighbors]
  ]
  [
    set audited n-of sample-size turtles
  ]

  ask audited [
    ifelse polluted? [
      if random-float 100 < platform-accuracy [
        set polluted? false
        set platform-deleted-count platform-deleted-count + 1
      ]
    ]
    [
      if random-float 100 < (100 - platform-accuracy) [
        set platform-false-deleted platform-false-deleted + 1
        mark-wrongly-removed
      ]
    ]
  ]
end


;; turtle 过程: 标记一个正常节点被误删 (去重计数)
to mark-wrongly-removed
  if not wrongly-removed? [
    set wrongly-removed? true
    set over-removal-count over-removal-count + 1
  ]
end


;; =============================================================
;; 报告器
;; =============================================================

;; 论文 公式(2): E(t) = 未污染节点比例 (%)
to-report effectiveness
  if not ticks-started? [ report 0 ]
  ifelse count turtles > 0 [
    report 100 - (pollution-count / count turtles) * 100
  ][
    report 0
  ]
end


;; Collateral damage / 误删暴露率 O(t)
;; = 累计至少遭遇一次错误治理的独立节点数 / 全体节点 N (%)
;; population-level unique exposure，严格有界于 [0,100]。
to-report over-removal-rate
  if not ticks-started? [ report 0 ]
  ifelse count turtles > 0 [
    report (over-removal-count / count turtles) * 100
  ][
    report 0
  ]
end


;; 复合指标: E_net = E - lambda * O
to-report net-effectiveness
  if not ticks-started? [ report 0 ]
  report effectiveness - (lambda-weight * over-removal-rate)
end


;; 事件级处置精确率：正确处置事件 / (正确处置事件 + false-positive 事件)
;; 与 over-removal-rate 的独立用户暴露比例不同。
to-report removal-precision
  if not ticks-started? [ report 0 ]
  let total (deleted-count + false-deleted)
  ifelse total > 0 [ report (deleted-count / total) * 100 ][ report 0 ]
end


to-report error-rate
  if not ticks-started? [ report 0 ]
  let total (deleted-count + false-deleted)
  ifelse total > 0 [ report (false-deleted / total) * 100 ][ report 0 ]
end


to-report current-pollution-rate
  if not ticks-started? [ report 0 ]
  ifelse count turtles > 0 [
    report (pollution-count / count turtles) * 100
  ][
    report 0
  ]
end


to-report avg-response-time
  if not ticks-started? [ report 0 ]
  ifelse treatment = "legal" [
    report legal-response-time
  ][
    ifelse treatment = "platform" [ report 1 ][ report 0 ]
  ]
end


;; ---------- 诊断报告器 ----------

to-report legal-load
  report round (count turtles * legal-strength / 100)
end

to-report audit-load
  report round (count turtles * platform-speed / 100)
end

to-report mean-degree
  ifelse any? turtles [ report mean [count link-neighbors] of turtles ][ report 0 ]
end

to-report max-degree
  ifelse any? turtles [ report max [count link-neighbors] of turtles ][ report 0 ]
end

to-report degree-sd
  ifelse count turtles > 1 [
    report standard-deviation [count link-neighbors] of turtles
  ][ report 0 ]
end

to-report count-isolates
  report count turtles with [not any? link-neighbors]
end

to-report mean-super-degree
  ifelse any? turtles with [super-spreader?] [
    report mean [count link-neighbors] of turtles with [super-spreader?]
  ][ report 0 ]
end

to-report mean-ordinary-degree
  ifelse any? turtles with [not super-spreader?] [
    report mean [count link-neighbors] of turtles with [not super-spreader?]
  ][ report 0 ]
end

to-report count-super-spreaders
  report count turtles with [super-spreader?]
end

to-report count-wrongly-removed
  report count turtles with [wrongly-removed?]
end

to-report effective-beta-super
  report beta0 * (1 + amplification)
end


;; =============================================================
;; BehaviorSpace 使用说明
;; =============================================================
;;
;; [通用设置]
;;   重复次数:        10
;;   按顺序执行组合:  勾选
;;   setup 命令:      setup
;;   go 命令:         go
;;   终止条件:        ticks >= 50
;;   每一步运行指标:  勾选
;;   更新视图 / 更新图表: 取消勾选（提速）
;;   输出格式:        Table
;;
;; [通用 reporter]
;;   effectiveness
;;   over-removal-rate
;;   net-effectiveness
;;   removal-precision
;;   error-rate
;;   current-pollution-rate
;;   count-wrongly-removed
;;   deleted-count
;;   false-deleted
;;
;; [跨拓扑 / 跨规模实验额外 reporter]
;;   mean-degree
;;   max-degree
;;   degree-sd
;;   count-isolates
;;   mean-super-degree
;;   legal-load
;;   audit-load
;;
;; -------------------------------------------------------------
;; 实验 1 — exp1_baseline                       3 x 10 = 30 runs
;; -------------------------------------------------------------
;; ["treatment" "none"]
;; ["targeting-mode" "targeted"]
;; ["network-type" "BA"]
;; ["p0" 10 30 50]
;; ["num-nodes" 1000]
;; ["ba-m" 2]
;; ["ws-rewire-prob" 0.1]
;; ["beta0" 0.1]
;; ["amplification" 0.5]
;; ["super-ratio" 1]
;; ["legal-strength" 70]
;; ["legal-response-time" 5]
;; ["legal-accuracy" 95]
;; ["platform-accuracy" 80]
;; ["platform-speed" 75]
;; ["lambda-weight" 1]
;; ["max-ticks" 50]
;;
;; -------------------------------------------------------------
;; 实验 2 — exp2_legal_main                    27 x 10 = 270 runs
;; -------------------------------------------------------------
;; ["treatment" "legal"]
;; ["targeting-mode" "targeted"]
;; ["network-type" "BA"]
;; ["p0" 10 30 50]
;; ["legal-strength" 50 70 90]
;; ["legal-response-time" 1 5 10]
;; ["legal-accuracy" 95]
;; ["platform-accuracy" 80]
;; ["platform-speed" 75]
;; ["num-nodes" 1000]
;; ["ba-m" 2]
;; ["ws-rewire-prob" 0.1]
;; ["beta0" 0.1]
;; ["amplification" 0.5]
;; ["super-ratio" 1]
;; ["lambda-weight" 1]
;; ["max-ticks" 50]
;;
;; -------------------------------------------------------------
;; 实验 3 — exp3_platform_main                 27 x 10 = 270 runs
;; -------------------------------------------------------------
;; ["treatment" "platform"]
;; ["targeting-mode" "targeted"]
;; ["network-type" "BA"]
;; ["p0" 10 30 50]
;; ["platform-accuracy" 70 80 90]
;; ["platform-speed" 50 75 100]
;; ["legal-strength" 70]
;; ["legal-response-time" 5]
;; ["legal-accuracy" 95]
;; ["num-nodes" 1000]
;; ["ba-m" 2]
;; ["ws-rewire-prob" 0.1]
;; ["beta0" 0.1]
;; ["amplification" 0.5]
;; ["super-ratio" 1]
;; ["lambda-weight" 1]
;; ["max-ticks" 50]
;;
;; -------------------------------------------------------------
;; 实验 4 — exp4_2x2                         12 x 10 = 120 runs
;; Reviewer 1-A 核心机制识别实验
;; -------------------------------------------------------------
;; ["treatment" "legal" "platform"]
;; ["targeting-mode" "targeted" "random"]
;; ["network-type" "BA"]
;; ["p0" 10 30 50]
;; ["legal-strength" 70]
;; ["legal-response-time" 5]
;; ["legal-accuracy" 95]
;; ["platform-accuracy" 80]
;; ["platform-speed" 75]
;; ["num-nodes" 1000]
;; ["ba-m" 2]
;; ["ws-rewire-prob" 0.1]
;; ["beta0" 0.1]
;; ["amplification" 0.5]
;; ["super-ratio" 1]
;; ["lambda-weight" 1]
;; ["max-ticks" 50]
;;
;; 注意: platform-speed 必须 < 100，否则 platform-targeted 与
;;       platform-random 在全量审核下完全等价。
;;
;; -------------------------------------------------------------
;; 实验 5 — exp5_legal_accuracy_sensitivity    9 x 10 = 90 runs
;; -------------------------------------------------------------
;; ["treatment" "legal"]
;; ["targeting-mode" "targeted"]
;; ["network-type" "BA"]
;; ["p0" 10 30 50]
;; ["legal-accuracy" 90 95 100]
;; ["legal-strength" 70]
;; ["legal-response-time" 5]
;; ["platform-accuracy" 80]
;; ["platform-speed" 75]
;; ["num-nodes" 1000]
;; ["ba-m" 2]
;; ["ws-rewire-prob" 0.1]
;; ["beta0" 0.1]
;; ["amplification" 0.5]
;; ["super-ratio" 1]
;; ["lambda-weight" 1]
;; ["max-ticks" 50]
;;
;; -------------------------------------------------------------
;; 实验 6 — exp6_networktype                  27 x 10 = 270 runs
;; -------------------------------------------------------------
;; ["network-type" "BA" "ER" "WS"]
;; ["treatment" "none" "legal" "platform"]
;; ["targeting-mode" "targeted"]
;; ["p0" 10 30 50]
;; ["legal-strength" 70]
;; ["legal-response-time" 5]
;; ["legal-accuracy" 95]
;; ["platform-accuracy" 80]
;; ["platform-speed" 75]
;; ["num-nodes" 1000]
;; ["ba-m" 2]
;; ["ws-rewire-prob" 0.1]
;; ["beta0" 0.1]
;; ["amplification" 0.5]
;; ["super-ratio" 1]
;; ["lambda-weight" 1]
;; ["max-ticks" 50]
;;
;; -------------------------------------------------------------
;; 实验 7 — scale check（拆成 7a / 7b）
;; L 与 n_p 都是百分比，跨 N 自动缩放；除 N 外其余参数完全相同。
;; -------------------------------------------------------------
;; 7a — exp7a_scale_check_N1000                9 x 10 = 90 runs
;; ["treatment" "none" "legal" "platform"]
;; ["targeting-mode" "targeted"]
;; ["network-type" "BA"]
;; ["p0" 10 30 50]
;; ["num-nodes" 1000]
;; ["legal-strength" 70]
;; ["legal-response-time" 5]
;; ["legal-accuracy" 95]
;; ["platform-accuracy" 80]
;; ["platform-speed" 75]
;; ["ba-m" 2]
;; ["ws-rewire-prob" 0.1]
;; ["beta0" 0.1]
;; ["amplification" 0.5]
;; ["super-ratio" 1]
;; ["lambda-weight" 1]
;; ["max-ticks" 50]
;;
;; 7b — exp7b_scale_check_N5000                9 x 10 = 90 runs
;; 与 7a 完全相同，仅:
;; ["num-nodes" 5000]
;;
;; 总计 = 30 + 270 + 270 + 120 + 90 + 270 + 90 + 90
;;      = 1230 runs
;;
;; -------------------------------------------------------------
;; [两个实验管理原则]
;; 1. 不要把参数显式设为 0；fill-missing-parameters 会将 0 视作缺省。
;; 2. 因 setup 不 clear-all，每个 experiment 都显式列出完整参数，
;;    不依赖上一实验遗留的 global values。
;;
;; =============================================================
;; 建模假设备忘（论文 III.C / III.D / III.E / Limitations）
;; =============================================================
;; 1. legal-strength = L (%)：
;;    每次法律干预审查/处置全网 L% 的候选账号。
;;    sweep = 50/70/90，baseline = 70。
;;
;; 2. platform-speed = n_p (%)：
;;    每 tick 审核全网 n_p% 的账号。
;;    sweep = 50/75/100，baseline = 75。
;;
;; 3. 两者均为 percentage-based capacity，但时间机制不同：
;;    legal 每 tau_L ticks 执行一次；
;;    platform 每 tick 执行一次。
;;    因此不能把 L 与 n_p 解释为现实世界中完全相同的 throughput。
;;
;; 4. 基础传播过程为 SI-type diffusion：无自发恢复。
;;    treatment="none" 时污染状态为吸收态；
;;    legal/platform 可将 polluted 节点重置为 clean。
;;
;; 5. BA / ER / WS 均校准到近似相同平均度数 2*ba-m (=4)。
;;    ER / WS 结构诊断使用 mean-degree、degree-sd、count-isolates 等 reporter。
;;
;; 6. superspreader = degree centrality 排名前 super-ratio% 的节点；
;;    superspreader 身份只影响传播概率，不额外改变候选池。
;;
;; 7. targeting 与 treatment 严格正交：
;;    legal/platform 均从全网节点这一相同 candidate universe 出发；
;;    random = 随机抽取；
;;    targeted = degree-based top-n。
;;
;; 8. legal-accuracy 与 platform-accuracy 使用可比的二元错误结构：
;;    polluted candidate 错误 = false negative；
;;    clean candidate 错误 = false positive。
;;    但制度解释不同：
;;    alpha_L = 法律判断/程序准确率；
;;    alpha   = 平台识别准确率。
;;
;; 9. wrongly-removed? 记录用户是否至少经历过一次错误治理。
;;    被误伤节点不从网络拓扑中移除；模型衡量的是治理误伤暴露，
;;    而不是账号永久下线导致的拓扑变化。
;;
;; 10. over-removal-rate = unique wrongly affected users / N。
;;     removal-precision 为事件级指标，两者不可混同。
;;
;; 11. net-effectiveness = E - lambda*O 仅作为辅助复合指标。
;;     正文主分析优先分别报告 E 与 O。
;;
;; 12. 每个 run 输出 step 0-50 共 51 个 observation。
;;     step 0 用于初始状态/轨迹；如计算 50-tick 期内平均治理表现，
;;     建议主统计使用 step 1-50。
;; =============================================================
@#$#@#$#@
GRAPHICS-WINDOW
210
10
647
448
-1
-1
13.0
1
10
1
1
1
0
1
1
1
-16
16
-16
16
0
0
1
ticks
30.0

@#$#@#$#@
## WHAT IS IT?

(a general understanding of what the model is trying to show or explain)

## HOW IT WORKS

(what rules the agents use to create the overall behavior of the model)

## HOW TO USE IT

(how to use the model, including a description of each of the items in the Interface tab)

## THINGS TO NOTICE

(suggested things for the user to notice while running the model)

## THINGS TO TRY

(suggested things for the user to try to do (move sliders, switches, etc.) with the model)

## EXTENDING THE MODEL

(suggested things to add or change in the Code tab to make the model more complicated, detailed, accurate, etc.)

## NETLOGO FEATURES

(interesting or unusual features of NetLogo that the model uses, particularly in the Code tab; or where workarounds were needed for missing features)

## RELATED MODELS

(models in the NetLogo Models Library and elsewhere which are of related interest)

## CREDITS AND REFERENCES

(a reference to the model's URL on the web if it has one, as well as any other necessary credits, citations, and links)
@#$#@#$#@
default
true
0
Polygon -7500403 true true 150 5 40 250 150 205 260 250

airplane
true
0
Polygon -7500403 true true 150 0 135 15 120 60 120 105 15 165 15 195 120 180 135 240 105 270 120 285 150 270 180 285 210 270 165 240 180 180 285 195 285 165 180 105 180 60 165 15

arrow
true
0
Polygon -7500403 true true 150 0 0 150 105 150 105 293 195 293 195 150 300 150

box
false
0
Polygon -7500403 true true 150 285 285 225 285 75 150 135
Polygon -7500403 true true 150 135 15 75 150 15 285 75
Polygon -7500403 true true 15 75 15 225 150 285 150 135
Line -16777216 false 150 285 150 135
Line -16777216 false 150 135 15 75
Line -16777216 false 150 135 285 75

bug
true
0
Circle -7500403 true true 96 182 108
Circle -7500403 true true 110 127 80
Circle -7500403 true true 110 75 80
Line -7500403 true 150 100 80 30
Line -7500403 true 150 100 220 30

butterfly
true
0
Polygon -7500403 true true 150 165 209 199 225 225 225 255 195 270 165 255 150 240
Polygon -7500403 true true 150 165 89 198 75 225 75 255 105 270 135 255 150 240
Polygon -7500403 true true 139 148 100 105 55 90 25 90 10 105 10 135 25 180 40 195 85 194 139 163
Polygon -7500403 true true 162 150 200 105 245 90 275 90 290 105 290 135 275 180 260 195 215 195 162 165
Polygon -16777216 true false 150 255 135 225 120 150 135 120 150 105 165 120 180 150 165 225
Circle -16777216 true false 135 90 30
Line -16777216 false 150 105 195 60
Line -16777216 false 150 105 105 60

car
false
0
Polygon -7500403 true true 300 180 279 164 261 144 240 135 226 132 213 106 203 84 185 63 159 50 135 50 75 60 0 150 0 165 0 225 300 225 300 180
Circle -16777216 true false 180 180 90
Circle -16777216 true false 30 180 90
Polygon -16777216 true false 162 80 132 78 134 135 209 135 194 105 189 96 180 89
Circle -7500403 true true 47 195 58
Circle -7500403 true true 195 195 58

circle
false
0
Circle -7500403 true true 0 0 300

circle 2
false
0
Circle -7500403 true true 0 0 300
Circle -16777216 true false 30 30 240

cow
false
0
Polygon -7500403 true true 200 193 197 249 179 249 177 196 166 187 140 189 93 191 78 179 72 211 49 209 48 181 37 149 25 120 25 89 45 72 103 84 179 75 198 76 252 64 272 81 293 103 285 121 255 121 242 118 224 167
Polygon -7500403 true true 73 210 86 251 62 249 48 208
Polygon -7500403 true true 25 114 16 195 9 204 23 213 25 200 39 123

cylinder
false
0
Circle -7500403 true true 0 0 300

dot
false
0
Circle -7500403 true true 90 90 120

face happy
false
0
Circle -7500403 true true 8 8 285
Circle -16777216 true false 60 75 60
Circle -16777216 true false 180 75 60
Polygon -16777216 true false 150 255 90 239 62 213 47 191 67 179 90 203 109 218 150 225 192 218 210 203 227 181 251 194 236 217 212 240

face neutral
false
0
Circle -7500403 true true 8 7 285
Circle -16777216 true false 60 75 60
Circle -16777216 true false 180 75 60
Rectangle -16777216 true false 60 195 240 225

face sad
false
0
Circle -7500403 true true 8 8 285
Circle -16777216 true false 60 75 60
Circle -16777216 true false 180 75 60
Polygon -16777216 true false 150 168 90 184 62 210 47 232 67 244 90 220 109 205 150 198 192 205 210 220 227 242 251 229 236 206 212 183

fish
false
0
Polygon -1 true false 44 131 21 87 15 86 0 120 15 150 0 180 13 214 20 212 45 166
Polygon -1 true false 135 195 119 235 95 218 76 210 46 204 60 165
Polygon -1 true false 75 45 83 77 71 103 86 114 166 78 135 60
Polygon -7500403 true true 30 136 151 77 226 81 280 119 292 146 292 160 287 170 270 195 195 210 151 212 30 166
Circle -16777216 true false 215 106 30

flag
false
0
Rectangle -7500403 true true 60 15 75 300
Polygon -7500403 true true 90 150 270 90 90 30
Line -7500403 true 75 135 90 135
Line -7500403 true 75 45 90 45

flower
false
0
Polygon -10899396 true false 135 120 165 165 180 210 180 240 150 300 165 300 195 240 195 195 165 135
Circle -7500403 true true 85 132 38
Circle -7500403 true true 130 147 38
Circle -7500403 true true 192 85 38
Circle -7500403 true true 85 40 38
Circle -7500403 true true 177 40 38
Circle -7500403 true true 177 132 38
Circle -7500403 true true 70 85 38
Circle -7500403 true true 130 25 38
Circle -7500403 true true 96 51 108
Circle -16777216 true false 113 68 74
Polygon -10899396 true false 189 233 219 188 249 173 279 188 234 218
Polygon -10899396 true false 180 255 150 210 105 210 75 240 135 240

house
false
0
Rectangle -7500403 true true 45 120 255 285
Rectangle -16777216 true false 120 210 180 285
Polygon -7500403 true true 15 120 150 15 285 120
Line -16777216 false 30 120 270 120

leaf
false
0
Polygon -7500403 true true 150 210 135 195 120 210 60 210 30 195 60 180 60 165 15 135 30 120 15 105 40 104 45 90 60 90 90 105 105 120 120 120 105 60 120 60 135 30 150 15 165 30 180 60 195 60 180 120 195 120 210 105 240 90 255 90 263 104 285 105 270 120 285 135 240 165 240 180 270 195 240 210 180 210 165 195
Polygon -7500403 true true 135 195 135 240 120 255 105 255 105 285 135 285 165 240 165 195

line
true
0
Line -7500403 true 150 0 150 300

line half
true
0
Line -7500403 true 150 0 150 150

pentagon
false
0
Polygon -7500403 true true 150 15 15 120 60 285 240 285 285 120

person
false
0
Circle -7500403 true true 110 5 80
Polygon -7500403 true true 105 90 120 195 90 285 105 300 135 300 150 225 165 300 195 300 210 285 180 195 195 90
Rectangle -7500403 true true 127 79 172 94
Polygon -7500403 true true 195 90 240 150 225 180 165 105
Polygon -7500403 true true 105 90 60 150 75 180 135 105

plant
false
0
Rectangle -7500403 true true 135 90 165 300
Polygon -7500403 true true 135 255 90 210 45 195 75 255 135 285
Polygon -7500403 true true 165 255 210 210 255 195 225 255 165 285
Polygon -7500403 true true 135 180 90 135 45 120 75 180 135 210
Polygon -7500403 true true 165 180 165 210 225 180 255 120 210 135
Polygon -7500403 true true 135 105 90 60 45 45 75 105 135 135
Polygon -7500403 true true 165 105 165 135 225 105 255 45 210 60
Polygon -7500403 true true 135 90 120 45 150 15 180 45 165 90

sheep
false
15
Circle -1 true true 203 65 88
Circle -1 true true 70 65 162
Circle -1 true true 150 105 120
Polygon -7500403 true false 218 120 240 165 255 165 278 120
Circle -7500403 true false 214 72 67
Rectangle -1 true true 164 223 179 298
Polygon -1 true true 45 285 30 285 30 240 15 195 45 210
Circle -1 true true 3 83 150
Rectangle -1 true true 65 221 80 296
Polygon -1 true true 195 285 210 285 210 240 240 210 195 210
Polygon -7500403 true false 276 85 285 105 302 99 294 83
Polygon -7500403 true false 219 85 210 105 193 99 201 83

square
false
0
Rectangle -7500403 true true 30 30 270 270

square 2
false
0
Rectangle -7500403 true true 30 30 270 270
Rectangle -16777216 true false 60 60 240 240

star
false
0
Polygon -7500403 true true 151 1 185 108 298 108 207 175 242 282 151 216 59 282 94 175 3 108 116 108

target
false
0
Circle -7500403 true true 0 0 300
Circle -16777216 true false 30 30 240
Circle -7500403 true true 60 60 180
Circle -16777216 true false 90 90 120
Circle -7500403 true true 120 120 60

tree
false
0
Circle -7500403 true true 118 3 94
Rectangle -6459832 true false 120 195 180 300
Circle -7500403 true true 65 21 108
Circle -7500403 true true 116 41 127
Circle -7500403 true true 45 90 120
Circle -7500403 true true 104 74 152

triangle
false
0
Polygon -7500403 true true 150 30 15 255 285 255

triangle 2
false
0
Polygon -7500403 true true 150 30 15 255 285 255
Polygon -16777216 true false 151 99 225 223 75 224

truck
false
0
Rectangle -7500403 true true 4 45 195 187
Polygon -7500403 true true 296 193 296 150 259 134 244 104 208 104 207 194
Rectangle -1 true false 195 60 195 105
Polygon -16777216 true false 238 112 252 141 219 141 218 112
Circle -16777216 true false 234 174 42
Rectangle -7500403 true true 181 185 214 194
Circle -16777216 true false 144 174 42
Circle -16777216 true false 24 174 42
Circle -7500403 false true 24 174 42
Circle -7500403 false true 144 174 42
Circle -7500403 false true 234 174 42

turtle
true
0
Polygon -10899396 true false 215 204 240 233 246 254 228 266 215 252 193 210
Polygon -10899396 true false 195 90 225 75 245 75 260 89 269 108 261 124 240 105 225 105 210 105
Polygon -10899396 true false 105 90 75 75 55 75 40 89 31 108 39 124 60 105 75 105 90 105
Polygon -10899396 true false 132 85 134 64 107 51 108 17 150 2 192 18 192 52 169 65 172 87
Polygon -10899396 true false 85 204 60 233 54 254 72 266 85 252 107 210
Polygon -7500403 true true 119 75 179 75 209 101 224 135 220 225 175 261 128 261 81 224 74 135 88 99

wheel
false
0
Circle -7500403 true true 3 3 294
Circle -16777216 true false 30 30 240
Line -7500403 true 150 285 150 15
Line -7500403 true 15 150 285 150
Circle -7500403 true true 120 120 60
Line -7500403 true 216 40 79 269
Line -7500403 true 40 84 269 221
Line -7500403 true 40 216 269 79
Line -7500403 true 84 40 221 269

wolf
false
0
Polygon -16777216 true false 253 133 245 131 245 133
Polygon -7500403 true true 2 194 13 197 30 191 38 193 38 205 20 226 20 257 27 265 38 266 40 260 31 253 31 230 60 206 68 198 75 209 66 228 65 243 82 261 84 268 100 267 103 261 77 239 79 231 100 207 98 196 119 201 143 202 160 195 166 210 172 213 173 238 167 251 160 248 154 265 169 264 178 247 186 240 198 260 200 271 217 271 219 262 207 258 195 230 192 198 210 184 227 164 242 144 259 145 284 151 277 141 293 140 299 134 297 127 273 119 270 105
Polygon -7500403 true true -1 195 14 180 36 166 40 153 53 140 82 131 134 133 159 126 188 115 227 108 236 102 238 98 268 86 269 92 281 87 269 103 269 113

x
false
0
Polygon -7500403 true true 270 75 225 30 30 225 75 270
Polygon -7500403 true true 30 75 75 30 270 225 225 270
@#$#@#$#@
NetLogo 6.4.0
@#$#@#$#@
@#$#@#$#@
@#$#@#$#@
<experiments>
  <experiment name="experiment(t1.1" repetitions="10" runMetricsEveryStep="true">
    <setup>setup</setup>
    <go>go</go>
    <metric>count turtles</metric>
  </experiment>
  <experiment name="exp1_baseline" repetitions="10" runMetricsEveryStep="true">
    <setup>setup</setup>
    <go>go</go>
    <exitCondition>ticks &gt;= 50</exitCondition>
    <metric>effectiveness</metric>
    <metric>over-removal-rate</metric>
    <metric>net-effectiveness</metric>
    <metric>removal-precision</metric>
    <metric>error-rate</metric>
    <metric>current-pollution-rate</metric>
    <metric>count-wrongly-removed</metric>
    <metric>deleted-count</metric>
    <metric>false-deleted</metric>
    <enumeratedValueSet variable="treatment">
      <value value="&quot;none&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="targeting-mode">
      <value value="&quot;targeted&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="network-type">
      <value value="&quot;BA&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="p0">
      <value value="10"/>
      <value value="30"/>
      <value value="50"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="num-nodes">
      <value value="1000"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ba-m">
      <value value="2"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ws-rewire-prob">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="beta0">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="amplification">
      <value value="0.5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="super-ratio">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-strength">
      <value value="70"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-response-time">
      <value value="5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-accuracy">
      <value value="95"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-accuracy">
      <value value="80"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-speed">
      <value value="75"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="lambda-weight">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="max-ticks">
      <value value="50"/>
    </enumeratedValueSet>
  </experiment>
  <experiment name="exp2_legal_main" repetitions="10" runMetricsEveryStep="true">
    <setup>setup</setup>
    <go>go</go>
    <exitCondition>ticks &gt;= 50</exitCondition>
    <metric>effectiveness</metric>
    <metric>over-removal-rate</metric>
    <metric>net-effectiveness</metric>
    <metric>removal-precision</metric>
    <metric>error-rate</metric>
    <metric>current-pollution-rate</metric>
    <metric>count-wrongly-removed</metric>
    <metric>deleted-count</metric>
    <metric>false-deleted</metric>
    <enumeratedValueSet variable="treatment">
      <value value="&quot;legal&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="targeting-mode">
      <value value="&quot;targeted&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="network-type">
      <value value="&quot;BA&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="p0">
      <value value="10"/>
      <value value="30"/>
      <value value="50"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-strength">
      <value value="50"/>
      <value value="70"/>
      <value value="90"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-response-time">
      <value value="1"/>
      <value value="5"/>
      <value value="10"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-accuracy">
      <value value="95"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-accuracy">
      <value value="80"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-speed">
      <value value="75"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="num-nodes">
      <value value="1000"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ba-m">
      <value value="2"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ws-rewire-prob">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="beta0">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="amplification">
      <value value="0.5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="super-ratio">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="lambda-weight">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="max-ticks">
      <value value="50"/>
    </enumeratedValueSet>
  </experiment>
  <experiment name="exp3_platform_main" repetitions="10" runMetricsEveryStep="true">
    <setup>setup</setup>
    <go>go</go>
    <exitCondition>ticks &gt;= 50</exitCondition>
    <metric>effectiveness</metric>
    <metric>over-removal-rate</metric>
    <metric>net-effectiveness</metric>
    <metric>removal-precision</metric>
    <metric>error-rate</metric>
    <metric>current-pollution-rate</metric>
    <metric>count-wrongly-removed</metric>
    <metric>deleted-count</metric>
    <metric>false-deleted</metric>
    <enumeratedValueSet variable="treatment">
      <value value="&quot;platform&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="targeting-mode">
      <value value="&quot;targeted&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="network-type">
      <value value="&quot;BA&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="p0">
      <value value="10"/>
      <value value="30"/>
      <value value="50"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-accuracy">
      <value value="70"/>
      <value value="80"/>
      <value value="90"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-speed">
      <value value="50"/>
      <value value="75"/>
      <value value="100"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-strength">
      <value value="70"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-response-time">
      <value value="5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-accuracy">
      <value value="95"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="num-nodes">
      <value value="1000"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ba-m">
      <value value="2"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ws-rewire-prob">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="beta0">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="amplification">
      <value value="0.5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="super-ratio">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="lambda-weight">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="max-ticks">
      <value value="50"/>
    </enumeratedValueSet>
  </experiment>
  <experiment name="exp5_legal_accuracy_sensitivity" repetitions="10" runMetricsEveryStep="true">
    <setup>setup</setup>
    <go>go</go>
    <exitCondition>ticks &gt;= 50</exitCondition>
    <metric>effectiveness</metric>
    <metric>over-removal-rate</metric>
    <metric>net-effectiveness</metric>
    <metric>removal-precision</metric>
    <metric>error-rate</metric>
    <metric>current-pollution-rate</metric>
    <metric>count-wrongly-removed</metric>
    <metric>deleted-count</metric>
    <metric>false-deleted</metric>
    <enumeratedValueSet variable="treatment">
      <value value="&quot;legal&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="targeting-mode">
      <value value="&quot;targeted&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="network-type">
      <value value="&quot;BA&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="p0">
      <value value="10"/>
      <value value="30"/>
      <value value="50"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-accuracy">
      <value value="90"/>
      <value value="95"/>
      <value value="100"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-strength">
      <value value="70"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-response-time">
      <value value="5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-accuracy">
      <value value="80"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-speed">
      <value value="75"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="num-nodes">
      <value value="1000"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ba-m">
      <value value="2"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ws-rewire-prob">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="beta0">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="amplification">
      <value value="0.5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="super-ratio">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="lambda-weight">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="max-ticks">
      <value value="50"/>
    </enumeratedValueSet>
  </experiment>
  <experiment name="exp7a_scale-check(a)" repetitions="10" runMetricsEveryStep="true">
    <setup>setup</setup>
    <go>go</go>
    <exitCondition>ticks &gt;= 50</exitCondition>
    <metric>effectiveness</metric>
    <metric>over-removal-rate</metric>
    <metric>net-effectiveness</metric>
    <metric>removal-precision</metric>
    <metric>error-rate</metric>
    <metric>current-pollution-rate</metric>
    <metric>count-wrongly-removed</metric>
    <metric>deleted-count</metric>
    <metric>false-deleted</metric>
    <metric>mean-degree</metric>
    <metric>max-degree</metric>
    <metric>degree-sd</metric>
    <metric>count-isolates</metric>
    <metric>mean-super-degree</metric>
    <metric>legal-load</metric>
    <metric>audit-load</metric>
    <enumeratedValueSet variable="treatment">
      <value value="&quot;none&quot;"/>
      <value value="&quot;legal&quot;"/>
      <value value="&quot;platform&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="targeting-mode">
      <value value="&quot;targeted&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="network-type">
      <value value="&quot;BA&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="p0">
      <value value="10"/>
      <value value="30"/>
      <value value="50"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="num-nodes">
      <value value="1000"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-strength">
      <value value="70"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-response-time">
      <value value="5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-accuracy">
      <value value="95"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-accuracy">
      <value value="80"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-speed">
      <value value="75"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ba-m">
      <value value="2"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ws-rewire-prob">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="beta0">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="amplification">
      <value value="0.5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="super-ratio">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="lambda-weight">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="max-ticks">
      <value value="50"/>
    </enumeratedValueSet>
  </experiment>
  <experiment name="exp4_2*2" repetitions="10" runMetricsEveryStep="true">
    <setup>setup</setup>
    <go>go</go>
    <exitCondition>ticks &gt;= 50</exitCondition>
    <metric>effectiveness</metric>
    <metric>over-removal-rate</metric>
    <metric>net-effectiveness</metric>
    <metric>removal-precision</metric>
    <metric>error-rate</metric>
    <metric>current-pollution-rate</metric>
    <metric>count-wrongly-removed</metric>
    <metric>deleted-count</metric>
    <metric>false-deleted</metric>
    <enumeratedValueSet variable="treatment">
      <value value="&quot;legal&quot;"/>
      <value value="&quot;platform&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="targeting-mode">
      <value value="&quot;targeted&quot;"/>
      <value value="&quot;random&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="network-type">
      <value value="&quot;BA&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="p0">
      <value value="10"/>
      <value value="30"/>
      <value value="50"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-strength">
      <value value="70"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-response-time">
      <value value="5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-accuracy">
      <value value="95"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-accuracy">
      <value value="80"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-speed">
      <value value="75"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="num-nodes">
      <value value="1000"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ba-m">
      <value value="2"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ws-rewire-prob">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="beta0">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="amplification">
      <value value="0.5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="super-ratio">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="lambda-weight">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="max-ticks">
      <value value="50"/>
    </enumeratedValueSet>
  </experiment>
  <experiment name="exp6_networktype" repetitions="10" runMetricsEveryStep="true">
    <setup>setup</setup>
    <go>go</go>
    <exitCondition>ticks &gt;= 50</exitCondition>
    <metric>effectiveness</metric>
    <metric>over-removal-rate</metric>
    <metric>net-effectiveness</metric>
    <metric>removal-precision</metric>
    <metric>error-rate</metric>
    <metric>current-pollution-rate</metric>
    <metric>count-wrongly-removed</metric>
    <metric>deleted-count</metric>
    <metric>false-deleted</metric>
    <metric>mean-degree</metric>
    <metric>max-degree</metric>
    <metric>degree-sd</metric>
    <metric>count-isolates</metric>
    <metric>mean-super-degree</metric>
    <metric>legal-load</metric>
    <metric>audit-load</metric>
    <enumeratedValueSet variable="network-type">
      <value value="&quot;BA&quot;"/>
      <value value="&quot;ER&quot;"/>
      <value value="&quot;WS&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="treatment">
      <value value="&quot;none&quot;"/>
      <value value="&quot;legal&quot;"/>
      <value value="&quot;platform&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="targeting-mode">
      <value value="&quot;targeted&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="p0">
      <value value="10"/>
      <value value="30"/>
      <value value="50"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-strength">
      <value value="70"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-response-time">
      <value value="5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-accuracy">
      <value value="95"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-accuracy">
      <value value="80"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-speed">
      <value value="75"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="num-nodes">
      <value value="1000"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ba-m">
      <value value="2"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ws-rewire-prob">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="beta0">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="amplification">
      <value value="0.5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="super-ratio">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="lambda-weight">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="max-ticks">
      <value value="50"/>
    </enumeratedValueSet>
  </experiment>
  <experiment name="exp7b_scale-check(b)" repetitions="10" runMetricsEveryStep="true">
    <setup>setup</setup>
    <go>go</go>
    <exitCondition>ticks &gt;= 50</exitCondition>
    <metric>effectiveness</metric>
    <metric>over-removal-rate</metric>
    <metric>net-effectiveness</metric>
    <metric>removal-precision</metric>
    <metric>error-rate</metric>
    <metric>current-pollution-rate</metric>
    <metric>count-wrongly-removed</metric>
    <metric>deleted-count</metric>
    <metric>false-deleted</metric>
    <metric>mean-degree</metric>
    <metric>max-degree</metric>
    <metric>degree-sd</metric>
    <metric>count-isolates</metric>
    <metric>mean-super-degree</metric>
    <metric>legal-load</metric>
    <metric>audit-load</metric>
    <enumeratedValueSet variable="treatment">
      <value value="&quot;none&quot;"/>
      <value value="&quot;legal&quot;"/>
      <value value="&quot;platform&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="targeting-mode">
      <value value="&quot;targeted&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="network-type">
      <value value="&quot;BA&quot;"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="p0">
      <value value="10"/>
      <value value="30"/>
      <value value="50"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="num-nodes">
      <value value="5000"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-strength">
      <value value="70"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-response-time">
      <value value="5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="legal-accuracy">
      <value value="95"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-accuracy">
      <value value="80"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="platform-speed">
      <value value="75"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ba-m">
      <value value="2"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="ws-rewire-prob">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="beta0">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="amplification">
      <value value="0.5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="super-ratio">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="lambda-weight">
      <value value="1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="max-ticks">
      <value value="50"/>
    </enumeratedValueSet>
  </experiment>
</experiments>
@#$#@#$#@
@#$#@#$#@
default
0.0
-0.2 0 0.0 1.0
0.0 1 1.0 0.0
0.2 0 0.0 1.0
link direction
true
0
Line -7500403 true 150 150 90 180
Line -7500403 true 150 150 210 180
@#$#@#$#@
0
@#$#@#$#@
