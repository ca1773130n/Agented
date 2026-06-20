#!/usr/bin/env python3
from __future__ import annotations

import math
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

OUT_DIR = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(OUT_DIR / ".matplotlib-cache"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from PIL import Image


EMERALD = "#10b981"
AMBER = "#f59e0b"
RED = "#dc2626"
SLATE_BORDER = "#9ca3af"
LIGHT_SLATE = "#f3f4f6"
DARK_TEXT = "#111827"
MUTED = "#6b7280"
DARK_RED = "#7f1d1d"
GREEN_FILL = "#d1fae5"
AMBER_FILL = "#fef3c7"
RED_FILL = "#fee2e2"
PILL_FILL = "#e5e7eb"
_GRAPHVIZ_INSTALL_ATTEMPTED = False


@dataclass
class VerifyResult:
    filename: str
    size: tuple[int, int]
    ok: bool
    reason: str | None = None

    def summary(self) -> str:
        width, height = self.size
        status = "VERIFIED" if self.ok else f"BROKEN: {self.reason}"
        return f"{self.filename} · {width}x{height} · {status}"


def maybe_install_graphviz() -> None:
    global _GRAPHVIZ_INSTALL_ATTEMPTED
    try:
        import graphviz  # noqa: F401

        return
    except Exception:
        pass

    if _GRAPHVIZ_INSTALL_ATTEMPTED:
        return
    _GRAPHVIZ_INSTALL_ATTEMPTED = True

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "graphviz"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=25,
        )
    except Exception:
        return


def html_label(title: str, subtitle: str) -> str:
    escaped = subtitle.replace("\n", "<BR/>")
    return f'<<B>{title}</B><BR/><FONT POINT-SIZE="10">{escaped}</FONT>>'


def plain_label_from_html(label: str) -> tuple[str, str]:
    label = label.strip("<>")
    title_start = label.find("<B>") + 3
    title_end = label.find("</B>")
    title = label[title_start:title_end]
    font_start = label.find('POINT-SIZE="10">') + len('POINT-SIZE="10">')
    font_end = label.find("</FONT>")
    subtitle = label[font_start:font_end].replace("<BR/>", "\n")
    return title, subtitle


def draw_card(
    ax,
    center: tuple[float, float],
    size: tuple[float, float],
    title: str,
    subtitle: str = "",
    *,
    fill: str,
    edge: str,
    fontsize: int = 12,
    subtitle_size: int = 10,
    rounded: bool = True,
    shape: str = "box",
) -> None:
    x, y = center
    w, h = size
    if shape == "ellipse":
        patch = matplotlib.patches.Ellipse((x, y), w, h, facecolor=fill, edgecolor=edge, lw=1.6)
        ax.add_patch(patch)
    else:
        boxstyle = "round,pad=0.025,rounding_size=0.045" if rounded else "square,pad=0.025"
        patch = FancyBboxPatch(
            (x - w / 2, y - h / 2),
            w,
            h,
            boxstyle=boxstyle,
            linewidth=1.6,
            edgecolor=edge,
            facecolor=fill,
        )
        ax.add_patch(patch)

    if subtitle:
        ax.text(
            x,
            y + 0.08 * h,
            title,
            ha="center",
            va="center",
            fontsize=fontsize,
            fontweight="bold",
            color=DARK_TEXT,
            family="Helvetica",
        )
        ax.text(
            x,
            y - 0.22 * h,
            subtitle,
            ha="center",
            va="center",
            fontsize=subtitle_size,
            color=MUTED,
            family="Helvetica",
            linespacing=1.2,
        )
    else:
        ax.text(
            x,
            y,
            title,
            ha="center",
            va="center",
            fontsize=fontsize,
            color=DARK_TEXT,
            family="Helvetica",
        )


