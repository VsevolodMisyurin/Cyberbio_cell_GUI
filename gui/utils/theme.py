"""gui/utils/theme.py — Central design tokens."""

BG_DARK      = "#0d1117"
BG_PANEL     = "#161b22"
BG_FIELD     = "#ffffff"
ACCENT       = "#238636"
ACCENT2      = "#1f6feb"
DANGER       = "#da3633"
WARNING      = "#d29922"
TEXT_PRIMARY = "#e6edf3"
TEXT_MUTED   = "#8b949e"
BORDER       = "#30363d"

GENOME_COLORS = [
    "#58a6ff", "#3fb950", "#f78166", "#d2a8ff", "#ffa657",
    "#79c0ff", "#56d364", "#ff7b72", "#e3b341", "#bc8cff",
]

def genome_color(genome_id: int) -> str:
    return GENOME_COLORS[genome_id % len(GENOME_COLORS)]

FONT_SIZE_NORMAL = 13
FONT_SIZE_SMALL  = 11
FONT_SIZE_LARGE  = 16
PAD   = 12
PAD_S = 6
CELL_DOT_PX  = 6
JITTER_PX    = 2
DEFAULT_TPS  = 1.0
SPEED_FACTOR = 1.20


def btn_style(bg: str, hover_bg: str = None, text: str = "#ffffff",
              radius: int = 4, padding: str = "5px 12px",
              font_size: int = 13) -> str:
    """Button stylesheet with visible hover/press feedback."""
    if hover_bg is None:
        try:
            r = min(255, int(bg[1:3], 16) + 40)
            g = min(255, int(bg[3:5], 16) + 40)
            b = min(255, int(bg[5:7], 16) + 40)
            hover_bg = f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            hover_bg = bg
    return (
        f"QPushButton{{background:{bg};color:{text};border:none;"
        f"border-radius:{radius}px;padding:{padding};"
        f"font-weight:bold;font-size:{font_size}px;}}"
        f"QPushButton:hover{{background:{hover_bg};"
        f"border:1px solid rgba(255,255,255,0.3);}}"
        f"QPushButton:pressed{{background:{bg};"
        f"border:1px solid rgba(255,255,255,0.6);}}"
        f"QPushButton:disabled{{background:#2d333b;color:#484f58;border:none;}}"
    )


def apply_btn_style(btn, bg: str, **kwargs):
    btn.setStyleSheet(btn_style(bg, **kwargs))
