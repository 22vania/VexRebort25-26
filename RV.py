# ============================================================
# RV (Route Visualizer) | dark mode
#
# # designed and developed by Vania Dutta using chatGPT
# 
# ============================================================

import math
import json
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from tkinter import ttk, messagebox, filedialog

# ----------------------------
# Helpers
# ----------------------------
EPS = 1e-9


def normalize_deg(a: float) -> float:
    """Normalize to (-180, 180]."""
    a = (a + 180.0) % 360.0 - 180.0
    if a <= -180.0:
        a += 360.0
    return a


def angle_deg(dx: float, dy: float) -> float:
    return normalize_deg(math.degrees(math.atan2(dy, dx)))


def rotate_points(points, angle_deg_view):
    """VIEW-ONLY rotation around origin (0,0)."""
    print("Hello, world!")  # Added print statement before the for loop
    a = math.radians(float(angle_deg_view))
    ca, sa = math.cos(a), math.sin(a)
    out = []
    for x, y in points:
        xr = x * ca - y * sa
        yr = x * sa + y * ca
        out.append((xr, yr))
    return out


def rot2(x: float, y: float, ang_rad: float) -> tuple[float, float]:
    """Rotate (x,y) by ang_rad about origin."""
    ca, sa = math.cos(ang_rad), math.sin(ang_rad)
    return (x * ca - y * sa, x * sa + y * ca)


def close_xy(a, b, tol=1e-4):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


