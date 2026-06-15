"""
Generate bell-wiring circuit diagrams as PDFs using matplotlib.
  bell_simple.pdf  — GPIO 22 → relay module → bell coil
  bell_555.pdf     — 555 astable 20 Hz gated by GPIO 22 → NPN → relay → bell
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import numpy as np
import os

OUT = "/home/user/rotary-pi/diagrams"
os.makedirs(OUT, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Low-level drawing helpers
# ─────────────────────────────────────────────────────────────────────────────

def wire(ax, x0, y0, x1, y1, **kw):
    kw.setdefault("color", "black")
    kw.setdefault("lw", 1.5)
    ax.plot([x0, x1], [y0, y1], **kw)

def dot(ax, x, y, r=0.06, **kw):
    kw.setdefault("color", "black")
    ax.add_patch(plt.Circle((x, y), r, **kw))

def open_terminal(ax, x, y, label, loc="left", r=0.10):
    ax.add_patch(plt.Circle((x, y), r, color="white", ec="black", lw=1.5, zorder=4))
    off = 0.22
    ha = {"left": "right", "right": "left", "top": "center", "bottom": "center"}[loc]
    va = {"left": "center", "right": "center", "top": "bottom", "bottom": "top"}[loc]
    dx = {"left": -off, "right": off, "top": 0, "bottom": 0}[loc]
    dy = {"left": 0, "right": 0, "top": off, "bottom": -off}[loc]
    ax.text(x + dx, y + dy, label, ha=ha, va=va, fontsize=8, family="monospace")

def resistor(ax, x0, y0, x1, y1, label="", label_side="top"):
    """Draw a resistor between two points (horizontal or vertical)."""
    horiz = abs(y1 - y0) < 1e-6
    length = abs(x1 - x0) if horiz else abs(y1 - y0)
    nzag = 8
    zag_h = 0.15  # half-amplitude
    t = np.linspace(0, 1, nzag * 4 + 1)
    zigzag = np.zeros_like(t)
    for i, ti in enumerate(t):
        phase = (ti * nzag) % 1
        if phase < 0.25:
            zigzag[i] = phase / 0.25
        elif phase < 0.75:
            zigzag[i] = 1 - (phase - 0.25) / 0.25
        else:
            zigzag[i] = -(phase - 0.75) / 0.25
    zigzag = zigzag * zag_h

    body = 0.55  # fraction of length used by zigzag
    margin = (1 - body) / 2
    if horiz:
        xs = x0 + t * (x1 - x0)
        ys = y0 + zigzag
        # lead wires
        ax.plot([x0, x0 + margin * (x1 - x0)], [y0, y0], color="black", lw=1.5)
        ax.plot([x1 - margin * (x1 - x0), x1], [y0, y0], color="black", lw=1.5)
    else:
        ys = y0 + t * (y1 - y0)
        xs = x0 + zigzag
        ax.plot([x0, x0], [y0, y0 + margin * (y1 - y0)], color="black", lw=1.5)
        ax.plot([x0, x0], [y1 - margin * (y1 - y0), y1], color="black", lw=1.5)

    body_mask = (t >= margin) & (t <= 1 - margin)
    ax.plot(xs[body_mask], ys[body_mask], color="black", lw=1.5)

    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    if label:
        offx = 0 if horiz else 0.28
        offy = 0.28 if horiz else 0
        if label_side in ("bottom", "left"):
            offx, offy = -offx, -offy
        ax.text(mx + offx, my + offy, label, ha="center", va="center",
                fontsize=8, family="monospace")


def capacitor(ax, x, y, vert=True, label="", label_side="right"):
    """Draw a capacitor symbol centered at (x, y)."""
    gap = 0.10
    arm = 0.25
    lw = 2.5
    if vert:
        ax.plot([x - arm, x + arm], [y + gap, y + gap], color="black", lw=lw)
        ax.plot([x - arm, x + arm], [y - gap, y - gap], color="black", lw=lw)
        if label:
            off = 0.35 if label_side == "right" else -0.35
            ha = "left" if label_side == "right" else "right"
            ax.text(x + off, y, label, ha=ha, va="center", fontsize=8, family="monospace")
    else:
        ax.plot([x + gap, x + gap], [y - arm, y + arm], color="black", lw=lw)
        ax.plot([x - gap, x - gap], [y - arm, y + arm], color="black", lw=lw)
        if label:
            ax.text(x, y + arm + 0.12, label, ha="center", va="bottom",
                    fontsize=8, family="monospace")


def inductor(ax, x0, y0, x1, y1, loops=4, label="", label_side="right"):
    """Draw an inductor (coil) between two points (vertical only)."""
    total = y1 - y0
    loop_h = total / loops
    r = abs(loop_h) / 2
    xs = []
    ys = []
    for i in range(loops):
        cy = y0 + (i + 0.5) * loop_h
        theta = np.linspace(np.pi, 0, 60) if total > 0 else np.linspace(0, np.pi, 60)
        xs.extend(x0 + r * np.cos(theta))
        ys.extend(cy + r * np.sin(theta) * np.sign(total))
    ax.plot(xs, ys, color="black", lw=1.5)
    mx = x0
    my = (y0 + y1) / 2
    if label:
        off = 0.35 if label_side == "right" else -0.35
        ha = "left" if label_side == "right" else "right"
        ax.text(mx + off, my, label, ha=ha, va="center", fontsize=8, family="monospace")


def diode(ax, x0, y0, x1, y1, reverse=False, label="", color="black"):
    """Draw a diode symbol (vertical)."""
    mx = x0
    my = (y0 + y1) / 2
    h = 0.22  # half-height of triangle
    w = 0.18  # half-width

    # Anode (triangle base) is at y0 side, cathode (bar) at y1 side (if not reversed)
    if not reverse:
        tri = np.array([[mx - w, my - h], [mx + w, my - h], [mx, my + h]])
        bar_y = my + h
    else:
        tri = np.array([[mx - w, my + h], [mx + w, my + h], [mx, my - h]])
        bar_y = my - h

    ax.add_patch(plt.Polygon(tri, closed=True, color=color, zorder=3))
    ax.plot([mx - w, mx + w], [bar_y, bar_y], color=color, lw=2.5, zorder=4)
    # Lead wires
    ax.plot([mx, mx], [y0, my - h if not reverse else my - h], color="black", lw=1.5)
    ax.plot([mx, mx], [my + h if not reverse else my + h, y1], color="black", lw=1.5)
    if label:
        ax.text(mx + 0.32, my, label, ha="left", va="center", fontsize=8,
                family="monospace", color=color)


def npn_transistor(ax, cx, cy, label="Q1\n2N2222"):
    """Draw an NPN BJT with base at left, collector up-right, emitter down-right."""
    # Circle
    r = 0.45
    ax.add_patch(plt.Circle((cx + r * 0.6, cy), r, fill=False, ec="black", lw=1.5))
    # Body line
    ax.plot([cx + r * 0.3, cx + r * 0.3], [cy - r * 0.7, cy + r * 0.7],
            color="black", lw=2)
    # Base wire
    ax.plot([cx, cx + r * 0.3], [cy, cy], color="black", lw=1.5)
    # Collector (upper right)
    ax.plot([cx + r * 0.3, cx + r * 1.1], [cy + r * 0.55, cy + r * 1.2],
            color="black", lw=1.5)
    # Emitter (lower right) with arrow
    ax.plot([cx + r * 0.3, cx + r * 1.1], [cy - r * 0.55, cy - r * 1.2],
            color="black", lw=1.5)
    # Emitter arrow
    ex, ey = cx + r * 0.85, cy - r * 0.9
    dx, dy = r * 0.26, -r * 0.3
    ax.annotate("", xy=(ex + dx, ey + dy), xytext=(ex, ey),
                arrowprops=dict(arrowstyle="-|>", color="black", lw=1.2))
    ax.text(cx + r * 1.4, cy, label, ha="left", va="center",
            fontsize=8, family="monospace")
    # Return anchor points
    base = (cx, cy)
    collector = (cx + r * 1.1, cy + r * 1.2)
    emitter = (cx + r * 1.1, cy - r * 1.2)
    return base, collector, emitter


def ground_sym(ax, x, y, label=""):
    w = 0.22
    for i, scale in enumerate([1.0, 0.65, 0.3]):
        yy = y - i * 0.12
        ax.plot([x - w * scale, x + w * scale], [yy, yy], color="black", lw=1.5)
    if label:
        ax.text(x + 0.15, y - 0.32, label, ha="left", va="top",
                fontsize=7.5, family="monospace")


def relay_module_box(ax, x, y, w=1.4, h=1.0, label="5 V Relay\nModule"):
    rect = mpatches.FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle="round,pad=0.05",
        linewidth=1.5, edgecolor="black", facecolor="#e8f0e8"
    )
    ax.add_patch(rect)
    ax.text(x, y, label, ha="center", va="center", fontsize=8, fontweight="bold")
    # Return connection points: IN (left), VCC (top), GND (bottom-left), COM/NO (right)
    return {
        "IN":  (x - w / 2, y),
        "VCC": (x, y + h / 2),
        "GND": (x - w / 4, y - h / 2),
        "COM": (x + w / 2, y + h * 0.25),
        "NO":  (x + w / 2, y - h * 0.25),
    }


def ic_box(ax, x, y, w=2.0, h=3.5, title="NE555"):
    rect = mpatches.FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle="round,pad=0.05",
        linewidth=1.8, edgecolor="black", facecolor="#e8eaf6"
    )
    ax.add_patch(rect)
    ax.text(x, y + 0.25, title, ha="center", va="center",
            fontsize=9, fontweight="bold")
    ax.text(x, y - 0.25, "astable\n20 Hz", ha="center", va="center",
            fontsize=7, color="#444")


def pin_label(ax, x, y, name, side="left", num=None):
    off = 0.12
    ha = "right" if side == "left" else "left"
    dx = -off if side == "left" else off
    text = f"{name}" if num is None else f"{name} ({num})"
    ax.text(x + dx, y, text, ha=ha, va="center", fontsize=7, color="#333")


def note_box(ax, fig, lines):
    fig.text(
        0.02, 0.01,
        "\n".join(lines),
        fontsize=7,
        verticalalignment="bottom",
        family="monospace",
        linespacing=1.5,
        bbox=dict(boxstyle="round,pad=0.5", fc="#f8f8f0", ec="#aaa", lw=0.8),
    )


def make_fig(title):
    fig, ax = plt.subplots(figsize=(13, 9))
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    return fig, ax


# ═════════════════════════════════════════════════════════════════════════════
# DIAGRAM 1 — Simple relay
# ═════════════════════════════════════════════════════════════════════════════
def diagram_simple():
    fig, ax = make_fig(
        "Bell Wiring — Option 1: Simple Relay\n"
        "GPIO 22 → 5 V Relay Module → Bell Coil  (single strike per toggle)"
    )
    ax.set_xlim(-1.5, 10)
    ax.set_ylim(-5.5, 4.5)

    # ── Control circuit ───────────────────────────────────────────────────────
    # GPIO 22
    open_terminal(ax, -1.0, 2.0, "GPIO 22\n(Pi pin 15)", loc="left")
    wire(ax, -0.9, 2.0, 1.2, 2.0)

    # 5 V relay module box
    rly = relay_module_box(ax, 2.6, 2.0, w=2.0, h=1.6)
    wire(ax, 1.2, 2.0, rly["IN"][0], rly["IN"][1])

    # 5 V to relay VCC
    wire(ax, rly["VCC"][0], rly["VCC"][1], rly["VCC"][0], 3.6)
    open_terminal(ax, rly["VCC"][0], 3.6, "5 V  (Pi pin 2)", loc="top")

    # GND from relay module
    wire(ax, rly["GND"][0], rly["GND"][1], rly["GND"][0], 0.8)
    ground_sym(ax, rly["GND"][0], 0.8, "Pi GND\n(Pi pin 6)")

    # ── Flyback diode across coil (inside the module, shown externally) ───────
    ax.text(2.6, 1.05, "D_flyback\n1N4007\n(built-in or\nadd externally)",
            ha="center", va="top", fontsize=6.5, color="#b00", style="italic")

    # ── Load circuit: 12 V → switch → bell → return ───────────────────────────
    # 12 V supply
    open_terminal(ax, 5.0, 3.6, "12 V DC\nsupply (+)", loc="right")
    wire(ax, 4.4, 3.6, 5.1, 3.6)
    wire(ax, 4.4, 3.6, 4.4, 2.4)  # down to relay COM
    dot(ax, 4.4, 3.6)

    # Relay COM connection
    wire(ax, rly["COM"][0], rly["COM"][1], 4.4, rly["COM"][1])
    dot(ax, 4.4, rly["COM"][1])
    wire(ax, 4.4, rly["COM"][1], 4.4, rly["COM"][1])  # already there

    # Relay NO contact symbol (external switch)
    sw_x, sw_y = 6.0, 2.0
    # Wire from relay NO to switch
    wire(ax, rly["NO"][0], rly["NO"][1], sw_x - 0.5, sw_y)
    # Switch symbol
    dot(ax, sw_x - 0.5, sw_y, r=0.05)
    ax.plot([sw_x - 0.5, sw_x + 0.15, sw_x + 0.5],
            [sw_y, sw_y + 0.45, sw_y],
            color="black", lw=1.5)
    dot(ax, sw_x + 0.5, sw_y, r=0.05)
    ax.text(sw_x, sw_y + 0.7, "Relay NO\ncontact", ha="center", va="bottom",
            fontsize=7.5, family="monospace")
    wire(ax, sw_x + 0.5, sw_y, 7.2, sw_y)
    wire(ax, 7.2, sw_y, 7.2, 3.6)   # up to 12V rail
    wire(ax, 4.4, 3.6, 7.2, 3.6)    # 12V rail

    # Bell coil (inductor)
    ax.text(sw_x + 0.5 + 0.6 + 0.6, sw_y - 0.25, "Bell coil\n(Type 500\nringer)",
            ha="left", va="top", fontsize=8, family="monospace")
    wire(ax, sw_x + 0.5, sw_y, sw_x + 0.5, -0.5)
    inductor(ax, sw_x + 0.5, -0.5, sw_x + 0.5, -3.0, loops=4)
    wire(ax, sw_x + 0.5, -3.0, sw_x + 0.5, -4.0)
    open_terminal(ax, sw_x + 0.5, -4.0, "12 V DC\nsupply (−)", loc="right")

    # ── Flyback diode across bell coil ────────────────────────────────────────
    diode(ax, sw_x + 0.5 + 0.6, -0.5, sw_x + 0.5 + 0.6, -3.0,
          reverse=True, label="D1\n1N4007\n(flyback)", color="#b00")
    wire(ax, sw_x + 0.5, -0.5, sw_x + 0.5 + 0.6, -0.5)
    wire(ax, sw_x + 0.5, -3.0, sw_x + 0.5 + 0.6, -3.0)

    # ── Legend box ────────────────────────────────────────────────────────────
    ax.text(-1.2, -1.5,
            "Relay module wiring:\n"
            "  IN  → GPIO 22 (Pi pin 15)\n"
            "  VCC → Pi 5 V (Pi pin 2)\n"
            "  GND → Pi GND (Pi pin 6)\n"
            "  COM → 12 V supply (+)\n"
            "  NO  → bell coil top",
            fontsize=8, va="top", family="monospace",
            bbox=dict(boxstyle="round", fc="#fffde7", ec="#ccc"))

    note_box(ax, fig, [
        "Operation: GPIO 22 HIGH → relay energises → 12 V reaches bell coil → clapper strikes ONCE per toggle.",
        "The script's 2 s ON / 4 s OFF cadence produces two strikes per ring cycle (one energise, one de-energise).",
        "For authentic mechanical oscillating ring use Option 2 (555 timer at 20 Hz) instead.",
        "Relay module: 5 V active-high board (SRD-05VDC-SL-C, HW-482, or equivalent).",
        "D1 (red) — flyback diode: ESSENTIAL — clamps inductive back-EMF that would destroy the transistor inside the relay module.",
        "Bell supply: 12–24 V DC, ≥ 500 mA.  Higher voltage rings louder; do not exceed bell coil rating.",
        "Pi GPIO 22 max output current: 16 mA — NEVER connect a relay coil directly to a GPIO pin; always use a relay module.",
    ])

    fig.savefig(f"{OUT}/bell_simple.pdf", format="pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {OUT}/bell_simple.pdf")


# ═════════════════════════════════════════════════════════════════════════════
# DIAGRAM 2 — 555 astable 20 Hz gated by GPIO 22
# ═════════════════════════════════════════════════════════════════════════════
def diagram_555():
    fig, ax = make_fig(
        "Bell Wiring — Option 2: 555 Astable at 20 Hz, Gated by GPIO 22\n"
        "Authentic mechanical ring — clapper oscillates at 20 Hz during ring cadence"
    )
    ax.set_xlim(-2.5, 12)
    ax.set_ylim(-6.5, 7.5)

    # ── 555 IC box ────────────────────────────────────────────────────────────
    ic_cx, ic_cy = 2.5, 1.5
    ic_w, ic_h = 2.2, 5.0
    ic_box(ax, ic_cx, ic_cy, w=ic_w, h=ic_h)
    ic_left  = ic_cx - ic_w / 2
    ic_right = ic_cx + ic_w / 2
    ic_top   = ic_cy + ic_h / 2
    ic_bot   = ic_cy - ic_h / 2

    # Pin positions (left side, bottom to top)
    # pin 1 GND, pin 2 TRG, pin 6 THR, pin 7 DIS  (left)
    # pin 8 VCC, pin 4 RST                          (top)
    # pin 3 OUT, pin 5 CTL                          (right)
    p = {
        "GND": (ic_left, ic_bot + 0.5),   # pin 1
        "TRG": (ic_left, ic_bot + 1.4),   # pin 2
        "THR": (ic_left, ic_bot + 2.3),   # pin 6
        "DIS": (ic_left, ic_top - 1.0),   # pin 7
        "VCC": (ic_cx - 0.5, ic_top),     # pin 8
        "RST": (ic_cx + 0.5, ic_top),     # pin 4
        "CTL": (ic_right, ic_bot + 1.4),  # pin 5
        "OUT": (ic_right, ic_bot + 2.8),  # pin 3
    }

    for name, (px, py) in p.items():
        ax.text(px + (0.12 if px == ic_left else -0.12),
                py,
                {"GND": "1 GND", "TRG": "2 TRG", "THR": "6 THR",
                 "DIS": "7 DIS", "VCC": "8 VCC", "RST": "4 RST",
                 "CTL": "5 CTL", "OUT": "3 OUT"}[name],
                ha=("left" if px == ic_left else "right") if py != ic_top else "center",
                va="center" if py != ic_top else "bottom",
                fontsize=6.5, color="#333")

    # ── VCC (pin 8) → 5 V rail ────────────────────────────────────────────────
    vcc_y = 6.5
    wire(ax, p["VCC"][0], p["VCC"][1], p["VCC"][0], vcc_y)
    wire(ax, p["RST"][0], p["RST"][1], p["RST"][0], vcc_y)
    wire(ax, p["VCC"][0], vcc_y, p["RST"][0], vcc_y)
    dot(ax, p["VCC"][0], vcc_y)
    dot(ax, p["RST"][0], vcc_y)
    # 5V terminal
    open_terminal(ax, p["VCC"][0], vcc_y, "5 V", loc="top")

    # ── RST pull-up resistor (VCC → RST) ─────────────────────────────────────
    rst_node_y = vcc_y - 0.6
    pull_x = p["RST"][0] + 0.8
    wire(ax, p["RST"][0], vcc_y, pull_x, vcc_y)
    dot(ax, p["RST"][0], vcc_y)
    resistor(ax, pull_x, vcc_y, pull_x, rst_node_y, label="R_pu\n10 kΩ", label_side="right")
    wire(ax, pull_x, rst_node_y, p["RST"][0], rst_node_y)
    dot(ax, p["RST"][0], rst_node_y)
    wire(ax, p["RST"][0], p["RST"][1], p["RST"][0], rst_node_y)

    # GPIO 22 wire → RST node
    wire(ax, -1.8, rst_node_y, p["RST"][0], rst_node_y)
    open_terminal(ax, -1.8, rst_node_y, "GPIO 22\n(Pi pin 15)\n3.3 V logic", loc="left")

    # ── GND (pin 1) ───────────────────────────────────────────────────────────
    wire(ax, p["GND"][0], p["GND"][1], ic_left - 0.7, p["GND"][1])
    ground_sym(ax, ic_left - 0.7, p["GND"][1])

    # ── Timing network: R1, R2, C1 ───────────────────────────────────────────
    # R1: VCC rail → DIS (pin 7)
    r1_x = ic_left - 1.5
    wire(ax, p["VCC"][0], vcc_y, r1_x, vcc_y)
    dot(ax, p["VCC"][0], vcc_y)
    wire(ax, r1_x, vcc_y, r1_x, p["DIS"][1] + 0.5)
    resistor(ax, r1_x, p["DIS"][1] + 0.5, r1_x, p["DIS"][1],
             label="R1\n1 kΩ", label_side="left")
    wire(ax, r1_x, p["DIS"][1], p["DIS"][0], p["DIS"][1])
    dot(ax, r1_x, p["DIS"][1])

    # R2: DIS node → THR/TRG junction
    r2_mid_y = (p["DIS"][1] + p["THR"][1]) / 2
    resistor(ax, r1_x, p["DIS"][1], r1_x, p["THR"][1],
             label="R2\n36 kΩ", label_side="left")
    thr_x = r1_x
    thr_y = p["THR"][1]
    wire(ax, thr_x, thr_y, p["THR"][0], p["THR"][1])
    wire(ax, thr_x, thr_y, thr_x, p["TRG"][1])
    wire(ax, thr_x, p["TRG"][1], p["TRG"][0], p["TRG"][1])
    dot(ax, thr_x, thr_y)

    # C1: THR/TRG junction → GND
    c1_x = thr_x - 0.6
    wire(ax, thr_x, p["TRG"][1], c1_x, p["TRG"][1])
    wire(ax, c1_x, p["TRG"][1], c1_x, p["TRG"][1] - 0.4)
    capacitor(ax, c1_x, p["TRG"][1] - 0.7, vert=True, label="C1\n1 µF", label_side="left")
    wire(ax, c1_x, p["TRG"][1] - 1.0, c1_x, p["GND"][1])
    ground_sym(ax, c1_x, p["GND"][1])

    # ── CTL (pin 5) bypass cap ────────────────────────────────────────────────
    ctl_x = ic_right + 0.7
    wire(ax, p["CTL"][0], p["CTL"][1], ctl_x, p["CTL"][1])
    wire(ax, ctl_x, p["CTL"][1], ctl_x, p["CTL"][1] - 0.3)
    capacitor(ax, ctl_x, p["CTL"][1] - 0.6, vert=True,
              label="C2\n0.1 µF\n(ceramic)", label_side="right")
    wire(ax, ctl_x, p["CTL"][1] - 0.9, ctl_x, p["GND"][1])
    ground_sym(ax, ctl_x, p["GND"][1])

    # ── OUT (pin 3) → R3 → NPN base ──────────────────────────────────────────
    r3_end_x = ic_right + 2.2
    wire(ax, p["OUT"][0], p["OUT"][1], ic_right + 0.5, p["OUT"][1])
    resistor(ax, ic_right + 0.5, p["OUT"][1], r3_end_x, p["OUT"][1],
             label="R3\n1 kΩ", label_side="top")

    # NPN transistor
    q_cx = r3_end_x + 0.15
    q_cy = p["OUT"][1]
    base, collector, emitter = npn_transistor(ax, q_cx, q_cy, label="Q1\n2N2222")
    wire(ax, r3_end_x, p["OUT"][1], base[0], base[1])

    # Emitter → GND
    wire(ax, emitter[0], emitter[1], emitter[0], emitter[1] - 0.4)
    ground_sym(ax, emitter[0], emitter[1] - 0.4)

    # Collector → relay coil → 5 V
    coil_top_y = collector[1] + 2.5
    wire(ax, collector[0], collector[1], collector[0], collector[1] + 0.3)
    inductor(ax, collector[0], collector[1] + 0.3, collector[0], coil_top_y,
             loops=3, label="Relay coil\n(5 V module)", label_side="right")
    wire(ax, collector[0], coil_top_y, collector[0], coil_top_y + 0.5)
    open_terminal(ax, collector[0], coil_top_y + 0.5, "5 V (relay\nmodule VCC)", loc="top")

    # Flyback diode across relay coil
    diode(ax, collector[0] - 0.55, collector[1] + 0.3,
          collector[0] - 0.55, coil_top_y,
          reverse=True, label="D1\n1N4007\n(flyback)", color="#b00")
    wire(ax, collector[0], collector[1] + 0.3, collector[0] - 0.55, collector[1] + 0.3)
    wire(ax, collector[0], coil_top_y, collector[0] - 0.55, coil_top_y)
    dot(ax, collector[0], collector[1] + 0.3)
    dot(ax, collector[0], coil_top_y)

    # ── Relay NO contact + bell coil ─────────────────────────────────────────
    sw_x = collector[0] + 2.2
    sw_top_y = coil_top_y + 0.5

    # 12 V supply rail
    open_terminal(ax, sw_x + 1.2, sw_top_y, "12 V DC\nsupply (+)", loc="right")
    wire(ax, sw_x - 0.8, sw_top_y, sw_x + 1.3, sw_top_y)
    wire(ax, sw_x, sw_top_y, sw_x, sw_top_y - 0.3)

    # Switch symbol (relay NO)
    dot(ax, sw_x, sw_top_y - 0.3, r=0.05)
    ax.plot([sw_x, sw_x + 0.18, sw_x], [sw_top_y - 0.3, sw_top_y - 0.7, sw_top_y - 1.1],
            color="black", lw=1.5)
    dot(ax, sw_x, sw_top_y - 1.1, r=0.05)
    ax.text(sw_x + 0.3, sw_top_y - 0.7, "Relay\nNO\ncontact", ha="left", va="center",
            fontsize=7.5, family="monospace")
    wire(ax, sw_x, sw_top_y - 1.1, sw_x, sw_top_y - 1.5)

    # Bell coil
    inductor(ax, sw_x, sw_top_y - 1.5, sw_x, sw_top_y - 4.5, loops=4,
             label="Bell coil\n(Type 500\nringer)", label_side="right")
    wire(ax, sw_x, sw_top_y - 4.5, sw_x, sw_top_y - 5.0)
    open_terminal(ax, sw_x, sw_top_y - 5.0, "12 V DC\nsupply (−)", loc="right")

    # Dashed line linking relay coil to relay contacts (mechanical link)
    mid_relay_x = (collector[0] + sw_x - 0.5) / 2
    wire(ax, collector[0] + 0.3, (collector[1] + coil_top_y) / 2,
         sw_x - 0.5, sw_top_y - 0.7,
         color="#aaa", lw=1.0, linestyle="dashed")
    ax.text(mid_relay_x - 0.2,
            ((collector[1] + coil_top_y) / 2 + sw_top_y - 0.7) / 2 + 0.2,
            "mechanical\nlink", ha="center", va="center",
            fontsize=7, color="#888", style="italic")

    note_box(ax, fig, [
        "555 astable frequency:  f = 1.44 ÷ ((R1 + 2×R2) × C1)  =  1.44 ÷ (73 000 × 0.000001)  ≈  19.7 Hz  (nominal 20 Hz)",
        "GPIO 22 HIGH → RESET (pin 4) released → 555 oscillates → 20 Hz square wave on OUT → Q1 switches relay at 20 Hz → clapper oscillates → authentic bell ring.",
        "GPIO 22 LOW  → RESET held LOW → 555 output frozen LOW → relay open → bell silent.  Ring cadence (2 s on / 4 s off) is still controlled by the script.",
        "GPIO 22 is 3.3 V logic; 555 RESET LOW threshold ≈ 0.7 V for 5 V supply — direct connection works, no level-shifter needed.",
        "R_pu (10 kΩ): pull-up from 5 V to RESET — keeps RESET HIGH if GPIO floats at boot, preventing spurious ringing during startup.",
        "Q1 (2N2222 NPN): R3 = 1 kΩ base resistor.  Handles relay coil current ≤ 100 mA.  Substitute 2N3904 for coils ≤ 50 mA.",
        "D1 (red) — flyback diode: ESSENTIAL across relay coil; cathode (banded end) toward 5 V rail.  Without it Q1 fails instantly on de-energise.",
        "C2 (0.1 µF ceramic): bypass cap on 555 pin 5 (CTL) — suppresses VCC noise coupling into timing; place as close to IC as possible.",
        "Tune frequency: R2 = 27 kΩ → ≈25 Hz;  R2 = 47 kΩ → ≈15 Hz.  Bell electromagnet is rated 20 Hz; stay within 16–25 Hz for reliable ringing.",
    ])

    fig.savefig(f"{OUT}/bell_555.pdf", format="pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {OUT}/bell_555.pdf")


if __name__ == "__main__":
    print("Generating bell wiring diagrams…")
    diagram_simple()
    diagram_555()
    print("Done.")
