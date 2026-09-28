#!/usr/bin/env python3
"""Draw manuscript and supplementary figures from audited, unrounded summaries.

Usage: python make_figures.py --project ../implementation --data ../processed --out ../figures
Only read inputs; every figure has a CSV containing its plotted observations.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.colors import Normalize
import numpy as np
import pandas as pd

P0S = (10, 30, 50)
COLORS = {"none": "#676767", "legal": "#D55E00", "platform": "#0072B2"}
OUTCOME_COLORS = {"E_mean": "#0072B2", "O_final": "#D55E00"}
ACTORS = {"none": "No governance", "legal": "Legal", "platform": "Platform"}
LABELS = {"E_mean": r"Mean effectiveness $\bar E$ (%)", "O_final": r"Collateral exposure $O(50)$ (%)",
          "PR_final": r"Removal precision $P_R(50)$ (%)", "cumulative_reviews": "Cumulative reviews (thousands)",
          "clean_review_exposure": "Clean-account reviews (thousands)"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Figures:
    def __init__(self, project, data, out):
        self.project, self.data, self.out = map(Path, (project, data, out))
        self.out.mkdir(parents=True, exist_ok=True)
        self.plotdir = self.out / "plot_data"
        self.plotdir.mkdir(exist_ok=True)
        self.conditions = pd.read_csv(self.project / "design/conditions.csv")
        self.groups = pd.read_csv(self.project / "design/condition_groups.csv")
        self.summary = pd.read_csv(self.data / "condition_summary.csv")
        self.traj = pd.read_csv(self.data / "trajectory_summary.csv")
        self.contrasts = pd.read_csv(self.data / "contrasts.csv")
        self.contrasts["mean"] = self.contrasts["estimate"]
        # Condition metadata are joined once, with explicit uniqueness checks.
        self.summary = self.summary.merge(self.conditions, on="condition_id", how="left", validate="many_to_one", suffixes=("", "_design"))
        self.traj = self.traj.merge(self.conditions, on="condition_id", how="left", validate="many_to_one", suffixes=("", "_design"))
        self.catalog = []
        self.captions = []
        plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                             "axes.titlesize": 11, "axes.labelsize": 10,
                             "xtick.labelsize": 9, "ytick.labelsize": 9,
                             "legend.fontsize": 9, "axes.spines.top": False,
                             "axes.spines.right": False, "pdf.fonttype": 42,
                             "ps.fonttype": 42, "savefig.dpi": 220,
                             "axes.axisbelow": True})

    def module(self, module, frame=None):
        ids = self.groups.loc[self.groups.module.eq(module), "condition_id"]
        return (self.summary if frame is None else frame).loc[lambda d: d.condition_id.isin(ids)].copy()

    def save(self, fig, name, data, caption):
        fig.savefig(self.out / f"{name}.pdf", bbox_inches="tight", metadata={"Title": name, "Creator": "make_figures.py"})
        fig.savefig(self.out / f"{name}.png", bbox_inches="tight", facecolor="white")
        data.to_csv(self.plotdir / f"{name}.csv", index=False, float_format="%.17g")
        self.catalog.append({"figure": name, "pdf_sha256": sha(self.out/f"{name}.pdf"),
                             "plot_data_sha256": sha(self.plotdir/f"{name}.csv"), "plotted_rows": len(data)})
        self.captions.append(f"### {name}\n\n{caption}\n")
        plt.close(fig)

    @staticmethod
    def error(ax, x, rows, color, marker="o", label=None, scale=1, horizontal=False, **kwargs):
        m = rows["mean"].to_numpy(float)/scale
        lo = rows["ci_low"].to_numpy(float)/scale
        hi = rows["ci_high"].to_numpy(float)/scale
        errors = np.maximum(0, np.vstack([m-lo, hi-m]))
        if horizontal:
            return ax.errorbar(m, x, xerr=errors, fmt=marker, color=color, markersize=5,
                               capsize=3, linewidth=1.2, label=label, **kwargs)
        return ax.errorbar(x, m, yerr=errors, fmt=marker, color=color, markersize=5,
                           capsize=3, linewidth=1.2, label=label, **kwargs)

    @staticmethod
    def panel(ax, letter, title):
        ax.set_title(f"({letter}) {title}", loc="left", pad=10)
        ax.grid(alpha=.18)

    @staticmethod
    def percent_ylim(ax, frame, pad=3):
        lo = min(0, frame.ci_low.min())
        hi = max(100, frame.ci_high.max())
        ax.set_ylim(lo-pad, hi+pad)

    def fig2(self):
        ids = self.conditions.loc[(self.conditions.primary_module.eq("baseline_none")) |
                                 ((self.conditions.design_family.eq("grid")) &
                                  (self.conditions["network-type"].eq("BA")) &
                                  self.conditions["num-nodes"].eq(1000) &
                                  self.conditions["targeting-mode"].eq("targeted") &
                                  (((self.conditions.treatment.eq("legal")) & self.conditions["legal-strength"].eq(70) &
                                    self.conditions["legal-response-time"].eq(5) & self.conditions["legal-tpr"].eq(95) & self.conditions["legal-tnr"].eq(95)) |
                                   ((self.conditions.treatment.eq("platform")) & self.conditions["platform-speed"].eq(75) &
                                    self.conditions["platform-tpr"].eq(80) & self.conditions["platform-tnr"].eq(80) &
                                    self.conditions["platform-workload-mode"].eq("fixed")))), "condition_id"]
        assert len(ids)==9
        d = self.traj[self.traj.condition_id.isin(ids) & self.traj.outcome.isin(["E", "O"])].copy()
        assert len(d)==9*51*2, (d.outcome.unique(), len(d))
        fig, axs = plt.subplots(2, 3, figsize=(11.4, 6.6), sharex=True, sharey="row", layout="constrained")
        for j,p0 in enumerate(P0S):
            for i,outcome in enumerate(["E", "O"]):
                ax = axs[i,j]
                q=d[d.p0.eq(p0)&d.outcome.eq(outcome)]
                for actor in ACTORS:
                    g=q[q.treatment.eq(actor)].sort_values("step")
                    ax.fill_between(g.step.to_numpy(), g.ci_low.to_numpy(), g.ci_high.to_numpy(), color=COLORS[actor], alpha=.17, linewidth=0)
                    ax.plot(g.step, g["mean"], color=COLORS[actor], label=ACTORS[actor], lw=1.6)
                self.panel(ax, chr(97+i*3+j), rf"$p_0={p0}\%$")
                ax.set_xlim(0,50); self.percent_ylim(ax,q)
                if i==1: ax.set_xlabel("Tick")
                if j==0: ax.set_ylabel("Effectiveness E(t) (%)" if outcome=="E" else "Collateral exposure O(t) (%)")
        fig.legend([Line2D([0],[0],color=COLORS[a],lw=2) for a in ACTORS], list(ACTORS.values()), loc="outside lower center", ncol=3, frameon=False)
        self.save(fig,"fig2",d,"Benchmark trajectories of effectiveness E(t) (a–c) and cumulative distinct-account collateral exposure O(t) (d–f). Lines are means of 30 independent runs; shaded bands are pointwise 95% t confidence intervals, not simultaneous bands. Ticks 0–50 are displayed; tick 0 is excluded from time-averaged effectiveness. BA networks have N=1,000. Legal settings are L=70%, response interval 5 and TPR=TNR=95%; platform settings are per-tick coverage 75%, fixed workload and TPR=TNR=80%. Governance uses degree-targeted selection. Intervals are not clipped to physical bounds.")

    def heat(self, ax, d, xcol, ycol, title, xlabel, ylabel, cmap="viridis"):
        a=d.pivot(index=ycol,columns=xcol,values="mean").sort_index().sort_index(axis=1)
        assert a.size==9 and not a.isna().any().any()
        im=ax.pcolormesh(np.arange(a.shape[1]+1)-.5, np.arange(a.shape[0]+1)-.5,
                         a.to_numpy(), norm=Normalize(0,100), cmap=cmap, shading="flat", rasterized=False)
        ax.set_xlim(-.5,a.shape[1]-.5);ax.set_ylim(-.5,a.shape[0]-.5)
        ax.set_xticks(range(len(a.columns)), [f"{x:g}" for x in a.columns])
        ax.set_yticks(range(len(a.index)), [f"{x:g}" for x in a.index])
        ax.set_xlabel(xlabel);ax.set_ylabel(ylabel);ax.set_title(title,loc="left",pad=10)
        for i in range(a.shape[0]):
            for j in range(a.shape[1]):
                v=float(a.iloc[i,j]); color="white" if v<55 else "#111111"
                ax.text(j,i,f"{v:.1f}",ha="center",va="center",color=color,fontsize=11)
        return im

    def fig3(self):
        d=pd.concat([self.module("core_legal"), self.module("core_platform")]).query("outcome == 'E_mean'").copy()
        fig,axs=plt.subplots(2,3,figsize=(11.4,6.8),layout="constrained")
        for i,actor in enumerate(["legal","platform"]):
            for j,p0 in enumerate(P0S):
                g=d[d.treatment.eq(actor)&d.p0.eq(p0)]
                if actor=="legal": x,y="legal-response-time","legal-strength";xl,yl=r"Response interval $\tau_L$ (ticks)",r"Coverage $L$ (%)"
                else: x,y="platform-speed","platform-tpr";xl,yl=r"Per-tick coverage $n_p$ (%)",r"Accuracy $\alpha$ (%)"
                im=self.heat(axs[i,j],g,x,y,f"({chr(97+i*3+j)}) {ACTORS[actor]}, $p_0={p0}\\%$",xl,yl)
        fig.colorbar(im,ax=axs.ravel().tolist(),label=r"Mean effectiveness $\bar E$ (%)",shrink=.8,pad=.03)
        self.save(fig,"fig3",d,"Mean-effectiveness response surfaces for the frozen core grid. Legal panels (a–c) cross coverage L={50,70,90}% with response intervals {1,5,10}; TPR=TNR=95%. Platform panels (d–f) cross per-tick coverage {50,75,100}% with TPR=TNR={70,80,90}%. Each cell is the mean of 30 independent run-level averages over ticks 1–50. Cell labels are rounded to one decimal only for display; all figures and analyses use unrounded values. All panels share a 0–100% scale. Confidence intervals remain available in the associated plot data and condition tables.")

    def fig4(self):
        frames=[]
        fig,axs=plt.subplots(3,3,figsize=(11.6,10.2),layout="constrained")
        core=pd.concat([self.module("core_legal"),self.module("core_platform")]).query("outcome in ['E_mean','O_final']").copy()
        core["panel_group"]="parameter_grid";frames.append(core)
        target=self.module("targeting").query("outcome in ['E_mean','O_final']").copy(); target["panel_group"]="targeting";frames.append(target)
        accuracy=self.module("legal_accuracy").query("outcome in ['E_mean','O_final']").copy();accuracy["panel_group"]="legal_accuracy";frames.append(accuracy)
        for j,p0 in enumerate(P0S):
            ax=axs[0,j]
            for actor,marker in [("legal","o"),("platform","s")]:
                q=core[core.p0.eq(p0)&core.treatment.eq(actor)]
                e=q[q.outcome.eq("E_mean")].set_index("condition_id").sort_index()
                o=q[q.outcome.eq("O_final")].set_index("condition_id").reindex(e.index)
                ax.errorbar(o["mean"],e["mean"],xerr=np.vstack([o["mean"]-o.ci_low,o.ci_high-o["mean"]]),yerr=np.vstack([e["mean"]-e.ci_low,e.ci_high-e["mean"]]),fmt=marker,color=COLORS[actor],ms=5,capsize=2,elinewidth=.8,label=ACTORS[actor],alpha=.8)
            ax.set_xlabel(r"$O(50)$ (%)");ax.set_ylabel(r"$\bar E$ (%)");self.panel(ax,chr(97+j),rf"$p_0={p0}\%$: parameter grid")
            ax.legend(frameon=False,fontsize=8,loc="lower right")
            ax=axs[1,j]
            for k,outcome in enumerate(["E_mean","O_final"]):
                q=target[target.p0.eq(p0)&target.outcome.eq(outcome)]
                order=[("legal","random"),("legal","targeted"),("platform","random"),("platform","targeted")]
                q=q.set_index(["treatment","targeting-mode"]).reindex(order)
                self.error(ax,np.arange(4)+(-.09 if k==0 else .09),q,OUTCOME_COLORS[outcome],marker="o" if k==0 else "s",label=r"$\bar E$" if k==0 else r"$O(50)$")
            ax.set_xticks(range(4),["Legal\nrandom","Legal\ntargeted","Platform\nrandom","Platform\ntargeted"],fontsize=8)
            ax.set_ylabel("Outcome (%)");self.panel(ax,chr(100+j),"Benchmark targeting")
            ax.legend(frameon=False,ncol=2,fontsize=8,loc="lower left")
            self.percent_ylim(ax,target[target.p0.eq(p0)])
            ax=axs[2,j]
            for outcome,ls,marker in [("E_mean","-","o"),("O_final","--","s")]:
                q=accuracy[accuracy.p0.eq(p0)&accuracy.outcome.eq(outcome)].sort_values("legal-tpr")
                self.error(ax,q["legal-tpr"],q,OUTCOME_COLORS[outcome],marker=marker,label=r"$\bar E$" if outcome=="E_mean" else r"$O(50)$",linestyle=ls)
            ax.set_xlabel(r"Legal accuracy $\alpha_L$ (%)");ax.set_xticks([90,95,100]);ax.set_ylabel("Outcome (%)")
            self.panel(ax,chr(103+j),"Legal accuracy")
            ax.legend(frameon=False,ncol=2,fontsize=8);self.percent_ylim(ax,accuracy[accuracy.p0.eq(p0)])
        self.save(fig,"fig4",pd.concat(frames,ignore_index=True),"Effectiveness and collateral exposure. Panels (a–c) plot one point per core-grid condition: mean effectiveness versus cumulative distinct-account collateral exposure at tick 50. Horizontal and vertical whiskers are marginal 95% t confidence intervals, not joint confidence regions. Panels (d–f) compare random and degree-targeted selection at benchmark legal and platform settings. Panels (g–i) vary legal TPR=TNR from 90% to 100% at L=70% and response interval 5; solid blue denotes mean effectiveness and dashed orange denotes collateral exposure. Each condition contains 30 independent runs. Line segments join the tested settings as visual guides; they do not establish responses between those settings.")

    def fig5(self):
        d=self.contrasts[self.contrasts.family.isin(["topology","scale"])&self.contrasts.outcome.isin(["E_mean","O_final"])].copy()
        fig,axs=plt.subplots(4,3,figsize=(11.6,11.2),layout="constrained",sharex="row")
        for i,(family,outcome) in enumerate([("topology","E_mean"),("topology","O_final"),("scale","E_mean"),("scale","O_final")]):
            for j,p0 in enumerate(P0S):
                ax=axs[i,j];q=d[d.family.eq(family)&d.outcome.eq(outcome)&d.p0.eq(p0)].copy()
                for k,actor in enumerate(ACTORS):
                    if family=="topology":
                        for topology,offset,marker in [("ER",-.13,"o"),("WS",.13,"s")]:
                            row=q[q.actor.eq(actor)&q.comparison_id.str.contains(f"_{topology}_minus_BA_")]
                            assert len(row)==1
                            self.error(ax,[k+offset],row,COLORS[actor],marker=marker,horizontal=True)
                    else:
                        row=q[q.actor.eq(actor)];assert len(row)==1
                        self.error(ax,[k],row,COLORS[actor],horizontal=True)
                ax.axvline(0,c="#555555",lw=.9,ls="--")
                ax.set_yticks(range(3),list(ACTORS.values()) if j==0 else ["","",""])
                ax.set_ylim(2.5,-.5)
                metric=r"$\Delta\bar E$" if outcome=="E_mean" else r"$\Delta O(50)$"
                ax.set_xlabel(f"{metric} (percentage points)")
                self.panel(ax,chr(97+i*3+j),rf"{'Topology' if family=='topology' else 'Size'}, $p_0={p0}\%$")
                if i==0 and j==0:
                    ax.legend(handles=[Line2D([0],[0],marker="o",ls="",c="#555555",label="ER − BA"),Line2D([0],[0],marker="s",ls="",c="#555555",label="WS − BA")],frameon=False,fontsize=8,loc="lower right")
        self.save(fig,"fig5",d,"Network robustness. Rows 1–2 show differences in mean effectiveness and collateral exposure for ER minus BA (circles) and WS minus BA (squares) at N=1,000. Rows 3–4 show the corresponding differences for BA networks with N=5,000 minus N=1,000. Columns show initial pollution 10%, 30%, and 50%. Whiskers are 95% Welch confidence intervals from independent runs (30 per condition); identical condition weights are combined before computing each variance. Other settings are held at the regime-specific benchmark. All differences are percentage points. Intervals overlapping zero do not establish equivalence.")

    def p3(self):
        outcomes=["E_mean","O_final","PR_final","cumulative_reviews","clean_review_exposure"]
        d=self.module("P3").loc[lambda x:x.outcome.isin(outcomes)].copy()
        d["workload_label"]=np.where(d["platform-workload-mode"].eq("fixed"),"Fixed",d["demand-kappa"].map(lambda x:f"kappa={x:g}"))
        fig,axs=plt.subplots(5,3,figsize=(11.4,13.5),layout="constrained",sharey="row")
        for i,outcome in enumerate(outcomes):
            for j,p0 in enumerate(P0S):
                ax=axs[i,j];q=d[d.p0.eq(p0)&d.outcome.eq(outcome)].set_index("workload_label").reindex(["Fixed","kappa=1","kappa=2","kappa=5"])
                scale=1000 if outcome in ["cumulative_reviews","clean_review_exposure"] else 1
                self.error(ax,np.arange(4),q,COLORS["platform"],scale=scale)
                ax.set_xticks(range(4),["Fixed",r"$\kappa=1$",r"$\kappa=2$",r"$\kappa=5$"])
                self.panel(ax,chr(97+i*3+j),rf"$p_0={p0}\%$")
                if j==0: ax.set_ylabel(LABELS[outcome])
                if outcome=="PR_final":
                    for k,(_,r) in enumerate(q.iterrows()):
                        ax.annotate(f"n={int(r['n'])}",(k,r["mean"]),xytext=(0,11),textcoords="offset points",ha="center",fontsize=8)
                    ax.margins(y=.22)
                elif outcome in ["E_mean","O_final"]: self.percent_ylim(ax,q)
        self.save(fig,"figS1_workload",d,"Alternative platform workload specification (P3). Columns correspond to the three initial pollution levels. Rows report mean effectiveness, collateral exposure, run-level removal precision, cumulative reviews and cumulative clean-account reviews. Fixed workload audits 75% of accounts per tick. State-responsive workload audits min(N, round(0.75N), round(kappa × polluted accounts before review)), with kappa={1,2,5}; TPR=TNR=80%. Points and whiskers are condition means and 95% t confidence intervals based on 30 independent runs. Precision averages only defined run-level ratios; the number of defined runs is printed. Review counts include repeated reviews of the same account, whereas collateral exposure counts distinct ever-wrongly-flagged accounts. Intervals are not clipped.")

    def p5(self):
        d=self.contrasts[self.contrasts.family.isin(["P5","P5_high_coverage_reference"])&self.contrasts.outcome.isin(["E_mean","O_final"])].copy()
        d["coverage"]=d.comparison_id.str.extract(r"coverage(\d+)").astype(int)
        fig,axs=plt.subplots(2,3,figsize=(11.5,7.4),layout="constrained",sharey="row")
        for i,actor in enumerate(["legal","platform"]):
            cov=[5,10,20,70 if actor=="legal" else 75]
            for j,p0 in enumerate(P0S):
                ax=axs[i,j]
                for k,outcome in enumerate(["E_mean","O_final"]):
                    q=d[d.actor.eq(actor)&d.p0.eq(p0)&d.outcome.eq(outcome)].set_index("coverage").reindex(cov)
                    self.error(ax,np.arange(4)+(-.07 if k==0 else .07),q,OUTCOME_COLORS[outcome],marker="o" if k==0 else "s",label=r"$\Delta\bar E$" if k==0 else r"$\Delta O(50)$")
                ax.axhline(0,c="#555555",lw=.9,ls="--");ax.axvline(2.5,color="#999999",ls=":",lw=.8)
                ax.set_xticks(range(4),[str(c) for c in cov[:-1]]+[f"{cov[-1]}\nreference"])
                ax.set_xlabel("Coverage (%) · tested settings")
                if j==0: ax.set_ylabel("Targeted − random (percentage points)")
                self.panel(ax,chr(97+i*3+j),rf"{ACTORS[actor]}, $p_0={p0}\%$")
        fig.legend(handles=[Line2D([0],[0],marker="o",ls="",c=OUTCOME_COLORS['E_mean'],label=r"$\Delta\bar E$"),Line2D([0],[0],marker="s",ls="",c=OUTCOME_COLORS['O_final'],label=r"$\Delta O(50)$")],loc="outside lower center",frameon=False,ncol=2)
        self.save(fig,"figS3_low_coverage_targeting",d,"Low-coverage targeting comparisons (P5). Points show degree-targeted minus random selection at coverage 5%, 10%, and 20%, with the original legal 70% and platform 75% benchmark comparisons retained as references. Coverage positions are categorical, not a continuous linear axis. Blue circles show differences in mean effectiveness; orange squares show differences in collateral exposure, both in percentage points. Whiskers are independent-condition 95% Welch confidence intervals (30 runs per condition). Legal response interval is 5 and TPR=TNR=95%; platform workload is fixed and TPR=TNR=80%. Intervals crossing zero do not establish equivalence.")

    def p6(self):
        d=pd.concat([self.module("P6_legal"),self.module("P6_platform")]).query("outcome in ['E_mean','O_final']").copy()
        for p0 in P0S:
            q=d[d.p0.eq(p0)].copy()
            fig,axs=plt.subplots(3,2,figsize=(8.6,11),layout="constrained")
            for i,(actor,cov) in enumerate([("legal",70),("platform",50),("platform",75)]):
                for j,outcome in enumerate(["E_mean","O_final"]):
                    g=q[q.treatment.eq(actor)&q.outcome.eq(outcome)&q["legal-strength" if actor=="legal" else "platform-speed"].eq(cov)]
                    metric=r"$\bar E$" if outcome=="E_mean" else r"$O(50)$"
                    im=self.heat(axs[i,j],g,f"{actor}-tnr",f"{actor}-tpr",f"({chr(97+i*2+j)}) {ACTORS[actor]}, coverage {cov}%: {metric}","True-negative rate (%)","True-positive rate (%)")
            fig.suptitle(rf"Separate sensitivity and specificity: $p_0={p0}\%$",fontsize=13)
            fig.colorbar(im,ax=axs.ravel().tolist(),label="Outcome (%)",shrink=.7,pad=.03)
            self.save(fig,f"figS4_accuracy_p{p0:02d}",q,f"Independent variation of TPR and TNR (P6), initial pollution {p0}%. Rows show legal coverage 70% (response interval 5), platform coverage 50%, and platform coverage 75%; platform workload is fixed. Left panels show mean effectiveness and right panels show cumulative collateral exposure. Columns within each heatmap vary TNR and rows vary TPR. Each cell is a mean over 30 independent runs; effectiveness first averages ticks 1–50 within runs. All panels share a 0–100% scale. Display labels are rounded to one decimal only; full means and 95% t intervals are in the plot data. False-positive flags accumulate exposure but do not delete accounts or links or otherwise feed back into diffusion in this model.")

    def hypotheses(self):
        d=self.contrasts[self.contrasts.family.eq("H1")].copy()
        order=["H1_legal_tau1_minus_tau5","H1_legal_tau1_minus_tau10","H1_platform_coverage100_minus_50","H1_platform_coverage100_minus_75"]
        names=[r"Legal: $D_L(1)-D_L(5)$",r"Legal: $D_L(1)-D_L(10)$",r"Platform: $D_\alpha(100)-D_\alpha(50)$",r"Platform: $D_\alpha(100)-D_\alpha(75)$"]
        d["contrast_path"]=d.comparison_id.str.replace(r"_p\d+$","",regex=True)
        fig,axs=plt.subplots(1,3,figsize=(11.6,4.1),layout="constrained",sharex=True)
        for j,p0 in enumerate(P0S):
            ax=axs[j];q=d[d.p0.eq(p0)].set_index("contrast_path").reindex(order)
            for k,(_,r) in enumerate(q.iterrows()): self.error(ax,[k],r.to_frame().T,COLORS["legal" if k<2 else "platform"],horizontal=True)
            ax.set_yticks(range(4),names if j==0 else [""]*4);ax.set_ylim(3.6,-.6);ax.axvline(0,c="#555555",ls="--",lw=.9)
            self.panel(ax,chr(97+j),rf"$p_0={p0}\%$");ax.set_xlabel("Difference in gains (percentage points)")
        self.save(fig,"figS5a_H1",d,"H1: predefined differences in effectiveness gains. D_L(tau) is the mean-effectiveness difference for legal coverage 90% minus 50% at response interval tau and TPR=TNR=95%. D_alpha(c) is the platform mean-effectiveness difference for accuracy 90% minus 70% at coverage c. Negative contrasts indicate the specified diminishing-gain pattern; they do not establish universal diminishing returns. Points and whiskers show weighted contrasts and 95% Welch intervals, with repeated condition weights combined before variance estimation. Conditions each contain 30 independent runs. Intervals are marginal rather than simultaneous; no significance stars are used.")
        d=self.contrasts[self.contrasts.family.eq("H3")].copy()
        order=["H3_legal_coverage","H3_legal_frequency","H3_platform_coverage","H3_legal_accuracy","H3_platform_accuracy"]
        names=["Legal coverage: 90 − 50%","Legal interval: 1 − 10 ticks","Platform coverage: 100 − 50%","Legal accuracy: 100 − 90%","Platform accuracy: 90 − 70%"]
        d["contrast_path"]=d.comparison_id.str.replace(r"_p\d+$","",regex=True)
        fig,axs=plt.subplots(2,3,figsize=(11.9,7),layout="constrained",sharex="row")
        for i,outcome in enumerate(["E_mean","O_final"]):
            for j,p0 in enumerate(P0S):
                ax=axs[i,j];q=d[d.p0.eq(p0)&d.outcome.eq(outcome)].set_index("contrast_path").reindex(order)
                self.error(ax,np.arange(5),q,OUTCOME_COLORS[outcome],horizontal=True)
                ax.set_yticks(range(5),names if j==0 else [""]*5);ax.set_ylim(4.6,-.6);ax.axvline(0,c="#555555",ls="--",lw=.9)
                self.panel(ax,chr(97+i*3+j),rf"$p_0={p0}\%$")
                ax.set_xlabel((r"$\Delta\bar E$" if i==0 else r"$\Delta O(50)$")+" (percentage points)")
        self.save(fig,"figS5b_H3",d,"H3: effectiveness and collateral-exposure contrasts along five predefined intervention paths. Rows show differences in mean effectiveness and collateral exposure for the same paths; columns show initial pollution. Parameters outside each path remain at the benchmark settings. Points and whiskers are weighted contrasts with marginal 95% Welch confidence intervals (30 independent runs per condition). They are not joint confidence regions and do not imply simultaneous coverage. The shared-control covariance for joint interpretation is retained in the statistical outputs. A confidence interval crossing zero is not evidence of equivalence.")

    def run(self):
        for fn in [self.fig2,self.fig3,self.fig4,self.fig5,self.p3,self.p5,self.p6,self.hypotheses]:
            fn()
        (self.out/"figure_captions.md").write_text("# Figure captions\n\nAll plots are generated from audited, unrounded version 2.0 outputs. PDF files are vector figures; PNG files are previews. Source rows and intervals are preserved in the corresponding plot_data CSV files.\n\n"+"\n".join(self.captions),encoding="utf-8")
        manifest={"script_sha256":sha(__file__),"inputs":{str(p.relative_to(self.data)):sha(p) for p in [self.data/"condition_summary.csv",self.data/"trajectory_summary.csv",self.data/"contrasts.csv"]},"figures":self.catalog}
        (self.out/"figure_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        print(json.dumps({"figures":len(self.catalog),"output":str(self.out)},indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",required=True,type=Path)
    p.add_argument("--data",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    Figures(a.project,a.data,a.out).run()

if __name__=="__main__": main()