def arrow(
    ax,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    label: str | None = None,
    rad: float = 0.0,
    label_offset: float = 0.12,
    linewidth: float = 1.5,
    mutation_scale: float = 14,
    color: str = MUTED,
) -> None:
    patch = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=mutation_scale,
        linewidth=linewidth,
        color=color,
        connectionstyle=f"arc3,rad={rad}",
    )
    ax.add_patch(patch)
    if label:
        lx = (start[0] + end[0]) / 2
        ly = (start[1] + end[1]) / 2
        ax.text(
            lx,
            ly + label_offset,
            label,
            ha="center",
            va="center",
            fontsize=10,
            color=MUTED,
            family="Helvetica",
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.5},
        )


def save_matplotlib(path: Path, fig: plt.Figure) -> None:
    fig.savefig(path, dpi=100, facecolor="white")
    plt.close(fig)


def verify(path: Path) -> VerifyResult:
    filename = path.name
    try:
        img = Image.open(path).convert("RGB")
        pixels = list(img.getdata())
        mean = sum(pixel[0] for pixel in pixels) / len(pixels)
        size_bytes = path.stat().st_size
        print(f"{filename} {img.size} {size_bytes} bytes mean_first_channel={mean:.2f}")
        if img.size[0] < 800 or img.size[1] < 120:
            reason = f"size {img.size[0]}x{img.size[1]} below 800x120"
            print(f"BROKEN: {filename} -- {reason}")
            return VerifyResult(filename, img.size, False, reason)
        if mean >= 252:
            reason = f"mean pixel {mean:.2f} >= 252"
            print(f"BROKEN: {filename} -- {reason}")
            return VerifyResult(filename, img.size, False, reason)
        print(f"VERIFIED: {filename}")
        return VerifyResult(filename, img.size, True)
    except Exception as exc:
        print(f"BROKEN: {filename} -- {exc}")
        return VerifyResult(filename, (0, 0), False, str(exc))


def render_01() -> VerifyResult:
    path = OUT_DIR / "01-benchmark-vs-auditeval.png"
    labels = ["Mastra OM", "ByteRover", "Letta", "Zep +18.5% vs MemGPT", "Mem0"]
    values = [94.87, 92.8, 83.2, 18.5, 49.0]
    colors = [EMERALD, EMERALD, EMERALD, AMBER, RED]
    y = np.arange(len(labels))

    fig, axes = plt.subplots(1, 2, figsize=(14.4, 5.2), dpi=100, facecolor="white")
    fig.subplots_adjust(left=0.16, right=0.97, top=0.82, bottom=0.18, wspace=0.25)

    axes[0].barh(y, values, color=colors, edgecolor="white", height=0.58)
    axes[0].set_yticks(y, labels)
    axes[0].invert_yaxis()
    axes[0].set_xlim(0, 100)
    axes[0].set_xlabel("Score (%)", color=DARK_TEXT)
    axes[0].set_title("LongMemEval (published)", fontweight="bold", color=DARK_TEXT)
    axes[0].grid(axis="x", color="#e5e7eb", linewidth=1)
    for yi, value in zip(y, values):
        axes[0].text(
            min(value + 1.2, 98),
            yi,
            f"{value:g}%",
            va="center",
            ha="left" if value < 94 else "right",
            fontsize=10,
            color=DARK_TEXT,
        )

    axes[1].set_title("AuditEval (does not exist)", fontweight="bold", color=DARK_TEXT)
    axes[1].set_xlim(0, 100)
    axes[1].set_ylim(-0.5, len(labels) - 0.5)
    axes[1].invert_yaxis()
    axes[1].set_yticks(y, [""] * len(labels))
    axes[1].set_xlabel("Score (%)", color=DARK_TEXT)
    axes[1].grid(axis="x", color="#e5e7eb", linewidth=1)
    for yi in y:
        rect = matplotlib.patches.Rectangle(
            (0, yi - 0.29),
            100,
            0.58,
            fill=False,
            edgecolor=RED,
            linewidth=2,
            linestyle=(0, (6, 4)),
        )
        axes[1].add_patch(rect)
        axes[1].text(50, yi, "?", ha="center", va="center", fontsize=18, color=RED, fontweight="bold")

    for ax in axes:
        ax.tick_params(colors=MUTED)
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        ax.spines["left"].set_color(SLATE_BORDER)
        ax.spines["bottom"].set_color(SLATE_BORDER)

    fig.text(
        0.5,
        0.055,
        "A field winning the wrong race.",
        ha="center",
        va="center",
        fontsize=13,
        style="italic",
        color=MUTED,
    )
    save_matplotlib(path, fig)
    return verify(path)


