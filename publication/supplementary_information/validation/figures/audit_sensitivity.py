from pathlib import Path
import pandas as pd, numpy as np, json, re, hashlib, importlib.util
ROOT=Path('/workspace/scratch/7bb7c0cf7233')
SRC=ROOT/'tmp/supp_figures/source/supp_fig'
OUT=ROOT/'tmp/supp_figures/audit'
PRO=ROOT/'revision_review/results_v2/processed'
DES=ROOT/'revision_review/implementation/design'
report={'scope':'Supplementary figures S5-S11; supplied plot CSV and TeX mappings versus saved experimental analysis outputs, run-level metrics and archived bootstrap draws','tolerance':{'plot_vs_processed':'exact parsed numeric equality including NaN','reconstruction_vs_12_sigfig_csv':'absolute 5e-10 for means and inputs; absolute 5e-12 for indices/intervals'},'new_simulations_run':False,'bootstrap_rerun':False,'errors':[],'checks':[],'plot_files':[],'figure_summaries':{}}
def check(name,ok,detail=None):
 r={'check':name,'passed':bool(ok)}
 if detail is not None:r['detail']=detail
 report['checks'].append(r)
 if not ok:report['errors'].append(r)
def eq(a,b,tol=0):
 a=np.asarray(a);b=np.asarray(b)
 return a.shape==b.shape and bool(np.allclose(a,b,rtol=0,atol=tol,equal_nan=True))
def check_df(name,a,b):
 ok=list(a.columns)==list(b.columns) and len(a)==len(b)
 if ok:
  for c in a:
   if pd.api.types.is_numeric_dtype(a[c]) and pd.api.types.is_numeric_dtype(b[c]):ok=ok and eq(a[c],b[c])
   else:ok=ok and a[c].fillna('<NA>').astype(str).tolist()==b[c].fillna('<NA>').astype(str).tolist()
 check(name,ok,{'rows':len(a),'columns':len(a.columns)})
 return ok
