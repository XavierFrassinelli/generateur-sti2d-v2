"""Dialog for weekly details and real timetable placement."""

import tkinter as tk
from tkinter import ttk, messagebox

from constants import BLEU, ORANGE, VERT, GRIS, GRIS2, BLANC, TEXTE, bind_mousewheel, show_quick_help
from planning_common import JOURS_SEMAINE, _darken_hex, _parse_hhmm, _seance_sort_key, _truncate_text_px
from planning_seance_dialog import SeanceDialog
class WeekDetailDialog(tk.Toplevel):
    """Fenêtre de détail d'une semaine : liste et gestion des séances."""

    TYPE_COLORS = {
        "Cours": BLEU, "TP": VERT, "TD": ORANGE,
        "Évaluation": "#C62828", "Projet": "#6A1B9A",
    }

    def _sequence_types_summary(self):
        types = []
        for seance in self.seances:
            type_name = str(seance.get("type", "")).strip()
            if type_name and type_name not in types:
                types.append(type_name)
        if types:
            return ", ".join(types[:3]) + ("..." if len(types) > 3 else "")
        return str(self.seq.get("type", "")).strip()

    def __init__(self, parent, seq, week, ref_comp, ref_conn, sequences,
                 themes=None, on_save=None, generer_callback=None):
        super().__init__(parent)
        self.title(f"Semaine {week:02d}  —  {seq.get('titre', '')}")
        base_w, base_h = 760, 660
        max_w = max(660, self.winfo_screenwidth() - 120)
        max_h = max(520, self.winfo_screenheight() - 120)
        self.geometry(f"{min(base_w, max_w)}x{min(base_h, max_h)}")
        self.minsize(640, 520)
        self.configure(bg=BLANC)
        self.grab_set()
        self.resizable(True, True)

        self.seq              = seq
        self.week             = week
        self.ref_comp         = ref_comp
        self.ref_conn         = ref_conn
        self.sequences        = sequences
        self.themes           = themes if isinstance(themes, list) else []
        self.on_save          = on_save
        self.generer_callback = generer_callback
        self.pb               = seq.get("_pb_obj")
        self.theme            = seq.get("_theme_obj") or self._find_theme(seq.get("theme_id"))
        if not self.theme and seq.get("theme_titre"):
            self.theme = self._find_theme_by_title(seq.get("theme_titre"))
        self.seances          = list(
            seq.get("semaines", {}).get(str(week), {}).get("seances", [])
        )
        if not self.pb and self.theme:
            self.pb = self._find_pb_in_theme(self.theme, seq.get("pb_titre"))
        self._build()
        self.bind("<F1>", lambda e: show_quick_help(
            self,
            "Aide — Détail semaine",
            [
                "Cette fenêtre regroupe les séances planifiées sur la semaine.",
                "Utilisez « Ajouter une séance » pour compléter la semaine.",
                "Chaque carte permet modifier, générer ou supprimer la séance.",
            ],
        ))

    def _build(self):
        color = self.seq.get("couleur", BLEU)
        hdr = tk.Frame(self, bg=color)
        hdr.pack(fill="x")
        tk.Button(hdr, text="?",
                  command=lambda: show_quick_help(
                      self,
                      "Aide — Détail semaine",
                      [
                          "Cette fenêtre regroupe les séances planifiées sur la semaine.",
                          "Utilisez « Ajouter une séance » pour compléter la semaine.",
                          "Chaque carte permet modifier, générer ou supprimer la séance.",
                      ],
                  ),
                  bg="#2F5E9A", fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), width=3).pack(side="right", padx=(0, 8), pady=6)
        tk.Label(hdr, text=f"Semaine {self.week:02d}  ·  {self.seq.get('titre', '')}",
                 bg=color, fg=BLANC, font=("Segoe UI", 13, "bold"), pady=7
                 ).pack(side="left", padx=14)
        tk.Label(hdr, text=f"{self.seq.get('classe', '')}  ·  {self._sequence_types_summary()}",
                 bg=color, fg=BLANC, font=("Segoe UI", 10), pady=7
                 ).pack(side="right", padx=14)

        if self.seq.get("pb_titre"):
            tk.Label(self, text=f"Problématique : {self.seq['pb_titre']}",
                     bg=GRIS2, fg=TEXTE, font=("Segoe UI", 9, "italic"),
                     anchor="w", pady=4, padx=14).pack(fill="x")

        # Mini planning hebdomadaire (créneaux réels)
        frm_sched = tk.Frame(self, bg=BLANC, padx=12, pady=8)
        frm_sched.pack(fill="x", pady=(0, 0))
        tk.Label(
            frm_sched,
            text="Planning hebdomadaire (créneaux réels)",
            bg=BLANC,
            fg=BLEU,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        tk.Label(
            frm_sched,
            text="Renseignez jour + heures dans chaque séance pour les positionner.",
            bg=BLANC,
            fg="#777",
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(0, 4))
        legend = tk.Frame(frm_sched, bg=BLANC)
        legend.pack(anchor="w", pady=(0, 6))
        tk.Label(
            legend,
            text="Types :",
            bg=BLANC,
            fg=TEXTE,
            font=("Segoe UI", 8, "bold"),
        ).pack(side="left", padx=(0, 6))
        for type_name in ["Cours", "TP", "TD", "Évaluation", "Projet"]:
            short = "Eval" if type_name == "Évaluation" else type_name
            tk.Label(
                legend,
                text=f" {short} ",
                bg=self.TYPE_COLORS.get(type_name, BLEU),
                fg=BLANC,
                font=("Segoe UI", 7, "bold"),
                padx=4,
                pady=1,
            ).pack(side="left", padx=2)
        self.schedule_canvas = tk.Canvas(
            frm_sched,
            bg="#FAFBFF",
            height=205,
            highlightbackground="#DADCE0",
            highlightthickness=1,
            bd=0,
        )
        self.schedule_canvas.pack(fill="x")
        self.schedule_canvas.bind("<Configure>", lambda e: self._render_week_schedule())
        self.schedule_canvas.bind("<Button-1>", self._on_schedule_click)

        # Liste compacte des séances — toujours visible
        self.frm_list = tk.Frame(self, bg=GRIS2, padx=12, pady=6)
        self.frm_list.pack(fill="x")

        # Détail de la séance sélectionnée — vide par défaut
        self.frm_detail = tk.Frame(self, bg=BLANC, padx=12, pady=4)
        self.frm_detail.pack(fill="x")
        self._selected_seance_idx = None

        self._render_seance_list()
        self._show_seance_detail(None)
        self._render_week_schedule()

        # Pied de page
        frm_foot = tk.Frame(self, bg=GRIS, pady=8)
        frm_foot.pack(side="bottom", fill="x", padx=12)
        tk.Button(frm_foot, text="➕  Ajouter une séance",
                  command=self._ajouter,
                  bg=VERT, fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10
                  ).pack(side="left")
        tk.Button(frm_foot, text="Fermer", command=self.destroy,
                  bg="#DDD", fg=TEXTE, relief="flat",
                  font=("Segoe UI", 10)).pack(side="right")

    def _render_seances(self):
        """Rétro-compatibilité : délègue vers la liste compacte."""
        self._render_seance_list()

    def _render_card(self, idx, seance, parent=None):
        if parent is None:
            parent = getattr(self, "frm_detail", self)
        tc   = self.TYPE_COLORS.get(seance.get("type", "Cours"), BLEU)
        card = tk.Frame(parent, bg=GRIS2,
                        highlightbackground="#C8D0E0", highlightthickness=1)
        card.pack(fill="x", pady=4, padx=2)

        top = tk.Frame(card, bg=GRIS2)
        top.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(top, text=f"  {seance.get('type', 'Cours')}  ",
                 bg=tc, fg=BLANC, font=("Segoe UI", 9, "bold"),
                 padx=4, pady=2).pack(side="left")
        tk.Label(top, text=f"  {seance.get('titre', '—')}",
                 bg=GRIS2, fg=TEXTE, font=("Segoe UI", 10, "bold"),
                 anchor="w").pack(side="left", fill="x", expand=True)
        slot_txt = ""
        if seance.get("jour") and seance.get("heure_debut") and seance.get("heure_fin"):
            slot_txt = f"{seance.get('jour')} {seance.get('heure_debut')}→{seance.get('heure_fin')}"
        if slot_txt:
            tk.Label(top, text=slot_txt,
                     bg=GRIS2, fg=BLEU, font=("Segoe UI", 9, "bold")).pack(side="right", padx=(8, 0))
        tk.Label(top, text=f"{seance.get('duree', 0)}h",
                 bg=GRIS2, fg="#666", font=("Segoe UI", 10)).pack(side="right")

        pb_titre = str(seance.get("pb_titre", "")).strip()
        if pb_titre:
            tk.Label(card, text=f"Problématique : {pb_titre}",
                     bg=GRIS2, fg="#555", font=("Segoe UI", 8, "italic"),
                     anchor="w").pack(fill="x", padx=10, pady=(0, 1))

        cos = seance.get("competences_visees", [])
        if cos:
            tk.Label(card, text=f"Compétences : {', '.join(cos)}",
                     bg=GRIS2, fg=BLEU, font=("Segoe UI", 9),
                     anchor="w").pack(fill="x", padx=10, pady=(0, 2))

        doc = seance.get("document_genere")
        if doc:
            tk.Label(card, text=f"📄  {doc.get('nom', '')}  ({doc.get('date', '')})",
                     bg=GRIS2, fg=VERT, font=("Segoe UI", 8, "italic"),
                     anchor="w").pack(fill="x", padx=10)

        btn_frm = tk.Frame(card, bg=GRIS2)
        btn_frm.pack(fill="x", padx=10, pady=(2, 8))
        tk.Button(btn_frm, text="✏  Modifier",
                  command=lambda s=seance, i=idx: self._modifier(i, s),
                  bg="#E3EAFF", fg=BLEU, relief="flat",
                  font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
        if self.generer_callback and self.pb:
            tk.Button(btn_frm, text="📄  Générer doc",
                      command=lambda s=seance: self.generer_callback(self.seq, self.week, s),
                      bg=BLEU, fg=BLANC, relief="flat",
                      font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
        tk.Button(btn_frm, text="🗑  Supprimer",
                  command=lambda i=idx: self._supprimer(i),
                  bg="#FFEBEE", fg="#C62828", relief="flat",
                  font=("Segoe UI", 9)).pack(side="left")

    def _ajouter(self):
        if not self.pb and not self.theme:
            messagebox.showwarning("Données manquantes",
                                   "Problématique introuvable pour cette séquence.")
            return
        SeanceDialog(self, self.pb, self.ref_comp, self.ref_conn, self.sequences,
                     self.seq.get("classe", ""), theme=self.theme, sequence=self.seq,
                     callback=self._on_ajout)

    def _on_ajout(self, seance):
        self.seances.append(seance)
        self._commit()

    def _modifier(self, idx, seance):
        if not self.pb and not self.theme:
            return
        SeanceDialog(self, self.pb, self.ref_comp, self.ref_conn, self.sequences,
                     self.seq.get("classe", ""), seance=dict(seance),
                     theme=self.theme, sequence=self.seq,
                     callback=lambda s, i=idx: self._on_modif(i, s))

    def _find_theme(self, theme_id):
        for theme in self.themes:
            if theme.get("id") == theme_id:
                return theme
        return None

    def _find_theme_by_title(self, theme_titre):
        wanted = str(theme_titre or "").strip()
        for theme in self.themes:
            if str(theme.get("titre", "")).strip() == wanted:
                return theme
        return None

    def _find_pb_in_theme(self, theme, pb_titre):
        if not isinstance(theme, dict):
            return None
        wanted = str(pb_titre or "").strip()
        for pb in theme.get("problematiques", []):
            if str(pb.get("titre", "")).strip() == wanted:
                return pb
        pbs = theme.get("problematiques", [])
        return pbs[0] if pbs else None

    def _on_modif(self, idx, seance):
        self.seances[idx] = seance
        self._commit()

    def _supprimer(self, idx):
        titre = self.seances[idx].get("titre", "?")
        if messagebox.askyesno("Supprimer", f"Supprimer la séance « {titre} » ?"):
            del self.seances[idx]
            self._commit()

    def _commit(self):
        if self.on_save:
            self.on_save(self.seq["id"], self.week, self.seances)
        self._selected_seance_idx = None
        self._render_seance_list()
        self._show_seance_detail(None)
        self._render_week_schedule()

    def _on_schedule_click(self, event):
        """Sélectionne la séance cliquée dans le canvas du planning."""
        cx, cy = event.x, event.y
        for orig_idx, seance, x1, y1, x2, y2 in getattr(self, "_placed_seances", []):
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                self._select_seance(orig_idx)
                return
        # Clic dans une zone vide → désélectionner
        self._selected_seance_idx = None
        combo = getattr(self, "cb_seances", None)
        if combo is not None:
            combo.set("Sélectionner une séance…")
        self._show_seance_detail(None)
        self._render_week_schedule()

    def _select_seance(self, idx):
        """Sélectionne la séance d'index idx et affiche sa carte de détail."""
        self._selected_seance_idx = idx
        if 0 <= idx < len(self.seances):
            combo = getattr(self, "cb_seances", None)
            idx_to_pos = getattr(self, "_combo_idx_to_pos", {})
            if combo is not None and idx in idx_to_pos:
                combo.current(idx_to_pos[idx])
            self._show_seance_detail(idx, self.seances[idx])
            self._render_week_schedule()  # redessine pour surligner la sélection

    def _on_combo_select(self, event=None):
        """Réagit à la sélection d'une séance dans la liste déroulante."""
        combo = getattr(self, "cb_seances", None)
        pos_to_idx = getattr(self, "_combo_pos_to_idx", [])
        if combo is None:
            return
        try:
            pos = int(combo.current())
        except Exception:
            return
        if 0 <= pos < len(pos_to_idx):
            self._select_seance(pos_to_idx[pos])

    def _show_seance_detail(self, idx, seance=None):
        """Affiche (ou efface) la carte de détail dans frm_detail."""
        frm = getattr(self, "frm_detail", None)
        if frm is None:
            return
        for w in frm.winfo_children():
            w.destroy()
        if idx is None or seance is None:
            tk.Label(
                frm,
                text="Cliquez sur une séance dans le planning ou dans la liste ci-dessous pour la modifier.",
                bg=BLANC, fg="#999", font=("Segoe UI", 9, "italic"),
                pady=6, anchor="w",
            ).pack(fill="x")
            return
        self._render_card(idx, seance, parent=frm)

    def _render_seance_list(self):
        """Affiche une liste déroulante des séances."""
        frm = getattr(self, "frm_list", None)
        if frm is None:
            return
        for w in frm.winfo_children():
            w.destroy()
        self.cb_seances = None
        self._combo_pos_to_idx = []
        self._combo_idx_to_pos = {}

        if not self.seances:
            tk.Label(
                frm,
                text="Aucune séance — utilisez « ➕ Ajouter une séance ».",
                bg=GRIS2, fg="#999", font=("Segoe UI", 9, "italic"),
            ).pack(anchor="w")
            return

        tk.Label(
            frm,
            text="Séances :",
            bg=GRIS2,
            fg=TEXTE,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 8))

        values = []
        for i, seance in enumerate(self.seances):
            titre = str(seance.get("titre", "—") or "—")
            type_name = str(seance.get("type", "Cours") or "Cours")
            slot = ""
            if seance.get("jour") and seance.get("heure_debut"):
                slot = f" · {seance['jour']} {seance['heure_debut']}"
            values.append(f"{type_name} · {titre}{slot} · {seance.get('duree', 0)}h")
            self._combo_pos_to_idx.append(i)
            self._combo_idx_to_pos[i] = len(self._combo_pos_to_idx) - 1

        self.cb_seances = ttk.Combobox(
            frm,
            state="readonly",
            values=values,
            width=76,
            font=("Segoe UI", 9),
        )
        self.cb_seances.pack(side="left", fill="x", expand=True)
        self.cb_seances.bind("<<ComboboxSelected>>", self._on_combo_select)

        if self._selected_seance_idx in self._combo_idx_to_pos:
            self.cb_seances.current(self._combo_idx_to_pos[self._selected_seance_idx])
        else:
            self.cb_seances.set("Sélectionner une séance…")

    def _render_week_schedule(self):
        c = getattr(self, "schedule_canvas", None)
        if c is None:
            return
        c.delete("all")
        c.update_idletasks()

        w = max(int(c.winfo_width()), 620)
        h = max(int(c.winfo_height()), 180)
        left = 54
        top = 26
        right = w - 8
        bottom = h - 10
        days = JOURS_SEMAINE[:5]
        start_hour = 8
        end_hour = 18

        c.create_rectangle(left, top, right, bottom, fill="#FFFFFF", outline="#DADCE0")

        day_w = (right - left) / len(days)
        total_min = (end_hour - start_hour) * 60
        min_px = (bottom - top) / total_min

        for i, day in enumerate(days):
            x = left + i * day_w
            c.create_line(x, top, x, bottom, fill="#E6EAF2")
            c.create_text(x + day_w / 2, 12, text=day, fill=TEXTE,
                          font=("Segoe UI", 8, "bold"))
        c.create_line(right, top, right, bottom, fill="#E6EAF2")

        for hour in range(start_hour, end_hour + 1):
            y = top + (hour - start_hour) * 60 * min_px
            line_color = "#D5DCE8" if hour in (8, 10, 12, 14, 16, 18) else "#EEF1F7"
            c.create_line(left, y, right, y, fill=line_color)
            c.create_text(left - 4, y, text=f"{hour:02d}:00", anchor="e",
                          fill="#6A778B", font=("Consolas", 8))

        self._placed_seances = []
        placed = 0
        for orig_idx, seance in enumerate(self.seances):
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
            is_sel = (orig_idx == getattr(self, "_selected_seance_idx", None))
            outline = "#FFFFFF" if is_sel else _darken_hex(color)
            lw = 2 if is_sel else 1
            c.create_rectangle(x1, y1, x2, y2, fill=color, outline=outline, width=lw)
            txt = _truncate_text_px(str(seance.get("titre", "Séance")), int(day_w) - 10, ("Segoe UI", 7, "bold"))
            c.create_text(x1 + 4, y1 + 3, text=txt, anchor="nw", fill=BLANC,
                          font=("Segoe UI", 7, "bold"))
            c.create_text(x1 + 4, y1 + 14,
                          text=f"{seance.get('heure_debut')}->{seance.get('heure_fin')}",
                          anchor="nw", fill=BLANC, font=("Consolas", 7))
            self._placed_seances.append((orig_idx, seance, x1, y1, x2, y2))
            placed += 1

        if placed == 0:
            c.create_text(
                (left + right) / 2,
                (top + bottom) / 2,
                text="Aucun créneau réel saisi pour cette semaine.",
                fill="#8A94A6",
                font=("Segoe UI", 9, "italic"),
            )


# ─── Fenêtre d'ajout / édition d'une séquence ────────────────────────────────
