from pathlib import Path
import csv, math, json, hashlib, collections
import numpy as np
from scipy.stats import t

ROOT = Path('/workspace/scratch/7bb7c0cf7233')
BASE = ROOT / 'tmp/supp_figures/source/supp_fig/data'
OUT = ROOT / 'tmp/supp_figures/audit'
DIRS = ['figS1_workload', 'figS4_accuracy_p10', 'figS4_accuracy_p30', 'figS4_accuracy_p50']
ATOL, RTOL = 1e-9, 1e-11
issues = []
def close(a, b):
    return math.isclose(float(a), float(b), abs_tol=ATOL, rel_tol=RTOL)
def read(p):
    with p.open(newline='') as f:
        return list(csv.DictReader(f))
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

source_rows = []
files = []
for d in DIRS:
    for p in sorted((BASE/d).glob('*.csv')):
        rows = read(p)
        source_rows += [(str(p.relative_to(ROOT)), r) for r in rows]
        files.append({'file': str(p.relative_to(ROOT)), 'rows': len(rows), 'sha256': digest(p)})
pairs = {(r['condition_id'], r['outcome']) for _, r in source_rows}
ids = {c for c, _ in pairs}
runpath = ROOT/'revision_review/results_v2/processed/run_metrics.csv'
sumpath = ROOT/'revision_review/results_v2/processed/condition_summary.csv'
runs = collections.defaultdict(list)
with runpath.open(newline='') as f:
    for r in csv.DictReader(f):
        if r['condition_id'] in ids:
            runs[r['condition_id']].append(r)
summary = {(r['condition_id'], r['outcome']):r for r in read(sumpath) if r['condition_id'] in ids}

# Recompute every plotted outcome, plus PR_final for all included conditions.
all_pairs = pairs | {(c,'PR_final') for c in ids}
details = []
max_errors = collections.defaultdict(float)
missing_values = {'', 'NA', 'NaN', 'nan'}
for c in sorted(ids, key=int):
    rr = runs[c]
    for name, vals in [('run_id', [r['run_id'] for r in rr]),
                       ('replicate_id', [r['replicate_id'] for r in rr]),
                       ('seed', [r['seed'] for r in rr])]:
        if len(vals) != 30 or len(set(vals)) != 30:
            issues.append({'condition_id':c, 'check':'30 unique '+name, 'n':len(vals), 'n_unique':len(set(vals))})
    if {int(r['final_step']) for r in rr} != {50}:
        issues.append({'condition_id':c, 'check':'final_step 50'})

global_unique_counts = {}
for field in ['run_id', 'seed']:
    values = [r[field] for rr in runs.values() for r in rr]
    global_unique_counts[field] = len(set(values))
    if len(values) != len(set(values)):
        issues.append({'check':'globally unique '+field,'records':len(values),'unique':len(set(values))})

for c, outcome in sorted(all_pairs, key=lambda v:(int(v[0]), v[1])):
    rr = runs[c]
    a = np.array([float(r[outcome]) for r in rr if r[outcome] not in missing_values], dtype=float)
    a = a[np.isfinite(a)]
    n = len(a)
    if n < 2:
        issues.append({'condition_id':c, 'outcome':outcome, 'check':'n>=2','n':n})
        continue
    mean = float(np.mean(a))
    sd = float(np.std(a, ddof=1))
    se = sd/math.sqrt(n)
    hw = float(t.ppf(.975, n-1))*se
    calculated = {'n':n, 'n_total':len(rr), 'n_missing':len(rr)-n,
                  'mean':mean, 'sd':sd, 'se':se, 'ci_low':mean-hw, 'ci_high':mean+hw}
    official = summary[(c,outcome)]
    errors = {}
    for k, v in calculated.items():
        expected = float(official[k])
        err = abs(v-expected)
        errors[k] = err
        max_errors[k] = max(max_errors[k], err)
        if not close(v, expected):
            issues.append({'condition_id':c, 'outcome':outcome, 'check':k,
                           'recomputed':v, 'official':expected, 'absolute_error':err})
    details.append({'condition_id':c, 'outcome':outcome, 'displayed_in_attachment':(c,outcome) in pairs,
                    'recomputed':calculated, 'official':official, 'absolute_errors':errors})