ind=pd.read_csv(PRO/'sensitivity_indices.csv')
dia=pd.read_csv(PRO/'sensitivity_diagnostics.csv')
resp=pd.read_csv(PRO/'sensitivity_design_responses.csv')
bins=pd.read_csv(PRO/'sensitivity_response_bins.csv')
prcc=ind[ind.method=='PRCC']
inputs={'legal':['legal-strength','legal-response-time','alpha_legal'],'platform':['platform-speed','alpha_platform']}
ylookup={'legal-strength':4,'legal-response-time':3,'alpha_legal':2,'platform-speed':1,'alpha_platform':0}
figs=['figS2b_PRCC','figS2d_bins_E_mean','figS2d_bins_O_final','sensitivity_response_legal_E_mean','sensitivity_response_legal_O_final','sensitivity_response_platform_E_mean','sensitivity_response_platform_O_final']
for ix,fig in enumerate(figs,5):
 files=sorted((SRC/'data'/fig).glob('*.csv'))
 tex=(SRC/f'{fig}.tex').read_text()
 refs=re.findall(r'\{(data/[^{}]+\.csv)\}',tex)
 check(f'S{ix}: plotted CSV reference coverage',set(refs)=={str(f.relative_to(SRC)) for f in files if f.name!='source.csv'} and len(refs)==len(set(refs)),{'files':len(files),'references':len(refs)})
 report['figure_summaries'][f'S{ix}']={'filename':fig,'csv_file_count':len(files),'point_estimates':0,'ci_endpoints':0}
 for f in files:
  a=pd.read_csv(f)
  if f.name=='source.csv':
   b=prcc.reset_index(drop=True) if fig=='figS2b_PRCC' else dia[dia.outcome==('E_mean' if fig.endswith('E_mean') else 'O_final')].reset_index(drop=True)
  elif fig=='figS2b_PRCC':
   m=re.fullmatch(r'(E_mean|O_final)_p(10|30|50)_(legal|platform)_(points|row_ci|mc_ci)',f.stem);out,p,actor,kind=m.groups();p=int(p)
   base=prcc[(prcc.actor==actor)&(prcc.p0==p)&(prcc.outcome==out)].set_index('input').loc[inputs[actor]].reset_index()
   if kind=='points':
    b=pd.DataFrame({'estimate':base.estimate,'y':[ylookup[x] for x in base.input]})
    report['figure_summaries'][f'S{ix}']['point_estimates']+=len(base)
   else:
    rows=[];typ=kind.split('_')[0];offset=.08 if typ=='row' else -.08
    for _,r in base.iterrows():rows.extend([[r[f'{typ}_ci95_low'],ylookup[r.input]+offset],[r[f'{typ}_ci95_high'],ylookup[r.input]+offset],[np.nan,np.nan]])
    b=pd.DataFrame(rows,columns=['x','y']);report['figure_summaries'][f'S{ix}']['ci_endpoints']+=2*len(base)
  elif fig.startswith('figS2d'):
   m=re.fullmatch(r'(legal|platform)_p(10|30|50)_(.+)_(median|mean|maximum)',f.stem);actor,p,inp,agg=m.groups();out='E_mean' if fig.endswith('E_mean') else 'O_final'
   b=dia[(dia.actor==actor)&(dia.p0==int(p))&(dia.input==inp)&(dia.aggregation==agg)&(dia.outcome==out)].sort_values('bins').reset_index(drop=True)
   report['figure_summaries'][f'S{ix}']['point_estimates']+=len(b)
  else:
   m=re.fullmatch(r'sensitivity_response_(legal|platform)_(E_mean|O_final)',fig);actor,out=m.groups()
   m=re.fullmatch(r'p(10|30|50)_(.+)_(points|bins)',f.stem);p,inp,kind=m.groups();p=int(p)
   if kind=='points':
    b=resp[(resp.actor==actor)&(resp.p0==p)][['condition_id','lhs_point_id',inp,out]].rename(columns={inp:'x',out:'y'}).reset_index(drop=True)
    report['figure_summaries'][f'S{ix}']['point_estimates']+=len(b)
    check(f'{f.name}: exactly 500 unique parameter points',len(a)==500 and a.condition_id.nunique()==500 and a.lhs_point_id.tolist()==list(range(1,501)))
   else:b=bins[(bins.actor==actor)&(bins.p0==p)&(bins.input==inp)&(bins.outcome==out)].sort_values('bin').reset_index(drop=True)
  ok=check_df(str(f.relative_to(SRC)),a,b)
  report['plot_files'].append({'path':str(f.relative_to(SRC)),'rows':len(a),'passed':ok,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
# Reconstruct responses and deterministic point statistics from run-level outputs; no resampling.
cols=['condition_id','replicate_id','lhs_point_id','sensitivity_actor','p0','E_mean','O_final','legal-strength','legal-response-time','legal-tpr','legal-tnr','platform-speed','platform-tpr','platform-tnr']
runs=pd.read_csv(PRO/'run_metrics.csv',usecols=cols)
runs=runs[runs.sensitivity_actor.isin(inputs)]
check('Run-level sensitivity scope',len(runs)==90000 and runs.condition_id.nunique()==3000,{'run_count':len(runs),'condition_count':runs.condition_id.nunique()})
spec=importlib.util.spec_from_file_location('audit_analysis',ROOT/'revision_review/results_v2/scripts/analyze_sensitivity.py');analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(analysis)
archive=np.load(PRO/'sensitivity_bootstrap_draws.npz')
maxerr={'mean_response':0.,'input_parameter':0.,'PRCC_estimate':0.,'PAWN_diagnostic_estimate':0.,'archived_interval_endpoint':0.,'bin_summary':0.}
for actor,names in inputs.items():
 lhs=pd.read_csv(DES/f'lhs_{actor}.csv').sort_values('lhs_point_id')
 x=lhs[names].to_numpy(float);masks,groups,records=analysis.make_bins(x,names)
 for p in [10,30,50]:
  stratum=f'{actor}_p{p:03d}'
  rr=runs[(runs.sensitivity_actor==actor)&(runs.p0==p)].sort_values(['lhs_point_id','replicate_id'])
  dr=resp[(resp.actor==actor)&(resp.p0==p)].sort_values('lhs_point_id')
  check(f'{stratum}: 500 points x 30 runs and replicate identities',rr.groupby('lhs_point_id').replicate_id.apply(list).tolist()==[list(range(1,31))]*500)
  first=rr.drop_duplicates('lhs_point_id')
  check(f'{stratum}: condition_id/LHS binding',first.condition_id.tolist()==dr.condition_id.tolist())
  for j,name in enumerate(names):
   source=f'{actor}-tpr' if name.startswith('alpha_') else name
   err=float(np.max(np.abs(dr[name].to_numpy()-x[:,j])));maxerr['input_parameter']=max(maxerr['input_parameter'],err)
   check(f'{stratum}: {name} source inputs',eq(first[source],x[:,j],1e-12) and eq(dr[name],x[:,j],5e-10))
   if name.startswith('alpha_'):check(f'{stratum}: symmetric accuracy',eq(first[f'{actor}-tpr'],first[f'{actor}-tnr']))
  yrep=rr[['E_mean','O_final']].to_numpy().reshape(500,30,2);y=yrep.mean(axis=1)
  for o,out in enumerate(['E_mean','O_final']):
   err=float(np.max(np.abs(y[:,o]-dr[out].to_numpy())));maxerr['mean_response']=max(maxerr['mean_response'],err)
   check(f'{stratum}: {out} mean of 30 run-level outcomes',eq(y[:,o],dr[out],5e-10),{'max_absolute_error':err})
  pr=analysis.prcc_batch(x,y)[0]
  for o,out in enumerate(['E_mean','O_final']):
   pa=analysis.pawn_batch(y[:,o],masks,groups,len(names))[0]
   for j,name in enumerate(names):
    r=prcc[(prcc.actor==actor)&(prcc.p0==p)&(prcc.outcome==out)&(prcc.input==name)].iloc[0]
    e=abs(pr[o,j]-r.estimate);maxerr['PRCC_estimate']=max(maxerr['PRCC_estimate'],float(e));check(f'{stratum}/{out}/{name}: PRCC deterministic reconstruction',e<=5e-12)
    for typ in ['row','mc']:
     v=archive[f'{stratum}_{typ}_prcc'][:,o,j];lo,hi,n=analysis.interval(v)
     e=max(abs(lo-r[f'{typ}_ci95_low']),abs(hi-r[f'{typ}_ci95_high']));maxerr['archived_interval_endpoint']=max(maxerr['archived_interval_endpoint'],float(e))
     check(f'{stratum}/{out}/{name}: PRCC {typ} archived percentile CI',e<=5e-12 and n==int(r[f'{typ}_valid_resamples'])==1000)
    for ib,nb in enumerate([5,10,20]):
     for ia,agg in enumerate(['median','mean','maximum']):
      r=dia[(dia.actor==actor)&(dia.p0==p)&(dia.outcome==out)&(dia.input==name)&(dia.bins==nb)&(dia.aggregation==agg)].iloc[0]
      e=abs(pa[ib,ia,j]-r.estimate);maxerr['PAWN_diagnostic_estimate']=max(maxerr['PAWN_diagnostic_estimate'],float(e));check(f'{stratum}/{out}/{name}/{nb}/{agg}: PAWN deterministic reconstruction',e<=5e-12)
      for typ in ['row','mc']:
       v=archive[f'{stratum}_{typ}_pawn'][:,o,ib,ia,j];lo,hi,n=analysis.interval(v)
       e=max(abs(lo-r[f'{typ}_ci95_low']),abs(hi-r[f'{typ}_ci95_high']));maxerr['archived_interval_endpoint']=max(maxerr['archived_interval_endpoint'],float(e))
       check(f'{stratum}/{out}/{name}/{nb}/{agg}: PAWN {typ} archived percentile CI',e<=5e-12 and n==int(r[f'{typ}_valid_resamples'])==1000)
   for ib,j,sl in groups:
    if ib!=1:continue
    for k in range(10):
     sel=masks[:,sl.start+k];name=names[j]
     r=bins[(bins.actor==actor)&(bins.p0==p)&(bins.outcome==out)&(bins.input==name)&(bins.bin==k+1)].iloc[0]
     want=[x[sel,j].mean(),y[sel,o].mean(),y[sel,o].min(),y[sel,o].max()];got=r[['x_mean','response_mean','response_min','response_max']].to_numpy(float)
     e=float(np.max(np.abs(np.array(want)-got)));maxerr['bin_summary']=max(maxerr['bin_summary'],e)
     check(f'{stratum}/{out}/{name}/bin{k+1}: fixed-bin descriptive summary',e<=5e-10 and int(sel.sum())==r.n_lhs)
# Validate the actual TeX extraction fields, pollution-panel binding and aggregation styles.
plot_mapping_count=0
for fig,summary in report['figure_summaries'].items():
 tex=(SRC/(summary['filename']+'.tex')).read_text()
 for block in tex.split('\\nextgroupplot')[1:]:
  for match in re.finditer(r'\\addplot(?:\+)?\[(.*?)\]\s*table\[([^\]]*)\]\s*\{(data/[^{}]+\.csv)\}',block,re.S):
   style,opts,path=match.groups();name=Path(path).name
   kv=dict(pair.split('=',1) for pair in opts.split(',') if '=' in pair)
   if summary['filename']=='figS2b_PRCC':expected=('estimate','y') if name.endswith('_points.csv') else ('x','y')
   elif summary['filename'].startswith('figS2d_bins_'):expected=('bins','estimate')
   else:expected=('x','y') if name.endswith('_points.csv') else ('x_mean','response_mean')
   ok=(kv.get('x'),kv.get('y'))==expected
   if summary['filename'].startswith('figS2d_bins_'):
    agg=re.search(r'_(median|mean|maximum)\.csv',name).group(1)
    ok=ok and {'median':'solid','mean':'dashed','maximum':'dotted'}[agg] in style.split(',')
   pollution_match=re.search(r'_p(10|30|50)_|^p(10|30|50)_',name)
   if pollution_match:
    pollution=next(g for g in pollution_match.groups() if g)
    title=re.search(r'title=\{(.*?)\}',block,re.S)
    ok=ok and title is not None and f'p_0={pollution}\\%' in title.group(1)
   check(f'{fig}: TeX x/y, subplot and aggregation mapping: {name}',ok)
   plot_mapping_count+=1
report['plot_reference_mapping_count']=plot_mapping_count
report['maximum_reconstruction_errors']=maxerr
report['metadata']={'unique_lhs_points_per_actor_and_p0':500,'runs_per_lhs_point':30,'total_unique_parameter_conditions':3000,'total_sensitivity_runs':90000,'fixed_response_bins':10,'bin_definition':'Continuous inputs: fixed empirical quantile boundaries of the complete frozen LHS design. Integer legal response interval: fixed consecutive 2-tick groups (1-2,...,19-20), never splitting identical values.','bootstrap_resamples_each_kind':1000,'interval_percentiles':[2.5,97.5],'interval_interpretation':'Separate marginal row-bootstrap stability and within-point Monte Carlo intervals; not combined and not claimed statistically independent.','scope_limit':'Numerical traceability to saved run_metrics.csv and saved bootstrap draws; original NetLogo raw files were not rerun or independently re-extracted in this audit.'}
report['status']='PASS' if not report['errors'] else 'FAIL'
report['check_count']=len(report['checks']);report['plot_file_count']=len(report['plot_files'])
(OUT/'sensitivity_figures_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
lines=['# S5–S11 数据核查','',f"结果：{report['status']}。{report['check_count']} 项检查，{len(report['errors'])} 项未通过；核对 {report['plot_file_count']} 份绘图 CSV。",'', '|图|绘图 CSV 数|点估计/点绘制数|图示 CI 端点|','|---|---:|---:|---:|']
for k,v in report['figure_summaries'].items():lines.append(f"|{k}|{v['csv_file_count']}|{v['point_estimates']}|{v['ci_endpoints']}|")
lines+=['','- 绘图 CSV 与对应正式 processed CSV 全部按数值精确核对，包含参数、结果、CI、样本数与标识符。','- 3,000 个条件分别含 30 次运行，共 90,000 次敏感性模拟；图中同一条件在多个输入面板重复绘制，不作为额外模拟计数。','- 从已有 run_metrics.csv 复核全部响应均值、PRCC 点估计及 270 项 PAWN 诊断估计；从已有 bootstrap draw 档案复核两类区间，没有运行新的模拟或 bootstrap。','- 连续输入的10个响应分箱使用原始完整LHS设计的固定经验分位边界；整数响应间隔按1–2、3–4、…、19–20 ticks分箱。曲线是分箱均值描述，并非拟合、因果曲线或置信带。','- S5原图用文字解释颜色/区间，S6–S7聚合方式仅文字说明，S8–S11缺少真正图例；建议使用符号与线型图例补齐。','- 数值审计止于保存的运行级输出与bootstrap档案，本轮未重新运行NetLogo或独立重新提取原始仿真文件。','', '重构与12位有效数字CSV的最大绝对误差：', '```json',json.dumps(maxerr,ensure_ascii=False,indent=2),'```']
if report['errors']:lines+=['','错误：','```json',json.dumps(report['errors'],ensure_ascii=False,indent=2),'```']
(OUT/'sensitivity_figures_audit.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'status':report['status'],'checks':len(report['checks']),'errors':len(report['errors']),'files':len(report['plot_files']),'maximum_errors':maxerr,'error_examples':report['errors'][:5]},indent=2))
