"""
Draw the EXP-001 report figures as static SVG from the saved validation results.

    .venv\\Scripts\\python evaluation\\make_charts.py

Reads results/evaluator_validation_<version>.json and writes results/charts/*.svg.
Colours are the validated reference palette (slot 1 blue, slot 2 orange; checked with the
dataviz validator in light and dark). Hovering a bar shows its exact value (SVG <title>).
"""
import json
import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUT = RESULTS / "charts"
VERSIONS = ["safe-sop-eval-1.0", "safe-sop-eval-1.1"]
GROUP_LABELS = {"standard": "Standard defects", "hard-dev": "Hard cases (dev)", "hard-heldout": "Hard cases (held-out)"}

# Light colours are written as attributes on every element (PDF converters and other
# non-browser renderers ignore <style>); the stylesheet only overrides them in dark mode.
LIGHT = {
    "surface": 'fill="#fcfcfb"', "ink": 'fill="#0b0b0b"', "ink2": 'fill="#52514e"', "muted": 'fill="#898781"',
    "grid": 'stroke="#e1e0d9" stroke-width="1"', "axis": 'stroke="#c3c2b7" stroke-width="1"',
    "s1": 'fill="#2a78d6"', "s2": 'fill="#eb6834"',
}
STYLE = """
<style>
  text { font-family: Inter, "Segoe UI", system-ui, sans-serif; }
  @media (prefers-color-scheme: dark) {
    .surface { fill: #1a1a19; } .ink { fill: #f0efec; } .ink2 { fill: #c3c2b7; }
    .grid { stroke: #2c2c2a; } .axis { stroke: #383835; } .s1 { fill: #3987e5; } .s2 { fill: #d95926; }
  }
</style>"""


def bar(x, y, width, height, cls, tooltip, radius=4):
    """Horizontal bar anchored at the baseline, rounded only at the data end."""
    r = min(radius, width / 2, height / 2)
    if width <= 0:
        return f'<rect x="{x}" y="{y}" width="1.5" height="{height}" class="{cls}"><title>{escape(tooltip)}</title></rect>'
    return (f'<path class="{cls}" d="M{x},{y} h{width - r:.1f} a{r},{r} 0 0 1 {r},{r} v{height - 2 * r} '
            f'a{r},{r} 0 0 1 -{r},{r} h-{width - r:.1f} z"><title>{escape(tooltip)}</title></path>')


def frame(width, height, title, subtitle, body):
    svg = _frame(width, height, title, subtitle, body)
    return re.sub(r'class="(\w+)"', lambda m: f'class="{m[1]}" {LIGHT[m[1]]}', svg)


def _frame(width, height, title, subtitle, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'role="img" aria-label="{escape(title)}">{STYLE}'
            f'<rect class="surface" width="{width}" height="{height}" rx="8"/>'
            f'<text x="24" y="32" class="ink" font-size="16" font-weight="600">{escape(title)}</text>'
            f'<text x="24" y="52" class="ink2" font-size="12">{escape(subtitle)}</text>{body}</svg>')


def x_grid(left, top, plot_width, bottom):
    parts = []
    for tick in (0, 25, 50, 75, 100):
        x = left + plot_width * tick / 100
        parts.append(f'<line x1="{x}" y1="{top}" x2="{x}" y2="{bottom}" class="{"axis" if tick == 0 else "grid"}"/>')
        parts.append(f'<text x="{x}" y="{bottom + 16}" class="muted" font-size="11" text-anchor="middle">{tick}%</text>')
    return "".join(parts)


def chart_by_group(runs):
    groups = ["standard", "hard-dev", "hard-heldout"]
    left, plot_width, top, bar_h, gap, group_gap = 170, 360, 96, 16, 2, 22
    height = top + len(groups) * (2 * bar_h + gap + group_gap) + 30
    parts = [
        # Legend: two series, also named in each bar's label, so identity is never colour alone.
        f'<rect x="24" y="66" width="12" height="12" rx="3" class="s1"/><text x="42" y="76" class="ink2" font-size="12">v1.0</text>',
        f'<rect x="84" y="66" width="12" height="12" rx="3" class="s2"/><text x="102" y="76" class="ink2" font-size="12">v1.1</text>',
        x_grid(left, top - 6, plot_width, height - 30),
    ]
    y = top
    for group in groups:
        parts.append(f'<text x="{left - 12}" y="{y + bar_h + 5}" class="ink" font-size="12" text-anchor="end">{GROUP_LABELS[group]}</text>')
        for cls, version in (("s1", VERSIONS[0]), ("s2", VERSIONS[1])):
            m = runs[version]["summary"]["per_group"][group]
            width = plot_width * m["accuracy"]
            label = f"{m['correct']}/{m['cases']}"
            parts.append(bar(left, y, width, bar_h, cls, f"{version} · {GROUP_LABELS[group]}: {label} correct ({round(m['accuracy'] * 100)}%)"))
            parts.append(f'<text x="{left + width + 6}" y="{y + bar_h - 4}" class="ink2" font-size="11">{label}</text>')
            y += bar_h + gap
        y += group_gap
    return frame(600, height, "Cases handled correctly, by case group",
                 "EXP-001 · same 42 cases · held-out cases were written before v1.1", "".join(parts))



def main():
    runs = {v: json.loads((RESULTS / f"evaluator_validation_{v}.json").read_text(encoding="utf-8")) for v in VERSIONS}
    OUT.mkdir(exist_ok=True)
    (OUT / "exp001_accuracy_by_group.svg").write_text(chart_by_group(runs), encoding="utf-8")
    print("written:", ", ".join(p.name for p in sorted(OUT.glob("*.svg"))))


if __name__ == "__main__":
    main()
