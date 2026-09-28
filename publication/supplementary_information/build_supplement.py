#!/usr/bin/env python3
"""Compile the combined Supplementary Information and resolve its contents links."""
from pathlib import Path
import subprocess
import shutil
ROOT=Path(__file__).resolve().parent
BUILD=ROOT/'build'
BUILD.mkdir(exist_ok=True)
if not shutil.which('pdflatex'):
    raise SystemExit('Install TeX Live or MiKTeX with pdfLaTeX first.')
for run in range(3):
    p=subprocess.run(['pdflatex','-interaction=nonstopmode','-halt-on-error','-output-directory='+str(BUILD),'supplementary_information.tex'],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if p.returncode:
        raise SystemExit(p.stdout[-6000:])
shutil.copy2(BUILD/'supplementary_information.pdf',ROOT/'supplementary_information.pdf')
print('Created supplementary_information.pdf')