def render_03() -> VerifyResult:
    path = OUT_DIR / "03-toxicskills-breakdown.png"
    total = 3984
    segments = [
        ("Clean", 2517, LIGHT_SLATE, SLATE_BORDER, DARK_TEXT, "2,517 clean\n63.2%"),
        ("Flawed", 933, AMBER, AMBER, DARK_TEXT, "933 flawed\n23.4%"),
        ("Critical", 534, RED, RED, "white", "534 critical\n13.4%"),
        ("Malicious", 76, DARK_RED, DARK_RED, "white", ""),
    ]

    fig, ax = plt.subplots(figsize=(14.4, 3), dpi=100, facecolor="white")
    fig.subplots_adjust(left=0.05, right=0.88, top=0.72, bottom=0.25)
    left = 0
    for name, value, color, edge, text_color, label in segments:
        ax.barh([0], [value], left=left, color=color, edgecolor=edge, height=0.42)
        if label:
            ax.text(
                left + value / 2,
                0,
                label,
                ha="center",
                va="center",
                fontsize=11,
                color=text_color,
                fontweight="bold" if name in {"Flawed", "Critical"} else "normal",
            )
        left += value

    malicious_left = total - 76
    ax.annotate(
        "76 malicious\n1.9%",
        xy=(malicious_left + 38, 0),
        xytext=(total + 300, 0.02),
        ha="left",
        va="center",
        fontsize=11,
        color=DARK_RED,
        fontweight="bold",
        arrowprops={"arrowstyle": "->", "color": DARK_RED, "lw": 1.5},
    )
    ax.set_xlim(0, total + 620)
    ax.set_ylim(-0.8, 0.8)
    ax.set_yticks([])
    ax.set_xlabel("Skill count", color=DARK_TEXT)
    ax.set_title("3,984 Skills Audited", fontsize=17, fontweight="bold", color=DARK_TEXT, pad=24)
    ax.text(
        0.5,
        1.04,
        "AuditEval taxonomy applied to a real harness skill library",
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=12,
        color=MUTED,
    )
    ax.grid(axis="x", color="#e5e7eb", linewidth=1)
    ax.tick_params(colors=MUTED)
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(SLATE_BORDER)
    save_matplotlib(path, fig)
    return verify(path)


def try_graphviz_render(
    path: Path,
    build: Callable[[object], None],
) -> bool:
    maybe_install_graphviz()
    try:
        from graphviz import Digraph
    except Exception:
        return False

    try:
        graph = Digraph(format="png", engine="dot")
        graph.graph_attr["dpi"] = "150"
        graph.graph_attr["bgcolor"] = "white"
        build(graph)
        graph.render(filename=str(path.with_suffix("")), format="png", engine="dot", cleanup=True)
        return True
    except Exception:
        return False


def render_02_fallback(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(14.4, 1.6), dpi=100, facecolor="white")
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    nodes = [
        ("Agent action", "used scripts/deploy.sh", LIGHT_SLATE, SLATE_BORDER),
        ("Rule R", "deploy.sh canonical path", GREEN_FILL, EMERALD),
        ("Evolution Round", "Round herxsa3s86\napplied 2026-03-14", AMBER_FILL, AMBER),
        ("Takeaway", "tk-9xz4q1\nconfidence 0.92", GREEN_FILL, EMERALD),
        ("Session", "sess-bwqayo\n2026-03-12 · super_agent", LIGHT_SLATE, SLATE_BORDER),
        ("Database", "verifiable · timestamped", LIGHT_SLATE, SLATE_BORDER),
    ]
    labels = ["sourced from", "created by", "motivated by", "extracted from", "transcript in"]
    xs = np.linspace(0.095, 0.905, len(nodes))
    y = 0.5
    w, h = 0.13, 0.68
    for x, (title, subtitle, fill, edge) in zip(xs, nodes):
        draw_card(ax, (x, y), (w, h), title, subtitle, fill=fill, edge=edge, fontsize=12)
    for i, label in enumerate(labels):
        arrow(
            ax,
            (xs[i] + w / 2, y),
            (xs[i + 1] - w / 2, y),
            label=label,
            label_offset=0.22,
        )

    save_matplotlib(path, fig)


