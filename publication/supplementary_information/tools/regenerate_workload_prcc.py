from pathlib import Path
import csv

OUT=Path(__file__).resolve().parents[1]

start=r'''\documentclass[tikz,border=4pt]{standalone}
\input{figure_style.tex}
\begin{document}
\begin{tikzpicture}
'''
end='\\end{tikzpicture}\n\\end{document}\n'

# S1: same four conditions and 95% t intervals, shared scales within each row.
metrics=[('E_mean',r'Mean effectiveness\\$\bar E$ (\%)',-3,105,'0,25,50,75,100'),
 ('O_final',r'Wrongful exposure\\$O(50)$ (\%)',-3,105,'0,25,50,75,100'),
 ('PR_final',r'Removal precision\\$P_R(50)$ (\%)',-2,60,'0,20,40,60'),
 ('cumulative_reviews',r'Reviews\\(thousands)',-1,40,'0,10,20,30,40'),
 ('clean_review_exposure',r'Clean reviews\\(thousands)',-1,40,'0,10,20,30,40')]
lines=[start,r'''% Values and error widths are read from the supplied CSV files.
\begin{groupplot}[abm axis,group style={group size=3 by 5,horizontal sep=0.65cm,vertical sep=0.9cm},
 width=4.1cm,height=2.35cm,xmin=-0.45,xmax=3.45,xtick={0,1,2,3},
 xticklabels={Fixed,$\kappa=1$,$\kappa=2$,$\kappa=5$},xmajorgrids=false,
 ylabel style={align=center},title style={at={(0,1)},anchor=south west,yshift=3pt}]
''']
for row,(metric,ylabel,ymin,ymax,ticks) in enumerate(metrics):
 for col,p0 in enumerate([10,30,50]):
  letter=chr(97+row*3+col)
  opts=[f'title={{({letter})'+(f' $p_0={p0}\\%$' if row==0 else '')+'}',
        f'ymin={ymin},ymax={ymax},ytick={{{ticks}}}']
  if col==0:opts.append('ylabel={'+ylabel+'}')
  else:opts.append('yticklabels={}')
  if row<4:opts.append('xticklabels={},xtick style={draw=none}')
  lines.append('\\nextgroupplot['+','.join(opts)+']')
  path=f'data/figS1_workload/{metric}_p{p0}.csv'
  lines.append(r'''\addplot[only marks,mark=none,forget plot,
error bars/.cd,y dir=both,y explicit,error bar style={draw=black!80,line width=0.55pt},error mark options={rotate=90,mark size=1.7pt}]
table[col sep=comma,x=plot_x,y=value,y error minus=error_minus,y error plus=error_plus] {'''+path+'};')
  lines.append(r'\addplot[only marks,mark=diamond*,mark size=2.3pt,black!75,restrict x to domain=-0.1:0.1,forget plot] table[col sep=comma,x=plot_x,y=value] {'+path+'};')
  lines.append(r'\addplot[only marks,mark=*,mark size=2.0pt,abmBlue,restrict x to domain=0.9:3.1,forget plot] table[col sep=comma,x=plot_x,y=value] {'+path+'};')
lines.append(r'''\end{groupplot}
% Graphical key; no data lines connect the discrete workload specifications.
\coordinate (legendbase) at ($(group c1r5.south west)!0.5!(group c3r5.south east)+(0,-1.05cm)$);
\begin{scope}[shift={(legendbase)},font=\fontsize{8}{10}\selectfont]
\draw[black!75] plot[only marks,mark=diamond*,mark size=2.3pt] coordinates {(-5.65,0)};
\node[anchor=west] at (-5.43,0) {Fixed coverage};
\draw[abmBlue] plot[only marks,mark=*,mark size=2pt] coordinates {(-2.6,0)};
\node[anchor=west] at (-2.38,0) {State-responsive coverage};
\draw[black!80,line width=0.55pt] (2.12,-0.13)--(2.12,0.13);
\draw[black!80,line width=0.55pt] (2.02,-0.13)--(2.22,-0.13) (2.02,0.13)--(2.22,0.13);
\node[anchor=west] at (2.38,0) {95\% Student-$t$ CI};
\end{scope}
''')
(OUT/'figS1_workload.tex').write_text('\n'.join(lines)+end)

