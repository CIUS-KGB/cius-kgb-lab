#!/usr/bin/env python3
"""
Generate a pack of standalone SVG visualizations from comparison_results.json.

Goal: quick, dependency-free SVG exports you can drop into docs / slides.
Focus: accuracy, alignment, divergence between AI vs Human (labels + framing).

Usage (from repo root):
  python scripts/generate_alignment_svgs.py
  python scripts/generate_alignment_svgs.py --src docs/fixtures/comparison_results.json --out dev/svg_accuracy_alignment_pack_2026-05-06
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Palette (primary-colour, slide-friendly)
#
# Background : warm off-white  #f5f4f0
# Ink (text) : near-black      #111827
# Blue       : #2563eb   primary "category" / correct
# Red        : #dc2626   primary errors / mismatches
# Yellow     : #f59e0b   primary "framing" / secondary dimension
# Green      : #16a34a   best-outcome / both agreed
# Grid       : #dedad4   gridlines and bar tracks
# Subtitle   : #4b5563   secondary text
# ---------------------------------------------------------------------------

COL_BG       = "#f5f4f0"
COL_INK      = "#111827"
COL_SUBTITLE = "#4b5563"
COL_GRID     = "#dedad4"
COL_BLUE     = "#2563eb"
COL_RED      = "#dc2626"
COL_YELLOW   = "#f59e0b"
COL_GREEN    = "#16a34a"

_FONT = "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial"


# ---------------------------------------------------------------------------
# SVG primitives
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _truncate(s: str, max_chars: int) -> str:
    s = (s or "").strip()
    if max_chars <= 0:
        return ""
    if len(s) <= max_chars:
        return s
    if max_chars <= 1:
        return "..."
    return s[: max_chars - 1].rstrip() + "..."


def _wrap_lines(s: str, max_chars: int) -> List[str]:
    """Greedy word wrap for SVG text (approx by character count)."""
    s = (s or "").strip()
    if not s:
        return []
    if max_chars <= 8:
        return [_truncate(s, max_chars)]
    words = s.split()
    lines: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for w in words:
        w_len = len(w)
        if not cur:
            cur = [w]
            cur_len = w_len
            continue
        if cur_len + 1 + w_len <= max_chars:
            cur.append(w)
            cur_len += 1 + w_len
        else:
            lines.append(" ".join(cur))
            cur = [w]
            cur_len = w_len
    if cur:
        lines.append(" ".join(cur))
    return lines

def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
    )


def _svg_header(w: int, h: int, aria: str = "Chart") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{_xml_escape(aria)}">'
    )


def _svg_footer() -> str:
    return "</svg>"


def _rect(x: float, y: float, w: float, h: float, *,
          fill: str, stroke: str = "none", stroke_w: float = 1.0, rx: float = 0.0) -> str:
    rx_attr = f' rx="{rx}" ry="{rx}"' if rx else ""
    return (
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{max(0.0, w):.2f}" height="{max(0.0, h):.2f}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}"{rx_attr}/>'
    )


def _text(
    x: float, y: float, s: str, *,
    size: int = 14,
    weight: int = 400,
    fill: str = COL_INK,
    anchor: str = "start",
    transform: str = "",
) -> str:
    tr = f' transform="{transform}"' if transform else ""
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" font-family="{_FONT}" text-anchor="{anchor}"{tr}>'
        f'{_xml_escape(s)}</text>'
    )


def _line(x1: float, y1: float, x2: float, y2: float, *,
          stroke: str = COL_GRID, stroke_w: float = 1.0) -> str:
    return (
        f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
        f'stroke="{stroke}" stroke-width="{stroke_w}"/>'
    )


# ---------------------------------------------------------------------------
# Chart: 100% stacked outcomes bar
# ---------------------------------------------------------------------------

def _stacked_outcomes_svg(
    *,
    title: str,
    subtitle: str,
    counts: Dict[str, int],
    total: int,
    out_path: Path,
    minimal_text: bool = False,
) -> None:
    if total <= 0:
        return

    order = [
        "Both agreed",
        "Framing agreed, category did not",
        "Category agreed, framing did not",
        "Neither agreed",
    ]
    colors = {
        "Both agreed": COL_GREEN,
        "Framing agreed, category did not": COL_YELLOW,
        "Category agreed, framing did not": COL_BLUE,
        "Neither agreed": COL_RED,
    }

    w, h = 1200, 420
    margin_l = 80
    margin_r = 80
    margin_t = 120
    bar_h = 56
    bar_y = margin_t
    chart_w = w - margin_l - margin_r

    parts = [_svg_header(w, h, title)]
    parts.append(_rect(0, 0, w, h, fill=COL_BG))
    parts.append(_text(44, 50, title, size=21, weight=700))

    # subtitle (optional)
    if not minimal_text and subtitle:
        lines = _wrap_lines(subtitle, 110)[:3]
        for i, line in enumerate(lines):
            parts.append(_text(44, 70 + i * 17, line, size=13, fill=COL_SUBTITLE))

    # axis grid 0..100 (keep tick labels BELOW the bar; no overlap)
    for pct in range(0, 101, 10):
        gx = margin_l + (pct / 100.0) * chart_w
        parts.append(_line(gx, bar_y - 10, gx, bar_y + bar_h + 14, stroke=COL_GRID, stroke_w=1))
        if not minimal_text:
            parts.append(_text(gx, bar_y + bar_h + 34, f"{pct}%", size=11, fill=COL_SUBTITLE, anchor="middle"))

    # bar track
    parts.append(_rect(margin_l, bar_y, chart_w, bar_h, fill=COL_GRID, rx=6))

    # segments
    x = margin_l
    for key in order:
        c = int(counts.get(key, 0) or 0)
        if c <= 0:
            continue
        frac = c / total
        seg_w = frac * chart_w
        parts.append(_rect(x, bar_y, seg_w, bar_h, fill=colors[key], rx=6))

        # label inside if it fits
        label = f"{key} — {c:,} ({_fmt_pct(frac * 100)})"
        if seg_w >= 220:
            parts.append(_text(x + seg_w / 2, bar_y + bar_h * 0.67, label,
                               size=13, weight=700, fill="#ffffff", anchor="middle"))
        x += seg_w

    # No bottom footer label here: 100% stacked bars are self-explanatory.

    if not minimal_text:
        leg_y = bar_y + bar_h + 68
        lx = margin_l
        for key in order:
            c = int(counts.get(key, 0) or 0)
            if c <= 0:
                continue
            parts.append(_rect(lx, leg_y - 12, 14, 14, fill=colors[key], rx=2))
            parts.append(_text(lx + 18, leg_y, f"{key}: {c:,} ({_fmt_pct(100.0 * c / total)})",
                               size=11, fill=COL_SUBTITLE))
            leg_y += 18

    parts.append(_svg_footer())
    out_path.write_text("\n".join(parts), encoding="utf-8")


# ---------------------------------------------------------------------------
# Chart: length buckets vs agreement (supports "length is not the culprit")
# ---------------------------------------------------------------------------

def _length_bins_svg(
    *,
    title: str,
    subtitle: str,
    rows: Sequence[Dict[str, Any]],
    out_path: Path,
    minimal_text: bool = False,
) -> None:
    if not rows:
        return

    # Use max length across languages, as described in the whitepaper.
    def seg_len(r: Dict[str, Any]) -> int:
        return max(len(r.get("entry_eng") or ""), len(r.get("entry_rus") or ""))

    # Buckets aligned to common reading of the .tex discussion.
    # (The fixture is small; keep a small number of buckets.)
    bins = [
        ("≤49", 0, 49),
        ("50–99", 50, 99),
        ("100–199", 100, 199),
        ("≥200", 200, 10**9),
    ]

    both_counts: List[int] = []
    not_counts: List[int] = []
    totals: List[int] = []
    for _lab, lo, hi in bins:
        b = 0
        n = 0
        for r in rows:
            L = seg_len(r)
            if lo <= L <= hi:
                if r.get("both_match"):
                    b += 1
                else:
                    n += 1
        both_counts.append(b)
        not_counts.append(n)
        totals.append(b + n)

    w, h = 1200, 520
    margin_l, margin_r = 120, 60
    margin_t, margin_b = 120, 76
    chart_w = w - margin_l - margin_r
    chart_h = h - margin_t - margin_b

    max_total = max(totals) if totals else 1
    axis_max, ticks = _nice_count_axis(max_total)

    def x_of(v: float) -> float:
        return margin_l + (v / axis_max) * chart_w if axis_max else margin_l

    parts = [_svg_header(w, h, title)]
    parts.append(_rect(0, 0, w, h, fill=COL_BG))
    parts.append(_text(44, 50, title, size=21, weight=700))
    if not minimal_text and subtitle:
        for i, line in enumerate(_wrap_lines(subtitle, 110)[:3]):
            parts.append(_text(44, 70 + i * 17, line, size=13, fill=COL_SUBTITLE))

    # grid
    for t in ticks:
        gx = x_of(t)
        parts.append(_line(gx, margin_t - 6, gx, margin_t + chart_h, stroke=COL_GRID, stroke_w=1))
        if not minimal_text:
            parts.append(_text(gx, margin_t + chart_h + 17, str(int(t)), size=11, fill=COL_SUBTITLE, anchor="middle"))
    parts.append(_line(margin_l, margin_t, margin_l, margin_t + chart_h, stroke=COL_INK, stroke_w=1.3))
    if not minimal_text:
        parts.append(_text(margin_l + chart_w / 2, h - 10, "Number of segments (bucketed by max(ENG len, RUS len))",
                           size=12, fill=COL_SUBTITLE, anchor="middle"))

    # rows
    row_gap = 14
    row_h = (chart_h - row_gap * (len(bins) - 1)) / max(1, len(bins))
    for i, (lab, _lo, _hi) in enumerate(bins):
        y = margin_t + i * (row_h + row_gap)
        total_i = totals[i]
        if total_i <= 0:
            # show label but no bars
            parts.append(_text(margin_l - 10, y + row_h * 0.70, lab, size=13, weight=600, anchor="end"))
            continue

        b = both_counts[i]
        n = not_counts[i]
        bw = x_of(b) - margin_l
        nw = x_of(n) - margin_l

        # track
        parts.append(_rect(margin_l, y, chart_w, row_h, fill=COL_GRID, rx=4))
        # "both agreed" then "not both" stacked horizontally
        parts.append(_rect(margin_l, y, bw, row_h, fill=COL_GREEN, rx=4))
        parts.append(_rect(margin_l + bw, y, nw, row_h, fill=COL_RED, rx=4))

        parts.append(_text(margin_l - 10, y + row_h * 0.70, lab, size=13, weight=600, anchor="end"))
        parts.append(_text(margin_l + chart_w + 10, y + row_h * 0.70,
                           f"{total_i:,} total", size=12, fill=COL_SUBTITLE, anchor="start"))

        # tiny labels (only if room)
        if bw >= 46:
            parts.append(_text(margin_l + bw / 2, y + row_h * 0.70, f"{b}",
                               size=12, weight=700, fill="#ffffff", anchor="middle"))
        else:
            # place outside if too small
            parts.append(_text(margin_l + bw + 6, y + row_h * 0.70, f"{b}",
                               size=12, weight=700, fill=COL_INK, anchor="start"))

        if nw >= 46:
            parts.append(_text(margin_l + bw + nw / 2, y + row_h * 0.70, f"{n}",
                               size=12, weight=700, fill="#ffffff", anchor="middle"))
        else:
            parts.append(_text(margin_l + bw + nw + 6, y + row_h * 0.70, f"{n}",
                               size=12, weight=700, fill=COL_INK, anchor="start"))

    if not minimal_text:
        lx = margin_l
        ly = margin_t - 22
        parts.append(_rect(lx, ly - 12, 14, 14, fill=COL_GREEN, rx=2))
        parts.append(_text(lx + 18, ly, "Both agreed", size=11, fill=COL_SUBTITLE))
        parts.append(_rect(lx + 130, ly - 12, 14, 14, fill=COL_RED, rx=2))
        parts.append(_text(lx + 148, ly, "Not both agreed", size=11, fill=COL_SUBTITLE))

    parts.append(_svg_footer())
    out_path.write_text("\n".join(parts), encoding="utf-8")


# ---------------------------------------------------------------------------
# Chart: top Ideological Layers swap arrows (directional mismatch flow)
# ---------------------------------------------------------------------------

def _il_swap_arrows_svg(
    *,
    title: str,
    subtitle: str,
    pairs: List[Tuple[str, str]],
    out_path: Path,
    top_k: int = 3,
    minimal_text: bool = False,
) -> None:
    # pairs are (human_il, ai_il)
    counts: Counter = Counter()
    for h, a in pairs:
        h = (h or "").strip() or "(blank)"
        a = (a or "").strip() or "(blank)"
        if h == a:
            continue
        counts[(h, a)] += 1

    top = counts.most_common(top_k)
    if not top:
        return

    w, h = 1200, 460
    margin_l, margin_r = 70, 70
    margin_t, margin_b = 120, 60
    chart_w = w - margin_l - margin_r

    parts = [_svg_header(w, h, title)]
    parts.append(_rect(0, 0, w, h, fill=COL_BG))
    parts.append(_text(44, 50, title, size=21, weight=700))
    if not minimal_text and subtitle:
        for i, line in enumerate(_wrap_lines(subtitle, 110)[:3]):
            parts.append(_text(44, 70 + i * 17, line, size=13, fill=COL_SUBTITLE))

    # three lanes
    lane_y0 = margin_t + 40
    lane_gap = 90
    node_w = 360
    node_h = 44
    left_x = margin_l
    right_x = margin_l + chart_w - node_w

    max_c = max(c for (_, c) in top)

    for i, ((human, ai), c) in enumerate(top):
        y = lane_y0 + i * lane_gap
        # nodes
        parts.append(_rect(left_x, y, node_w, node_h, fill="rgba(220,38,38,0.08)", stroke="rgba(17,24,39,0.12)", stroke_w=1, rx=10))
        parts.append(_rect(right_x, y, node_w, node_h, fill="rgba(37,99,235,0.08)", stroke="rgba(17,24,39,0.12)", stroke_w=1, rx=10))
        parts.append(_text(left_x + 14, y + 28, _truncate(human, 42), size=14, weight=700, fill=COL_INK))
        parts.append(_text(right_x + 14, y + 28, _truncate(ai, 42), size=14, weight=700, fill=COL_INK))

        # arrow thickness by count
        t = math.sqrt(c / max_c) if max_c else 0.0
        sw = 2.0 + 9.0 * t
        ax1 = left_x + node_w + 16
        ax2 = right_x - 16
        ay = y + node_h / 2
        parts.append(
            f'<path d="M {ax1:.2f} {ay:.2f} C {(ax1+120):.2f} {(ay-30):.2f}, {(ax2-120):.2f} {(ay-30):.2f}, {ax2:.2f} {ay:.2f}" '
            f'fill="none" stroke="{COL_RED}" stroke-width="{sw:.2f}" opacity="0.78"/>'
        )
        # arrow head
        parts.append(
            f'<path d="M {ax2:.2f} {ay:.2f} l -10 -7 l 2 7 l -2 7 z" fill="{COL_RED}" opacity="0.78"/>'
        )
        parts.append(_text((ax1 + ax2) / 2, ay - 12, f"{c} segments", size=12, weight=700, fill=COL_INK, anchor="middle"))

        if not minimal_text:
            parts.append(_text(left_x, y - 10, "Human label", size=11, fill=COL_SUBTITLE))
            parts.append(_text(right_x, y - 10, "AI label", size=11, fill=COL_SUBTITLE))

    if not minimal_text:
        parts.append(_text(margin_l + chart_w / 2, h - 14, "Top directional swaps (off-diagonal only)",
                           size=12, fill=COL_SUBTITLE, anchor="middle"))
    parts.append(_svg_footer())
    out_path.write_text("\n".join(parts), encoding="utf-8")


# ---------------------------------------------------------------------------
# Chart: "ideological morpheme" cue words for a dominant swap
# ---------------------------------------------------------------------------

def _ideological_morpheme_cues_svg(
    *,
    title: str,
    subtitle: str,
    rows: Sequence[Dict[str, Any]],
    human_label: str,
    ai_label: str,
    out_path: Path,
    top_n: int = 14,
) -> None:
    """
    Show which recurring tokens are disproportionately present when the AI flips a
    given Ideological Layers label.

    Swap set  S: human_framing==human_label AND llm_framing==ai_label
    Control C: human_framing==human_label AND llm_framing==human_label

    Tokens are extracted from Russian text when present (fallback to English).
    We use a smoothed log-odds score to rank cues:
        score(w) = log((cS+α)/(NS-cS+α)) - log((cC+α)/(NC-cC+α))
    """
    human_label = (human_label or "").strip()
    ai_label = (ai_label or "").strip()
    if not human_label or not ai_label or human_label == ai_label:
        return

    swap = []
    ctrl = []
    for r in rows:
        hf = (r.get("human_framing") or "").strip()
        af = (r.get("llm_framing") or "").strip()
        if hf != human_label:
            continue
        if af == ai_label:
            swap.append(r)
        elif af == human_label:
            ctrl.append(r)

    if len(swap) < 8 or len(ctrl) < 8:
        return

    token_re = re.compile(r"[A-Za-zА-Яа-яЁёІіЇїЄєҐґ'-]{4,}")

    def tokens_for(r: Dict[str, Any]) -> List[str]:
        # Prefer Russian; fall back to English.
        txt = (r.get("entry_rus") or "").strip() or (r.get("entry_eng") or "").strip()
        toks = token_re.findall(txt)
        return [t.lower() for t in toks]

    # Use *segment-level presence* rather than raw token counts:
    # count how many segments contain the token at least once.
    segS = Counter()
    segC = Counter()
    for r in swap:
        segS.update(set(tokens_for(r)))
    for r in ctrl:
        segC.update(set(tokens_for(r)))

    nS = len(swap)
    nC = len(ctrl)
    if nS < 8 or nC < 8:
        return

    # Score: extra segments per 100 where token appears (swap - agreed).
    scores: List[Tuple[str, float, int, int]] = []
    vocab = set(segS) | set(segC)
    for w in vocab:
        s = int(segS.get(w, 0))
        c = int(segC.get(w, 0))
        if s + c < 4:
            continue
        rateS = 100.0 * s / nS
        rateC = 100.0 * c / nC
        score = rateS - rateC
        scores.append((w, score, s, c))

    scores.sort(key=lambda t: t[1], reverse=True)
    top = [t for t in scores if t[1] > 0][:top_n]
    if not top:
        return

    items = [(f"{w}  (swap {s} vs agreed {c})", float(sc)) for (w, sc, s, c) in top]
    # reuse bar chart; value is extra segments per 100 (swap - agreed)
    _bar_chart_svg(
        title=title,
        subtitle=subtitle,
        items=items,
        out_path=out_path,
        value_fmt="count",
        bar_colors=None,
        x_axis_label="Extra segments per 100 containing token (swap minus agreed; higher = more associated with the swap)",
    )


def _ideological_morpheme_cues_dumbbell_svg(
    *,
    title: str,
    subtitle: str,
    rows: Sequence[Dict[str, Any]],
    human_label: str,
    ai_label: str,
    out_path: Path,
    top_n: int = 14,
    minimal_text: bool = False,
) -> None:
    """
    More communicative view than "cue strength": show the two actual rates
    side-by-side (dumbbell plot):

      swap_rate(token)   vs   agreed_rate(token)

    where rates are "% of segments containing token at least once".
    """
    human_label = (human_label or "").strip()
    ai_label = (ai_label or "").strip()
    if not human_label or not ai_label or human_label == ai_label:
        return

    swap = []
    ctrl = []
    for r in rows:
        hf = (r.get("human_framing") or "").strip()
        af = (r.get("llm_framing") or "").strip()
        if hf != human_label:
            continue
        if af == ai_label:
            swap.append(r)
        elif af == human_label:
            ctrl.append(r)
    if len(swap) < 8 or len(ctrl) < 8:
        return

    token_re = re.compile(r"[A-Za-zА-Яа-яЁёІіЇїЄєҐґ'-]{4,}")

    def tokens_for(r: Dict[str, Any]) -> List[str]:
        txt = (r.get("entry_rus") or "").strip() or (r.get("entry_eng") or "").strip()
        toks = token_re.findall(txt)
        return [t.lower() for t in toks]

    segS = Counter()
    segC = Counter()
    for r in swap:
        segS.update(set(tokens_for(r)))
    for r in ctrl:
        segC.update(set(tokens_for(r)))

    nS = len(swap)
    nC = len(ctrl)

    rows_scored: List[Tuple[str, float, float, int, int]] = []
    for w in (set(segS) | set(segC)):
        s = int(segS.get(w, 0))
        c = int(segC.get(w, 0))
        if s + c < 4:
            continue
        rs = 100.0 * s / nS
        rc = 100.0 * c / nC
        if rs <= rc:
            continue
        rows_scored.append((w, rs, rc, s, c))

    rows_scored.sort(key=lambda t: (t[1] - t[2], t[1], t[3]), reverse=True)
    top = rows_scored[:top_n]
    if not top:
        return

    # Layout
    w, h = 1200, max(520, 160 + len(top) * 34)
    margin_l = 420
    margin_r = 60
    margin_t = 120
    margin_b = 70
    chart_w = w - margin_l - margin_r
    chart_h = h - margin_t - margin_b

    # x axis 0..max_rate rounded up
    max_rate = max(rs for (_w, rs, _rc, _s, _c) in top)
    x_hi = min(100.0, math.ceil(max_rate / 10.0) * 10.0)
    if x_hi < 20:
        x_hi = 20.0

    def x_of(pct: float) -> float:
        return margin_l + (pct / x_hi) * chart_w if x_hi else margin_l

    parts = [_svg_header(w, h, title)]
    parts.append(_rect(0, 0, w, h, fill=COL_BG))
    parts.append(_text(44, 50, title, size=21, weight=700))
    if not minimal_text and subtitle:
        for i, line in enumerate(_wrap_lines(subtitle, 110)[:3]):
            parts.append(_text(44, 70 + i * 17, line, size=13, fill=COL_SUBTITLE))

    # grid + ticks (0..x_hi)
    step = 10.0 if x_hi <= 60 else 20.0
    ticks = [t for t in [step * i for i in range(int(x_hi / step) + 1)] if t <= x_hi + 0.001]
    for t in ticks:
        gx = x_of(t)
        parts.append(_line(gx, margin_t - 6, gx, margin_t + chart_h, stroke=COL_GRID, stroke_w=1))
        if not minimal_text:
            parts.append(_text(gx, margin_t + chart_h + 17, f"{int(t)}%", size=11, fill=COL_SUBTITLE, anchor="middle"))
    parts.append(_line(margin_l, margin_t, margin_l, margin_t + chart_h, stroke=COL_INK, stroke_w=1.3))

    if not minimal_text:
        parts.append(_text(margin_l + chart_w / 2, h - 10,
                           "Share of segments containing token (swap vs agreed)",
                           size=12, fill=COL_SUBTITLE, anchor="middle"))

    if not minimal_text:
        lx = margin_l
        ly = margin_t - 22
        parts.append(_rect(lx, ly - 12, 14, 14, fill=COL_RED, rx=2))
        parts.append(_text(lx + 18, ly, "Swap set", size=11, fill=COL_SUBTITLE))
        parts.append(_rect(lx + 110, ly - 12, 14, 14, fill=COL_GREEN, rx=2))
        parts.append(_text(lx + 128, ly, "Agreed set", size=11, fill=COL_SUBTITLE))

    # rows
    row_h = chart_h / max(1, len(top))
    for i, (tok, rs, rc, s, c) in enumerate(top):
        y = margin_t + i * row_h + row_h * 0.62
        tok_label = f"{_truncate(tok, 18)}  (swap {s}/{nS}, agreed {c}/{nC})"
        # extra padding so the label doesn't touch the y-axis line
        parts.append(_text(margin_l - 26, y, tok_label, size=13, weight=600, anchor="end"))

        x1 = x_of(rc)
        x2 = x_of(rs)
        parts.append(_line(x1, y - 5, x2, y - 5, stroke="rgba(17,24,39,0.25)", stroke_w=3))
        parts.append(f'<circle cx="{x2:.2f}" cy="{(y-5):.2f}" r="6" fill="{COL_RED}" opacity="0.92"/>')
        parts.append(f'<circle cx="{x1:.2f}" cy="{(y-5):.2f}" r="6" fill="{COL_GREEN}" opacity="0.92"/>')

        # labels
        parts.append(_text(x2 + 10, y - 1, f"{rs:.0f}%", size=12, weight=700, fill=COL_INK, anchor="start"))
        parts.append(_text(x1 - 10, y - 1, f"{rc:.0f}%", size=12, weight=700, fill=COL_INK, anchor="end"))

    parts.append(_svg_footer())
    out_path.write_text("\n".join(parts), encoding="utf-8")


def _pct(n: int, d: int) -> float:
    return (100.0 * n / d) if d else 0.0


def _fmt_pct(p: float) -> str:
    if p >= 99.95:
        return "100%"
    if p <= 0.05:
        return "0%"
    if p >= 10:
        return f"{p:.0f}%"
    return f"{p:.1f}%"


def _nice_count_axis(raw_max: float) -> Tuple[float, List[float]]:
    """
    Given a raw maximum count, return (axis_max, tick_list) with clean round ticks.
    Targets roughly 5 ticks. Handles raw_max < 10 correctly.
    """
    if raw_max <= 0:
        return 5.0, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    # pick a step size that gives ~5 ticks
    rough_step = raw_max / 4.0
    magnitude  = 10 ** math.floor(math.log10(max(rough_step, 0.5)))
    nice_steps = [magnitude * m for m in (1, 2, 2.5, 5, 10)]
    step = next((s for s in nice_steps if s * 4 >= raw_max), nice_steps[-1])
    axis_max = step * math.ceil(raw_max / step)
    ticks = [step * i for i in range(int(axis_max / step) + 1)]
    return axis_max, ticks


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _read_rows(src: Path) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    data = json.loads(src.read_text(encoding="utf-8"))
    doc_meta: Dict[str, str] = {}
    for d in (data.get("documents") or []):
        if not isinstance(d, dict):
            continue
        doc_id = str(d.get("document_id") or "").strip()
        if not doc_id:
            continue
        short   = str(d.get("short_title")   or "").strip()
        display = str(d.get("display_name")   or "").strip()
        doc_meta[doc_id] = short or display or f"Doc {doc_id}"

    cbd: Dict[str, Any] = data.get("comparison_by_doc", {}) or {}
    out: List[Dict[str, Any]] = []
    for doc_id, payload in cbd.items():
        for r in (payload.get("aligned_rows") or []):
            rr = dict(r)
            rr["_doc_id"] = str(doc_id)
            out.append(rr)
    return out, doc_meta


# ---------------------------------------------------------------------------
# Chart: horizontal bar chart
# ---------------------------------------------------------------------------

def _bar_chart_svg(
    *,
    title: str,
    subtitle: str,
    items: Sequence[Tuple[str, float]],
    out_path: Path,
    value_fmt: str = "pct",
    bar_colors: Optional[Dict[str, str]] = None,
    x_axis_label: str = "",
    minimal_text: bool = False,
) -> None:
    """
    Horizontal bar chart.

    Percentage axis: uses a fixed 0–100% baseline so the visual scale is
    consistent across charts (no "weird" non-zero starts).

    Count axis: uses _nice_count_axis() for clean round tick values.

    Bar colour: explicit bar_colors entry wins. Fallback is COL_BLUE (uniform,
    no accidental value encoding through hue).
    """
    if not items:
        return

    LABEL_FONT = 13
    CHAR_W     = LABEL_FONT * 0.62
    MAX_CHARS  = 52

    labels_shown = [_truncate(lbl, MAX_CHARS) for lbl, _ in items]
    max_lbl_px   = max(len(l) * CHAR_W for l in labels_shown)

    w        = 1200
    h        = max(500, 110 + len(items) * 48)
    margin_l = int(max_lbl_px + 64)
    margin_r = 80
    margin_t = 108
    margin_b = 48 + (20 if x_axis_label else 0)
    chart_w  = w - margin_l - margin_r
    chart_h  = h - margin_t - margin_b

    vals = [v for _, v in items]

    if value_fmt == "pct":
        x_lo      = 0.0
        x_hi      = 100.0
        span      = 100.0
        tick_step = 10
        ticks     = [float(t) for t in range(0, 101, tick_step)]

        def bar_frac(v: float) -> float:
            return (v - x_lo) / span if span else 0.0
        def fmt_tick(t: float) -> str:
            return f"{int(t)}%"
        def fmt_val(v: float) -> str:
            return _fmt_pct(v)

    else:
        raw_max       = max(vals) if vals else 1.0
        x_hi, ticks   = _nice_count_axis(raw_max)
        x_lo          = 0.0
        span          = x_hi

        def bar_frac(v: float) -> float:
            return v / x_hi if x_hi else 0.0
        def fmt_tick(t: float) -> str:
            return str(int(t))
        def fmt_val(v: float) -> str:
            return f"{int(v):,}"

    def tick_x(t: float) -> float:
        return margin_l + ((t - x_lo) / span) * chart_w if span else margin_l

    parts = [_svg_header(w, h, title)]
    parts.append(_rect(0, 0, w, h, fill=COL_BG))

    # title
    parts.append(_text(44, 50, title, size=21, weight=700))

    # subtitle: optional (omit for slide-friendly SVGs)
    if not minimal_text and subtitle:
        words  = subtitle.split(" ")
        lines: List[str] = []
        cur    = ""
        for word in words:
            if len(cur) + 1 + len(word) > 110 and cur:
                lines.append(cur)
                cur = word
            else:
                cur = (cur + " " + word).strip()
        if cur:
            lines.append(cur)
        for li, line in enumerate(lines[:3]):
            parts.append(_text(44, 70 + li * 17, line, size=13, fill=COL_SUBTITLE))

    # gridlines + tick labels (optional)
    for t in ticks:
        gx = tick_x(t)
        parts.append(_line(gx, margin_t - 6, gx, margin_t + chart_h,
                           stroke=COL_GRID, stroke_w=1))
        if not minimal_text:
            parts.append(_text(gx, margin_t + chart_h + 17, fmt_tick(t),
                               size=11, fill=COL_SUBTITLE, anchor="middle"))

    # baseline axis line at x_lo
    parts.append(_line(tick_x(x_lo), margin_t, tick_x(x_lo), margin_t + chart_h,
                       stroke=COL_INK, stroke_w=1.3))

    if x_axis_label and not minimal_text:
        parts.append(_text(margin_l + chart_w / 2, h - 10, x_axis_label,
                           size=12, fill=COL_SUBTITLE, anchor="middle"))

    # bars
    n       = len(items)
    row_gap = 7
    row_h   = (chart_h - row_gap * (n - 1)) / max(1, n)

    for i, ((label, val), label_shown) in enumerate(zip(items, labels_shown)):
        y    = margin_t + i * (row_h + row_gap)
        bw   = max(2.0, bar_frac(val) * chart_w)
        fill = (bar_colors or {}).get(label, COL_BLUE)

        parts.append(_rect(margin_l, y, chart_w, row_h, fill=COL_GRID, rx=4))
        parts.append(_rect(margin_l, y, bw, row_h, fill=fill, rx=4))
        parts.append(_text(margin_l - 10, y + row_h * 0.70, label_shown,
                           size=LABEL_FONT, weight=600, anchor="end"))

        val_s  = fmt_val(val)
        val_px = len(val_s) * CHAR_W
        if bw > val_px + 20:
            parts.append(_text(margin_l + bw - 8, y + row_h * 0.70, val_s,
                               size=LABEL_FONT, weight=700, fill="#ffffff", anchor="end"))
        else:
            parts.append(_text(margin_l + bw + 6, y + row_h * 0.70, val_s,
                               size=LABEL_FONT, weight=700, anchor="start"))

    parts.append(_svg_footer())
    out_path.write_text("\n".join(parts), encoding="utf-8")


# ---------------------------------------------------------------------------
# Chart: confusion matrix
# ---------------------------------------------------------------------------

def _confusion_svg(
    *,
    title: str,
    subtitle: str,
    pairs: List[Tuple[str, str]],
    out_path: Path,
    top_n: int = 12,
    row_axis_label: str = "Human label",
    col_axis_label: str = "AI label",
    minimal_text: bool = False,
) -> None:
    """
    Confusion matrix with a two-tone colour scheme.
    Diagonal cells (AI agreed with human) use the blue ramp.
    Off-diagonal cells (disagreement) use the red ramp.
    This makes agreement vs error immediately visible by hue, not just by
    reading numbers.
    """
    counts: Counter = Counter()
    for a, b in pairs:
        counts[a] += 1
        counts[b] += 1

    top_labels = [k for k, _ in counts.most_common(top_n)]
    OTHER      = "__OTHER__"

    def norm(x: str) -> str:
        x = (x or "").strip() or "(blank)"
        return x if x in top_labels else OTHER

    mat: Counter = Counter()
    for human, ai in pairs:
        mat[(norm(human), norm(ai))] += 1

    grid_labels = top_labels + [OTHER]
    n = len(grid_labels)

    CELL      = 66
    LABEL_W   = 230
    COL_HDR_H = 150
    AXIS_TTL  = 30

    grid_px  = CELL * n
    w        = LABEL_W + AXIS_TTL + grid_px + 60
    # wrap title/subtitle to avoid overflowing small canvases
    wrap_chars = max(24, int((w - 72) / 7.2))
    title_lines = _wrap_lines(title, wrap_chars)
    subtitle_lines = _wrap_lines(subtitle, wrap_chars) if (subtitle and not minimal_text) else []
    title_h = 18 * max(1, len(title_lines)) + 10
    subtitle_h = 16 * len(subtitle_lines)
    TITLE_H = 28 + title_h + subtitle_h

    h        = TITLE_H + COL_HDR_H + grid_px + 60

    margin_l = LABEL_W + AXIS_TTL
    margin_t = TITLE_H + COL_HDR_H
    max_v    = max(mat.values()) if mat else 1

    parts = [_svg_header(w, h, title)]
    parts.append(_rect(0, 0, w, h, fill=COL_BG))

    y0 = 44
    for line in (title_lines or [title]):
        parts.append(_text(36, y0, line, size=21, weight=700))
        y0 += 22
    y0 += 2
    for line in subtitle_lines:
        parts.append(_text(36, y0, line, size=13, fill=COL_SUBTITLE))
        y0 += 17

    # axis titles (optional)
    if not minimal_text:
        cx_col = margin_l + grid_px / 2
        parts.append(_text(cx_col, TITLE_H - 4, col_axis_label,
                           size=14, weight=700, anchor="middle"))

        rx = 18.0
        ry = margin_t + grid_px / 2
        parts.append(_text(rx, ry, row_axis_label, size=14, weight=700, anchor="middle",
                           transform=f"rotate(-90 {rx:.1f} {ry:.1f})"))

    # column header labels rotated -45 around each cell's centre-top
    for j, lab in enumerate(grid_labels):
        show = "Other" if lab == OTHER else _truncate(lab, 22)
        cx   = margin_l + j * CELL + CELL / 2
        cy   = margin_t - 10
        parts.append(
            f'<text x="{cx:.2f}" y="{cy:.2f}" font-size="11" font-weight="600" '
            f'fill="{COL_INK}" font-family="{_FONT}" text-anchor="end" '
            f'transform="rotate(-45 {cx:.2f} {cy:.2f})">{_xml_escape(show)}</text>'
        )

    # row labels
    for i, lab in enumerate(grid_labels):
        show = "Other" if lab == OTHER else _truncate(lab, 28)
        y    = margin_t + i * CELL + CELL / 2 + 4
        parts.append(_text(margin_l - 10, y, show, size=11, anchor="end"))

    # cells: blue ramp on diagonal, red ramp off-diagonal
    for i, r_lab in enumerate(grid_labels):
        for j, c_lab in enumerate(grid_labels):
            v       = mat.get((r_lab, c_lab), 0)
            t       = math.sqrt(v / max_v) if max_v else 0.0
            is_diag = (r_lab == c_lab)

            if is_diag:
                r_ch, g_ch, b_ch = 37, 99, 235     # blue
            else:
                r_ch, g_ch, b_ch = 220, 38, 38     # red

            alpha     = 0.07 + 0.73 * t
            cell_fill = f"rgba({r_ch},{g_ch},{b_ch},{alpha:.2f})"
            cx        = margin_l + j * CELL
            cy        = margin_t + i * CELL

            parts.append(_rect(cx, cy, CELL, CELL, fill=cell_fill,
                               stroke="rgba(26,26,46,0.08)", stroke_w=1))
            if v:
                txt_fill = "#ffffff" if t > 0.52 else COL_INK
                parts.append(_text(cx + CELL / 2, cy + CELL / 2 + 5, str(v),
                                   size=12, weight=700, fill=txt_fill, anchor="middle"))

    if not minimal_text:
        leg_y = h - 24
        for col, lab, lx in (
            (COL_BLUE, "Agreed (on the diagonal)", margin_l),
            (COL_RED, "Disagreed (off-diagonal)",  margin_l + 220),
        ):
            parts.append(_rect(lx, leg_y - 12, 14, 14, fill=col, rx=2))
            parts.append(_text(lx + 18, leg_y, lab, size=11, fill=COL_SUBTITLE))

    parts.append(_svg_footer())
    out_path.write_text("\n".join(parts), encoding="utf-8")


# ---------------------------------------------------------------------------
# Chart: scatter plot -- segment length vs agreement
# ---------------------------------------------------------------------------

def _scatter_len_accuracy_svg(
    *,
    title: str,
    subtitle: str,
    rows: Sequence[Dict[str, Any]],
    out_path: Path,
) -> None:
    """
    Scatter: x = max(len(eng), len(rus)), y = agreed (1) or disagreed (0).

    X axis is capped at the 98th-percentile length to prevent extreme outliers
    from collapsing everything to the left. Points beyond the cap plot at the cap.

    Y positions are jittered vertically within a fixed band so dot density is
    readable even at high volumes.
    """
    pts: List[Tuple[int, int]] = []
    for r in rows:
        length = max(len(r.get("entry_eng") or ""), len(r.get("entry_rus") or ""))
        pts.append((length, 1 if r.get("both_match") else 0))
    if not pts:
        return

    xs    = sorted(p[0] for p in pts)
    p98   = xs[int(len(xs) * 0.98)] if xs else 200
    x_cap = max(200, int(math.ceil(p98 / 100) * 100))

    # x tick spacing: target ~7 ticks
    rough = x_cap / 6.0
    mag   = 10 ** math.floor(math.log10(max(rough, 1)))
    x_step = math.ceil(rough / mag) * mag
    x_ticks = list(range(0, x_cap + 1, int(x_step)))
    if x_ticks[-1] < x_cap:
        x_ticks.append(x_cap)

    w, h     = 1200, 660
    margin_l = 110
    margin_r = 40
    margin_t = 100
    margin_b = 68
    chart_w  = w - margin_l - margin_r
    chart_h  = h - margin_t - margin_b

    JITTER = 0.14   # jitter as fraction of half chart_h

    parts = [_svg_header(w, h, title)]
    parts.append(_rect(0, 0, w, h, fill=COL_BG))
    parts.append(_text(margin_l, 46, title, size=21, weight=700))
    parts.append(_text(margin_l, 68, subtitle, size=13, fill=COL_SUBTITLE))

    # axes
    parts.append(_line(margin_l, margin_t, margin_l, margin_t + chart_h,
                       stroke=COL_INK, stroke_w=1.4))
    parts.append(_line(margin_l, margin_t + chart_h,
                       margin_l + chart_w, margin_t + chart_h,
                       stroke=COL_INK, stroke_w=1.4))

    # x ticks
    for tick in x_ticks:
        gx = margin_l + (tick / x_cap) * chart_w
        parts.append(_line(gx, margin_t, gx, margin_t + chart_h,
                           stroke=COL_GRID, stroke_w=1))
        parts.append(_text(gx, margin_t + chart_h + 17, str(tick),
                           size=11, fill=COL_SUBTITLE, anchor="middle"))

    parts.append(_text(margin_l + chart_w / 2, h - 10,
                       "Passage length in characters (capped at 98th percentile; longer of the two language versions)",
                       size=12, fill=COL_SUBTITLE, anchor="middle"))

    # y band guides + labels
    for yv, label in ((0, "Disagreed"), (1, "Agreed")):
        yc = margin_t + chart_h - yv * chart_h
        parts.append(_line(margin_l, yc, margin_l + chart_w, yc,
                           stroke=COL_GRID, stroke_w=1.2))
        parts.append(_text(margin_l - 10, yc + 4, label,
                           size=12, fill=COL_SUBTITLE, anchor="end"))

    y_cx = 20.0
    y_cy = margin_t + chart_h / 2
    parts.append(_text(y_cx, y_cy, "Did AI and human agree?",
                       size=12, fill=COL_SUBTITLE, anchor="middle",
                       transform=f"rotate(-90 {y_cx:.1f} {y_cy:.1f})"))

    # legend
    for col, lab, lx in ((COL_GREEN, "Agreed", w - 200), (COL_RED, "Disagreed", w - 110)):
        parts.append(f'<circle cx="{lx:.0f}" cy="44" r="5" fill="{col}" opacity="0.85"/>')
        parts.append(_text(lx + 9, 48, lab, size=11, fill=COL_SUBTITLE))

    # scatter points
    for length, yv in pts:
        gx    = margin_l + (min(length, x_cap) / x_cap) * chart_w
        seed  = (hash((length, yv)) % 997) / 997.0 - 0.5
        jitter = seed * JITTER * chart_h
        gy    = margin_t + chart_h - yv * chart_h + jitter
        col   = COL_GREEN if yv else COL_RED
        parts.append(
            f'<circle cx="{gx:.2f}" cy="{gy:.2f}" r="2.6" fill="{col}" opacity="0.28"/>'
        )

    parts.append(_svg_footer())
    out_path.write_text("\n".join(parts), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="docs/fixtures/comparison_results.json",
                    help="Path to comparison_results.json (relative to repo root)")
    ap.add_argument("--out", default="dev/svg_accuracy_alignment_pack_2026-05-06",
                    help="Output directory (relative to repo root)")
    args = ap.parse_args()

    src     = (ROOT / args.src).resolve()
    out_dir = (ROOT / args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows, doc_meta = _read_rows(src)
    total = len(rows)
    if not total:
        raise SystemExit("No aligned rows found in comparison_by_doc.")

    cat_m  = sum(1 for r in rows if r.get("category_match"))
    fram_m = sum(1 for r in rows if r.get("framing_match"))
    both_m = sum(1 for r in rows if r.get("both_match"))
    minimal = False

    # 1. Overall agreement rates
    _bar_chart_svg(
        title="Overall: how often does the AI agree with human reviewers?",
        subtitle="",
        items=[
            ("Specific Details agreed",   _pct(cat_m, total)),
            ("Ideological Layers agreed", _pct(fram_m, total)),
            ("Both agreed",               _pct(both_m, total)),
        ],
        out_path=out_dir / "overall_alignment_rates.svg",
        bar_colors={
            "Specific Details agreed":   COL_BLUE,
            "Ideological Layers agreed": COL_YELLOW,
            "Both agreed":               COL_GREEN,
        },
        x_axis_label="Percent of segments",
        minimal_text=minimal,
    )

    # 2. Mismatch breakdown
    buckets: Counter = Counter()
    for r in rows:
        c = bool(r.get("category_match"))
        f = bool(r.get("framing_match"))
        if c and f:
            buckets["Both agreed"] += 1
        elif c:
            buckets["Category agreed, framing did not"] += 1
        elif f:
            buckets["Framing agreed, category did not"] += 1
        else:
            buckets["Neither agreed"] += 1

    _bar_chart_svg(
        title="Agreement breakdown: how many segments fall into each outcome?",
        subtitle="",
        items=[(k, float(v)) for k, v in buckets.most_common()],
        value_fmt="count",
        out_path=out_dir / "mismatch_buckets_counts.svg",
        bar_colors={
            "Both agreed":                         COL_GREEN,
            "Category agreed, framing did not":    COL_BLUE,
            "Framing agreed, category did not":    COL_YELLOW,
            "Neither agreed":                      COL_RED,
        },
        x_axis_label="Segments (count)",
        minimal_text=minimal,
    )

    # 3. Category confusion matrix
    cat_pairs = [
        ((r.get("human_category") or "").strip(), (r.get("llm_category") or "").strip())
        for r in rows
    ]
    _confusion_svg(
        title="Specific Details: where does the AI agree and where does it go wrong?",
        subtitle="",
        pairs=cat_pairs,
        out_path=out_dir / "confusion_category.svg",
        top_n=12,
        row_axis_label="Human's Specific Details",
        col_axis_label="AI's Specific Details",
        minimal_text=minimal,
    )

    # 4. Framing confusion matrix
    fram_pairs = [
        ((r.get("human_framing") or "").strip(), (r.get("llm_framing") or "").strip())
        for r in rows
    ]
    _confusion_svg(
        title="Ideological Layers: where does the AI agree and where does it go wrong?",
        subtitle="",
        pairs=fram_pairs,
        out_path=out_dir / "confusion_framing.svg",
        top_n=12,
        row_axis_label="Human's Ideological Layers",
        col_axis_label="AI's Ideological Layers",
        minimal_text=minimal,
    )

    # 5. Both-agreed rate by human category
    by_cat_total: Counter = Counter()
    by_cat_both:  Counter = Counter()
    for r in rows:
        hc = (r.get("human_category") or "").strip() or "(unlabelled)"
        by_cat_total[hc] += 1
        if r.get("both_match"):
            by_cat_both[hc] += 1

    cat_items = [
        (k, _pct(by_cat_both.get(k, 0), tot))
        for k, tot in by_cat_total.most_common(14)
    ]
    _bar_chart_svg(
        title="Full agreement rate by Specific Details label (top 14 by volume)",
        subtitle="",
        items=cat_items,
        out_path=out_dir / "both_match_by_human_category.svg",
        x_axis_label="Percent of segments",
        minimal_text=minimal,
    )

    # 6. Both-agreed rate by human framing
    by_f_total: Counter = Counter()
    by_f_both:  Counter = Counter()
    for r in rows:
        hf = (r.get("human_framing") or "").strip() or "(unlabelled)"
        by_f_total[hf] += 1
        if r.get("both_match"):
            by_f_both[hf] += 1

    fram_items = [
        (k, _pct(by_f_both.get(k, 0), tot))
        for k, tot in by_f_total.most_common(12)
    ]
    _bar_chart_svg(
        title="Full agreement rate by Ideological Layers label (top 12 by volume)",
        subtitle="",
        items=fram_items,
        out_path=out_dir / "both_match_by_human_framing.svg",
        x_axis_label="Percent of segments",
        minimal_text=minimal,
    )

    # 7. Per-document agreement ranking
    doc_counts: Counter = Counter(r["_doc_id"] for r in rows)
    doc_both:   Counter = Counter(r["_doc_id"] for r in rows if r.get("both_match"))
    doc_items = [
        (doc_meta.get(doc_id) or f"Doc {doc_id}",
         _pct(doc_both.get(doc_id, 0), tot))
        for doc_id, tot in doc_counts.most_common(12)
    ]
    _bar_chart_svg(
        title="Full agreement rate by document (top 12 by segment count)",
        subtitle="",
        items=doc_items,
        out_path=out_dir / "both_match_by_document_top12.svg",
        x_axis_label="Percent of segments",
        minimal_text=minimal,
    )

    # 8. Outcome narrative: 100% stacked bar
    _stacked_outcomes_svg(
        title="Accuracy story in one line: 100% of segments, split by agreement outcome",
        subtitle="",
        counts={k: int(v) for k, v in buckets.items()},
        total=total,
        out_path=out_dir / "agreement_outcomes_100pct.svg",
        minimal_text=minimal,
    )

    # 9. Ideological Layers mismatch flow (directional swaps)
    _il_swap_arrows_svg(
        title="Ideological Layers: the top directional swap errors",
        subtitle="",
        pairs=fram_pairs,  # (human_framing, llm_framing)
        out_path=out_dir / "ideological_layers_top_swaps_arrows.svg",
        top_k=3,
        minimal_text=minimal,
    )

    # 10. "Ideological morpheme" cues for the single biggest swap
    # Find the dominant off-diagonal pair (human → AI).
    swap_counts: Counter = Counter()
    for h_lab, a_lab in fram_pairs:
        h_lab = (h_lab or "").strip()
        a_lab = (a_lab or "").strip()
        if h_lab and a_lab and h_lab != a_lab:
            swap_counts[(h_lab, a_lab)] += 1
    (dom_h, dom_a), dom_c = swap_counts.most_common(1)[0] if swap_counts else (("",""),0)

    _ideological_morpheme_cues_svg(
        title="Ideological morphemes (proxy): cue words behind the biggest Ideological Layers swap",
        subtitle=(
            f"We compare segments where the human labelled '{dom_h}' but the AI labelled '{dom_a}' "
            f"(n={dom_c}) against segments where both agreed on '{dom_h}'. "
            "Bars show tokens (mostly Russian) that are unusually associated with the swap."
        ),
        rows=rows,
        human_label=dom_h,
        ai_label=dom_a,
        out_path=out_dir / "ideological_morpheme_cues_biggest_swap.svg",
        top_n=14,
    )

    _ideological_morpheme_cues_dumbbell_svg(
        title="Ideological morphemes (proxy): which tokens shift the AI toward the swap?",
        subtitle="",
        rows=rows,
        human_label=dom_h,
        ai_label=dom_a,
        out_path=out_dir / "ideological_morpheme_cues_biggest_swap_dumbbell.svg",
        top_n=14,
        minimal_text=minimal,
    )

    # 11. Length buckets: does disagreement concentrate in long segments?
    _length_bins_svg(
        title="Is segment length driving disagreement? (bucketed counts)",
        subtitle="",
        rows=rows,
        out_path=out_dir / "length_bins_both_agree_vs_not.svg",
        minimal_text=minimal,
    )

    # 12. Top category divergences
    cat_mismatch: Counter = Counter()
    for r in rows:
        if r.get("category_match"):
            continue
        hc = (r.get("human_category") or "").strip() or "(unlabelled)"
        ac = (r.get("llm_category")   or "").strip() or "(unlabelled)"
        cat_mismatch[(hc, ac)] += 1

    _bar_chart_svg(
        title="Most common topic category mix-ups: what did the human label vs what did the AI pick?",
        subtitle="",
        items=[(f"{h} / {a}", float(c)) for (h, a), c in cat_mismatch.most_common(14)],
        value_fmt="count",
        out_path=out_dir / "top_category_divergences.svg",
        x_axis_label="Segments (count)",
        minimal_text=minimal,
    )

    # 13. Best-performing documents (positive focus)
    min_segments = 25
    doc_perf = [
        (doc_meta.get(doc_id) or f"Doc {doc_id}", _pct(doc_both.get(doc_id, 0), tot), tot)
        for doc_id, tot in doc_counts.items()
        if tot >= min_segments
    ]
    doc_perf.sort(key=lambda t: (t[1], t[2]), reverse=True)

    _bar_chart_svg(
        title=f"Where the AI is strongest: highest full-agreement documents (≥ {min_segments} segments)",
        subtitle="",
        items=[(name, pct) for (name, pct, _tot) in doc_perf[:12]],
        out_path=out_dir / "best_documents_by_full_agreement_top12.svg",
        x_axis_label="Percent of segments",
        minimal_text=minimal,
    )

    print(f"Wrote SVGs to: {out_dir.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())