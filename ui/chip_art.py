"""Circuit-board artwork for the mode chips: pure Python, no Qt. chip_layout() makes the copper traces of one chip
(bundles of parallel lines that bend at 45 degrees and end in round pads, like a real board)."""
from __future__ import annotations

import random


def chip_layout(seed: int, pw: float, ph: float):
    """Returns (lines, nodes) for a panel pw x ph. lines: lists of (x, y) points. nodes: (x, y, hollow)."""
    rng = random.Random(seed)
    lines: list[list[tuple[float, float]]] = []
    nodes: list[tuple[float, float, bool]] = []
    gap = 2.5
    xs = [pw * 0.16, pw * 0.5, pw * 0.82]
    rng.shuffle(xs)
    for bundle, x0 in enumerate(xs):
        n = rng.randint(4, 6)
        shift = rng.choice((-1, 1)) * rng.uniform(5, 11)
        y_bend = ph * rng.uniform(0.55, 0.80)
        x0 = min(max(x0, gap * n / 2 + 3 + max(0, -shift)), pw - gap * n - 3 - max(0, shift))
        for k in range(n):
            x = x0 + k * gap
            top = min(ph * rng.uniform(0.02, 0.28) + k * 1.2, y_bend - abs(shift) - 3)
            pts = [(x, ph), (x, y_bend), (x + shift, y_bend - abs(shift)), (x + shift, top)]
            lines.append(pts)
            nodes.append((x + shift, top, rng.random() < 0.55))
            if rng.random() < 0.35:                         # a short branch to the side, ending in a pad
                by = rng.uniform(top + 5, max(top + 6, y_bend - abs(shift) - 2))
                bx = x + shift + rng.choice((-1, 1)) * rng.uniform(4, 8)
                if 2 < bx < pw - 2:
                    lines.append([(x + shift, by), (bx, by), (bx, by - 3)])
                    nodes.append((bx, by - 3, True))
        nodes.append((x0, ph - 1.5, False))                  # solder pad at the bottom of the bundle
    # a few lone traces that cross between the bundles, like the board in the picture
    for _ in range(3):
        y = rng.uniform(ph * 0.15, ph * 0.85)
        x1 = rng.uniform(2, pw * 0.4)
        x2 = x1 + rng.uniform(pw * 0.2, pw * 0.5)
        dy = rng.choice((-1, 1)) * rng.uniform(3, 7)
        lines.append([(x1, y), (x2 - abs(dy), y), (x2, y + dy)])
        nodes.append((x1, y, False))
        nodes.append((x2, y + dy, True))
    return lines, nodes
