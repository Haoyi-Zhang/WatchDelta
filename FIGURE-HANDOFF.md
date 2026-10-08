# Figure handoff

No external redraw is required and no PPTX is supplied. Every essential visual is already an editable vector LaTeX/TikZ/PGFPlots source.

1. `paper/figures/workflow.tex` shows the live watch path and isolated terminal-source reference. The branches must remain distinct.
2. `paper/figures/scaling.tex` renders data-derived latency and worker-CPU curves for 10, 250, 1,000, and 5,000 source files. `scripts/analyze_compound_scaling.py` regenerates its `.dat` inputs.
3. `paper/figures/diagnostic-panel.tex` shows the exact and distance-three panel/codebook construction without crossing modules or overlapping labels.

Captions remain in LaTeX and no figure contains an internal overall title. Rebuild and inspect with:

```bash
cd ../paper
make refresh
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
python verify_paper.py --visual-inspection-confirmed --render-dpi 200
```
