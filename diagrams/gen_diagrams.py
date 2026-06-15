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
#
# Column layout (data units)
#  Timing network      x = -2.5
#  IC centre           x =  4.5   (left=3.0, right=6.0)
#  C2 bypass cap       x =  7.5
#  R3 + Q1             x =  9.0  (base)
#  Relay coil          x = 11.5
#  D1 flyback          x = 13.2
#  Bell / NO contact   x = 16.0
#
# Row layout (data units)
#  5 V terminal (VCC pin)      y =  5.5
#  RST / GPIO junction         y =  6.5   (GPIO wire runs here — clears all
#  R_pu (top at 5V, bot=6.5)            vertical wires which top out at 5.5)
#  5 V terminal (R_pu top)     y =  8.0
#  IC top pins                 y =  4.5
#  DIS (pin 7)                 y =  3.0
#  THR (pin 6)                 y =  0.8
#  OUT (pin 3)                 y =  0.8
#  TRG (pin 2)                 y = -0.6
#  GND (pin 1)                 y = -1.8
# ═════════════════════════════════════════════════════════════════════════════
def diagram_555():
    fig, ax = make_fig(
        "Bell Wiring — Option 2: 555 Astable at 20 Hz, Gated by GPIO 22\n"
        "Authentic mechanical ring — clapper oscillates at 20 Hz during ring cadence"
    )
    fig.set_size_inches(15, 10)
    ax.set_xlim(-5.5, 20.5)
    ax.set_ylim(-6.5, 12.0)

    # ── 555 IC box ────────────────────────────────────────────────────────────
    ic_cx, ic_cy = 4.5, 1.0
    ic_w, ic_h   = 3.0, 7.0
    ic_box(ax, ic_cx, ic_cy, w=ic_w, h=ic_h)
    ic_left  = ic_cx - ic_w / 2   # 3.0
    ic_right = ic_cx + ic_w / 2   # 6.0
    ic_top   = ic_cy + ic_h / 2   # 4.5
    ic_bot   = ic_cy - ic_h / 2   # -2.5

    # ── Pin stub world-coordinates ────────────────────────────────────────────
    p_GND = (ic_left, ic_bot + 0.7)   # pin 1  y = -1.8
    p_TRG = (ic_left, ic_bot + 1.9)   # pin 2  y = -0.6
    p_THR = (ic_left, ic_bot + 3.3)   # pin 6  y =  0.8
    p_DIS = (ic_left, ic_top - 1.5)   # pin 7  y =  3.0
    p_CTL = (ic_right, ic_bot + 1.9)  # pin 5  y = -0.6
    p_OUT = (ic_right, ic_bot + 3.3)  # pin 3  y =  0.8
    p_VCC = (ic_cx - 0.6, ic_top)     # pin 8  x = 3.9
    p_RST = (ic_cx + 0.6, ic_top)     # pin 4  x = 5.1

    # Pin labels — placed inside the IC body, away from the edges
    for name, pt, side in [
            ("GND", p_GND, "left"),("TRG", p_TRG, "left"),
            ("THR", p_THR, "left"),("DIS", p_DIS, "left")]:
        lbl = {"GND":"1 GND","TRG":"2 TRG","THR":"6 THR","DIS":"7 DIS"}[name]
        ax.text(pt[0]+0.18, pt[1], lbl, ha="left", va="center",
                fontsize=7, color="#333")
    for name, pt in [("CTL", p_CTL), ("OUT", p_OUT)]:
        lbl = {"CTL":"5 CTL","OUT":"3 OUT"}[name]
        ax.text(pt[0]-0.18, pt[1], lbl, ha="right", va="center",
                fontsize=7, color="#333")
    # Top pin labels — below the pin stub, inside the box
    ax.text(p_VCC[0], p_VCC[1]-0.3, "8 VCC", ha="center", va="top",
            fontsize=7, color="#333")
    ax.text(p_RST[0], p_RST[1]-0.3, "4 RST", ha="center", va="top",
            fontsize=7, color="#333")

    # ── IC VCC (pin 8) — short wire up to its own 5 V terminal ───────────────
    wire(ax, p_VCC[0], p_VCC[1], p_VCC[0], p_VCC[1]+1.0)
    open_terminal(ax, p_VCC[0], p_VCC[1]+1.0, "5 V", loc="top")

    # ── Timing network: R1, R2, C1 at x = -2.5 ───────────────────────────────
    # The top of the timing column is at y ≈ 5.0 — safely BELOW the GPIO wire
    # at y = 6.5, so there is no wire crossing.
    tcol_x = -2.5

    # 5 V terminal at top of timing column (separate from IC VCC terminal)
    r1_top_y = p_DIS[1] + 1.2   # y = 4.2
    wire(ax, tcol_x, r1_top_y, tcol_x, r1_top_y + 0.8)
    open_terminal(ax, tcol_x, r1_top_y + 0.8, "5 V", loc="top")

    # R1: r1_top_y → DIS
    resistor(ax, tcol_x, r1_top_y, tcol_x, p_DIS[1],
             label="R1\n1 kΩ", label_side="left")
    dot(ax, tcol_x, p_DIS[1])
    wire(ax, tcol_x, p_DIS[1], p_DIS[0], p_DIS[1])   # → DIS pin

    # R2: DIS junction → THR junction
    resistor(ax, tcol_x, p_DIS[1], tcol_x, p_THR[1],
             label="R2\n36 kΩ", label_side="left")
    dot(ax, tcol_x, p_THR[1])
    wire(ax, tcol_x, p_THR[1], p_THR[0], p_THR[1])   # → THR pin

    # Continue wire down to TRG junction
    wire(ax, tcol_x, p_THR[1], tcol_x, p_TRG[1])
    dot(ax, tcol_x, p_TRG[1])
    wire(ax, tcol_x, p_TRG[1], p_TRG[0], p_TRG[1])   # → TRG pin

    # C1: TRG junction → GND  (extra x offset so label has room)
    c1_x = tcol_x - 1.2
    wire(ax, tcol_x, p_TRG[1], c1_x, p_TRG[1])
    wire(ax, c1_x, p_TRG[1], c1_x, p_TRG[1] - 0.4)
    capacitor(ax, c1_x, p_TRG[1] - 0.65, vert=True,
              label="C1\n1 µF", label_side="left")
    wire(ax, c1_x, p_TRG[1] - 0.9, c1_x, p_GND[1])
    ground_sym(ax, c1_x, p_GND[1])

    # IC GND (pin 1): short stub left then ground symbol
    wire(ax, p_GND[0], p_GND[1], p_GND[0] - 0.8, p_GND[1])
    ground_sym(ax, p_GND[0] - 0.8, p_GND[1])

    # ── RST (pin 4) pull-up + GPIO 22 ────────────────────────────────────────
    # GPIO wire runs at y=6.5, which is above the highest timing-column point
    # (y≈5.0) and above the IC VCC terminal (y≈5.5) — no crossings.
    gpio_y  = 6.5
    rpu_x   = p_RST[0]   # pull-up resistor sits on the RST wire column (x=5.1)
    rpu_top = 8.0         # 5V terminal for pull-up

    # RST pin wire goes up through the RST/GPIO junction to R_pu bottom
    wire(ax, p_RST[0], p_RST[1], p_RST[0], gpio_y)
    dot(ax, p_RST[0], gpio_y)                         # T-junction

    # R_pu: GPIO/RST junction → 5 V terminal
    wire(ax, p_RST[0], gpio_y, p_RST[0], gpio_y + 0.4)
    resistor(ax, p_RST[0], gpio_y + 0.4, p_RST[0], rpu_top - 0.3,
             label="R_pu\n10 kΩ", label_side="right")
    wire(ax, p_RST[0], rpu_top - 0.3, p_RST[0], rpu_top)
    open_terminal(ax, p_RST[0], rpu_top, "5 V", loc="top")

    # GPIO 22 wire arrives horizontally from the left at gpio_y
    gpio_x_start = -4.8
    wire(ax, gpio_x_start, gpio_y, p_RST[0], gpio_y)
    open_terminal(ax, gpio_x_start, gpio_y,
                  "GPIO 22\n(Pi pin 15)\n3.3 V logic", loc="left")

    # ── CTL (pin 5) bypass cap ────────────────────────────────────────────────
    # Well to the right of IC, separate from R3/Q1 area
    c2_x = 7.5
    wire(ax, p_CTL[0], p_CTL[1], c2_x, p_CTL[1])
    wire(ax, c2_x, p_CTL[1], c2_x, p_CTL[1] - 0.4)
    capacitor(ax, c2_x, p_CTL[1] - 0.65, vert=True,
              label="C2\n0.1 µF\n(ceramic)", label_side="right")
    wire(ax, c2_x, p_CTL[1] - 0.9, c2_x, p_GND[1])
    ground_sym(ax, c2_x, p_GND[1])

    # ── OUT (pin 3) → R3 → Q1 ────────────────────────────────────────────────
    # Q1 is far enough right that C2 (x=7.5) doesn't crowd it
    q_cx = 9.2
    q_cy = p_OUT[1]   # y = 0.8

    wire(ax, p_OUT[0], p_OUT[1], p_OUT[0] + 0.5, p_OUT[1])
    resistor(ax, p_OUT[0] + 0.5, p_OUT[1], q_cx - 0.25, p_OUT[1],
             label="R3   1 kΩ", label_side="top")
    base, collector, emitter = npn_transistor(ax, q_cx, q_cy,
                                               label="Q1\n2N2222")
    wire(ax, q_cx - 0.25, p_OUT[1], base[0], base[1])

    # Emitter → GND
    wire(ax, emitter[0], emitter[1], emitter[0], emitter[1] - 0.6)
    ground_sym(ax, emitter[0], emitter[1] - 0.6)

    # ── Relay coil at x = 11.5 ───────────────────────────────────────────────
    coil_x   = 11.5
    coil_bot = collector[1] + 0.3
    coil_top = coil_bot + 3.5
    vcc_rly_y = coil_top + 0.8

    wire(ax, collector[0], collector[1], collector[0], coil_bot)
    wire(ax, collector[0], coil_bot, coil_x, coil_bot)
    dot(ax, coil_x, coil_bot)
    dot(ax, coil_x, coil_top)

    inductor(ax, coil_x, coil_bot, coil_x, coil_top,
             loops=3, label="Relay\ncoil\n(5 V)", label_side="left")

    wire(ax, coil_x, coil_top, coil_x, vcc_rly_y)
    open_terminal(ax, coil_x, vcc_rly_y, "5 V (relay\nmodule VCC)", loc="top")

    # ── D1 flyback diode at x = 13.2 ─────────────────────────────────────────
    d1_x = 13.2
    wire(ax, coil_x, coil_bot, d1_x, coil_bot)
    wire(ax, coil_x, coil_top, d1_x, coil_top)
    diode(ax, d1_x, coil_bot, d1_x, coil_top,
          reverse=True, label="D1\n1N4007\n(flyback)", color="#b00")

    # ── Relay NO contact + bell coil at x = 16.0 ─────────────────────────────
    bell_x = 16.0
    rail_y = vcc_rly_y + 1.5   # 12 V supply rail above relay 5 V terminal

    open_terminal(ax, bell_x + 1.5, rail_y, "12 V DC\nsupply (+)", loc="right")
    wire(ax, bell_x - 0.5, rail_y, bell_x + 1.6, rail_y)
    wire(ax, bell_x, rail_y, bell_x, rail_y - 0.4)

    sw_top = rail_y - 0.4
    sw_bot = sw_top - 1.1
    dot(ax, bell_x, sw_top, r=0.05)
    ax.plot([bell_x, bell_x + 0.25, bell_x],
            [sw_top, (sw_top + sw_bot) / 2, sw_bot],
            color="black", lw=1.5)
    dot(ax, bell_x, sw_bot, r=0.05)
    ax.text(bell_x + 0.38, (sw_top + sw_bot) / 2,
            "Relay NO\ncontact", ha="left", va="center",
            fontsize=7.5, family="monospace")
    wire(ax, bell_x, sw_bot, bell_x, sw_bot - 0.4)

    bell_top = sw_bot - 0.4
    bell_bot = bell_top - 4.0
    inductor(ax, bell_x, bell_top, bell_x, bell_bot,
             loops=4, label="Bell coil\n(Type 500\nringer)", label_side="right")
    wire(ax, bell_x, bell_bot, bell_x, bell_bot - 0.5)
    open_terminal(ax, bell_x, bell_bot - 0.5, "12 V DC\nsupply (−)", loc="right")

    # ── Annotation ────────────────────────────────────────────────────────────
    ann_y = coil_bot - 1.2
    ax.annotate("",
                xy=(bell_x - 0.3, ann_y),
                xytext=(coil_x + 0.3, ann_y),
                arrowprops=dict(arrowstyle="-|>", color="#999", lw=1.0,
                                connectionstyle="arc3,rad=-0.2"))
    ax.text((coil_x + bell_x) / 2, ann_y - 0.25,
            "relay coil → NO contact (mechanical)",
            ha="center", va="top", fontsize=6.5, color="#888", style="italic")

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
