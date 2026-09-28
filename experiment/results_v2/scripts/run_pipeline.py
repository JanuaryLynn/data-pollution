#!/usr/bin/env python3
"""Analyze existing outputs; this entry point never invokes NetLogo."""
from pathlib import Path
import argparse,subprocess,sys,shutil

def main():
    base=Path(__file__).resolve().parents[1]
    p=argparse.ArgumentParser();p.add_argument('--project',type=Path,default=base.parent/'implementation');p.add_argument('--outputs',type=Path,default=base/'source/outputs');p.add_argument('--figures-only',action='store_true');p.add_argument('--compile-tables',action='store_true');a=p.parse_args()
    def run(name,*args):
        command=[sys.executable,str(base/'scripts'/name),*map(str,args)]
        print('Running '+name,flush=True);subprocess.run(command,check=True)
    if not a.figures_only:
        run('audit_extract.py','--project',a.project,'--outputs',a.outputs,'--out',base)
        run('summarize_contrasts.py','--project',a.project,'--data',base/'processed','--out',base)
        run('analyze_sensitivity.py','--project',a.project,'--data',base/'processed/run_metrics.csv','--out',base)
    run('make_figures.py','--project',a.project,'--data',base/'processed','--out',base/'figures')
    run('make_sensitivity_figures.py','--data',base/'processed','--out',base)
    run('make_tables.py','--project',a.project,'--data',base/'processed','--out',base/'tables')
    if a.compile_tables:
        tex=shutil.which('pdflatex')
        if not tex:raise RuntimeError('Install pdflatex to compile the optional table preview, or omit --compile-tables.')
        for _ in range(2):subprocess.run([tex,'-interaction=nonstopmode','-halt-on-error','all_tables.tex'],cwd=base/'tables',check=True,stdout=subprocess.DEVNULL)
    print('Completed. See figures/ and tables/.')

if __name__=='__main__':main()
