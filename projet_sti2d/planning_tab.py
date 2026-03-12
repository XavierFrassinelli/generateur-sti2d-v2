"""Planning tab (annual Gantt view and sequence management)."""

import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont

from constants import (
    BLEU, ORANGE, VERT, GRIS, GRIS2, BLANC, TEXTE,
    NIVEAU_GROUPE,
    PERIODES,
    NB_SEMAINES, ROW_H, HEADER_H, LEFT_W, WEEK_W, CANVAS_W,
)
from planning_common import JOURS_SEMAINE, _darken_hex, _parse_hhmm, _truncate_text_px
from planning_dialogs import SequenceDialog, WeekDetailDialog
class PlanningTab(tk.Frame):

    TYPE_COLORS = {
        "Cours": BLEU,
        "TP": VERT,
        "TD": ORANGE,
        "Évaluation": "#C62828",
        "Projet": "#6A1B9A",
    }

    def __init__(self, parent, themes, ref_comp, ref_conn, data_dir,
                 generer_callback=None, periodes=None, classes_options=None,
                 profile_name=None):
        super().__init__(parent, bg=GRIS)
        self.themes           = themes
        self.ref_comp         = ref_comp
        self.ref_conn         = ref_conn
        self.data_dir         = Path(data_dir)
        self.generer_callback = generer_callback
        self.periodes         = [tuple(p) for p in periodes] if periodes else list(PERIODES)
        self.profile_name     = str(profile_name or "STI2D").strip() or "STI2D"
        opts = [str(c).strip() for c in (classes_options or []) if str(c).strip()]
        self.classes_options  = opts or ["1ère IT", "1ère I2D", "1ère IT/I2D", "Terminale 2I2D"]
        self.filter_options   = ["Toutes"] + self._build_filter_options()
        self.sequences        = []
        self._tooltip_win     = None
        self._tooltip_key     = None
        self._hover_job       = None
        self._hover_pending_key = None
        self._font_cache      = {}
        self.var_filter_classe = tk.StringVar(value="Toutes")
        self._load()
        self._build()
        self._draw()

    # ── Persistance ───────────────────────────────────────────────────────────
    def _path(self):
        return self.data_dir / "planning.json"

    def _load(self):
        p = self._path()
        if p.exists():
            self.sequences = json.loads(p.read_text(encoding="utf-8"))
        for i, s in enumerate(self.sequences):
            if not s.get("id"):
                s["id"] = i + 1
            if "semaines" not in s:
                s["semaines"] = {}

    def _save(self):
        self._path().write_text(
            json.dumps(self.sequences, ensure_ascii=False, indent=2),
            encoding="utf-8")

    # ── Construction UI ───────────────────────────────────────────────────────
    def _build(self):
        toolbar = tk.Frame(self, bg=BLEU, height=44)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        tk.Label(toolbar, text=f"📅  Planning annuel {self.profile_name}",
                 bg=BLEU, fg=BLANC, font=("Segoe UI", 12, "bold")
                 ).pack(side="left", padx=15, pady=8)

        # Filtre d'affichage par classe (n'affecte pas les données enregistrées).
        tk.Label(toolbar, text="Classe :", bg=BLEU, fg=BLANC,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(10, 4))
        self.cb_filter_classe = ttk.Combobox(
            toolbar,
            textvariable=self.var_filter_classe,
            values=self.filter_options,
            state="readonly",
            width=16,
            font=("Segoe UI", 9),
        )
        self.cb_filter_classe.pack(side="left", padx=(0, 6), pady=6)
        self.cb_filter_classe.bind("<<ComboboxSelected>>", self._on_filter_change)

        tk.Button(toolbar, text="➕  Ajouter une séquence",
                  command=self._ajouter,
                  bg=VERT, fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10
                  ).pack(side="right", padx=10, pady=6)
        tk.Button(toolbar, text="🗑  Supprimer",
                  command=self._supprimer_selection,
                  bg="#C62828", fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10
                  ).pack(side="right", padx=4, pady=6)
        tk.Button(toolbar, text="✏️  Modifier",
                  command=self._modifier_selection,
                  bg=ORANGE, fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10
                  ).pack(side="right", padx=4, pady=6)

        # Légende + aide
        leg = tk.Frame(self, bg=GRIS2, pady=4)
        leg.pack(fill="x")
        tk.Label(leg, text="Périodes : ", bg=GRIS2,
                 font=("Segoe UI", 9, "bold"), fg=TEXTE).pack(side="left", padx=10)
        periode_colors = ["#DDEEFF", "#FFE8D0", "#E8F5E9", "#F3E5F5", "#FFF9C4"]
        for i, (label, s, e) in enumerate(self.periodes):
            frm = tk.Frame(leg, bg=periode_colors[i], padx=6, pady=2,
                           highlightbackground="#BBBBBB", highlightthickness=1)
            frm.pack(side="left", padx=4)
            tk.Label(frm, text=f"{label}  S{s:02d}–S{e:02d}",
                     bg=periode_colors[i], font=("Segoe UI", 8), fg=TEXTE).pack()
        tk.Label(leg, text="  ● = séances planifiées  |  Double-clic → détail semaine",
                 bg=GRIS2, font=("Segoe UI", 8, "italic"), fg="#666"
                 ).pack(side="right", padx=10)

        # Canvas scrollable
        frm_canvas = tk.Frame(self, bg=GRIS)
        frm_canvas.pack(fill="both", expand=True, padx=8, pady=8)
        sb_v = ttk.Scrollbar(frm_canvas, orient="vertical")
        sb_v.pack(side="right", fill="y")
        sb_h = ttk.Scrollbar(frm_canvas, orient="horizontal")
        sb_h.pack(side="bottom", fill="x")

        self.canvas = tk.Canvas(frm_canvas, bg=BLANC,
                                xscrollcommand=sb_h.set,
                                yscrollcommand=sb_v.set,
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        sb_v.config(command=self.canvas.yview)
        sb_h.config(command=self.canvas.xview)

        self.canvas.bind("<MouseWheel>",
                         lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        self.canvas.bind("<Button-1>",        self._on_click)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<Motion>",          self._on_motion)
        self.canvas.bind("<Leave>",           lambda e: self._hide_tooltip())

        self.selected_id = None

    def _on_filter_change(self, event=None):
        visible_ids = {s.get("id") for s in self._visible_sequences()}
        if self.selected_id is not None and self.selected_id not in visible_ids:
            self.selected_id = None
        self._draw()

    def _filter_tag(self, classe):
        raw = str(classe or "").strip()
        if not raw:
            return ""
        return str(NIVEAU_GROUPE.get(raw, raw)).strip()

    def _build_filter_options(self):
        options = []
        seen = set()

        for cls in self.classes_options:
            tag = self._filter_tag(cls)
            if not tag:
                continue
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            options.append(tag)

        return options

    def _visible_sequences(self):
        selected = str(self.var_filter_classe.get() or "Toutes").strip()
        if not selected or selected == "Toutes":
            return list(self.sequences)
        return [
            s for s in self.sequences
            if self._filter_tag(s.get("classe", "")) == selected
        ]

    # ── Dessin Gantt ──────────────────────────────────────────────────────────
    def _draw(self):
        c = self.canvas
        c.delete("all")
        nb_rows = max(len(self._visible_sequences()) + 2, 10)
        total_h = HEADER_H + nb_rows * ROW_H + 20
        total_w = CANVAS_W + 20
        c.configure(scrollregion=(0, 0, total_w, total_h))
        self._draw_header(c)
        self._draw_grid(c, nb_rows)
        self._draw_sequences(c)

    def _draw_header(self, c):
        c.create_rectangle(0, 0, LEFT_W + NB_SEMAINES * WEEK_W, HEADER_H,
                           fill=BLEU, outline="")
        c.create_text(LEFT_W // 2, HEADER_H // 2, text="Séquence", fill=BLANC,
                      font=("Segoe UI", 10, "bold"), anchor="center")

        periode_colors_dark = ["#1565C0", "#BF360C", "#1B5E20", "#4A148C", "#F57F17"]
        for i, (label, s_start, s_end) in enumerate(self.periodes):
            x1 = LEFT_W + (s_start - 1) * WEEK_W
            x2 = LEFT_W + s_end * WEEK_W
            c.create_rectangle(x1, 0, x2, 22, fill=periode_colors_dark[i], outline=BLANC)
            c.create_text((x1 + x2) // 2, 11, text=label, fill=BLANC,
                          font=("Segoe UI", 9, "bold"), anchor="center")

        for s in range(1, NB_SEMAINES + 1):
            x  = LEFT_W + (s - 1) * WEEK_W
            xc = x + WEEK_W // 2
            p_color = self._periode_bg(s)
            c.create_rectangle(x, 22, x + WEEK_W, HEADER_H,
                               fill=p_color, outline="#FFFFFF")
            c.create_text(xc, 22 + (HEADER_H - 22) // 2,
                          text=f"S{s:02d}", fill=BLANC,
                          font=("Segoe UI", 7), anchor="center")

    def _periode_bg(self, semaine):
        colors = ["#1976D2", "#E64A19", "#388E3C", "#7B1FA2", "#F9A825"]
        for i, (_, s, e) in enumerate(self.periodes):
            if s <= semaine <= e:
                return colors[i]
        return BLEU

    def _periode_bg_light(self, semaine):
        colors = ["#E3F2FD", "#FBE9E7", "#E8F5E9", "#F3E5F5", "#FFFDE7"]
        for i, (_, s, e) in enumerate(self.periodes):
            if s <= semaine <= e:
                return colors[i]
        return "#FAFAFA"

    def _draw_grid(self, c, nb_rows):
        total_h = HEADER_H + nb_rows * ROW_H
        for _, s_start, s_end in self.periodes:
            x1 = LEFT_W + (s_start - 1) * WEEK_W
            x2 = LEFT_W + s_end * WEEK_W
            color = self._periode_bg_light(s_start)
            c.create_rectangle(x1, HEADER_H, x2, total_h, fill=color, outline="")

        for s in range(NB_SEMAINES + 1):
            x  = LEFT_W + s * WEEK_W
            lw = 2 if any(s == e for _, _, e in self.periodes) else 1
            col = "#AAAAAA" if lw == 2 else "#DDDDDD"
            c.create_line(x, HEADER_H, x, total_h, fill=col, width=lw)

        for row in range(nb_rows):
            y1 = HEADER_H + row * ROW_H
            y2 = y1 + ROW_H
            bg = BLANC if row % 2 == 0 else "#F8F9FF"
            c.create_rectangle(0, y1, LEFT_W, y2, fill=bg, outline="#E0E0E0")
            c.create_line(0, y2, LEFT_W + NB_SEMAINES * WEEK_W, y2,
                         fill="#E8E8E8", width=1)

        c.create_line(LEFT_W, HEADER_H, LEFT_W, total_h, fill="#AAAAAA", width=2)

    def _draw_sequences(self, c):
        self._seq_rects = {}

        for row, seq in enumerate(self._visible_sequences()):
            y1 = HEADER_H + row * ROW_H + 6
            y2 = y1 + ROW_H - 12

            self._draw_left_info(c, seq, row)

            s1 = seq.get("s_debut", 1)
            s2 = seq.get("s_fin",   s1)
            x1 = LEFT_W + (s1 - 1) * WEEK_W + 2
            x2 = LEFT_W + s2 * WEEK_W - 2

            color    = seq.get("couleur", BLEU)
            selected = (seq.get("id") == self.selected_id)
            outline  = "#FFD700" if selected else self._darken(color)
            lw       = 3 if selected else 1

            c.create_rectangle(x1 + 2, y1 + 2, x2 + 2, y2 + 2,
                               fill="#CCCCCC", outline="", tags=("shadow",))
            rid = c.create_rectangle(x1, y1, x2, y2,
                                     fill=color, outline=outline,
                                     width=lw, tags=("seq", f"seq_{seq['id']}"))

            # Effet de luminosite hebdo actif a la selection.
            if selected and s2 >= s1:
                for wn in range(s1, s2 + 1):
                    if (wn - s1) % 2 != 0:
                        continue
                    bx1 = LEFT_W + (wn - 1) * WEEK_W + 1
                    bx2 = LEFT_W + wn * WEEK_W - 1
                    bx1 = max(bx1, x1 + 1)
                    bx2 = min(bx2, x2 - 1)
                    if bx2 <= bx1:
                        continue
                    c.create_rectangle(
                        bx1,
                        y1 + 1,
                        bx2,
                        y2 - 1,
                        fill=self._blend_hex(color, "#FFFFFF", 0.18),
                        outline="",
                        tags=(f"seq_{seq['id']}",),
                    )

            nb_sem = s2 - s1 + 1
            bar_w  = x2 - x1
            label  = seq.get("titre", "")
            if nb_sem >= 3 and bar_w > 60:
                label_fit = self._truncate_text(label, bar_w - 14, ("Segoe UI", 8, "bold"))
                c.create_text(x1 + 8, (y1 + y2) // 2, text=label_fit,
                             fill=BLANC, font=("Segoe UI", 8, "bold"),
                             anchor="w", tags=(f"seq_{seq['id']}",))
            elif nb_sem >= 2 and bar_w > 30:
                short = self._truncate_text(label, bar_w - 8, ("Segoe UI", 7))
                c.create_text((x1 + x2) // 2, (y1 + y2) // 2, text=short,
                             fill=BLANC, font=("Segoe UI", 7),
                             anchor="center", tags=(f"seq_{seq['id']}",))

            heures = seq.get("heures", "")
            if heures and bar_w > 35:
                c.create_text(x2 - 4, y1 + 4, text=f"{heures}h",
                             fill=BLANC, font=("Segoe UI", 7, "bold"),
                             anchor="ne", tags=(f"seq_{seq['id']}",))

            if bar_w > 90:
                self._draw_type_badges(c, seq, x1, y1, x2, y2)

            # Indicateurs de séances (points blancs en bas de la barre)
            semaines = seq.get("semaines", {})
            for week_str, week_data in semaines.items():
                if not week_data.get("seances"):
                    continue
                try:
                    wn = int(week_str)
                except ValueError:
                    continue
                if not (s1 <= wn <= s2):
                    continue
                dot_x = LEFT_W + (wn - 1) * WEEK_W + WEEK_W // 2
                dot_y = y2 - 5 if bar_w <= 90 else y2 - 4
                c.create_oval(dot_x - 3, dot_y - 3, dot_x + 3, dot_y + 3,
                             fill=BLANC, outline="", tags=(f"seq_{seq['id']}",))

            self._seq_rects[seq.get("id")] = (rid, row, x1, y1, x2, y2)

    def _draw_left_info(self, c, seq, row):
        y_center = HEADER_H + row * ROW_H + ROW_H // 2
        y1       = HEADER_H + row * ROW_H
        color    = seq.get("couleur", BLEU)

        c.create_rectangle(0, y1 + 4, 6, y1 + ROW_H - 4, fill=color, outline="")

        titre       = seq.get("titre", "—")
        short_titre = self._truncate_text(titre, LEFT_W - 30, ("Segoe UI", 9, "bold"))
        c.create_text(14, y_center - 10, text=short_titre,
                     fill=TEXTE, font=("Segoe UI", 9, "bold"), anchor="w")

        classe = seq.get("classe", "")
        s1, s2 = seq.get("s_debut", 1), seq.get("s_fin", 1)
        info_parts = [part for part in [classe, f"S{s1:02d}→S{s2:02d}"] if part]
        info   = "  ·  ".join(info_parts)
        info   = self._truncate_text(info, LEFT_W - 30, ("Segoe UI", 8))
        c.create_text(14, y_center + 8, text=info,
                     fill="#666666", font=("Segoe UI", 8), anchor="w")

    def _sequence_types_summary(self, seq):
        types = self._sequence_types(seq)
        if types:
            return ", ".join(types[:3]) + ("..." if len(types) > 3 else "")
        return str(seq.get("type", "")).strip()

    def _sequence_types(self, seq):
        types = []
        for week_data in (seq.get("semaines", {}) or {}).values():
            for seance in week_data.get("seances", []) or []:
                type_name = str(seance.get("type", "")).strip()
                if type_name and type_name not in types:
                    types.append(type_name)
        fallback = str(seq.get("type", "")).strip()
        if fallback and fallback not in types:
            types.append(fallback)
        return types

    def _draw_type_badges(self, c, seq, x1, y1, x2, y2):
        types = self._sequence_types(seq)
        if not types:
            return

        font_spec = ("Segoe UI", 6, "bold")
        f = self._font(font_spec)
        cursor_x = x1 + 6
        badge_y1 = y2 - 13
        badge_y2 = y2 - 2
        max_x = x2 - 6

        for type_name in types[:3]:
            short = type_name
            if type_name == "Évaluation":
                short = "Eval"
            text_w = f.measure(short)
            badge_w = text_w + 8
            if cursor_x + badge_w > max_x:
                break

            fill = self.TYPE_COLORS.get(type_name, self._darken(seq.get("couleur", BLEU)))
            c.create_rectangle(
                cursor_x,
                badge_y1,
                cursor_x + badge_w,
                badge_y2,
                fill=fill,
                outline="",
                tags=(f"seq_{seq['id']}",),
            )
            c.create_text(
                cursor_x + badge_w / 2,
                (badge_y1 + badge_y2) / 2,
                text=short,
                fill=BLANC,
                font=font_spec,
                anchor="center",
                tags=(f"seq_{seq['id']}",),
            )
            cursor_x += badge_w + 4

    def _font(self, font_spec):
        if font_spec not in self._font_cache:
            self._font_cache[font_spec] = tkfont.Font(font=font_spec)
        return self._font_cache[font_spec]

    def _truncate_text(self, text, max_px, font_spec):
        if not text:
            return ""
        f = self._font(font_spec)
        if f.measure(text) <= max_px:
            return text
        ell = "…"
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if f.measure(text[:mid].rstrip() + ell) <= max_px:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo].rstrip() + ell

    def _darken(self, hex_color):
        try:
            r = max(0, int(hex_color[1:3], 16) - 40)
            g = max(0, int(hex_color[3:5], 16) - 40)
            b = max(0, int(hex_color[5:7], 16) - 40)
            return f"#{r:02X}{g:02X}{b:02X}"
        except Exception:
            return "#000000"

    def _blend_hex(self, c1, c2, ratio):
        """Blend c1 toward c2. ratio in [0,1], 0=c1, 1=c2."""
        try:
            r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
            r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
            t = max(0.0, min(1.0, float(ratio)))
            r = int(r1 + (r2 - r1) * t)
            g = int(g1 + (g2 - g1) * t)
            b = int(b1 + (b2 - b1) * t)
            return f"#{r:02X}{g:02X}{b:02X}"
        except Exception:
            return c2

    # ── Interactions ──────────────────────────────────────────────────────────
    def _seq_at(self, x, y):
        """Retourne l'id de la séquence cliquée, ou None."""
        for seq_id, (rid, row, x1, y1, x2, y2) in self._seq_rects.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                return seq_id
        return None

    def _week_at(self, x):
        """Retourne le numéro de semaine (1-36) selon la position x, ou None."""
        if x < LEFT_W:
            return None
        week = int((x - LEFT_W) / WEEK_W) + 1
        return week if 1 <= week <= NB_SEMAINES else None

    def _find_pb(self, seq):
        """Retourne l'objet problématique correspondant à une séquence."""
        for t in self.themes:
            if t["id"] != seq.get("theme_id"):
                continue
            for pb in t.get("problematiques", []):
                if pb["titre"] == seq.get("pb_titre"):
                    return pb
        return None

    def _canvas_coords(self, event):
        return self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

    def _on_click(self, event):
        cx, cy = self._canvas_coords(event)
        self._hide_tooltip()
        self.selected_id = self._seq_at(cx, cy)
        self._draw()

    def _on_double_click(self, event):
        cx, cy = self._canvas_coords(event)
        self._hide_tooltip()
        sid = self._seq_at(cx, cy)
        if not sid:
            return
        week = self._week_at(cx)
        seq  = next((s for s in self.sequences if s.get("id") == sid), None)
        if seq and week and seq.get("s_debut", 1) <= week <= seq.get("s_fin", 1):
            self.selected_id = sid
            self._open_week_detail(seq, week)
        else:
            # Double-clic hors d'une semaine valide → ouvre l'éditeur de séquence
            self.selected_id = sid
            self._modifier_selection()

    def _open_week_detail(self, seq, week):
        seq_copy           = dict(seq)
        theme_obj = next((t for t in self.themes if t.get("id") == seq.get("theme_id")), None)
        seq_copy["_pb_obj"] = self._find_pb(seq)
        seq_copy["_theme_obj"] = theme_obj
        WeekDetailDialog(
            self, seq_copy, week,
            self.ref_comp, self.ref_conn, self.sequences,
            themes=self.themes,
            on_save=self._on_week_saved,
            generer_callback=self.generer_callback,
        )

    def _on_week_saved(self, seq_id, week, seances):
        for seq in self.sequences:
            if seq.get("id") == seq_id:
                if "semaines" not in seq:
                    seq["semaines"] = {}
                if seances:
                    seq["semaines"][str(week)] = {"seances": seances}
                else:
                    seq["semaines"].pop(str(week), None)
                break
        self._save()
        self._draw()

    def _on_motion(self, event):
        cx, cy = self._canvas_coords(event)
        sid = self._seq_at(cx, cy)
        if not sid:
            self._hide_tooltip()
            return

        seq = next((s for s in self.sequences if s.get("id") == sid), None)
        if not seq:
            self._hide_tooltip()
            return

        week = self._week_at(cx)
        if week and seq.get("s_debut", 1) <= week <= seq.get("s_fin", 1):
            week_data = (seq.get("semaines", {}) or {}).get(str(week), {})
            seances = list(week_data.get("seances", []) or [])
            if seances:
                key = ("week", sid, week)
                if key != self._tooltip_key and key != self._hover_pending_key:
                    self._schedule_tooltip(
                        key,
                        lambda xr=event.x_root, yr=event.y_root, seq=seq, week=week, seances=seances:
                            self._show_week_preview_tooltip(xr, yr, seq, week, seances),
                    )
                return

        key = ("seq", sid)
        if key != self._tooltip_key and key != self._hover_pending_key:
            self._schedule_tooltip(
                key,
                lambda xr=event.x_root, yr=event.y_root, seq=seq: self._show_tooltip(xr, yr, seq),
            )

    def _schedule_tooltip(self, key, callback, delay_ms=260):
        if self._hover_job is not None:
            try:
                self.after_cancel(self._hover_job)
            except Exception:
                pass
        self._hover_pending_key = key

        def _run():
            self._hover_job = None
            self._hover_pending_key = None
            callback()

        self._hover_job = self.after(delay_ms, _run)

    # ── Tooltip ───────────────────────────────────────────────────────────────
    def _show_tooltip(self, x_root, y_root, seq):
        self._hide_tooltip()
        win = tk.Toplevel(self)
        win.wm_overrideredirect(True)
        try:
            win.wm_attributes("-disabled", True)  # transparence souris (Windows)
        except tk.TclError:
            pass
        win.wm_geometry(f"+{x_root + 16}+{y_root + 10}")
        win.configure(bg="#FFFDE7")

        nb_seances = sum(
            len(v.get("seances", [])) for v in seq.get("semaines", {}).values()
        )
        lines = [
            ("titre", seq.get("titre", "—")),
            ("info",  f"Thème : {seq.get('theme_titre', seq.get('theme_id', ''))}"),
            ("info",  f"Problématique : {seq.get('pb_titre', '')}"),
            ("info",  f"Classe : {seq.get('classe', '')}  ·  Types : {self._sequence_types_summary(seq)}"),
            ("info",  f"Semaines : S{seq.get('s_debut', 1):02d} → S{seq.get('s_fin', 1):02d}"),
            ("info",  f"Volume : {seq.get('heures', '')} h"),
            ("comp",  f"Compétences : {seq.get('competences_str', '')}"),
            ("info",  f"Séances planifiées : {nb_seances}" if nb_seances else ""),
        ]
        for tag, txt in lines:
            if not txt.strip() or txt.strip().endswith(":"):
                continue
            bold = (tag == "titre")
            fg   = BLEU if bold else TEXTE
            tk.Label(win, text=txt, bg="#FFFDE7", fg=fg,
                     font=("Segoe UI", 9, "bold" if bold else "normal"),
                     anchor="w", padx=10, pady=2).pack(fill="x")

        self._tooltip_win = win
        self._tooltip_key = ("seq", seq.get("id"))
        self.after(4000, self._hide_tooltip)

    def _show_week_preview_tooltip(self, x_root, y_root, seq, week, seances):
        self._hide_tooltip()
        win = tk.Toplevel(self)
        win.wm_overrideredirect(True)
        try:
            win.wm_attributes("-disabled", True)  # transparence souris (Windows)
        except tk.TclError:
            pass
        win.wm_geometry(f"+{x_root + 16}+{y_root + 10}")
        win.configure(bg="#FFFDE7")

        header = tk.Frame(win, bg="#FFFDE7")
        header.pack(fill="x")
        header_label = tk.Label(
            header,
            text=f"Semaine {week:02d}  ·  {seq.get('titre', '—')}",
            bg="#FFFDE7",
            fg=BLEU,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            padx=8,
            pady=6,
        )
        header_label.pack(fill="x")

        canvas = tk.Canvas(
            win,
            width=360,
            height=190,
            bg="#FAFBFF",
            highlightbackground="#DADCE0",
            highlightthickness=1,
            bd=0,
        )
        canvas.pack(padx=8, pady=(0, 8))
        self._render_week_preview_canvas(canvas, seances)

        # Pas de handler <Button-1> : la fenêtre est désactivée (-disabled),
        # les clics traversent directement vers le canvas sous-jacent.

        self._tooltip_win = win
        self._tooltip_key = ("week", seq.get("id"), week)
        self.after(4000, self._hide_tooltip)

    def _open_week_detail_from_preview(self, seq, week):
        self.selected_id = seq.get("id")
        self._hide_tooltip()
        self._open_week_detail(seq, week)

    def _render_week_preview_canvas(self, c, seances):
        c.delete("all")
        c.update_idletasks()

        w = max(int(c.winfo_width()), 360)
        h = max(int(c.winfo_height()), 190)
        left = 42
        top = 22
        right = w - 8
        bottom = h - 8
        days = JOURS_SEMAINE[:5]
        start_hour = 8
        end_hour = 18

        c.create_rectangle(left, top, right, bottom, fill="#FFFFFF", outline="#DADCE0")

        day_w = (right - left) / len(days)
        total_min = (end_hour - start_hour) * 60
        min_px = (bottom - top) / total_min if total_min else 1

        for i, day in enumerate(days):
            x = left + i * day_w
            c.create_line(x, top, x, bottom, fill="#E6EAF2")
            c.create_text(x + day_w / 2, 10, text=day, fill=TEXTE,
                          font=("Segoe UI", 7, "bold"))
        c.create_line(right, top, right, bottom, fill="#E6EAF2")

        for hour in range(start_hour, end_hour + 1):
            y = top + (hour - start_hour) * 60 * min_px
            line_color = "#D5DCE8" if hour in (8, 10, 12, 14, 16, 18) else "#EEF1F7"
            c.create_line(left, y, right, y, fill=line_color)
            c.create_text(left - 4, y, text=f"{hour:02d}", anchor="e",
                          fill="#6A778B", font=("Consolas", 7))

        placed = 0
        for seance in seances:
            day = str(seance.get("jour", "")).strip()
            if day not in days:
                continue
            start_m = _parse_hhmm(seance.get("heure_debut"))
            end_m = _parse_hhmm(seance.get("heure_fin"))
            if start_m is None or end_m is None or end_m <= start_m:
                continue

            start_ref = start_hour * 60
            end_ref = end_hour * 60
            seg_start = max(start_m, start_ref)
            seg_end = min(end_m, end_ref)
            if seg_end <= seg_start:
                continue

            day_idx = days.index(day)
            x1 = left + day_idx * day_w + 3
            x2 = left + (day_idx + 1) * day_w - 3
            y1 = top + (seg_start - start_ref) * min_px + 1
            y2 = top + (seg_end - start_ref) * min_px - 1

            color = self.TYPE_COLORS.get(seance.get("type", "Cours"), BLEU)
            c.create_rectangle(x1, y1, x2, y2, fill=color, outline=_darken_hex(color), width=1)
            txt = _truncate_text_px(str(seance.get("titre", "Séance")), int(day_w) - 10, ("Segoe UI", 7, "bold"))
            c.create_text(x1 + 4, y1 + 3, text=txt, anchor="nw", fill=BLANC,
                          font=("Segoe UI", 7, "bold"))
            placed += 1

        if placed == 0:
            c.create_text(
                (left + right) / 2,
                (top + bottom) / 2,
                text="Aucun créneau réel saisi",
                fill="#8A94A6",
                font=("Segoe UI", 8, "italic"),
            )

    def _hide_tooltip(self):
        if self._hover_job is not None:
            try:
                self.after_cancel(self._hover_job)
            except Exception:
                pass
            self._hover_job = None
        self._hover_pending_key = None
        if self._tooltip_win:
            try:
                self._tooltip_win.destroy()
            except Exception:
                pass
            self._tooltip_win = None
        self._tooltip_key = None

    # ── CRUD séquences ────────────────────────────────────────────────────────
    def _next_id(self):
        ids = [s.get("id", 0) for s in self.sequences]
        return max(ids, default=0) + 1

    def _ajouter(self):
        SequenceDialog(self, self.themes, self.ref_comp, self.ref_conn,
                       callback=self._on_ajout,
                       classes_options=self.classes_options)

    def _on_ajout(self, seq):
        seq["id"] = self._next_id()
        self.sequences.append(seq)
        self._save()
        self._draw()

    def _modifier_selection(self):
        if not self.selected_id:
            messagebox.showinfo("Sélection", "Cliquez d'abord sur une séquence.")
            return
        seq = next((s for s in self.sequences if s.get("id") == self.selected_id), None)
        if seq:
            SequenceDialog(self, self.themes, self.ref_comp, self.ref_conn,
                           sequence=dict(seq), callback=self._on_modif,
                           classes_options=self.classes_options)

    def _on_modif(self, seq):
        for i, s in enumerate(self.sequences):
            if s.get("id") == seq.get("id"):
                self.sequences[i] = seq
                break
        self._save()
        self._draw()

    def _supprimer_selection(self):
        if not self.selected_id:
            messagebox.showinfo("Sélection", "Cliquez d'abord sur une séquence.")
            return
        seq = next((s for s in self.sequences if s.get("id") == self.selected_id), None)
        if seq and messagebox.askyesno("Supprimer",
                                        f"Supprimer « {seq.get('titre', '?')} » ?\n"
                                        f"Les séances associées seront aussi supprimées."):
            self.sequences = [s for s in self.sequences
                              if s.get("id") != self.selected_id]
            self.selected_id = None
            self._save()
            self._draw()