# S5: row-bootstrap intervals remain graphical; separate MC intervals in a
# numeric column prevent very narrow intervals from masking the estimate mark.
src=list(csv.DictReader((OUT/'data/figS2b_PRCC/source.csv').open()))
inp=['legal-strength','legal-response-time','alpha_legal','platform-speed','alpha_platform']
y_map={name:4-i for i,name in enumerate(inp)}
derived=OUT/'derived';derived.mkdir(exist_ok=True)
for p0 in [10,30,50]:
 for outcome in ['E_mean','O_final']:
  rows=sorted([r for r in src if int(r['p0'])==p0 and r['outcome']==outcome],key=lambda r:inp.index(r['input']))
  with (derived/f'prcc_{outcome}_p{p0}.csv').open('w',newline='') as f:
   fields=list(rows[0])+['plot_y'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
   for r in rows:w.writerow(dict(r,plot_y=y_map[r['input']]))

lines=[start,r'''% Source: supplied data/figS2b_PRCC/source.csv, validated separately.
% derived/prcc_*.csv adds only plot_y; all statistical fields retain source strings.
\begin{groupplot}[abm axis,group style={group size=2 by 3,horizontal sep=4.0cm,vertical sep=1.45cm},
 width=3.6cm,height=3.35cm,xmin=-1.05,xmax=1.05,xtick={-1,-0.5,0,0.5,1},
 ymin=-0.6,ymax=4.6,ytick={4,3,2,1,0},yticklabels={$L$,$\tau_L$,$\alpha_L$,$n_p$,$\alpha_P$},
 xlabel={PRCC},ymajorgrids=false,ytick style={draw=none},clip=false,
 title style={at={(0,1)},anchor=south west,yshift=4pt}]
''']
for row,p0 in enumerate([10,30,50]):
 for col,outcome in enumerate(['E_mean','O_final']):
  letter=chr(97+row*2+col)
  lines.append(f'\\nextgroupplot[title={{({letter}) $p_0={p0}\\%$}}'+(',xlabel={}' if row<2 else '')+']')
  lines.append(r'\addplot[black!50,densely dashed,line width=0.45pt,forget plot] coordinates {(0,-0.6) (0,4.6)};')
  rows=sorted([r for r in src if int(r['p0'])==p0 and r['outcome']==outcome],key=lambda r:inp.index(r['input']))
  for r in rows:
   y=y_map[r['input']];lo=r['row_ci95_low'];hi=r['row_ci95_high'];estimate=r['estimate']
   color,mark=('abmBlue','*') if r['actor']=='legal' else ('abmOrange','square*')
   lines.append(f'\\addplot[abmGray,line width=0.65pt,forget plot] coordinates {{({lo},{y}) ({hi},{y})}};')
   lines.append(f'\\draw[abmGray,line width=0.65pt] (axis cs:{lo},{y-0.08})--(axis cs:{lo},{y+0.08}) (axis cs:{hi},{y-0.08})--(axis cs:{hi},{y+0.08});')
   lines.append(f'\\addplot[only marks,mark={mark},mark size=2pt,{color},forget plot] coordinates {{({estimate},{y})}};')
  lines.append(r'''\fill[abmLight] ([xshift=0.27cm]rel axis cs:1,0) rectangle ([xshift=3.10cm]rel axis cs:1,1);
\node[anchor=south,font=\fontsize{8}{10}\selectfont] at ([xshift=1.69cm,yshift=2pt]rel axis cs:1,1) {MC 95\% interval};
\draw[black!18,line width=0.35pt] (rel axis cs:0,0.40385)--([xshift=3.10cm]rel axis cs:1,0.40385);
''')
  for r in rows:
   y=y_map[r['input']]
   lines.append(r'\node[font=\fontsize{8}{10}\selectfont,anchor=center] at ([xshift=1.69cm]axis cs:1.05,'+str(y)+r') {$['+rf'{float(r["mc_ci95_low"]):.4f},\,{float(r["mc_ci95_high"]):.4f}'+']$};')
lines.append(r'''\end{groupplot}
\node[font=\fontsize{10}{12}\selectfont,anchor=south] at ($(group c1r1.north west)+(3.2cm,0.9cm)$) {Mean effectiveness $\bar E$};
\node[font=\fontsize{10}{12}\selectfont,anchor=south] at ($(group c2r1.north west)+(3.2cm,0.9cm)$) {Wrongful exposure $O(50)$};
\coordinate (legendbase) at ($(group c1r3.south west)!0.5!([xshift=3.1cm]group c2r3.south east)+(0,-1.25cm)$);
\begin{scope}[shift={(legendbase)},font=\fontsize{8}{10}\selectfont]
\draw[abmBlue] plot[only marks,mark=*,mark size=2pt] coordinates {(-5.9,0)};
\node[anchor=west] at (-5.66,0) {Legal estimate};
\draw[abmOrange] plot[only marks,mark=square*,mark size=2pt] coordinates {(-2.9,0)};
\node[anchor=west] at (-2.66,0) {Platform estimate};
\draw[abmGray,line width=0.65pt] (0.65,0)--(1.25,0) (0.65,-0.07)--(0.65,0.07) (1.25,-0.07)--(1.25,0.07);
\node[anchor=west] at (1.43,0) {95\% row-bootstrap stability interval};
\end{scope}
''')
(OUT/'figS2b_PRCC.tex').write_text('\n'.join(lines)+end)
print('Generated S1 and S5 LaTeX sources.')
