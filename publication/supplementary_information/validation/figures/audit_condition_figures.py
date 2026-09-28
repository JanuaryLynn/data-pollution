from pathlib import Path
import csv,json,re,math,hashlib,collections
R=Path('/workspace/scratch/7bb7c0cf7233'); B=R/'tmp/supp_figures/source/supp_fig'; O=R/'tmp/supp_figures/audit'; P=R/'revision_review/results_v2/processed'
read=lambda p:list(csv.DictReader(p.open())); sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
formal={(x['condition_id'],x['outcome']):x for x in read(P/'condition_summary.csv')}
metadata={}
with (P/'run_metrics.csv').open() as fh:
 for row in csv.DictReader(fh):metadata.setdefault(row['condition_id'],row)
# Tolerances chosen well below visible precision; comparisons use original scale unless stated.
ATOL=1e-10;RTOL=1e-12
issues=[];notes=[];rows_all=[];filechecks=[];maxdev=collections.defaultdict(float);comparisoncounts=collections.Counter()
def match(a,b,kind):
 try:
  aa=float(a);bb=float(b)
  if math.isnan(aa) or math.isnan(bb):return math.isnan(aa) and math.isnan(bb)
  dev=abs(aa-bb);maxdev[kind]=max(maxdev[kind],dev);comparisoncounts[kind]+=1
  return dev<=ATOL+RTOL*abs(bb)
 except (ValueError,TypeError):comparisoncounts[kind]+=1;return a==b
folders=['figS1_workload']+[f'figS4_accuracy_p{p}' for p in (10,30,50)]
for folder in folders:
 for f in sorted((B/'data'/folder).glob('*.csv')):
  rows=read(f);local=[];checks=[]
  expected_n=4 if folder=='figS1_workload' else 9
  if len(rows)!=expected_n:local.append('Unexpected displayed record count')
  coords=[];keys=[]
  for i,row in enumerate(rows,1):
   key=(row['condition_id'],row['outcome']);keys.append(key);src=formal[key];meta=metadata[row['condition_id']];detail=[]
   for col,val in src.items():
    if col not in row or not match(row[col],val,'summary_fields'):detail.append('source summary mismatch: '+col)
   # Metadata is independently taken from the first formal run record for the condition.
   for col,val in row.items():
    if col in meta and col not in src:
     if not match(val,meta[col],'metadata_fields'):detail.append('condition metadata mismatch: '+col)
   outcome=row['outcome'];scale=1000 if outcome in ('cumulative_reviews','clean_review_exposure') else 1
   if float(row['plot_scale'])!=scale:detail.append('plot_scale incorrect')
   want={'value':float(src['mean'])/scale,'lower':float(src['ci_low'])/scale,'upper':float(src['ci_high'])/scale,
         'error_minus':(float(src['mean'])-float(src['ci_low']))/scale,'error_plus':(float(src['ci_high'])-float(src['mean']))/scale}
   for col,val in want.items():
    if not match(row[col],val,'plot_transform_fields'):detail.append('plot transform mismatch: '+col)
   if float(row['error_minus'])<0 or float(row['error_plus'])<0:detail.append('Negative error-bar length')
   x=int(row['plot_x']);y=int(row['plot_y']);coords.append((x,y))
   if folder=='figS1_workload':
    expected_p=int(re.search(r'_p(\d+)',f.stem).group(1));expected_out=re.sub(r'_p\d+$','',f.stem)
    state=row['platform-workload-mode'];k=int(float(row['demand-kappa']))
    expected_x=0 if state=='fixed' else {1:1,2:2,5:3}.get(k)
    expected_label='Fixed' if state=='fixed' else f'kappa={k}'
    if (x,y)!=(expected_x,0):detail.append('Workload category coordinates incorrect')
    if row['workload_label']!=expected_label:detail.append('Workload label incorrect')
    if row['treatment']!='platform' or float(row['platform-speed'])!=75:detail.append('Unexpected workload treatment/coverage')
   else:
    expected_p=int(folder.rsplit('p',1)[1]);actor,expected_out=f.stem.split('_',1)
    regime='legal' if actor=='legal70' else 'platform';coverage=70 if actor=='legal70' else 50 if actor=='platform50' else 75
    rates=[90,95,100] if regime=='legal' else [70,80,90]
    if row['treatment']!=regime:detail.append('Heatmap actor mismatch')
    if float(row['legal-strength'] if regime=='legal' else row['platform-speed'])!=coverage:detail.append('Heatmap coverage mismatch')
    if float(row[f'{regime}-tnr'])!=rates[x] or float(row[f'{regime}-tpr'])!=rates[y]:detail.append('Heatmap x=TNR/y=TPR mapping incorrect')
   if float(row['p0'])!=expected_p or outcome!=expected_out:detail.append('Filename p0/outcome mapping incorrect')
   if row['n_total']!='30':detail.append('Unexpected total run count')
   checks.append({'row':i,'condition_id':key[0],'outcome':outcome,'plot_x':x,'plot_y':y,'scale':scale,'status':'PASS' if not detail else 'FAIL','issues':detail})
   local += [f'row {i}: {z}' for z in detail];rows_all.append(row)
  if len(set(keys))!=len(keys):local.append('Duplicate condition/outcome key in file')
  expected_coords=[(i,0) for i in range(4)] if folder=='figS1_workload' else [(x,y) for y in range(3) for x in range(3)]
  if coords!=expected_coords:local.append('CSV mesh/category order incorrect')
  filechecks.append({'file':str(f),'sha256':sha(f),'rows':len(rows),'status':'PASS' if not local else 'FAIL','issues':local,'row_checks':checks})
  issues += [f'{folder}/{f.name}: {z}' for z in local]

