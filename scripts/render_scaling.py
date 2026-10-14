# Copyright (c) 2026 WatchDelta contributors
# SPDX-License-Identifier: MIT
"""Optional retained-data vector route; no experiments or summary recomputation.

Drawing code reused from paper/figures/draw_scaling.py. See the artifact LICENSE.
Pass --source (retained data directory), --output-dir and --font-root explicitly.
"""
import argparse
import math
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor


def require_fonts(root):
    """Use installed metrics/outlines; never search, install, or copy fonts."""
    for relative in ("afm/urw/times/utmr8a.afm", "type1/urw/times/utmr8a.pfb"):
        if not (root / relative).is_file():
            raise FileNotFoundError(f"Required installed font: {root / relative}")


def load_data(source, name):
    lines = (source / ("scaling-" + name + ".dat")).read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].split() != ["files", "s0", "s1", "s2", "s3"]:
        raise ValueError("Expected files s0 s1 s2 s3 header")
    data = [tuple(map(float, line.split())) for line in lines[1:] if line.strip()]
    if any(len(row) != 5 for row in data) or [row[0] for row in data] != [10, 250, 1000, 5000]:
        raise ValueError("Expected four retained file counts and four series")
    low, high = (80, 1600) if name == "latency" else (8, 16000)
    if any(not math.isfinite(v) or not low <= v <= high for row in data for v in row[1:]):
        raise ValueError(f"{name} values must be finite and inside the retained log axis")
    return data

SERIES = [
    ("TS/native", "#24629b", [], "circle"),
    ("TS/content", "#a23e36", [4, 2], "square"),
    ("Docs/relevant", "#444444", [1, 2], "triangle"),
    ("Docs/content", "#714d94", [4, 2, 1, 2], "diamond"),
]


def marker(c, xp, yp, shape):
    if shape == "circle":
        c.circle(xp, yp, 1.8, stroke=0, fill=1)
    elif shape == "square":
        c.rect(xp - 1.8, yp - 1.8, 3.6, 3.6, stroke=0, fill=1)
    else:
        points = [(0, 2.3), (-2, -1.5), (2, -1.5)] if shape == "triangle" else [(0, 2.3), (-2.3, 0), (0, -2.3), (2.3, 0)]
        path = c.beginPath()
        path.moveTo(xp + points[0][0], yp + points[0][1])
        for dx, dy in points[1:]:
            path.lineTo(xp + dx, yp + dy)
        path.close()
        c.drawPath(path, stroke=0, fill=1)


def panel(c, data, left, right, limits, ticks, ylabel):
    bottom, top = 31, 119
    x = lambda v: left + (math.log10(v) - math.log10(8)) / (math.log10(6500) - math.log10(8)) * (right - left)
    ymin, ymax = limits
    y = lambda v: bottom + (math.log10(v) - math.log10(ymin)) / (math.log10(ymax) - math.log10(ymin)) * (top - bottom)
    c.setFont("ManuscriptRoman", 8)
    c.setLineWidth(.35)
    c.setFillColor(HexColor("#222222"))
    c.setStrokeColor(HexColor("#d6d6d6"))
    for tick, label in ticks:
        c.line(left, y(tick), right, y(tick))
        c.drawRightString(left - 5, y(tick) - 2.5, label)
    for tick, label in [(10, "10"), (100, "100"), (1000, "1k"), (5000, "5k")]:
        c.line(x(tick), bottom, x(tick), top)
        c.drawCentredString(x(tick), bottom - 12, label)
    c.setStrokeColor(HexColor("#444444"))
    c.setLineWidth(.5)
    c.line(left, bottom, left, top)
    c.line(left, bottom, right, bottom)
    c.setFont("ManuscriptRoman", 9)
    c.drawCentredString((left + right) / 2, 7, "Source files")
    c.saveState()
    c.translate(left - 35, (bottom + top) / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, ylabel)
    c.restoreState()
    for index, (_, color, dash, shape) in enumerate(SERIES, 1):
        c.setStrokeColor(HexColor(color))
        c.setFillColor(HexColor(color))
        c.setLineWidth(1)
        c.setDash(dash)
        path = c.beginPath()
        path.moveTo(x(data[0][0]), y(data[0][index]))
        for row in data[1:]:
            path.lineTo(x(row[0]), y(row[index]))
        c.drawPath(path)
        c.setDash([])
        for row in data:
            marker(c, x(row[0]), y(row[index]), shape)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    latency = load_data(args.source, "latency")
    cpu = load_data(args.source, "cpu")
    require_fonts(args.font_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    face = pdfmetrics.EmbeddedType1Face(
        str(args.font_root / "afm/urw/times/utmr8a.afm"),
        str(args.font_root / "type1/urw/times/utmr8a.pfb"))
    pdfmetrics.registerTypeFace(face)
    pdfmetrics.registerFont(pdfmetrics.Font("ManuscriptRoman", face.name, "WinAnsiEncoding"))
    c = canvas.Canvas(str(args.output_dir / "scaling.pdf"), pagesize=(516, 5.2 * 72 / 2.54),
                      invariant=1, initialFontName="ManuscriptRoman")
    c.setTitle("")
    panel(c, latency, 48, 245, (80, 1600),
          [(100, "100"), (300, "300"), (1000, "1k")],
          "Median final-agreement latency (ms)")
    panel(c, cpu, 311, 508, (8, 16000),
          [(10, "10"), (100, "100"), (1000, "1k"), (10000, "10k")],
          "Median worker CPU (ms)")
    for i, (label, color, dash, shape) in enumerate(SERIES):
        xp, yp = 44 + 118 * i, 136
        c.setStrokeColor(HexColor(color))
        c.setFillColor(HexColor(color))
        c.setLineWidth(1)
        c.setDash(dash)
        c.line(xp, yp, xp + 15, yp)
        c.setDash([])
        marker(c, xp + 7.5, yp, shape)
        c.setFillColor(HexColor("#222222"))
        c.setFont("ManuscriptRoman", 8)
        c.drawString(xp + 20, yp - 2.5, label)
    c.showPage()
    c.save()


if __name__ == "__main__":
    main()