def render_02() -> VerifyResult:
    path = OUT_DIR / "02-provenance-chain.png"

    def build(graph) -> None:
        graph.attr(
            rankdir="LR",
            bgcolor="white",
            dpi="100",
            size="14.4,1.6!",
            ratio="fill",
            margin="0",
            pad="0.04,0.04",
        )
        graph.attr(
            "node",
            shape="box",
            style="filled,rounded",
            fontname="Helvetica",
            fontsize="12",
            margin="0.3,0.2",
        )
        graph.attr(
            "edge",
            fontname="Helvetica",
            fontsize="10",
            color=MUTED,
            labeldistance="1.5",
            labelangle="0",
        )
        specs = [
            ("n1", "Agent action", "used scripts/deploy.sh", LIGHT_SLATE, SLATE_BORDER),
            ("n2", "Rule R", "deploy.sh canonical path", GREEN_FILL, EMERALD),
            ("n3", "Evolution Round", "Round herxsa3s86\napplied 2026-03-14", AMBER_FILL, AMBER),
            ("n4", "Takeaway", "tk-9xz4q1\nconfidence 0.92", GREEN_FILL, EMERALD),
            ("n5", "Session", "sess-bwqayo\n2026-03-12 · super_agent", LIGHT_SLATE, SLATE_BORDER),
            ("n6", "Database", "verifiable · timestamped", LIGHT_SLATE, SLATE_BORDER),
        ]
        for node_id, title, subtitle, fill, edge in specs:
            graph.node(node_id, html_label(title, subtitle), fillcolor=fill, color=edge)
        for source, target, label in [
            ("n1", "n2", "sourced from"),
            ("n2", "n3", "created by"),
            ("n3", "n4", "motivated by"),
            ("n4", "n5", "extracted from"),
            ("n5", "n6", "transcript in"),
        ]:
            graph.edge(source, target, label=f"\\n{label}\\n")

    if not try_graphviz_render(path, build):
        render_02_fallback(path)
    return verify(path)


