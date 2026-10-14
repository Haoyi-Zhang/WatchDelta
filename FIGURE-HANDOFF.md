# Figure reproduction

The complete project includes the manuscript figure sources in the sibling
`paper` directory. The standalone artifact repository contains the retained
measurements and their analysis, rather than a second copy of the paper.

The workflow and diagnostic-panel figures are editable TikZ schematics.
The scaling figure is a Python-generated vector PDF: `figures/draw_scaling.py`
reads `generated/scaling-latency.dat` and `generated/scaling-cpu.dat`, covering
10, 250, 1,000, and 5,000 source files. The analysis in
`scripts/analyze_compound_scaling.py` derives those tables from the retained
episodes. Rendering does not execute subjects, measure time, or fit a model.

From the manuscript directory, with ReportLab and the TeX URW Times font
available, regenerate the plotted PDF and compile the paper:

```sh
python figures/draw_scaling.py --font-root /path/to/texmf-dist/fonts
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

The PDF embeds the manuscript-compatible font. Captions remain in LaTeX.
Check the rendered plot's axes, units, series and source-table values after
regeneration. The live-watch and isolated-reference branches in the workflow
schematic remain distinct.