# Cross-check each attachment record against the official independent summary,
# including any division by 1,000 for review-event plot axes.
attachment_max_errors = collections.defaultdict(float)
for file, row in source_rows:
    c, o = row['condition_id'], row['outcome']
    formal = summary[(c,o)]
    for k in ['n','n_total','n_missing','mean','sd','se','ci_low','ci_high']:
        error = abs(float(row[k])-float(formal[k]))
        attachment_max_errors[k] = max(attachment_max_errors[k], error)
        if not close(row[k], formal[k]):
            issues.append({'file':file, 'condition_id':c, 'outcome':o, 'check':'attachment '+k})
    if row['ci_status'] != formal['ci_status']:
        issues.append({'file':file, 'condition_id':c, 'outcome':o, 'check':'ci_status'})
    scale = float(row['plot_scale'])
    for k, expected in [('value', float(row['mean'])/scale),
                        ('lower', float(row['ci_low'])/scale),
                        ('upper', float(row['ci_high'])/scale),
                        ('error_minus', (float(row['mean'])-float(row['ci_low']))/scale),
                        ('error_plus', (float(row['ci_high'])-float(row['mean']))/scale)]:
        error = abs(float(row[k])-expected)
        attachment_max_errors[k] = max(attachment_max_errors[k],error)
        if not close(row[k],expected):
            issues.append({'file':file, 'condition_id':c, 'outcome':o, 'check':'plot transform '+k})
    if scale != (1000 if o in ['cumulative_reviews','clean_review_exposure'] else 1):
        issues.append({'file':file, 'condition_id':c, 'outcome':o, 'check':'expected plot scale'})
    first = runs[c][0]
    for k in ['p0','treatment','network-type','num-nodes','legal-strength','legal-response-time',
              'legal-tpr','legal-tnr','platform-speed','platform-tpr','platform-tnr',
              'platform-workload-mode','demand-kappa','targeting-mode','configuration_hash']:
        if row[k] != first[k]:
            try:
                equivalent = close(row[k], first[k])
            except ValueError:
                equivalent = False
            if not equivalent:
                issues.append({'file':file, 'condition_id':c, 'outcome':o, 'check':'metadata '+k,
                               'attachment':row[k], 'run':first[k]})

semantic_max_errors = collections.defaultdict(float)
semantic_n = collections.Counter()
pr_n = {}
for c, rr in sorted(runs.items(), key=lambda v:int(v[0])):
    n_defined = 0
    for r in rr:
        tp, fp, tn, fn = [float(r[k]) for k in ['cumulative_tp','cumulative_fp','cumulative_tn','cumulative_fn']]
        checks = {
            'O_final = 100 * distinct_wronged / num-nodes':(float(r['O_final']), 100*float(r['distinct_wronged'])/float(r['num-nodes'])),
            'cumulative_reviews = TP + FP + TN + FN':(float(r['cumulative_reviews']),tp+fp+tn+fn),
            'clean_review_exposure = FP + TN':(float(r['clean_review_exposure']),fp+tn),
        }
        if tp+fp > 0:
            n_defined += 1
            checks['PR_final = 100 * TP / (TP + FP)'] = (float(r['PR_final']), 100*tp/(tp+fp))
            if r['PR_defined'].lower() != 'true':
                issues.append({'run_id':r['run_id'],'check':'PR_defined flag'})
        elif r['PR_final'] not in missing_values or r['PR_defined'].lower() != 'false':
            issues.append({'run_id':r['run_id'],'check':'undefined PR represented as missing'})
        for name,(v,e) in checks.items():
            error = abs(v-e)
            semantic_max_errors[name] = max(semantic_max_errors[name],error)
            semantic_n[name] += 1
            if not close(v,e):
                issues.append({'run_id':r['run_id'],'check':name,'value':v,'expected':e})
        for name in ['cumulative_reviews','clean_review_exposure','distinct_wronged']:
            v = float(r[name])
            if v < 0 or not v.is_integer():
                issues.append({'run_id':r['run_id'],'check':'nonnegative integer '+name})
    pr_n[c] = n_defined
    if int(summary[(c,'PR_final')]['n']) != n_defined:
        issues.append({'condition_id':c,'check':'PR effective n from TP+FP'})

group_stats = {}
for d in DIRS:
    rr = [r for file,r in source_rows if '/'+d+'/' in file]
    group_stats[d] = {'csv_files':sum('/'+d+'/' in f['file'] for f in files),
                      'attachment_rows':len(rr), 'unique_conditions':len({r['condition_id'] for r in rr}),
                      'outcomes': sorted({r['outcome'] for r in rr})}