texchecks=[];numeric_labels=0;pr_labels=0
num=r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'
for folder in folders:
 f=B/(folder+'.tex');s=f.read_text();local=[];panels=s.split('\\nextgroupplot')[1:];panelchecks=[]
 expected_panels=15 if folder=='figS1_workload' else 6
 if len(panels)!=expected_panels:local.append('Panel count mismatch')
 if folder=='figS1_workload':
  if r'xticklabels={Fixed,$\kappa=1$,$\kappa=2$,$\kappa=5$}' not in s:local.append('Workload tick category labels mismatch')
 else:
  if r'xlabel={True-negative rate (\%)}' not in s or r'ylabel={True-positive rate (\%)}' not in s:local.append('Accuracy axis labels mismatch')
  if r'point meta min=0,point meta max=100' not in s:local.append('Heatmap color domain mismatch')
  if r'ylabel={Outcome (\%)}' not in s:local.append('Heatmap outcome colorbar unit missing')
  expected_p=folder.rsplit('p',1)[1]
  if f'$p_0={expected_p}\\%$: separate TPR and TNR' not in s:local.append('Figure p0 heading mismatch')
 for pi,panel in enumerate(panels):
  paths=re.findall(r'\{(data/[^}]+\.csv)\}',panel)
  if len(paths)!=1:local.append(f'panel {pi+1}: data file count not one');continue
  rows=read(B/paths[0]);coords={(float(x['plot_x']),float(x['plot_y'])):x for x in rows}
  outcome=rows[0]['outcome'];check={'panel':pi+1,'file':paths[0],'outcome':outcome,'n_points':len(rows)}
  if folder=='figS1_workload':
   expected_order=[f'{o}_p{p}.csv' for o in ('E_mean','O_final','PR_final','cumulative_reviews','clean_review_exposure') for p in (10,30,50)]
   if Path(paths[0]).name!=expected_order[pi]:local.append(f'panel {pi+1}: outcome/p0 position wrong')
   expected_p=int(rows[0]['p0'])
   if f'$p_0={expected_p}\\%$' not in panel:local.append(f'panel {pi+1}: p0 title mismatch')
   ymin=float(re.search(r'ymin=('+num+')',panel).group(1));ymax=float(re.search(r'ymax=('+num+')',panel).group(1))
   for row in rows:
    if not ymin<=float(row['lower'])<=float(row['upper'])<=ymax:local.append(f'panel {pi+1}: interval clipped by y axis')
   nodes=re.findall(r'at \(axis cs:('+num+'),('+num+r')\) \{\$n=(\d+)\$\}',panel)
   if outcome=='PR_final':
    if len(nodes)!=4:local.append(f'panel {pi+1}: nPR label count incorrect')
    for x,y,n in nodes:
     row=coords[(float(x),0.0)];pr_labels+=1
     if not match(y,row['upper'],'hardcoded_labels') or n!=row['n']:local.append(f'panel {pi+1}: nPR label mismatch')
   elif nodes:local.append(f'panel {pi+1}: extraneous nPR labels')
   if pi%3==0:
    ylabel={'E_mean':r'Mean effectiveness (\%)','O_final':r'Collateral exposure (\%)','PR_final':r'Removal precision (\%)','cumulative_reviews':'Reviews (thousands)','clean_review_exposure':'Clean reviews (thousands)'}[outcome]
    if 'ylabel={'+ylabel+'}' not in panel:local.append(f'panel {pi+1}: outcome units mismatch')
  else:
   expected_order=[f'{a}_{o}.csv' for a in ('legal70','platform50','platform75') for o in ('E_mean','O_final')]
   if Path(paths[0]).name!=expected_order[pi]:local.append(f'panel {pi+1}: actor/outcome position wrong')
   actor=rows[0]['treatment'];rates='90,95,100' if actor=='legal' else '70,80,90'
   if 'xticklabels={'+rates+'}' not in panel or 'yticklabels={'+rates+'}' not in panel:local.append(f'panel {pi+1}: categorical rate ticks incorrect')
   expected_title=('Legal, 70' if actor=='legal' else 'Platform, '+str(int(float(rows[0]['platform-speed']))))+r'\%: '+(r'$\bar E$' if outcome=='E_mean' else '$O(50)$')
   if expected_title not in panel:local.append(f'panel {pi+1}: title actor/coverage/outcome mismatch')
   nodes=re.findall(r'at \(axis cs:('+num+'),('+num+r')\) \{\\pgfmathprintnumber\[([^\]]+)\]\{('+num+r')\}\}',panel)
   if len(nodes)!=9:local.append(f'panel {pi+1}: heatmap label count incorrect')
   for x,y,fmt,value in nodes:
    row=coords[(float(x),float(y))];numeric_labels+=1
    if not match(value,row['value'],'hardcoded_labels'):local.append(f'panel {pi+1}: hardcoded heatmap number mismatch')
    if 'precision=1' not in fmt or 'fixed zerofill' not in fmt:local.append(f'panel {pi+1}: heatmap label precision inconsistent')
  panelchecks.append(check)
 texchecks.append({'file':str(f),'sha256':sha(f),'status':'PASS' if not local else 'FAIL','issues':local,'panels':panelchecks})
 issues += [f.name+': '+z for z in local]