# ----------------------------
# Scrollable left panel
# ----------------------------
class ScrollableFrame(ttk.Frame):
    """A vertically scrollable frame (mouse wheel works when hovered)."""

    def __init__(self, master, width=330, canvas_bg=None, **kwargs):
        super().__init__(master, **kwargs)
        self._wheel_bound = False

        self.canvas = tk.Canvas(self, highlightthickness=0, width=width)
        if canvas_bg is not None:
            self.canvas.configure(bg=canvas_bg)

        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = ttk.Frame(self.canvas)
        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)
        self.inner.bind("<Enter>", self._bind_mousewheel)
        self.inner.bind("<Leave>", self._unbind_mousewheel)

    def _on_inner_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.inner_id, width=event.width)

    def _bind_mousewheel(self, _event=None):
        if self._wheel_bound:
            return
        self._wheel_bound = True
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel_linux)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel_linux)

    def _unbind_mousewheel(self, _event=None):
        if not self._wheel_bound:
            return
        self._wheel_bound = False
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        delta = int(-1 * (event.delta / 120))
        self.canvas.yview_scroll(delta, "units")

    def _on_mousewheel_linux(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")


# ----------------------------
# Model
# ----------------------------
@dataclass
class Segment:
    length_mm: float
    turn_deg: float  # applied AFTER this segment


def compute_vertices(
    segments: list[Segment], start_heading_deg: float, start_pos: tuple[float, float]
) -> list[tuple[float, float]]:
    """Forward-kinematics build of vertices from segments + start heading, starting at start_pos."""
    x, y = float(start_pos[0]), float(start_pos[1])
    heading = float(start_heading_deg)
    verts = [(x, y)]
    for seg in segments:
        rad = math.radians(heading)
        x += seg.length_mm * math.cos(rad)
        y += seg.length_mm * math.sin(rad)
        verts.append((x, y))
        heading = heading + seg.turn_deg
    return verts


def compute_segment_headings(
    segments: list[Segment], start_heading_deg: float
) -> list[float]:
    """Heading at the START of each segment (size = n)."""
    heading = float(start_heading_deg)
    heads = []
    for seg in segments:
        heads.append(heading)
        heading = heading + seg.turn_deg
    return heads


def solve_segments_from_vertices(
    vertices: list[tuple[float, float]],
    prev_segments: list[Segment],
    prev_start_heading: float,
    edited_index: int | None = None,
    edited_length: float | None = None,
) -> tuple[float, list[Segment]]:
    """
    Given fixed vertices, compute segment lengths/turns that reproduce them,
    preserving each segment's sign from prev_segments (except edited_index).
    """
    n = len(vertices) - 1
    if n <= 0:
        return prev_start_heading, []

    signs = []
    for i in range(n):
        s = 1.0 if prev_segments[i].length_mm >= 0 else -1.0
        signs.append(s)

    if edited_index is not None and edited_length is not None:
        if abs(edited_length) >= EPS:
            signs[edited_index] = 1.0 if edited_length > 0 else -1.0

    old_heads = compute_segment_headings(prev_segments, prev_start_heading)

    seg_heads = [0.0] * n
    seg_lens = [0.0] * n

    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[i + 1]
        dx, dy = (x2 - x1), (y2 - y1)
        dist = math.hypot(dx, dy)

        if dist < EPS:
            h = old_heads[i] if i < len(old_heads) else 0.0
            seg_heads[i] = normalize_deg(h)
            seg_lens[i] = 0.0
            continue

        v_ang = angle_deg(dx, dy)

        if signs[i] >= 0:
            seg_heads[i] = v_ang
            seg_lens[i] = dist
        else:
            seg_heads[i] = normalize_deg(v_ang + 180.0)
            seg_lens[i] = -dist

    if edited_index is not None and edited_length is not None:
        seg_lens[edited_index] = float(edited_length)
        i = edited_index
        x1, y1 = vertices[i]
        x2, y2 = vertices[i + 1]
        dx, dy = (x2 - x1), (y2 - y1)
        dist = math.hypot(dx, dy)
        if dist >= EPS:
            v_ang = angle_deg(dx, dy)
            seg_heads[i] = v_ang if seg_lens[i] >= 0 else normalize_deg(v_ang + 180.0)

    new_start_heading = seg_heads[0]

    new_segments: list[Segment] = []
    for i in range(n):
        if i < n - 1:
            turn = normalize_deg(seg_heads[i + 1] - seg_heads[i])
        else:
            turn = prev_segments[i].turn_deg if i < len(prev_segments) else 0.0
        new_segments.append(Segment(length_mm=seg_lens[i], turn_deg=turn))

    return new_start_heading, new_segments


# ----------------------------
# App
# ----------------------------
class RV(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RV (Route Viewer)")
        self.geometry("1320x920")

        # ---- Dark mode palette ----
        self.D_BG = "#141414"
        self.D_PANEL = "#1b1b1b"
        self.D_WIDGET = "#202020"
        self.D_FIELD = "#262626"
        self.D_BORDER = "#3a3a3a"
        self.D_TEXT = "#e6e6e6"
        self.D_MUTED = "#bfbfbf"
        self.D_CANVAS = "#101010"
        self.D_LINE = "#e6e6e6"
        self.D_POINT = "#e6e6e6"
        self.D_LABEL_BG = "#1a1a1a"
        self.D_LABEL_OUT = "#3a3a3a"

        self._apply_dark_mode()

        # Canonical model
        self.start_pos = (0.0, 0.0)
        self.start_heading_deg = 90.0
        self.segments = [
            Segment(300, 45),
            Segment(200, -90),
            Segment(250, 30),
        ]

        # View-only rotation (display)
        self.view_rotation_var = tk.StringVar(value="0")

        # Length edit mode: which endpoint moves when editing a Length cell
        self.length_edit_mode = tk.StringVar(value="end")

        # Label font size
        self.label_font_size_var = tk.StringVar(value="10")

        # Endpoint locks
        self.lock_start_var = tk.BooleanVar(value=True)
        self.lock_end_var = tk.BooleanVar(value=False)
        self.locked_start_pos: tuple[float, float] | None = self.start_pos
        self.locked_end_pos: tuple[float, float] | None = None

        # Kept for UI compatibility
        self.min_downstream_turns_var = tk.BooleanVar(value=False)

        # Pan/Zoom state (screen pixels)
        self.view_scale = 1.0
        self.view_offx = 0.0
        self.view_offy = 0.0
        self._auto_fit_once = True

        self._panning = False
        self._pan_last = (0, 0)

        # cell editor overlay state
        self._edit_entry = None
        self._edit_info = None  # (tree_widget, row_idx, col_idx)

        self._build_ui()
        self._refresh_segments_tree()
        self._refresh_vertices_tree()
        self._capture_locked_positions()
        self.redraw()

    # ----------------------------
    # Dark mode
    # ----------------------------
    def _apply_dark_mode(self):
        self.configure(bg=self.D_BG)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=self.D_BG, foreground=self.D_TEXT)

        style.configure("TFrame", background=self.D_BG)
        style.configure("TLabelframe", background=self.D_BG, foreground=self.D_TEXT)
        style.configure("TLabelframe.Label", background=self.D_BG, foreground=self.D_TEXT)
        style.configure("TLabel", background=self.D_BG, foreground=self.D_TEXT)

        style.configure(
            "TButton",
            background=self.D_WIDGET,
            foreground=self.D_TEXT,
            bordercolor=self.D_BORDER,
            focusthickness=1,
            focuscolor=self.D_BORDER,
        )
        style.map(
            "TButton",
            background=[("active", self.D_FIELD), ("pressed", self.D_FIELD)],
            foreground=[("disabled", self.D_MUTED)],
        )

        style.configure("TCheckbutton", background=self.D_BG, foreground=self.D_TEXT)
        style.map("TCheckbutton", foreground=[("disabled", self.D_MUTED)])

        style.configure("TRadiobutton", background=self.D_BG, foreground=self.D_TEXT)
        style.map("TRadiobutton", foreground=[("disabled", self.D_MUTED)])

        style.configure(
            "TEntry",
            fieldbackground=self.D_FIELD,
            background=self.D_FIELD,
            foreground=self.D_TEXT,
            bordercolor=self.D_BORDER,
            insertcolor=self.D_TEXT,
        )

        style.configure(
            "Vertical.TScrollbar", background=self.D_BG, troughcolor=self.D_PANEL
        )

        style.configure(
            "Treeview",
            background=self.D_FIELD,
            fieldbackground=self.D_FIELD,
            foreground=self.D_TEXT,
            bordercolor=self.D_BORDER,
            rowheight=24,
        )
        style.configure(
            "Treeview.Heading",
            background=self.D_WIDGET,
            foreground=self.D_TEXT,
            relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", self.D_BORDER)],
            foreground=[("selected", self.D_TEXT)],
        )

    # ----------------------------
    # UI
    # ----------------------------
    def _build_ui(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        left_scroll = ScrollableFrame(outer, width=455, canvas_bg=self.D_BG)
        left_scroll.pack(side="left", fill="y")
        left = left_scroll.inner

        # Top actions: About button
        top_actions = ttk.Frame(left)
        top_actions.pack(fill="x", pady=(0, 8))
        ttk.Button(top_actions, text="About", command=self._show_about).pack(side="left")

        # --- Segments table ---
        ttk.Label(
            left,
            text="Segments (double-click a cell to edit)",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 6))

        seg_box = ttk.Frame(left)
        seg_box.pack(fill="x", expand=False)

        self.seg_tree = ttk.Treeview(
            seg_box,
            columns=("length", "turn"),
            show="headings",
            height=12,
            selectmode="browse",
        )
        self.seg_tree.heading("length", text="Length (mm)")
        self.seg_tree.heading("turn", text="Turn (deg)")
        self.seg_tree.column("length", width=200, anchor="center")
        self.seg_tree.column("turn", width=200, anchor="center")

        seg_vsb = ttk.Scrollbar(seg_box, orient="vertical", command=self.seg_tree.yview)
        self.seg_tree.configure(yscrollcommand=seg_vsb.set)

        self.seg_tree.grid(row=0, column=0, sticky="nsew")
        seg_vsb.grid(row=0, column=1, sticky="ns")
        seg_box.columnconfigure(0, weight=1)

        self.seg_tree.bind("<Double-1>", self._begin_edit_cell)
        self.seg_tree.bind("<Delete>", lambda e: self._delete_selected_segment())

        # --- Vertex table ---
        ttk.Label(
            left,
            text="Vertices (edit X/Y to move a vertex)",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(14, 6))

        vtx_box = ttk.Frame(left)
        vtx_box.pack(fill="x", expand=False)

        self.vtx_tree = ttk.Treeview(
            vtx_box,
            columns=("v", "x", "y"),
            show="headings",
            height=10,
            selectmode="browse",
        )
        self.vtx_tree.heading("v", text="Vertex")
        self.vtx_tree.heading("x", text="X (mm)")
        self.vtx_tree.heading("y", text="Y (mm)")
        self.vtx_tree.column("v", width=90, anchor="center")
        self.vtx_tree.column("x", width=155, anchor="center")
        self.vtx_tree.column("y", width=155, anchor="center")

        vtx_vsb = ttk.Scrollbar(vtx_box, orient="vertical", command=self.vtx_tree.yview)
        self.vtx_tree.configure(yscrollcommand=vtx_vsb.set)

        self.vtx_tree.grid(row=0, column=0, sticky="nsew")
        vtx_vsb.grid(row=0, column=1, sticky="ns")
        vtx_box.columnconfigure(0, weight=1)

        self.vtx_tree.bind("<Double-1>", self._begin_edit_cell)

        # --- Buttons ---
        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(12, 6))
        ttk.Button(btns, text="Add segment", command=self._add_segment).pack(
            fill="x", pady=2
        )
        ttk.Button(btns, text="Delete selected segment", command=self._delete_selected_segment).pack(
            fill="x", pady=2
        )
        ttk.Button(btns, text="Fit view", command=self._fit_view_and_redraw).pack(
            fill="x", pady=2
        )

        # --- Locks ---
        lockbox = ttk.LabelFrame(left, text="Endpoint locks (highest priority)", padding=8)
        lockbox.pack(fill="x", pady=(10, 8))

        ttk.Checkbutton(
            lockbox,
            text="Lock START vertex (vertex 0)",
            variable=self.lock_start_var,
            command=self._on_locks_changed,
        ).pack(anchor="w")

        ttk.Checkbutton(
            lockbox,
            text="Lock FINAL endpoint (last vertex)",
            variable=self.lock_end_var,
            command=self._on_locks_changed,
        ).pack(anchor="w")

        ttk.Checkbutton(
            lockbox,
            text="Prefer minimal downstream turn changes (CCD fallback)",
            variable=self.min_downstream_turns_var,
        ).pack(anchor="w", pady=(6, 0))

        # --- Length edit endpoint mode ---
        modebox = ttk.LabelFrame(left, text="Length edit: move which endpoint?", padding=8)
        modebox.pack(fill="x", pady=(8, 8))
        ttk.Radiobutton(
            modebox,
            text="Move END vertex (keep START fixed)",
            variable=self.length_edit_mode,
            value="end",
        ).pack(anchor="w")
        ttk.Radiobutton(
            modebox,
            text="Move START vertex (keep END fixed)",
            variable=self.length_edit_mode,
            value="start",
        ).pack(anchor="w")

        # --- View rotation ---
        viewbox = ttk.LabelFrame(left, text="View rotation (display only)", padding=8)
        viewbox.pack(fill="x", pady=(8, 8))
        ttk.Label(viewbox, text="Rotate view (deg):").pack(anchor="w")
        e = ttk.Entry(viewbox, textvariable=self.view_rotation_var)
        e.pack(fill="x", pady=(2, 6))
        e.bind("<Return>", lambda ev: self.redraw())
        e.bind("<FocusOut>", lambda ev: self.redraw())

        presets = ttk.Frame(viewbox)
        presets.pack(fill="x")
        presets.columnconfigure(0, weight=1)
        presets.columnconfigure(1, weight=1)
        ttk.Button(presets, text="0°", command=lambda: self._set_view_rot(0)).grid(
            row=0, column=0, sticky="ew", padx=(0, 4), pady=2
        )
        ttk.Button(presets, text="90°", command=lambda: self._set_view_rot(90)).grid(
            row=0, column=1, sticky="ew", padx=(4, 0), pady=2
        )
        ttk.Button(presets, text="180°", command=lambda: self._set_view_rot(180)).grid(
            row=1, column=0, sticky="ew", padx=(0, 4), pady=2
        )
        ttk.Button(presets, text="270°", command=lambda: self._set_view_rot(270)).grid(
            row=1, column=1, sticky="ew", padx=(4, 0), pady=2
        )

        # --- Label font ---
        labelbox = ttk.LabelFrame(left, text="Labels", padding=8)
        labelbox.pack(fill="x", pady=(8, 8))
        ttk.Label(labelbox, text="Font size:").pack(anchor="w")
        spin = tk.Spinbox(
            labelbox,
            from_=6,
            to=40,
            increment=1,
            textvariable=self.label_font_size_var,
            width=6,
            bg=self.D_FIELD,
            fg=self.D_TEXT,
            insertbackground=self.D_TEXT,
            highlightbackground=self.D_BORDER,
        )
        spin.pack(anchor="w", pady=(2, 0))
        spin.bind("<Return>", lambda ev: self.redraw())
        spin.bind("<FocusOut>", lambda ev: self.redraw())

        # --- Save/Load/Export ---
        ttk.Separator(left).pack(fill="x", pady=10)
        ttk.Button(left, text="Save JSON…", command=self._save_json).pack(fill="x", pady=2)
        ttk.Button(left, text="Load JSON…", command=self._load_json).pack(fill="x", pady=2)
        ttk.Button(left, text="Export Length/Turn (L#/T# text)…", command=self._export_length_turn_csv).pack(fill="x", pady=2)

        # --- Canvas area ---
        right = ttk.Frame(outer)
        right.pack(side="right", fill="both", expand=True, padx=(10, 0))

        topbar = ttk.Frame(right)
        topbar.pack(fill="x")
        self.status = ttk.Label(topbar, text="Ready")
        self.status.pack(side="left")

        self.canvas = tk.Canvas(
            right, bg=self.D_CANVAS, highlightthickness=1, highlightbackground=self.D_BORDER
        )
        self.canvas.pack(fill="both", expand=True, pady=(8, 0))
        self.canvas.bind("<Configure>", lambda e2: self.redraw())

        # Touchpad-friendly:
        # - two-finger scroll pans
        # - Ctrl+scroll zooms (pinch often emits Ctrl+wheel on Windows)
        # - Shift+scroll pans horizontally
        self.canvas.bind("<MouseWheel>", self._on_wheel_pan_or_zoom)
        self.canvas.bind("<Control-MouseWheel>", self._on_wheel_pan_or_zoom)
        self.canvas.bind("<Shift-MouseWheel>", self._on_wheel_pan_or_zoom)

        # Linux wheel support (optional)
        self.canvas.bind("<Button-4>", self._on_linux_wheel)
        self.canvas.bind("<Button-5>", self._on_linux_wheel)
        self.canvas.bind("<Control-Button-4>", self._on_linux_wheel)
        self.canvas.bind("<Control-Button-5>", self._on_linux_wheel)
        self.canvas.bind("<Shift-Button-4>", self._on_linux_wheel)
        self.canvas.bind("<Shift-Button-5>", self._on_linux_wheel)

        # pan with right mouse
        self.canvas.bind("<ButtonPress-3>", self._pan_start)
        self.canvas.bind("<B3-Motion>", self._pan_move)
        self.canvas.bind("<ButtonRelease-3>", self._pan_end)

    def _show_about(self):
        year = datetime.now().year
        messagebox.showinfo(
            "About", f"Designed and developed by Vania Dutta using chatGPT"
        )

    # ----------------------------
    # NEW: Export Length/Turn CSV line
    # ----------------------------
    def _export_length_turn_csv(self):
        # Exports a plain-text file in this Python-friendly format:
        # global L1_mm, L2_mm, L3_mm, ...
        # global T1_deg, T2_deg, T3_deg, ...
        #
        # L1_mm = 95.00
        # T1_deg = -90.00
        # ...
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
            title="Export Length/Turn (globals) as .txt",
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            n = len(self.segments)
            l_names = [f"L{i}_mm" for i in range(1, n + 1)]
            t_names = [f"T{i}_deg" for i in range(1, n + 1)]

            f.write("global " + ", ".join(l_names) + "\n")
            f.write("global " + ", ".join(t_names) + "\n\n")

            for i, seg in enumerate(self.segments, start=1):
                f.write(f"L{i}_mm = {seg.length_mm:.2f}\n")
                f.write(f"T{i}_deg = {seg.turn_deg:.2f}\n")

    # ----------------------------
    # Locks
    # ----------------------------
    def _current_vertices(self):
        return compute_vertices(self.segments, self.start_heading_deg, self.start_pos)

    def _capture_locked_positions(self):
        verts = self._current_vertices()
        self.locked_start_pos = verts[0] if self.lock_start_var.get() else None
        self.locked_end_pos = verts[-1] if self.lock_end_var.get() else None

    def _on_locks_changed(self):
        verts = self._current_vertices()

        if self.lock_start_var.get():
            if self.locked_start_pos is None:
                self.locked_start_pos = verts[0]
        else:
            self.locked_start_pos = None

        if self.lock_end_var.get():
            if self.locked_end_pos is None:
                self.locked_end_pos = verts[-1]
        else:
            self.locked_end_pos = None

        ok = self._ensure_endpoint_locks()
        if not ok:
            messagebox.showerror("Lock conflict", "Those lock settings conflict with the current geometry.")
            self.lock_end_var.set(False)
            self.locked_end_pos = None
            self._ensure_endpoint_locks()

        self._refresh_vertices_tree()
        self.redraw()

    def _ensure_endpoint_locks(self) -> bool:
        # Force start
        if self.lock_start_var.get():
            if self.locked_start_pos is None:
                self.locked_start_pos = self.start_pos
            self.start_pos = self.locked_start_pos

        verts = self._current_vertices()

        # Force end
        if self.lock_end_var.get():
            if self.locked_end_pos is None:
                self.locked_end_pos = verts[-1]
            current_end = verts[-1]

            # If start is not locked, translate by changing start_pos
            if not self.lock_start_var.get():
                dx = self.locked_end_pos[0] - current_end[0]
                dy = self.locked_end_pos[1] - current_end[1]
                self.start_pos = (self.start_pos[0] + dx, self.start_pos[1] + dy)
                return True

            # Both locked: must already match
            verts2 = self._current_vertices()
            if not close_xy(verts2[-1], self.locked_end_pos):
                return False

        return True

    # ----------------------------
    # Turn edit special rule:
    # If START and END locked, allow NEXT link length + turn to change
    # ----------------------------
    def _try_adjust_next_link_to_keep_end_locked(self, edited_turn_index: int) -> bool:
        n = len(self.segments)
        i = edited_turn_index
        j = i + 1
        if j >= n:
            return False
        if self.locked_end_pos is None:
            return False

        verts = self._current_vertices()  # uses updated turn_i already
        A = verts[j]
        E = self.locked_end_pos

        heads = compute_segment_headings(self.segments, self.start_heading_deg)
        theta = math.radians(heads[j])

        Dx = E[0] - A[0]
        Dy = E[1] - A[1]
        Dx_p, Dy_p = rot2(Dx, Dy, -theta)

        tail = self.segments[j + 1 :]
        if len(tail) == 0:
            if abs(Dy_p) > 1e-3:
                return False
            self.segments[j].length_mm = Dx_p
            return True

        tail_verts = compute_vertices(tail, start_heading_deg=0.0, start_pos=(0.0, 0.0))
        V0x, V0y = tail_verts[-1]
        r = math.hypot(V0x, V0y)

        if r < EPS:
            if abs(Dy_p) > 1e-3:
                return False
            self.segments[j].length_mm = Dx_p
            return True

        beta = math.atan2(V0y, V0x)
        s = Dy_p / r
        if s < -1.0 - 1e-8 or s > 1.0 + 1e-8:
            return False
        s = max(-1.0, min(1.0, s))
        a = math.asin(s)
        phi1 = a - beta
        phi2 = (math.pi - a) - beta

        cur_phi = math.radians(self.segments[j].turn_deg)

        def diff_deg(x, y):
            return abs(normalize_deg(math.degrees(x - y)))

        phi = phi1 if diff_deg(phi1, cur_phi) <= diff_deg(phi2, cur_phi) else phi2

        V0x_r, V0y_r = rot2(V0x, V0y, phi)
        t = Dx_p - V0x_r

        self.segments[j].length_mm = t
        self.segments[j].turn_deg = normalize_deg(math.degrees(phi))
        return True

    # ----------------------------
    # Coordinate edit: user edits vertex X/Y
    # ----------------------------
    def _apply_vertex_coord_change(self, v_idx: int, axis: str, new_val: float) -> bool:
        verts = self._current_vertices()
        last_idx = len(verts) - 1

        if v_idx == 0 and self.lock_start_var.get():
            messagebox.showerror(
                "Locked vertex", "START vertex is locked. Turn off 'Lock START' to edit vertex 0."
            )
            return False
        if v_idx == last_idx and self.lock_end_var.get():
            messagebox.showerror(
                "Locked vertex",
                "FINAL endpoint is locked. Turn off 'Lock FINAL' to edit the last vertex.",
            )
            return False

        x, y = verts[v_idx]
        if axis == "x":
            x = float(new_val)
        else:
            y = float(new_val)
        verts[v_idx] = (x, y)

        # Force locked endpoints
        if self.lock_start_var.get() and self.locked_start_pos is not None:
            verts[0] = self.locked_start_pos
        if self.lock_end_var.get() and self.locked_end_pos is not None:
            verts[-1] = self.locked_end_pos

        prev_segments = [Segment(s.length_mm, s.turn_deg) for s in self.segments]
        new_start_heading, new_segments = solve_segments_from_vertices(
            vertices=verts, prev_segments=prev_segments, prev_start_heading=self.start_heading_deg
        )

        self.start_heading_deg = new_start_heading
        self.segments = new_segments
        self.start_pos = verts[0]

        if not self._ensure_endpoint_locks():
            messagebox.showerror("Lock conflict", "That vertex move conflicts with endpoint locks.")
            return False

        return True

    # ----------------------------
    # Touchpad-friendly pan/zoom
    # ----------------------------
    def _zoom_at(self, cx: float, cy: float, wheel_delta: float):
        factor = 1.001 ** wheel_delta
        new_scale = self.view_scale * factor
        new_scale = max(0.02, min(200.0, new_scale))

        wx, wy = self._screen_to_world(cx, cy)
        self.view_scale = new_scale
        self.view_offx = cx - wx * self.view_scale
        self.view_offy = cy + wy * self.view_scale

    def _on_wheel_pan_or_zoom(self, event):
        SHIFT_MASK = 0x0001
        CTRL_MASK = 0x0004

        is_shift = (event.state & SHIFT_MASK) != 0
        is_ctrl = (event.state & CTRL_MASK) != 0

        d = float(event.delta)

        if is_ctrl:
            self._zoom_at(event.x, event.y, d)
        else:
            pan_px = -d * (40.0 / 120.0)
            if is_shift:
                self.view_offx += pan_px
            else:
                self.view_offy += pan_px

        self.redraw()

    def _on_linux_wheel(self, event):
        SHIFT_MASK = 0x0001
        CTRL_MASK = 0x0004

        is_shift = (event.state & SHIFT_MASK) != 0
        is_ctrl = (event.state & CTRL_MASK) != 0

        d = 120.0 if event.num == 4 else -120.0

        if is_ctrl:
            self._zoom_at(event.x, event.y, d)
        else:
            pan_px = -d * (40.0 / 120.0)
            if is_shift:
                self.view_offx += pan_px
            else:
                self.view_offy += pan_px

        self.redraw()

    # ----------------------------
    # Pan/Zoom transforms
    # ----------------------------
    def _world_to_screen(self, xw: float, yw: float) -> tuple[float, float]:
        xs = xw * self.view_scale + self.view_offx
        ys = -yw * self.view_scale + self.view_offy
        return xs, ys

    def _screen_to_world(self, xs: float, ys: float) -> tuple[float, float]:
        xw = (xs - self.view_offx) / self.view_scale
        yw = -(ys - self.view_offy) / self.view_scale
        return xw, yw

    def _fit_view(self, pts_world: list[tuple[float, float]]):
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        xs = [p[0] for p in pts_world]
        ys = [p[1] for p in pts_world]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)

        dx = max(maxx - minx, 1.0)
        dy = max(maxy - miny, 1.0)

        margin = 70
        sx = (w - 2 * margin) / dx
        sy = (h - 2 * margin) / dy
        self.view_scale = max(0.01, min(sx, sy))

        cx = (minx + maxx) / 2
        cy = (miny + maxy) / 2
        self.view_offx = w / 2 - cx * self.view_scale
        self.view_offy = h / 2 + cy * self.view_scale

    def _fit_view_and_redraw(self):
        pts = self._get_draw_points()
        if pts:
            self._fit_view(pts)
        self.redraw()

    def _pan_start(self, event):
        self._panning = True
        self._pan_last = (event.x, event.y)

    def _pan_move(self, event):
        if not self._panning:
            return
        lx, ly = self._pan_last
        self.view_offx += (event.x - lx)
        self.view_offy += (event.y - ly)
        self._pan_last = (event.x, event.y)
        self.redraw()

    def _pan_end(self, _event):
        self._panning = False

    # ----------------------------
    # Font size
    # ----------------------------
    def _get_label_font_size(self) -> int:
        try:
            n = int(float(self.label_font_size_var.get().strip()))
            return max(6, min(40, n))
        except ValueError:
            self.label_font_size_var.set("10")
            return 10

    # ----------------------------
    # Formatting
    # ----------------------------
    @staticmethod
    def _fmt(x: float) -> str:
        if abs(x - round(x)) < 1e-10:
            return str(int(round(x)))
        return f"{x:.6f}".rstrip("0").rstrip(".")

    # ----------------------------
    # Tree refresh
    # ----------------------------
    def _refresh_segments_tree(self):
        sel = self._selected_segment_index()
        self.seg_tree.delete(*self.seg_tree.get_children())
        for seg in self.segments:
            self.seg_tree.insert("", "end", values=(self._fmt(seg.length_mm), self._fmt(seg.turn_deg)))
        kids = self.seg_tree.get_children()
        if kids:
            self.seg_tree.selection_set(kids[0 if sel is None else min(sel, len(kids) - 1)])

    def _refresh_vertices_tree(self):
        verts = self._current_vertices()
        self.vtx_tree.delete(*self.vtx_tree.get_children())
        for i, (x, y) in enumerate(verts):
            self.vtx_tree.insert("", "end", values=(f"V{i}", self._fmt(x), self._fmt(y)))

    def _selected_segment_index(self):
        sel = self.seg_tree.selection()
        if not sel:
            return None
        return self.seg_tree.index(sel[0])

    # ----------------------------
    # Cell editing (segments + vertices)
    # ----------------------------
    def _begin_edit_cell(self, event):
        if self._edit_entry is not None:
            return

        tree = event.widget
        region = tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        row_id = tree.identify_row(event.y)
        col_id = tree.identify_column(event.x)
        if not row_id or not col_id:
            return

        row_idx = tree.index(row_id)
        col_idx = int(col_id.replace("#", "")) - 1

        # Vertex table: prevent editing "Vertex" name column
        if tree is self.vtx_tree and col_idx == 0:
            return

        bbox = tree.bbox(row_id, col_id)
        if not bbox:
            return
        x, y, w, h = bbox

        current_values = tree.item(row_id, "values")
        current_text = current_values[col_idx] if current_values else ""

        self._edit_info = (tree, row_idx, col_idx)
        self._edit_entry = ttk.Entry(tree)
        self._edit_entry.insert(0, current_text)
        self._edit_entry.select_range(0, tk.END)
        self._edit_entry.place(x=x, y=y, width=w, height=h)
        self._edit_entry.focus_set()

        self._edit_entry.bind("<Return>", self._commit_edit)
        self._edit_entry.bind("<Escape>", self._cancel_edit)
        self._edit_entry.bind("<FocusOut>", self._commit_edit)

    def _cancel_edit(self, _event=None):
        if self._edit_entry is not None:
            self._edit_entry.destroy()
        self._edit_entry = None
        self._edit_info = None

    def _commit_edit(self, _event=None):
        if self._edit_entry is None or self._edit_info is None:
            return

        tree, row_idx, col_idx = self._edit_info
        text = self._edit_entry.get().strip()

        try:
            val = float(text)
        except ValueError:
            messagebox.showerror("Invalid input", "Please enter a number.")
            self._cancel_edit()
            return

        prev_state = (
            self.start_pos,
            self.start_heading_deg,
            [Segment(s.length_mm, s.turn_deg) for s in self.segments],
            self.locked_start_pos,
            self.locked_end_pos,
        )

        ok = True

        if tree is self.seg_tree:
            if col_idx == 0:
                ok = self._apply_length_change(segment_index=row_idx, new_length=val)
            else:
                ok = self._apply_turn_change(segment_index=row_idx, new_turn=val)

        elif tree is self.vtx_tree:
            axis = "x" if col_idx == 1 else "y"
            ok = self._apply_vertex_coord_change(v_idx=row_idx, axis=axis, new_val=val)

        if not ok:
            self.start_pos, self.start_heading_deg, segs, self.locked_start_pos, self.locked_end_pos = prev_state
            self.segments = segs

        self._refresh_segments_tree()
        self._refresh_vertices_tree()
        self.redraw()
        self._cancel_edit()

    # ----------------------------
    # Segment edits
    # ----------------------------
    def _apply_length_change(self, segment_index: int, new_length: float) -> bool:
        n = len(self.segments)
        if not (0 <= segment_index < n):
            return False

        verts = self._current_vertices()
        last_vertex_idx = len(verts) - 1

        i = segment_index
        x1, y1 = verts[i]
        x2, y2 = verts[i + 1]
        dx, dy = (x2 - x1), (y2 - y1)
        dist = math.hypot(dx, dy)
        if dist < EPS:
            messagebox.showerror(
                "Cannot edit", "This segment currently has ~0 length; cannot define direction."
            )
            return False

        ux, uy = dx / dist, dy / dist

        mode = self.length_edit_mode.get()
        desired_move_idx = i if mode == "start" else (i + 1)
        other_idx = (i + 1) if mode == "start" else i

        def is_locked_vertex(v_idx: int) -> bool:
            if v_idx == 0 and self.lock_start_var.get():
                return True
            if v_idx == last_vertex_idx and self.lock_end_var.get():
                return True
            return False

        if is_locked_vertex(desired_move_idx):
            desired_move_idx, other_idx = other_idx, desired_move_idx

        if is_locked_vertex(desired_move_idx):
            messagebox.showerror(
                "Locked endpoints",
                "Both endpoints are locked for this edit; cannot change this segment length.",
            )
            return False

        if desired_move_idx == i:
            endx, endy = verts[i + 1]
            verts[i] = (endx - ux * new_length, endy - uy * new_length)
        else:
            startx, starty = verts[i]
            verts[i + 1] = (startx + ux * new_length, starty + uy * new_length)

        prev_segments = [Segment(s.length_mm, s.turn_deg) for s in self.segments]
        self.start_heading_deg, self.segments = solve_segments_from_vertices(
            vertices=verts,
            prev_segments=prev_segments,
            prev_start_heading=self.start_heading_deg,
            edited_index=i,
            edited_length=new_length,
        )
        self.start_pos = verts[0]

        if not self._ensure_endpoint_locks():
            messagebox.showerror("Lock conflict", "This length edit conflicts with endpoint locks.")
            return False
        return True

    def _apply_turn_change(self, segment_index: int, new_turn: float) -> bool:
        n = len(self.segments)
        if not (0 <= segment_index < n):
            return False

        # last segment turn doesn't affect geometry
        if segment_index == n - 1:
            self.segments[segment_index].turn_deg = float(new_turn)
            return True

        self.segments[segment_index].turn_deg = float(new_turn)

        # start lock
        if self.lock_start_var.get() and self.locked_start_pos is not None:
            self.start_pos = self.locked_start_pos

        # end not locked
        if not self.lock_end_var.get():
            return self._ensure_endpoint_locks()

        # end locked but start not locked: translate
        if not self.lock_start_var.get():
            return self._ensure_endpoint_locks()

        # both locked: allow next link length+turn adjust
        if self.locked_end_pos is None:
            self.locked_end_pos = self._current_vertices()[-1]

        adjusted = self._try_adjust_next_link_to_keep_end_locked(segment_index)
        if adjusted and self._ensure_endpoint_locks():
            return True

        messagebox.showerror(
            "Locked endpoint",
            "Could not satisfy locked endpoints for this Turn change using the 'next link' adjustment.\n"
            "Try unlocking the FINAL endpoint, or edit a vertex coordinate instead.",
        )
        return False

    # ----------------------------
    # CRUD
    # ----------------------------
    def _add_segment(self):
        prev_state = (self.start_pos, self.start_heading_deg, [Segment(s.length_mm, s.turn_deg) for s in self.segments])
        self.segments.append(Segment(100.0, 0.0))
        ok = self._ensure_endpoint_locks()
        if not ok:
            self.start_pos, self.start_heading_deg, self.segments = prev_state
            messagebox.showerror("Lock conflict", "Cannot add a segment under the current endpoint locks.")
        self._refresh_segments_tree()
        self._refresh_vertices_tree()
        self.redraw()

    def _delete_selected_segment(self):
        idx = self._selected_segment_index()
        if idx is None:
            return
        if len(self.segments) <= 1:
            messagebox.showinfo("Info", "At least one segment must remain.")
            return
        prev_state = (self.start_pos, self.start_heading_deg, [Segment(s.length_mm, s.turn_deg) for s in self.segments])
        del self.segments[idx]
        ok = self._ensure_endpoint_locks()
        if not ok:
            self.start_pos, self.start_heading_deg, self.segments = prev_state
            messagebox.showerror("Lock conflict", "Cannot delete a segment under the current endpoint locks.")
        self._refresh_segments_tree()
        self._refresh_vertices_tree()
        self.redraw()

    # ----------------------------
    # Save/Load
    # ----------------------------
    def _save_json(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        payload = {
            "start_pos": {"x": self.start_pos[0], "y": self.start_pos[1]},
            "start_heading_deg": self.start_heading_deg,
            "segments": [{"length_mm": s.length_mm, "turn_deg": s.turn_deg} for s in self.segments],
            "locks": {
                "lock_start": bool(self.lock_start_var.get()),
                "lock_end": bool(self.lock_end_var.get()),
                "locked_start_pos": None
                if self.locked_start_pos is None
                else {"x": self.locked_start_pos[0], "y": self.locked_start_pos[1]},
                "locked_end_pos": None
                if self.locked_end_pos is None
                else {"x": self.locked_end_pos[0], "y": self.locked_end_pos[1]},
            },
            "solver": {"minimize_downstream_turns": bool(self.min_downstream_turns_var.get())},
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def _load_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        prev_state = (
            self.start_pos,
            self.start_heading_deg,
            [Segment(s.length_mm, s.turn_deg) for s in self.segments],
            self.lock_start_var.get(),
            self.lock_end_var.get(),
            self.locked_start_pos,
            self.locked_end_pos,
            self.min_downstream_turns_var.get(),
        )
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            sp = data.get("start_pos", {"x": 0.0, "y": 0.0})
            self.start_pos = (float(sp.get("x", 0.0)), float(sp.get("y", 0.0)))
            self.start_heading_deg = float(data.get("start_heading_deg", 90.0))

            segs = data.get("segments", [])
            self.segments = [Segment(float(r["length_mm"]), float(r["turn_deg"])) for r in segs]
            if not self.segments:
                raise ValueError("No segments found.")

            locks = data.get("locks", {})
            self.lock_start_var.set(bool(locks.get("lock_start", True)))
            self.lock_end_var.set(bool(locks.get("lock_end", False)))

            lsp = locks.get("locked_start_pos")
            lep = locks.get("locked_end_pos")
            self.locked_start_pos = None if lsp is None else (float(lsp["x"]), float(lsp["y"]))
            self.locked_end_pos = None if lep is None else (float(lep["x"]), float(lep["y"]))

            solver = data.get("solver", {})
            self.min_downstream_turns_var.set(bool(solver.get("minimize_downstream_turns", False)))

            if self.lock_start_var.get() and self.locked_start_pos is None:
                self.locked_start_pos = self._current_vertices()[0]
            if self.lock_end_var.get() and self.locked_end_pos is None:
                self.locked_end_pos = self._current_vertices()[-1]

            if not self._ensure_endpoint_locks():
                raise ValueError("Loaded geometry conflicts with endpoint locks.")

            self._refresh_segments_tree()
            self._refresh_vertices_tree()
            self._auto_fit_once = True
            self.redraw()

        except Exception as e:
            (
                self.start_pos,
                self.start_heading_deg,
                segs,
                ls,
                le,
                lsp,
                lep,
                mindown,
            ) = prev_state
            self.segments = segs
            self.lock_start_var.set(ls)
            self.lock_end_var.set(le)
            self.locked_start_pos = lsp
            self.locked_end_pos = lep
            self.min_downstream_turns_var.set(mindown)
            messagebox.showerror("Load failed", str(e))

    # ----------------------------
    # View rotation
    # ----------------------------
    def _set_view_rot(self, deg):
        self.view_rotation_var.set(str(deg))
        self.redraw()

    def _get_view_rot(self) -> float:
        try:
            return float(self.view_rotation_var.get().strip())
        except ValueError:
            self.view_rotation_var.set("0")
            return 0.0

    def _get_draw_points(self):
        if not self.segments:
            return []
        world_pts = self._current_vertices()
        return rotate_points(world_pts, self._get_view_rot())

    # ----------------------------
    # Drawing
    # ----------------------------
    def redraw(self):
        self.canvas.delete("all")
        world_verts = self._current_vertices()
        draw_pts = rotate_points(world_verts, self._get_view_rot())
        if not draw_pts:
            return

        if self._auto_fit_once:
            self._fit_view(draw_pts)
            self._auto_fit_once = False

        spts = [self._world_to_screen(x, y) for (x, y) in draw_pts]

        # Draw segments + length labels
        for i in range(len(spts) - 1):
            x1, y1 = spts[i]
            x2, y2 = spts[i + 1]
            self.canvas.create_line(x1, y1, x2, y2, width=3, fill=self.D_LINE)
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            self._label(mx, my, f"L{i+1}: {self._fmt(self.segments[i].length_mm)} mm")

        # Draw vertices + coordinate labels + turn labels
        for i, (sx, sy) in enumerate(spts):
            r = 5
            self.canvas.create_oval(sx - r, sy - r, sx + r, sy + r, fill=self.D_POINT, outline="")

            vx, vy = world_verts[i]
            coord_line = f"V{i} ({self._fmt(vx)}, {self._fmt(vy)})"

            if i == 0:
                extra = f"startHeading={self._fmt(self.start_heading_deg)}°\nviewRot={self._fmt(self._get_view_rot())}°"
                self._label(sx + 10, sy + 10, coord_line + "\n" + extra)
            else:
                turn = self.segments[i - 1].turn_deg
                self._label(sx + 10, sy - 18, coord_line + f"\nTurn{i}: {self._fmt(turn)}°")

        lock_s = "ON" if self.lock_start_var.get() else "OFF"
        lock_e = "ON" if self.lock_end_var.get() else "OFF"
        self.status.config(
            text=f"Segments: {len(self.segments)} | Vertices: {len(world_verts)} | LockStart={lock_s} | LockEnd={lock_e} | zoom={self.view_scale:.4f} px/mm | labelFont={self._get_label_font_size()}pt"
        )

    def _label(self, x, y, text):
        pad = 3
        t = self.canvas.create_text(
            x,
            y,
            text=text,
            anchor="nw",
            font=("Segoe UI", self._get_label_font_size()),
            fill=self.D_TEXT,
        )
        bbox = self.canvas.bbox(t)
        if bbox:
            x1, y1, x2, y2 = bbox
            rect = self.canvas.create_rectangle(
                x1 - pad, y1 - pad, x2 + pad, y2 + pad, fill=self.D_LABEL_BG, outline=self.D_LABEL_OUT
            )
            self.canvas.tag_lower(rect, t)


if __name__ == "__main__":
    RV().mainloop()