def render_04_fallback(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=100, facecolor="white")
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    pos = {
        "top": (0.5, 0.89),
        "pill": (0.5, 0.75),
        "a": (0.28, 0.635),
        "b": (0.28, 0.505),
        "c": (0.28, 0.375),
        "d": (0.72, 0.635),
        "e": (0.72, 0.505),
        "f": (0.72, 0.375),
        "g": (0.5, 0.215),
        "h": (0.5, 0.085),
    }
    draw_card(
        ax,
        pos["top"],
        (0.36, 0.11),
        "Session completes",
        "trigger_execution · workflow\nsuper_agent · project_session · team_session",
        fill=LIGHT_SLATE,
        edge=SLATE_BORDER,
    )
    draw_card(
        ax,
        pos["pill"],
        (0.34, 0.075),
        "on_session_complete event channel",
        fill=PILL_FILL,
        edge=SLATE_BORDER,
        shape="ellipse",
    )
    draw_card(ax, pos["a"], (0.25, 0.1), "Failure Annotator", "H2 · H3 · H4 · general", fill=GREEN_FILL, edge=EMERALD)
    ax.text(*pos["b"], "negative signal", ha="center", va="center", fontsize=12, color=DARK_TEXT)
    draw_card(ax, pos["c"], (0.21, 0.08), "Rules · Hooks", fill=RED_FILL, edge=RED)
    draw_card(ax, pos["d"], (0.25, 0.1), "Takeaway Extractor", "heuristic + Codex LLM", fill=AMBER_FILL, edge=AMBER)
    ax.text(*pos["e"], "positive signal", ha="center", va="center", fontsize=12, color=DARK_TEXT)
    draw_card(ax, pos["f"], (0.24, 0.1), "Skills · Commands\nMemory · KG", fill=GREEN_FILL, edge=EMERALD)
    draw_card(ax, pos["g"], (0.28, 0.1), "Evolver Round", "operator approves diff", fill=AMBER_FILL, edge=AMBER)
    draw_card(ax, pos["h"], (0.34, 0.085), "Forge primitives", "git-traceable · per-project bindings", fill=LIGHT_SLATE, edge=SLATE_BORDER)

    arrow(ax, (0.5, 0.835), (0.5, 0.79))
    arrow(ax, (0.43, 0.725), (0.32, 0.685))
    arrow(ax, (0.57, 0.725), (0.68, 0.685))
    arrow(ax, (0.28, 0.585), (0.28, 0.52))
    arrow(ax, (0.28, 0.465), (0.28, 0.41))
    arrow(ax, (0.72, 0.585), (0.72, 0.52))
    arrow(ax, (0.72, 0.465), (0.72, 0.415))
    arrow(ax, (0.28, 0.325), (0.43, 0.25), rad=-0.05)
    arrow(ax, (0.72, 0.325), (0.57, 0.25), rad=0.05)
    arrow(ax, (0.5, 0.165), (0.5, 0.125))

    save_matplotlib(path, fig)


def render_04() -> VerifyResult:
    path = OUT_DIR / "04-two-evidence-streams.png"

    def build(graph) -> None:
        graph.attr(
            rankdir="TB",
            bgcolor="white",
            dpi="150",
            pad="0.1,0.2",
            nodesep="1.0",
            ranksep="0.6",
        )
        graph.attr(
            "node",
            shape="box",
            style="filled,rounded",
            fontname="Helvetica",
            fontsize="12",
            margin="0.25,0.15",
        )
        graph.attr("edge", fontname="Helvetica", fontsize="10", color=MUTED)
        graph.node("top", html_label("Session completes", "trigger_execution · workflow\nsuper_agent · project_session · team_session"), fillcolor=LIGHT_SLATE, color=SLATE_BORDER)
        graph.node("pill", "on_session_complete event channel", shape="ellipse", fillcolor=PILL_FILL, color=SLATE_BORDER)
        graph.node("a", html_label("Failure Annotator", "H2 · H3 · H4 · general"), fillcolor=GREEN_FILL, color=EMERALD)
        graph.node("b", "negative signal", shape="plaintext", style="")
        graph.node("c", "Rules · Hooks", fillcolor=RED_FILL, color=RED)
        graph.node("d", html_label("Takeaway Extractor", "heuristic + Codex LLM"), fillcolor=AMBER_FILL, color=AMBER)
        graph.node("e", "positive signal", shape="plaintext", style="")
        graph.node("f", "Skills · Commands\nMemory · KG", fillcolor=GREEN_FILL, color=EMERALD)
        graph.node(
            "g",
            html_label("Evolver Round", "operator approves diff"),
            fillcolor=AMBER_FILL,
            color=AMBER,
            margin="0.2,0.15",
        )
        graph.node(
            "h",
            html_label("Forge primitives", "git-traceable · per-project bindings"),
            fillcolor=LIGHT_SLATE,
            color=SLATE_BORDER,
            margin="0.2,0.15",
        )
        with graph.subgraph() as same_rank:
            same_rank.attr(rank="same")
            same_rank.node("c")
            same_rank.node("f")
        for source, target in [
            ("top", "pill"),
            ("pill", "a"),
            ("pill", "d"),
            ("a", "b"),
            ("b", "c"),
            ("d", "e"),
            ("e", "f"),
            ("c", "g"),
            ("f", "g"),
            ("g", "h"),
        ]:
            graph.edge(source, target)

    if not try_graphviz_render(path, build):
        render_04_fallback(path)
    return verify(path)