keys={(r['condition_id'],r['outcome']) for r in rows_all};conditions={r['condition_id'] for r in rows_all}
notes=['O_final / O(50) is a percentage of distinct accounts ever wronged by step 50; it is not a count of wrongful review events.', 'cumulative_reviews and clean_review_exposure count review events over steps 1–50, including repeat reviews; plot_scale=1000 means thousands of events, not a percentage.', 'PR_final is the mean of defined run-level precision ratios; all 12 displayed S1 precision cells have n=30, n_total=30, n_missing=0.', 'S1 Fixed has demand-kappa=1 recorded but kappa is inactive in fixed mode; the displayed Fixed category correctly avoids interpreting it as responsive kappa=1.', 'S2–S4 retain CI endpoints in CSV but show only means on the heatmaps; the hardcoded numeric labels display one decimal.', 'The attachment lacks figure_style.tex; these standalone sources require the established shared style file to compile.']
report={'status':'PASS' if not issues else 'FAIL','scope':'S1–S4 plot CSV versus condition_summary, formal run metadata, transformations, categorical coordinates, TeX file mappings and hardcoded labels; separate run-level independent recalculation is reported in condition_runlevel_recheck.json.','csv_files':len(filechecks),'plotted_records':len(rows_all),'unique_condition_outcome_pairs':len(keys),'unique_conditions':len(conditions),'tex_figures':len(texchecks),'heatmap_hardcoded_labels_checked':numeric_labels,'precision_n_labels_checked':pr_labels,'source_summary_path':str(P/'condition_summary.csv'),'source_summary_sha256':sha(P/'condition_summary.csv'),'source_run_metrics_path':str(P/'run_metrics.csv'),'source_run_metrics_sha256':sha(P/'run_metrics.csv'),'numeric_tolerance':{'absolute':ATOL,'relative':RTOL},'max_absolute_deviations':dict(maxdev),'comparison_counts':dict(comparisoncounts),'issues':issues,'semantic_notes':notes,'data_files':filechecks,'tex_files':texchecks}
(O/'condition_figures_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
md=['# 补充图 S1–S4 数据与绘图映射核查','',f"结果：**{report['status']}**。33 份绘图 CSV、222 条图示结果记录（{len(keys)} 个唯一 condition_id/outcome、{len(conditions)} 个唯一条件），共 4 个 TeX 文件。",'','逐字段比对正式 condition_summary.csv；条件参数独立取自正式 run_metrics.csv。核对原始数值、缩放后均值及区间端点、误差长度、参数坐标、面板顺序、162 个热图硬编码数值标签与 12 个 nPR 标签。','',f'容差：绝对 {ATOL:g} + 相对 {RTOL:g}×来源绝对值。最大绝对偏差：'+str(dict(maxdev)),'','## 单位与语义','']+['- '+x for x in notes]+['','## 问题','']+(issues or ['未发现数据、缩放、坐标或硬编码标签错误。'])+['','运行级独立重算另见 condition_runlevel_recheck.{json,md}；未重新运行模拟。']
(O/'condition_figures_audit.md').write_text('\n'.join(md))
print(json.dumps({k:v for k,v in report.items() if k not in ('data_files','tex_files','semantic_notes')},ensure_ascii=False,indent=2))
