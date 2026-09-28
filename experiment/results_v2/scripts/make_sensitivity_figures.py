#!/usr/bin/env python3
"""Draw fixed PAWN/PRCC results with separate stability and Monte Carlo intervals."""
from pathlib import Path
import argparse,json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

INPUTS=['legal-strength','legal-response-time','alpha_legal','platform-speed','alpha_platform']
LABELS=['Legal coverage $L$','Legal interval $\u03c4$','Legal accuracy $\u03b1_L$','Platform coverage $n_p$','Platform accuracy $\u03b1_P$']
COLORS=['#196B8A']*3+['#BF6723']*2

def main():
    here=Path(__file__).resolve().parents[1]
    ap=argparse.ArgumentParser();ap.add_argument('--data',type=Path,default=here/'processed');ap.add_argument('--out',type=Path,default=here)
    args=ap.parse_args();figdir=args.out/'figures';figdir.mkdir(parents=True,exist_ok=True)
    datadir=args.out/'plot_data';datadir.mkdir(exist_ok=True)
    ix=pd.read_csv(args.data/'sensitivity_indices.csv');diff=pd.read_csv(args.data/'sensitivity_differences.csv');diag=pd.read_csv(args.data/'sensitivity_diagnostics.csv')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.titlesize':11,'axes.labelsize':10,'pdf.fonttype':42,'ps.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
    index=[]
    def save(fig,name,title,note,df):
        fig.suptitle(title,fontsize=14,x=.12,ha='left',y=.985)
        fig.text(.12,.018,note,fontsize=8,ha='left',va='bottom')
        fig.subplots_adjust(left=.205,right=.985,top=.90,bottom=.17,wspace=.25,hspace=.39)
        for ext in ['pdf','png']:fig.savefig(figdir/f'{name}.{ext}',dpi=180,facecolor='white')
        plt.close(fig);df.to_csv(datadir/f'{name}.csv',index=False)
        index.append({'file':name,'title':title,'caption':note})
    handles=[Line2D([0],[0],marker='o',color='black',lw=0,label='30-run estimate'),Line2D([0],[0],color='#687681',lw=1.4,label='Row bootstrap: 95% stability interval'),Line2D([0],[0],color='#196B8A',lw=3.5,label='Within-point bootstrap: 95% MC interval')]
    for method,name,title in [('PAWN','figS2a_PAWN','Global sensitivity of effectiveness and wrongful exposure'),('PRCC','figS2b_PRCC','Supplementary rank-based associations')]:
        sub=ix[ix.method.eq(method)]
        fig,axs=plt.subplots(2,3,figsize=(12,7.4))
        for r,outcome in enumerate(['E_mean','O_final']):
            for col,p0 in enumerate([10,30,50]):
                ax=axs[r,col];part=sub[sub.p0.eq(p0)&sub.outcome.eq(outcome)].set_index('input')
                for j,key in enumerate(INPUTS):
                    row=part.loc[key];y=4-j
                    # Do not force a nonlinear percentile interval to contain its estimate.
                    ax.hlines(y+.075,row.row_ci95_low,row.row_ci95_high,color='#687681',lw=1.4)
                    ax.hlines(y-.075,row.mc_ci95_low,row.mc_ci95_high,color=COLORS[j],lw=3.5)
                    ax.plot(row.estimate,y,'o',color=COLORS[j],ms=5,zorder=4)
                ax.axhline(1.5,color='#DDE3E7',lw=.8);ax.grid(axis='x',alpha=.22);ax.set_ylim(-.6,4.6)
                ax.set_yticks(range(4,-1,-1),LABELS if col==0 else ['']*5)
                ax.set_title(f'{"Mean effectiveness" if r==0 else "Final wrongful exposure"} | $p_0={p0}\\%$')
                if method=='PAWN':ax.set_xlim(-.025,1.025);ax.set_xlabel('PAWN (10 bins; median KS)')
                else:ax.set_xlim(-1.05,1.05);ax.axvline(0,color='#98A3AB',lw=.7);ax.set_xlabel('PRCC')
        fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.58,.080),ncol=3,fontsize=8,frameon=False)
        note='500 LHS points per actor and pollution level; response = mean of 30 runs. Each bootstrap uses 1,000 resamples.\nRow intervals approximate design stability and do not preserve LHS strata. MC intervals are separate; intervals need not contain point estimates.'
        save(fig,name,title,note,sub)
    fig,axs=plt.subplots(2,3,figsize=(12,7.1))
    pos=['legal-strength','legal-response-time','platform-speed'];labels=['Legal: $L-\\alpha_L$','Legal: $\\tau-\\alpha_L$','Platform: $n_p-\\alpha_P$']
    for r,outcome in enumerate(['E_mean','O_final']):
        for col,p0 in enumerate([10,30,50]):
            ax=axs[r,col];part=diff[diff.p0.eq(p0)&diff.outcome.eq(outcome)].set_index('positive_input')
            for j,key in enumerate(pos):
                q=part.loc[key];y=2-j;color=COLORS[0 if j<2 else 3]
                ax.hlines(y+.055,q.row_ci95_low,q.row_ci95_high,color='#687681',lw=1.4)
                ax.hlines(y-.055,q.mc_ci95_low,q.mc_ci95_high,color=color,lw=3.5)
                ax.plot(q.estimate,y,'o',color=color,ms=5)
            ax.set_yticks([2,1,0],labels if col==0 else ['']*3);ax.set_ylim(-.5,2.5);ax.axvline(0,color='#606C76',lw=1,ls='--');ax.grid(axis='x',alpha=.2)
            ax.set_xlim(-.20,.70);ax.set_xlabel('Difference in PAWN indices')
            ax.set_title(f'{"H2: mean effectiveness" if r==0 else "Companion: wrongful exposure"}\n$p_0={p0}\\%$')
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.58,.080),ncol=3,fontsize=8,frameon=False)
    save(fig,'figS2c_H2_differences','Prespecified sensitivity contrasts','Input differences refer to sensitivity indices, not changes in the parameter values or policy cost-effectiveness.\nPrimary method: median KS over 10 fixed bins. All intervals are marginal; the lower row is a companion analysis, not H2.',diff)
    # Show whether ranks and numerical indices depend on bin count and aggregation.
    for outcome in ['E_mean','O_final']:
        fig,axs=plt.subplots(2,3,figsize=(12,7.5))
        for r,actor in enumerate(['legal','platform']):
            names=INPUTS[:3] if actor=='legal' else INPUTS[3:]
            for col,p0 in enumerate([10,30,50]):
                ax=axs[r,col]
                for j,key in enumerate(names):
                    for agg,style in [('median','-'),('mean','--'),('maximum',':')]:
                        q=diag[diag.input.eq(key)&diag.p0.eq(p0)&diag.outcome.eq(outcome)&diag.aggregation.eq(agg)].sort_values('bins')
                        ax.plot(q.bins,q.estimate,style,marker='o',ms=3,lw=1.3,color=['#196B8A','#BF6723','#687F39'][j],label=key.replace('legal-','').replace('platform-',''))
                ax.set_ylim(0,1);ax.set_xticks([5,10,20]);ax.set_xlabel('Number of fixed input bins');ax.set_ylabel('PAWN index' if col==0 else '');ax.grid(alpha=.2)
                ax.set_title(f'{actor.title()} | $p_0={p0}\\%$')
                if col==0:
                    ax.legend(handles=[Line2D([0],[0],color=['#196B8A','#BF6723','#687F39'][j],label=key.replace('legal-','').replace('platform-','')) for j,key in enumerate(names)],fontsize=8,frameon=False)
        fig.legend(handles=[Line2D([0],[0],color='black',ls=ls,label=agg) for agg,ls in [('Median (primary at 10 bins)','-'),('Mean','--'),('Maximum',':')]],loc='lower center',bbox_to_anchor=(.58,.077),ncol=3,fontsize=8,frameon=False)
        save(fig,'figS2d_bins_'+outcome,'PAWN diagnostic settings: '+('effectiveness' if outcome=='E_mean' else 'wrongful exposure'),'Curves display point estimates under diagnostic settings; they do not replace the frozen primary 10-bin median index.\nFull bootstrap intervals, 20/30-run estimates and ranks are retained in sensitivity_diagnostics.csv.',diag[diag.outcome.eq(outcome)])
    (figdir/'sensitivity_figure_index.json').write_text(json.dumps(index,indent=2))
    print(json.dumps({'sensitivity_figures':len(index)}))

if __name__=='__main__':main()