def render_05_fallback(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12.8, 6.0), dpi=100, facecolor="white")
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    clusters = [
        (
            "Months 0–6",
            AMBER,
            AMBER_FILL,
            [
                ("AuditEval prototype published", "source-attribution +\nsupersession axes"),
                ("Skill-signing standard proposed", "agentskills.io v2"),
                ("Snyk-style audits regular cycle", "quarterly reports"),
            ],
        ),
        (
            "Months 6–12",
            EMERALD,
            GREEN_FILL,
            [
                ("First regulated industry ships", "finance/healthcare RFPs\nname auditability axes"),
                ("Operator-approval gates default", "review-mode out of box"),
            ],
        ),
        (
            "Months 12–18",
            SLATE_BORDER,
            LIGHT_SLATE,
            [
                ("LongMemEval stops differentiating", "audit-axis benchmark\nwins enterprise mindshare"),
                ("Memory-startup pivots", "provenance can't\nbe retrofitted"),
                ("Signed skills + diff review = table stakes", "npm trust-collapse\nnarrowed avoided"),
            ],
        ),
    ]
    xs = [0.2, 0.5, 0.8]
    cluster_w = 0.26
    for x, (label, edge, fill, cards) in zip(xs, clusters):
        box = FancyBboxPatch(
            (x - cluster_w / 2, 0.17),
            cluster_w,
            0.7,
            boxstyle="round,pad=0.015,rounding_size=0.02",
            facecolor="white",
            edgecolor=edge,
            linewidth=1.8,
            linestyle=(0, (5, 4)),
        )
        ax.add_patch(box)
        ax.text(
            x,
            0.82,
            label,
            ha="center",
            va="center",
            fontsize=14,
            fontweight="bold",
            color=DARK_TEXT,
            family="Helvetica",
        )
        start_y = 0.66
        gap = 0.19
        for idx, (title, subtitle) in enumerate(cards):
            y = start_y - idx * gap
            draw_card(
                ax,
                (x, y),
                (0.215, 0.14),
                title,
                subtitle,
                fill=fill,
                edge=edge,
                fontsize=10,
                subtitle_size=9,
            )
    arrow(ax, (0.335, 0.47), (0.365, 0.47), linewidth=2, mutation_scale=17, color=SLATE_BORDER)
    arrow(ax, (0.635, 0.47), (0.665, 0.47), linewidth=2, mutation_scale=17, color=SLATE_BORDER)
    ax.hlines(0.08, 0.07, 0.93, colors=SLATE_BORDER, linestyles=(0, (4, 4)), linewidth=1)
    for x, label in [(0.2, "NOW"), (0.5, "+6MO"), (0.8, "+18MO")]:
        ax.vlines(x, 0.065, 0.095, colors=SLATE_BORDER, linewidth=1)
        ax.text(
            x,
            0.035,
            label,
            ha="center",
            va="center",
            fontsize=9,
            fontvariant="small-caps",
            color=MUTED,
            family="Helvetica",
        )

    save_matplotlib(path, fig)


