#!/usr/bin/env python3
"""Create auditable CSV and LaTeX result tables from unrounded summaries."""
from pathlib import Path
import argparse
import json
import pandas as pd

LABELS = {
 'condition_id':'ID','p0':r'$p_0$','treatment':'Regime',
 'legal-strength':r'$L$','legal-response-time':r'$\tau$',
 'legal-tpr':'TPR','legal-tnr':'TNR','platform-speed':r'$n_p$',
 'platform-tpr':'TPR','platform-tnr':'TNR','network-type':'Network',
 'num-nodes':r'$N$','targeting-mode':'Selection',
 'platform-workload-mode':'Workload','demand-kappa':r'$\kappa$',
 'E_mean':r'$\bar E$','E_final':r'$E(50)$','O_final':r'$O(50)$',
 'PR_final':r'$P_R(50)$','n_PR':'Valid PR',
 'cumulative_reviews':'Reviews','clean_review_exposure':'Clean reviews',
 'mean_degree':'Mean degree','max_degree':'Max degree',
 'degree_sd':'Degree SD','count_isolates':'Isolates',
 'mean_super_degree':'Super degree','network_edges':'Edges'}

def escape(x):
    return str(x).replace('_',r'\_').replace('%',r'\%').replace('&',r'\&')

def main():
    a=argparse.ArgumentParser()
    here=Path(__file__).resolve().parents[1]
    a.add_argument('--project',type=Path,default=here.parent/'implementation')
    a.add_argument('--data',type=Path,default=here/'processed')
    a.add_argument('--out',type=Path,default=here/'tables')
    args=a.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    c=pd.read_csv(args.project/'design/conditions.csv').set_index('condition_id',drop=False)
    g=pd.read_csv(args.project/'design/condition_groups.csv')
    s=pd.read_csv(args.data/'condition_summary.csv').set_index(['condition_id','outcome'])
    con=pd.read_csv(args.data/'contrasts.csv')
    table_index=[]

    def ids(module):
        return g.loc[g.module.eq(module),'condition_id'].tolist()

    def export(name, title, frame, raw, note):
        raw.to_csv(args.out/f'{name}.csv',index=False)
        # All fragments are longtable environments; compatible with booktabs/longtable.
        headers=[LABELS.get(x,escape(x)) for x in frame.columns]
        text=[r'\begingroup',r'\footnotesize',r'\setlength{\tabcolsep}{4pt}',
            r'\begin{longtable}{'+'l'*len(headers)+'}',
            r'\caption{'+title+r'}\label{tab:'+name+r'}\\',
            r'\toprule',' & '.join(headers)+r' \\',r'\midrule',r'\endfirsthead',
            r'\toprule',' & '.join(headers)+r' \\',r'\midrule',r'\endhead']
        for row in frame.itertuples(index=False,name=None):
            text.append(' & '.join(escape(v) for v in row)+r' \\')
        text.extend([r'\bottomrule',r'\end{longtable}',r'\noindent '+note,r'\endgroup'])
        (args.out/f'{name}.tex').write_text('\n'.join(text)+'\n')
        table_index.append({'file':name,'title':title,'rows':len(frame),'note':note})

    def condition_table(name,title,selected,keys,outcomes=None):
        outcomes=outcomes or ['E_mean','E_final','O_final','PR_final']
        meta=c.loc[sorted(set(selected)),['condition_id']+keys].copy()
        raw=meta.copy(); display=meta.copy()
        for metric in outcomes:
            sub=s.xs(metric,level='outcome').reindex(meta.index)
            for stat in ['n','n_total','mean','sd','se','ci_low','ci_high']:
                raw[f'{metric}_{stat}']=sub[stat].values
            display[metric]=[
                'NA' if pd.isna(row['mean']) else
                f"{row['mean']:.2f} [{row['ci_low']:.2f}, {row['ci_high']:.2f}]"
                if pd.notna(row['ci_low']) else f"{row['mean']:.2f} [NA]"
                for _,row in sub.iterrows()]
        if 'PR_final' in outcomes:
            display['n_PR']=s.xs('PR_final',level='outcome').reindex(meta.index)['n'].astype(int).values
        for col in ['condition_id','p0','num-nodes','legal-response-time']:
            if col in display:display[col]=display[col].astype(int)
        display=display.replace({'state-responsive':'responsive'})
        note=(r'Each condition uses 30 independent runs. Entries are mean [pointwise 95\% Student-$t$ CI]; intervals are not clipped. '
              r'Percent-scale outcome differences are percentage points. $\bar E$ averages steps 1--50; '
              r'$O(50)$ counts distinct accounts ever wronged. PR is averaged over defined run ratios only; NA is not zero. '
              r'Reused condition IDs refer to the same runs. Full unrounded values and sample sizes are in the companion CSV.')
        export(name,title,display,raw,note)

    benchmark=c.loc[ids('P1_topology')].query('`network-type` == "BA"').index.tolist()
    condition_table('table2_benchmark','Benchmark governance outcomes',benchmark,['p0','treatment'])
    condition_table('table3_legal','Legal parameter sweep',ids('core_legal'),['p0','legal-strength','legal-response-time'])
    condition_table('table4_platform','Platform parameter sweep',ids('core_platform'),['p0','platform-speed','platform-tpr'])
    effect=con[(con.family.eq('P5_high_coverage_reference')) | con.comparison_id.str.startswith('H3_legal_accuracy')]
    raw=effect.copy();disp=effect[['comparison_id','outcome']].copy()
    disp['Difference [95% CI]']=[f'{r.estimate:.2f} [{r.ci_low:.2f}, {r.ci_high:.2f}]' for r in effect.itertuples()]
    # Compact aliases keep table within landscape text width.
    disp['comparison_id']=disp.comparison_id.str.replace('P5_high_coverage_reference_','',regex=False).str.replace('_targeted_minus_random','_targeting',regex=False).str.replace('H3_','',regex=False)
    export('table5_mechanisms','Targeting and legal-accuracy effects',disp,raw,
           r'Differences use independent-condition Welch intervals. All E/O differences are percentage points. Targeting is targeted minus random; legal accuracy is 100 minus 90. No multiplicity adjustment or equivalence claim is implied.')
    condition_table('table6_targeting','Targeting mechanisms',ids('targeting'),['p0','treatment','targeting-mode'])
    condition_table('table7_topology','Network topology comparison',ids('P1_topology'),['p0','treatment','network-type'])
    condition_table('table8_scale','Network size comparison',ids('scale'),['p0','treatment','num-nodes'])
    condition_table('tableS1_P3','State-responsive platform moderation',ids('P3'),['p0','platform-workload-mode','demand-kappa'],['E_mean','O_final','PR_final'])
    condition_table('tableS1_P3_workload','Review burden under state-responsive moderation',ids('P3'),['p0','platform-workload-mode','demand-kappa'],['cumulative_reviews','clean_review_exposure'])
    for actor, coverage in [('legal','legal-strength'),('platform','platform-speed')]:
        selected=c.loc[ids('P5')].query('treatment == @actor').index.tolist()
        condition_table('tableS3_P5_'+actor,'Targeting at low and benchmark coverage: '+actor,selected,['p0','targeting-mode',coverage],['E_mean','O_final'])
    condition_table('tableS4_P6_legal','Separate true-positive and true-negative rates: legal',ids('P6_legal'),['p0','legal-tpr','legal-tnr'],['E_mean','O_final','PR_final'])
    for coverage in [50,75]:
        selected=c.loc[ids('P6_platform')].query('`platform-speed` == @coverage').index.tolist()
        condition_table('tableS4_P6_platform'+str(coverage),'Separate true-positive and true-negative rates: platform coverage '+str(coverage),selected,['p0','platform-tpr','platform-tnr'],['E_mean','O_final','PR_final'])
    condition_table('tableS_network','Realized network diagnostics',ids('P1_topology')+ids('scale'),['p0','treatment','network-type','num-nodes'],['mean_degree','max_degree','count_isolates'])
    # All network diagnostics, including degree heterogeneity, remain unrounded in a separate long table.
    network_metrics=['mean_degree','max_degree','degree_sd','network_edges','count_isolates','mean_super_degree','mean_ordinary_degree','super_count']
    net=s.reset_index();net=net[net.condition_id.isin(ids('P1_topology')+ids('scale')) & net.outcome.isin(network_metrics)]
    net.merge(c.reset_index(drop=True),on='condition_id',validate='many_to_one').to_csv(args.out/'network_summary.csv',index=False)
    (args.out/'table_index.json').write_text(json.dumps(table_index,ensure_ascii=False,indent=2))
    head=r'''\documentclass[10pt]{article}
\usepackage[a4paper,landscape,margin=15mm]{geometry}
\usepackage{booktabs,longtable,amsmath}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\begin{document}
\begin{center}\Large Simulation outcomes and prespecified comparisons\end{center}
\noindent 95,850 runs; 3,195 unique configurations; 30 independent runs per configuration. These tables use the frozen v2.0 design. Table numbers in this compilation are consecutive.
'''
    body='\n'.join(r'\input{'+t['file']+r'.tex}\clearpage' for t in table_index)
    (args.out/'all_tables.tex').write_text(head+body+'\n'+r'\end{document}'+'\n')
    print(json.dumps({'tables':len(table_index),'out':str(args.out)}))

if __name__=='__main__':main()