report = {
    'status':'PASS' if not issues else 'FAIL',
    'scope':'Recomputation from existing run_metrics; no simulations rerun; no TeX changes',
    'method':'Mean, sample SD (ddof=1), SE=SD/sqrt(n), CI=mean +/- t_(.975,n-1)*SE; intervals not clipped',
    'comparison_tolerance':{'absolute':ATOL, 'relative':RTOL,
                            'rationale':'Allows 12-significant-digit serialization in the official summary; far below displayed precision'},
    'counts':{'attachment_files':len(files),'attachment_rows':len(source_rows),
              'unique_displayed_condition_outcome_pairs':len(pairs),'unique_conditions':len(ids),
              'unique_runs':sum(len(rr) for rr in runs.values()),'recomputed_condition_outcome_pairs':len(all_pairs),
              'extra_PR_checks':len(all_pairs-pairs),
              'displayed_outcome_samples_not_unique_runs':sum(len(runs[c]) for c,o in pairs),
              'global_unique_run_ids':global_unique_counts['run_id'],
              'global_unique_seeds':global_unique_counts['seed']},
    'group_stats':group_stats, 'condition_ids':sorted(ids,key=int),
    'PR_effective_n_counts':dict(collections.Counter(pr_n.values())),
    'max_absolute_recomputation_errors':dict(max_errors),
    'max_absolute_attachment_vs_summary_or_transform_errors':dict(attachment_max_errors),
    'semantic_checks':{'counts':dict(semantic_n),'max_absolute_errors':dict(semantic_max_errors)},
    'units':{'E_mean':'percentage', 'O_final':'percentage of all accounts distinctly wronged by step 50',
             'PR_final':'percentage; average of defined run-level ratios',
             'cumulative_reviews':'cumulative review events, including repeat reviews; figure divided by 1000',
             'clean_review_exposure':'cumulative review events on clean accounts = FP+TN; figure divided by 1000'},
    'formal_sources':[{'file':str(p.relative_to(ROOT)),'sha256':digest(p)} for p in [runpath,sumpath]],
    'attachment_files':files,'details':details,'issues':issues
}
(OUT/'condition_runlevel_recheck.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
lines = [
    '# 条件组原始运行输出复核', '', f'结果：**{report["status"]}**。发现问题 {len(issues)} 项。', '',
    '从已有 `run_metrics.csv` 独立重新计算；未重跑仿真，未改附件、绘图代码或输出。', '',
    f'- 覆盖 {len(files)} 份附件 CSV、{len(source_rows)} 条图数据，去重后 {len(pairs)} 个条件—指标组合。',
    f'- 覆盖 {len(ids)} 个独立条件、{sum(len(rr) for rr in runs.values())} 条已有运行记录；每个条件均有 30 个独立 run_id、replicate_id 和 seed。',
    f'- 全部条件间 run_id 和 seed 也分别全局唯一；216×30=6,480 是图示指标观测数，独立条件运行数为 90×30=2,700，不能重复计作 6,480 次仿真。',
    f'- 附加核查所有条件的 PR_final，共复算 {len(all_pairs)} 个条件—指标组合。',
    '- 使用样本标准差（ddof=1）、SE=SD/√n 和 95% Student-t 区间（自由度 n−1），未截断区间。',
    f'- 比较容差：绝对 {ATOL:g}，相对 {RTOL:g}；用于吸收正式 CSV 的 12 位有效数字序列化误差。', '',
    '| 图数据目录 | 文件数 | 图数据行 | 条件数 |', '|---|---:|---:|---:|',
]
for d,g in group_stats.items():
    lines.append(f'| {d} | {g["csv_files"]} | {g["attachment_rows"]} | {g["unique_conditions"]} |')
lines += ['', '数值复核最大绝对误差：', '', '| 字段 | 误差 |','|---|---:|']
for k,v in max_errors.items(): lines.append(f'| {k} | {v:.12g} |')
lines += ['', '指标定义与单位：', '',
    '- 所有涉及条件的 PR_final 有效 n 均为 30；逐运行核对 PR_defined 与 TP+FP>0 一致，且 PR_final=100×TP/(TP+FP)。图值为运行级比率均值。',
    '- O_final=100×distinct_wronged/N，为截至第 50 步遭受误伤的不同账户占全部账户的百分比，不是事件计数。',
    '- cumulative_reviews=TP+FP+TN+FN；clean_review_exposure=FP+TN。二者为累计事件数，包含重复审查，不能解释为不同账户数。',
    '- 附件两个事件计数的 plot_scale=1000，点值、上下限和误差长度均正确除以 1000；其余指标 plot_scale=1。',
    '- 附件中的 n、n_total、n_missing、mean、sd、se、ci_low、ci_high、ci_status 与正式汇总一致；条件元数据与原始运行输出一致。',
    '', '附件与正式汇总、坐标换算的最大绝对误差：', '', '| 字段 | 误差 |','|---|---:|']
for k,v in attachment_max_errors.items(): lines.append(f'| {k} | {v:.12g} |')
lines += ['', '检查边界：本核查由现有 run_metrics 向上复算，不重新验证仿真引擎或重新构建每一步轨迹。各条件运行数可相加，但同一条件用于多个指标或图时只计一次；不能将显示的点数乘以 30 当作新增独立运行数。', '',
          '逐项结果、条件 ID、原始及附件 SHA-256 均记录于同目录 JSON。']
if issues:
    lines += ['', '问题：','```json',json.dumps(issues,ensure_ascii=False,indent=2),'```']
(OUT/'condition_runlevel_recheck.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({k:report[k] for k in ['status','counts','PR_effective_n_counts','max_absolute_recomputation_errors','semantic_checks','issues']},ensure_ascii=False,indent=2))