def render_05() -> VerifyResult:
    path = OUT_DIR / "05-forecast-timeline.png"

    def build(graph) -> None:
        graph.attr(
            rankdir="LR",
            bgcolor="white",
            dpi="150",
            pad="0.15,0.15",
            ranksep="0.4",
            nodesep="0.45",
        )
        graph.attr(
            "node",
            fontname="Helvetica",
            fontsize="11",
            margin="0.18,0.12",
            style="rounded,filled",
            shape="box",
            fixedsize="true",
            width="3.4",
            height="1.2",
        )
        graph.attr("edge", color=SLATE_BORDER, penwidth="2", arrowsize="1.2")
        clusters = [
            (
                "cluster_0",
                "Months 0–6",
                AMBER,
                AMBER_FILL,
                [
                    ("a1", "AuditEval prototype published", "source-attribution +\nsupersession axes"),
                    ("a2", "Skill-signing standard proposed", "agentskills.io v2"),
                    ("a3", "Snyk-style audits regular cycle", "quarterly reports"),
                ],
            ),
            (
                "cluster_1",
                "Months 6–12",
                EMERALD,
                GREEN_FILL,
                [
                    ("b1", "First regulated industry ships", "finance/healthcare RFPs\nname auditability axes"),
                    ("b2", "Operator-approval gates default", "review-mode out of box"),
                ],
            ),
            (
                "cluster_2",
                "Months 12–18",
                SLATE_BORDER,
                LIGHT_SLATE,
                [
                    ("c1", "LongMemEval stops differentiating", "audit-axis benchmark\nwins enterprise mindshare"),
                    ("c2", "Memory-startup pivots", "provenance can't\nbe retrofitted"),
                    ("c3", "Signed skills + diff review = table stakes", "npm trust-collapse\nnarrowed avoided"),
                ],
            ),
        ]
        anchors = []
        for name, label, edge, fill, cards in clusters:
            with graph.subgraph(name=name) as sub:
                sub.attr(
                    label=f"<<B><FONT POINT-SIZE='14' COLOR='{DARK_TEXT}'>{label}</FONT></B>>",
                    color=edge,
                    style="dashed",
                    rankdir="TB",
                    margin="14",
                    fontname="Helvetica",
                    fontsize="14",
                    fontcolor=DARK_TEXT,
                )
                anchor = f"{name}_anchor"
                anchors.append(anchor)
                sub.node(anchor, "", style="invis", width="0.01", height="0.01", fixedsize="true")
                previous = None
                for node_id, title, subtitle in cards:
                    sub.node(node_id, html_label(title, subtitle), fillcolor=fill, color=edge)
                    if previous:
                        sub.edge(previous, node_id, style="invis")
                    previous = node_id
                if len(cards) == 2:
                    spacer = f"{name}_spacer"
                    sub.node(spacer, "", style="invis", label="", fixedsize="true", width="3.4", height="1.2")
                    sub.edge(previous, spacer, style="invis")
        graph.node(
            "tick_now",
            "<<FONT POINT-SIZE='9'>NOW</FONT>>",
            shape="plaintext",
            style="",
            fixedsize="false",
            fontname="Helvetica",
            fontcolor=MUTED,
        )
        graph.node(
            "tick_6mo",
            "<<FONT POINT-SIZE='9'>+6MO</FONT>>",
            shape="plaintext",
            style="",
            fixedsize="false",
            fontname="Helvetica",
            fontcolor=MUTED,
        )
        graph.node(
            "tick_18mo",
            "<<FONT POINT-SIZE='9'>+18MO</FONT>>",
            shape="plaintext",
            style="",
            fixedsize="false",
            fontname="Helvetica",
            fontcolor=MUTED,
        )
        graph.edge("a2", "b1", constraint="false")
        graph.edge("b1", "c2", constraint="false")
        with graph.subgraph() as axis_rank:
            axis_rank.attr(rank="same")
            axis_rank.node("tick_now")
            axis_rank.node("tick_6mo")
            axis_rank.node("tick_18mo")
        graph.edge("a3", "tick_now", style="invis")
        graph.edge("tick_now", "tick_6mo", style="dashed", arrowhead="none", color=SLATE_BORDER, penwidth="1")
        graph.edge("tick_6mo", "tick_18mo", style="dashed", arrowhead="none", color=SLATE_BORDER, penwidth="1")

    if not try_graphviz_render(path, build):
        render_05_fallback(path)
    return verify(path)


def main() -> int:
    renderers = {
        "01": render_01,
        "02": render_02,
        "03": render_03,
        "04": render_04,
        "05": render_05,
    }
    selected = sys.argv[1:] or list(renderers)
    unknown = [name for name in selected if name not in renderers]
    if unknown:
        print(f"Unknown figure(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    results = []
    for name in selected:
        result = renderers[name]()
        results.append(result)
        if not result.ok:
            return 1

    print("SUMMARY")
    for result in results:
        print(result.summary())
    print(f"Script: {Path(__file__).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
