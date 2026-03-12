"""
editeur_themes.py — Onglet « Séquence » pour l'application STI2D V2

Permet de créer, éditer et supprimer des séquences personnalisées avec
sélection fine des compétences et connaissances du référentiel.
Inspiré du module éponyme de la V1, adapté à l'architecture V2.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import re
from pathlib import Path
from constants import BLEU, ORANGE, VERT, GRIS, GRIS2, BLANC, TEXTE, NIVEAU_GROUPE, bind_mousewheel, show_quick_help
from gestionnaire_profils import TableauEditable, _rows_to_comp_json, _rows_to_conn_json, _normalize_comp_code

ROUGE = "#C62828"


# ─── Onglet principal ─────────────────────────────────────────────────────────
class EditeurThemesTab(tk.Frame):
    """
        Onglet pour gérer les séquences personnalisées.
        - Panneau gauche : liste des séquences custom + liste des problématiques
        - Panneau droit  : formulaire (titre de la séquence OU éditeur de problématique)
      L'éditeur de problématique est en deux zones :
        • Haut  : compétences cochables (groupées par objectif)
        • Bas   : connaissances liées aux compétences cochées (dynamic)
    """

    def __init__(self, parent, themes_officiels, ref_comp, ref_conn, data_dir,
                 classes_options=None, custom_file_path=None,
                 comp_file_path=None, conn_file_path=None,
                 on_themes_updated=None):
        super().__init__(parent, bg=GRIS)
        self.themes_officiels  = themes_officiels or []
        self.ref_comp          = ref_comp
        self.ref_conn          = ref_conn
        self.data_dir          = Path(data_dir)
        self.custom_file       = Path(custom_file_path) if custom_file_path else (self.data_dir / "themes_custom.json")
        self.comp_file_path    = Path(comp_file_path) if comp_file_path else (self.data_dir / "referentiel_competences.json")
        self.conn_file_path    = Path(conn_file_path) if conn_file_path else (self.data_dir / "referentiel_connaissances.json")
        opts = [str(c).strip() for c in (classes_options or []) if str(c).strip()]
        self.classes_options   = opts or ["IT/I2D", "IT", "I2D", "2I2D"]
        self.on_themes_updated = on_themes_updated

        self.themes_custom  = self._load_custom()
        self._sel_theme_idx = None
        self._sel_pb_idx    = None
        self._tooltip_win   = None

        # Variables du formulaire pb (recréées à chaque ouverture)
        self.comp_vars_pb = {}  # {code: BooleanVar}
        self._sel_conn    = {}  # {ref:  BooleanVar} — reconstruit dynamiquement

        self._build()

    # ── Persistance ───────────────────────────────────────────────────────────
    def _load_custom(self):
        if self.custom_file.exists():
            try:
                data = json.loads(self.custom_file.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return []
        return []

    def _save_custom(self):
        self.custom_file.write_text(
            json.dumps(self.themes_custom, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if self.on_themes_updated:
            self.on_themes_updated(self.themes_custom)

    # ── Auto-ID ───────────────────────────────────────────────────────────────
    def _next_id(self):
        """Génère le prochain ID séquence (T8, T9…) après tous les IDs connus."""
        nums = []
        for t in self.themes_officiels + self.themes_custom:
            tid = t.get("id", "")
            if tid.startswith("T"):
                try:
                    nums.append(int(tid[1:]))
                except ValueError:
                    pass
        return f"T{max(nums, default=0) + 1}"

    # ── Construction UI ───────────────────────────────────────────────────────
    def _build(self):
        # ── Panneau gauche (fixed) ─────────────────────────────────────────
        left = tk.Frame(self, bg=BLANC,
                        highlightbackground="#DADCE0", highlightthickness=1)
        left.pack(side="left", fill="y", padx=(8, 4), pady=8)
        left.pack_propagate(False)
        left.configure(width=280)

        hdr_left = tk.Frame(left, bg=BLEU)
        hdr_left.pack(fill="x")
        tk.Label(hdr_left, text="🎨  Séquence",
                 bg=BLEU, fg=BLANC, font=("Segoe UI", 11, "bold"), pady=8
                 ).pack(side="left", padx=10)
        tk.Button(hdr_left, text="?",
                  command=lambda: show_quick_help(
                      self,
                      "Aide — Séquence",
                      [
                          "Créez une séquence puis ajoutez des problématiques.",
                          "Dans une problématique, cochez les compétences visées.",
                          "Les connaissances proposées se filtrent automatiquement.",
                          "Le bouton Référentiels permet de corriger CO/CN manuellement.",
                      ],
                  ),
                  bg="#2F5E9A", fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), width=3).pack(side="right", padx=8, pady=6)

        # ── Liste séquences ───────────────────────────────────────────────────
        frm_th = tk.Frame(left, bg=BLANC)
        frm_th.pack(fill="x", padx=8, pady=(10, 4))
        tk.Label(frm_th, text="Séquences personnalisées", bg=BLANC,
                 font=("Segoe UI", 9, "bold"), fg=TEXTE).pack(anchor="w")
        self.lb_themes = tk.Listbox(
            frm_th, height=8, selectmode="single",
            font=("Segoe UI", 10), bg="#FAFAFA",
            selectbackground=BLEU, selectforeground=BLANC,
            relief="flat", bd=1, activestyle="none",
        )
        self.lb_themes.pack(fill="x", pady=(4, 2))
        self.lb_themes.bind("<<ListboxSelect>>", self._on_select_theme)

        btn_th = tk.Frame(frm_th, bg=BLANC)
        btn_th.pack(fill="x")
        tk.Button(btn_th, text="➕ Nouvelle séquence", command=self._nouveau_theme,
                  bg=VERT, fg=BLANC, relief="flat",
                  font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Button(btn_th, text="🛠 Référentiels", command=self._open_referentiel_editor,
              bg="#546E7A", fg=BLANC, relief="flat",
              font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 0))
        tk.Button(btn_th, text="🗑", command=self._suppr_theme,
                  bg="#FFEBEE", fg=ROUGE, relief="flat",
                  font=("Segoe UI", 10)).pack(side="right")

        # ── Séparateur ─────────────────────────────────────────────────────
        tk.Frame(left, bg="#DADCE0", height=1).pack(fill="x", padx=8, pady=8)

        # ── Liste problématiques ───────────────────────────────────────────
        frm_pb = tk.Frame(left, bg=BLANC)
        frm_pb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        tk.Label(frm_pb, text="Problématiques", bg=BLANC,
                 font=("Segoe UI", 9, "bold"), fg=TEXTE).pack(anchor="w")
        self.lb_pbs = tk.Listbox(
            frm_pb, selectmode="single",
            font=("Segoe UI", 9), bg="#FAFAFA",
            selectbackground=ORANGE, selectforeground=BLANC,
            relief="flat", bd=1, activestyle="none",
        )
        self.lb_pbs.pack(fill="both", expand=True, pady=(4, 2))
        self.lb_pbs.bind("<<ListboxSelect>>", self._on_select_pb)

        btn_pb = tk.Frame(frm_pb, bg=BLANC)
        btn_pb.pack(fill="x")
        tk.Button(btn_pb, text="➕ Nouvelle problématique", command=self._nouvelle_pb,
                  bg=ORANGE, fg=BLANC, relief="flat",
                  font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Button(btn_pb, text="🗑", command=self._suppr_pb,
                  bg="#FFEBEE", fg=ROUGE, relief="flat",
                  font=("Segoe UI", 10)).pack(side="right")

        # ── Panneau droit (expandable) ─────────────────────────────────────
        self.right = tk.Frame(self, bg=BLANC,
                              highlightbackground="#DADCE0", highlightthickness=1)
        self.right.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=8)

        self._build_right_empty()
        self._refresh_themes_list()

    # ── Vue vide ──────────────────────────────────────────────────────────────
    def _build_right_empty(self):
        for w in self.right.winfo_children():
            w.destroy()
        tk.Label(
            self.right,
              text="Sélectionnez une séquence ou créez-en une nouvelle\n"
                  "avec le bouton « ➕ Nouvelle séquence ».",
            bg=BLANC, fg="#999",
            font=("Segoe UI", 10, "italic"),
            justify="center",
        ).pack(expand=True)

    # ── Listes ────────────────────────────────────────────────────────────────
    def _refresh_themes_list(self):
        self.lb_themes.delete(0, "end")
        for t in self.themes_custom:
            self.lb_themes.insert("end", f"  {t['id']}  {t['titre']}")

    def _refresh_pbs_list(self):
        self.lb_pbs.delete(0, "end")
        if self._sel_theme_idx is None:
            return
        theme = self.themes_custom[self._sel_theme_idx]
        for pb in theme.get("problematiques", []):
            niv = pb.get("niveau", "")
            badge = f"[{niv}] " if niv else ""
            self.lb_pbs.insert("end", f"  {badge}{pb['titre']}")

    # ── Sélection ─────────────────────────────────────────────────────────────
    def _on_select_theme(self, event=None):
        sel = self.lb_themes.curselection()
        if not sel:
            return
        self._sel_theme_idx = sel[0]
        self._sel_pb_idx    = None
        self._refresh_pbs_list()
        self._build_theme_form()

    def _on_select_pb(self, event=None):
        sel = self.lb_pbs.curselection()
        if not sel or self._sel_theme_idx is None:
            return
        self._sel_pb_idx = sel[0]
        self._build_pb_form()

    # ── Formulaire : titre de la séquence ─────────────────────────────────────
    def _build_theme_form(self):
        for w in self.right.winfo_children():
            w.destroy()

        theme = self.themes_custom[self._sel_theme_idx]

        tk.Label(self.right, text=f"✏  Séquence {theme['id']}",
                 bg=BLEU, fg=BLANC, font=("Segoe UI", 11, "bold"), pady=8
                 ).pack(fill="x")

        frm = tk.Frame(self.right, bg=BLANC, padx=20, pady=15)
        frm.pack(fill="x")
        frm.columnconfigure(1, weight=1)

        tk.Label(frm, text="Titre de la séquence :", bg=BLANC,
                 font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=8)
        var_titre = tk.StringVar(value=theme["titre"])
        tk.Entry(frm, textvariable=var_titre,
                 font=("Segoe UI", 11), width=44
                 ).grid(row=0, column=1, sticky="ew", padx=10)

        lbl_status = tk.Label(self.right, text="", bg=BLANC, fg=VERT,
                              font=("Segoe UI", 9))
        lbl_status.pack(anchor="w", padx=20)

        tk.Label(self.right,
                 text="→ Sélectionnez une problématique dans la liste de gauche,\n"
                     "ou créez-en une nouvelle avec « ➕ Nouvelle problématique ».",
                 bg=BLANC, fg="#888",
                 font=("Segoe UI", 9, "italic"), justify="left"
                 ).pack(anchor="w", padx=20, pady=6)

        def _save():
            t = var_titre.get().strip()
            if not t:
                messagebox.showwarning("Titre vide",
                                       "Le titre de la séquence ne peut pas être vide.")
                return
            self.themes_custom[self._sel_theme_idx]["titre"] = t
            self._save_custom()
            self._refresh_themes_list()
            self.lb_themes.selection_set(self._sel_theme_idx)
            lbl_status.config(text=f"✓  Séquence {theme['id']} sauvegardée.")

        tk.Button(self.right, text="💾  Sauvegarder la séquence", command=_save,
                  bg=BLEU, fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), pady=7
                  ).pack(fill="x", padx=20, pady=(10, 0))

    # ── Formulaire : éditeur de problématique ─────────────────────────────────
    def _build_pb_form(self):
        if self._tooltip_win:
            try:
                self._tooltip_win.destroy()
            except Exception:
                pass
            self._tooltip_win = None
        for w in self.right.winfo_children():
            w.destroy()

        theme = self.themes_custom[self._sel_theme_idx]
        pb    = theme["problematiques"][self._sel_pb_idx]

        self.comp_vars_pb = {}
        self._sel_conn    = {}

        comp_data = self.ref_comp.get("competences", {})
        objectifs = self.ref_comp.get("objectifs", {})
        exist_co  = set(pb.get("competences", []))
        exist_cn  = set(pb.get("connaissances", []))

        # ── Fonctions utilitaires (locales) ────────────────────────────────
        def _refs_comp(code):
            refs = []
            for raw_ref in comp_data.get(code, {}).get("connaissances", []):
                ref = str(raw_ref or "").strip()
                if not ref:
                    continue
                if "-" in ref:
                    chap_id = ref.split("-")[0]
                    chap_d = self.ref_conn.get(chap_id, {})
                    if ref in chap_d.get("sous_chapitres", {}):
                        if ref not in refs:
                            refs.append(ref)
                    elif ref not in refs:
                        refs.append(ref)
                    continue

                chap_d = self.ref_conn.get(ref, {})
                sous = chap_d.get("sous_chapitres", {})
                if sous:
                    expanded = sorted(sous.keys(), key=_ref_sort_key)
                    for ex_ref in expanded:
                        if ex_ref not in refs:
                            refs.append(ex_ref)
                elif ref not in refs:
                    refs.append(ref)
            return refs

        def _ref_sort_key(ref):
            parts = ref.split("-")
            try:
                return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
            except ValueError:
                return (999, 0)

        def _conn_titre(ref):
            chap   = ref.split("-")[0]
            chap_d = self.ref_conn.get(chap, {})
            sc_d   = chap_d.get("sous_chapitres", {}).get(ref, {})
            return sc_d.get("titre") or chap_d.get("titre", ref) or ref

        def _hide_tooltip(event=None):
            if self._tooltip_win:
                try:
                    self._tooltip_win.destroy()
                except Exception:
                    pass
                self._tooltip_win = None

        def _show_tooltip(event, text):
            if not text:
                return
            _hide_tooltip()
            win = tk.Toplevel(self)
            win.wm_overrideredirect(True)
            win.wm_geometry(f"+{event.x_root + 14}+{event.y_root + 12}")
            win.configure(bg="#FFFDE7")
            tk.Label(
                win,
                text=text,
                bg="#FFFDE7",
                fg=TEXTE,
                justify="left",
                wraplength=620,
                font=("Segoe UI", 9),
                padx=10,
                pady=6,
                anchor="w",
            ).pack(fill="x")
            self._tooltip_win = win

        def _bind_tooltip(widget, full_text):
            widget.bind("<Enter>", lambda e, t=full_text: _show_tooltip(e, t))
            widget.bind("<Leave>", _hide_tooltip)
            widget.bind("<Button-1>", _hide_tooltip)

        # ── Header ────────────────────────────────────────────────────────
        tk.Label(self.right, text=f"✏  Problématique — {theme['id']}",
                 bg=ORANGE, fg=BLANC, font=("Segoe UI", 11, "bold"), pady=8
                 ).pack(fill="x")

        # ── Titre + Niveau ─────────────────────────────────────────────────
        top = tk.Frame(self.right, bg=BLANC, padx=16, pady=8)
        top.pack(fill="x")
        top.columnconfigure(1, weight=1)

        tk.Label(top, text="Titre :", bg=BLANC,
                 font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        var_titre = tk.StringVar(value=pb.get("titre", ""))
        tk.Entry(top, textvariable=var_titre,
                 font=("Segoe UI", 10), width=48
                 ).grid(row=0, column=1, sticky="ew", padx=8)

        tk.Label(top, text="Niveau :", bg=BLANC,
                 font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=5)
        default_niv = pb.get("niveau", self.classes_options[0] if self.classes_options else "")
        var_niv = tk.StringVar(value=default_niv)
        niv_values = list(self.classes_options)
        if "" not in niv_values:
            niv_values.append("")
        cb_niv = ttk.Combobox(top, textvariable=var_niv,
                              values=niv_values,
                              state="readonly", font=("Segoe UI", 10), width=12)
        cb_niv.grid(row=1, column=1, sticky="w", padx=8)
        tk.Label(
            top,
            text=(
                "Comptage des vues (X/3) : STI2D est groupé par niveau "
                "(1ère / Terminale). BTS reste séparé par classe."
            ),
            bg=BLANC,
            fg="#666",
            font=("Segoe UI", 8, "italic"),
            anchor="w",
            justify="left",
            wraplength=560,
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=(0, 8), pady=(2, 0))

        # ── Bouton Sauvegarder — packagé en BOTTOM avant les zones expand ──
        frm_save = tk.Frame(self.right, bg=GRIS, pady=8)
        frm_save.pack(side="bottom", fill="x", padx=12)

        lbl_status = tk.Label(frm_save, text="", bg=GRIS, fg=VERT,
                              font=("Segoe UI", 9))
        lbl_status.pack(side="right", padx=10)

        def _save():
            titre = var_titre.get().strip()
            if not titre:
                messagebox.showwarning(
                    "Titre vide",
                    "Le titre de la problématique ne peut pas être vide.")
                return
            co_sel = [c for c, v in self.comp_vars_pb.items() if v.get()]
            cn_sel = [ref for ref, v in self._sel_conn.items() if v.get()]
            pb["titre"]         = titre
            pb["niveau"]        = var_niv.get()
            pb["competences"]   = co_sel
            pb["connaissances"] = cn_sel
            self._save_custom()
            self._refresh_pbs_list()
            if self._sel_pb_idx is not None:
                self.lb_pbs.selection_set(self._sel_pb_idx)
            lbl_status.config(text="✓  Problématique sauvegardée.")

        tk.Button(frm_save, text="💾  Sauvegarder", command=_save,
                  bg=BLEU, fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), pady=6
                  ).pack(side="left")

        # ── Section compétences ────────────────────────────────────────────
        tk.Frame(self.right, bg="#DADCE0", height=1).pack(fill="x", padx=12, pady=(2, 0))

        tk.Label(self.right, text="Compétences :",
                 bg=BLANC, font=("Segoe UI", 9, "bold"), fg=TEXTE
                 ).pack(anchor="w", padx=16, pady=(6, 2))

        comp_outer = tk.Frame(self.right, bg=BLANC,
                              highlightbackground="#E0E4F0", highlightthickness=1)
        comp_outer.pack(fill="x", padx=12)
        comp_outer.configure(height=200)
        comp_outer.pack_propagate(False)

        comp_canvas = tk.Canvas(comp_outer, bg=BLANC, bd=0, highlightthickness=0)
        comp_sb = ttk.Scrollbar(comp_outer, orient="vertical",
                                command=comp_canvas.yview)
        comp_canvas.configure(yscrollcommand=comp_sb.set)
        comp_sb.pack(side="right", fill="y")
        comp_canvas.pack(side="left", fill="both", expand=True)

        comp_inner = tk.Frame(comp_canvas, bg=BLANC)
        _wc = comp_canvas.create_window((0, 0), window=comp_inner, anchor="nw")
        comp_inner.bind("<Configure>",
            lambda e: comp_canvas.configure(scrollregion=comp_canvas.bbox("all")))
        comp_canvas.bind("<Configure>",
            lambda e: comp_canvas.itemconfig(_wc, width=e.width))

        # ── Section connaissances (expand=True) ────────────────────────────
        tk.Frame(self.right, bg="#DADCE0", height=1).pack(fill="x", padx=12, pady=(6, 0))

        tk.Label(self.right,
                 text="Connaissances liées aux compétences sélectionnées :",
                 bg=BLANC, font=("Segoe UI", 9, "bold"), fg=ORANGE
                 ).pack(anchor="w", padx=16, pady=(4, 2))

        conn_outer = tk.Frame(self.right, bg=BLANC,
                              highlightbackground="#E0E4F0", highlightthickness=1)
        conn_outer.pack(fill="both", expand=True, padx=12, pady=(0, 4))

        self._conn_canvas = tk.Canvas(conn_outer, bg=BLANC, bd=0, highlightthickness=0)
        conn_sb = ttk.Scrollbar(conn_outer, orient="vertical",
                                command=self._conn_canvas.yview)
        self._conn_canvas.configure(yscrollcommand=conn_sb.set)
        conn_sb.pack(side="right", fill="y")
        self._conn_canvas.pack(side="left", fill="both", expand=True)

        self._conn_inner = tk.Frame(self._conn_canvas, bg=BLANC)
        _wn = self._conn_canvas.create_window((0, 0), window=self._conn_inner, anchor="nw")
        self._conn_inner.bind("<Configure>",
            lambda e: self._conn_canvas.configure(
                scrollregion=self._conn_canvas.bbox("all")))
        self._conn_canvas.bind("<Configure>",
            lambda e: self._conn_canvas.itemconfig(_wn, width=e.width))

        # ── Reconstruction dynamique des connaissances ─────────────────────
        def _refresh_conn():
            """Reconstruit la liste des connaissances selon les compétences cochées."""
            prev = {ref: v.get() for ref, v in self._sel_conn.items()}
            for w in self._conn_inner.winfo_children():
                w.destroy()
            self._sel_conn = {}

            selected = [c for c, v in self.comp_vars_pb.items() if v.get()]
            visible_refs = []
            for c in selected:
                for ref in _refs_comp(c):
                    if ref not in visible_refs:
                        visible_refs.append(ref)
            visible_refs.sort(key=_ref_sort_key)

            if not visible_refs:
                tk.Label(self._conn_inner,
                         text="Cochez une compétence pour afficher\n"
                              "ses connaissances liées.",
                         bg=BLANC, fg="#999",
                         font=("Segoe UI", 9, "italic"),
                         justify="center"
                         ).pack(expand=True, pady=12)
                bind_mousewheel(self._conn_canvas, self._conn_inner)
                return

            current_chap = None
            for ref in visible_refs:
                chap_id   = ref.split("-")[0]
                chap_data = self.ref_conn.get(chap_id, {})

                if chap_id != current_chap:
                    current_chap = chap_id
                    tk.Label(self._conn_inner,
                             text=f"  {chap_id}. {chap_data.get('titre', '')}",
                             bg=GRIS2, fg=ORANGE,
                             font=("Segoe UI", 9, "bold"), anchor="w"
                             ).pack(fill="x", pady=(6, 2))

                checked = prev.get(ref, ref in exist_cn)
                var_cn  = tk.BooleanVar(value=checked)
                self._sel_conn[ref] = var_cn

                sc = chap_data.get("sous_chapitres", {}).get(ref, {})
                row = tk.Frame(self._conn_inner, bg=BLANC)
                row.pack(fill="x", padx=6, pady=1)
                tk.Checkbutton(row, variable=var_cn, bg=BLANC,
                               activebackground=BLANC).pack(side="left", padx=2)
                tk.Label(row, text=ref, bg=BLANC, fg=BLEU,
                         font=("Consolas", 9, "bold"), width=6).pack(side="left")
                tk.Label(row, text=sc.get("titre", _conn_titre(ref))[:72],
                         bg=BLANC, fg=TEXTE,
                         font=("Segoe UI", 9), anchor="w"
                         ).pack(side="left", fill="x", expand=True, padx=4)

            bind_mousewheel(self._conn_canvas, self._conn_inner)

        # ── Remplissage des compétences (groupé par objectif) ──────────────
        current_obj = None

        def _co_sort_key(item):
            code = item[0]
            co = item[1]
            obj = str(co.get("objectif", ""))
            m_obj = obj[1:] if obj.startswith("O") else obj
            m_code = code[2:] if code.startswith("CO") else code
            try:
                o_num = int(str(m_obj).split(".")[0])
            except Exception:
                o_num = 999
            try:
                c_parts = [int(x) for x in str(m_code).split(".")]
                c_num = (c_parts[0], c_parts[1] if len(c_parts) > 1 else 0)
            except Exception:
                c_num = (999, 999)
            return (o_num, c_num[0], c_num[1], code)

        def _level_candidates(raw_level):
            raw = str(raw_level or "").strip()
            if not raw:
                return []
            lower = raw.lower()
            candidates = [raw]

            if "1ère" in lower or "1ere" in lower:
                candidates.append("1ère")
            if "terminale" in lower:
                candidates.append("Terminale")
            if "it/i2d" in lower:
                candidates += ["IT/I2D", "IT", "I2D"]
            else:
                if "it" in lower:
                    candidates.append("IT")
                if "i2d" in lower:
                    candidates.append("I2D")
            if "2i2d" in lower:
                candidates.append("2I2D")

            seen = set()
            dedup = []
            for c in candidates:
                key = c.lower()
                if key in seen:
                    continue
                seen.add(key)
                dedup.append(c)
            return dedup

        def _is_zero_mark(value):
            v = str(value or "").strip().lower().replace(" ", "")
            return (not v) or (v in ("0", "-", "none", "non", "null"))

        def _is_comp_inactive_for_level(code, co, raw_level):
            candidates = _level_candidates(raw_level)
            if not candidates:
                return False

            niveaux = co.get("niveaux", {}) or {}
            matched_marks = []
            for key in candidates:
                if key in niveaux:
                    matched_marks.append(niveaux.get(key))
            if matched_marks:
                return all(_is_zero_mark(v) for v in matched_marks)

            refs = _refs_comp(code)
            found_taxo = False
            max_taxo = 0
            for ref in refs:
                chap = str(ref).split("-")[0]
                sc = ((self.ref_conn.get(chap) or {}).get("sous_chapitres") or {}).get(ref, {})
                taxo_map = sc.get("taxonomie", {}) or {}
                for key in candidates:
                    if key not in taxo_map:
                        continue
                    found_taxo = True
                    try:
                        taxo = int(taxo_map.get(key) or 0)
                    except Exception:
                        taxo = 0
                    if taxo > max_taxo:
                        max_taxo = taxo
            if found_taxo:
                return max_taxo <= 0
            return False

        comp_widgets = {}
        usage_badges = {}

        def _refresh_comp_graying(*_):
            selected_level = var_niv.get()
            for code, co in comp_data.items():
                widgets = comp_widgets.get(code)
                if not widgets:
                    continue
                inactive = _is_comp_inactive_for_level(code, co, selected_level)
                widgets["lbl_code"].configure(fg="#8D97A7" if inactive else BLANC)
                widgets["lbl_lib"].configure(fg="#8D97A7" if inactive else TEXTE)

        def _same_level(pb_level, selected_level):
            alias = {
                "it": "1ère",
                "i2d": "1ère",
                "it/i2d": "1ère",
                "2i2d": "Terminale",
            }

            def _canonical(raw):
                txt = str(raw or "").strip()
                if not txt:
                    return ""
                if txt in NIVEAU_GROUPE:
                    return str(NIVEAU_GROUPE.get(txt, txt)).strip()
                low = txt.lower()
                if low in alias:
                    return alias[low]
                return txt

            target = _canonical(selected_level)
            if not target:
                return True
            source = _canonical(pb_level)
            if not source:
                return False
            return source.lower() == target.lower()

        def _compute_usage_map_for_level():
            usage = {}
            current_level = str(var_niv.get() or "").strip()
            if not current_level:
                return usage
            planning_path = self.data_dir / "planning.json"
            if not planning_path.exists():
                return usage

            try:
                planning_data = json.loads(planning_path.read_text(encoding="utf-8"))
            except Exception:
                return usage

            if not isinstance(planning_data, list):
                return usage

            for seq in planning_data:
                if not isinstance(seq, dict):
                    continue
                if not _same_level(seq.get("classe", ""), current_level):
                    continue
                semaines = seq.get("semaines", {}) or {}
                if not isinstance(semaines, dict):
                    continue
                for week_data in semaines.values():
                    seances = (week_data or {}).get("seances", [])
                    if not isinstance(seances, list):
                        continue
                    for seance in seances:
                        competences = (seance or {}).get("competences_visees", [])
                        for co_code in competences:
                            co_code = str(co_code or "").strip()
                            if not co_code:
                                continue
                            usage[co_code] = usage.get(co_code, 0) + 1
            return usage

        def _refresh_usage_badges(*_):
            usage = _compute_usage_map_for_level()
            for co_code, badge in usage_badges.items():
                count = usage.get(co_code, 0)
                badge.configure(text=f" {count}/3 ", fg=VERT if count == 3 else "#666")

        def _on_comp_toggle():
            _refresh_conn()
            _refresh_usage_badges()

        def _edit_objectif_text(obj_code):
            current = str(objectifs.get(obj_code, "") or "").strip()
            dlg = tk.Toplevel(self)
            dlg.title(f"Description objectif {obj_code}")
            dlg.transient(self.winfo_toplevel())
            dlg.grab_set()
            dlg.configure(bg=BLANC)
            dlg.geometry("760x240")
            dlg.minsize(620, 200)

            tk.Label(
                dlg,
                text=(
                    "Collez/éditez le texte de l'objectif. "
                    "Les retours ligne seront convertis en espaces à la sauvegarde."
                ),
                bg=BLANC,
                fg="#555",
                font=("Segoe UI", 9, "italic"),
                anchor="w",
                justify="left",
            ).pack(fill="x", padx=12, pady=(10, 4))

            txt = tk.Text(dlg, wrap="word", font=("Segoe UI", 10), height=6)
            txt.pack(fill="both", expand=True, padx=12, pady=(0, 10))
            txt.insert("1.0", current)
            txt.focus_set()

            result = {"value": None}

            def _save_and_close(event=None):
                raw = txt.get("1.0", "end-1c")
                cleaned = raw.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
                cleaned = re.sub(r"\s+", " ", cleaned).strip()
                result["value"] = cleaned
                dlg.destroy()

            def _cancel(event=None):
                dlg.destroy()

            txt.bind("<Control-Return>", _save_and_close)
            txt.bind("<Control-KP_Enter>", _save_and_close)

            frm_btn = tk.Frame(dlg, bg=BLANC)
            frm_btn.pack(fill="x", padx=12, pady=(0, 10))
            tk.Button(
                frm_btn,
                text="Annuler",
                command=_cancel,
                bg="#DDD",
                fg=TEXTE,
                relief="flat",
                font=("Segoe UI", 9),
            ).pack(side="right", padx=(6, 0))
            tk.Button(
                frm_btn,
                text="Enregistrer",
                command=_save_and_close,
                bg=VERT,
                fg=BLANC,
                relief="flat",
                font=("Segoe UI", 9, "bold"),
            ).pack(side="right")

            dlg.bind("<Escape>", _cancel)
            dlg.wait_window(dlg)

            new_text = result["value"]
            if new_text is None:
                return
            text = str(new_text).strip() or obj_code
            self.ref_comp.setdefault("objectifs", {})[obj_code] = text
            objectifs[obj_code] = text
            try:
                self.comp_file_path.write_text(
                    json.dumps(self.ref_comp, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as e:
                messagebox.showerror("Sauvegarde impossible", str(e), parent=self)
                return
            self._build_pb_form()

        for code, co in sorted(comp_data.items(), key=_co_sort_key):
            obj = co.get("objectif", "")
            if obj != current_obj:
                current_obj = obj
                obj_txt = objectifs.get(obj, obj)
                obj_row = tk.Frame(comp_inner, bg=GRIS2)
                obj_row.pack(fill="x", pady=(6, 2))
                lbl_obj = tk.Label(
                    obj_row,
                    text=f"  {obj} — {obj_txt[:60]}",
                    bg=GRIS2,
                    fg=BLEU,
                    font=("Segoe UI", 8, "italic"),
                    anchor="w",
                )
                lbl_obj.pack(side="left", fill="x", expand=True)
                if len(str(obj_txt)) > 60:
                    _bind_tooltip(lbl_obj, f"{obj} — {obj_txt}")
                tk.Button(
                    obj_row,
                    text="✎",
                    command=lambda o=obj: _edit_objectif_text(o),
                    bg=GRIS2,
                    fg=BLEU,
                    relief="flat",
                    font=("Segoe UI", 8, "bold"),
                    padx=6,
                ).pack(side="right", padx=2)

            var_co = tk.BooleanVar(value=code in exist_co)
            self.comp_vars_pb[code] = var_co

            row = tk.Frame(comp_inner, bg=BLANC)
            row.pack(fill="x", padx=4, pady=1)
            tk.Checkbutton(row, variable=var_co, bg=BLANC, activebackground=BLANC,
                           command=_on_comp_toggle
                           ).pack(side="left", padx=2)
            lbl_code = tk.Label(row, text=code, bg=BLEU, fg=BLANC,
                                font=("Segoe UI", 9, "bold"),
                                padx=6, pady=2)
            lbl_code.pack(side="left")
            full_lib = co.get("libelle", "—")
            lbl_lib = tk.Label(row, text=f"  {full_lib[:70]}",
                               bg=BLANC, fg=TEXTE, font=("Segoe UI", 9), anchor="w")
            lbl_lib.pack(side="left", fill="x", expand=True, padx=4)
            badge = tk.Label(row, text=" 0/3 ", bg=BLANC, fg="#666",
                             font=("Consolas", 8, "bold"))
            badge.pack(side="right", padx=4)
            comp_widgets[code] = {
                "lbl_code": lbl_code,
                "lbl_lib": lbl_lib,
            }
            usage_badges[code] = badge
            if len(full_lib) > 70:
                _bind_tooltip(lbl_lib, f"{code} — {full_lib}")

        bind_mousewheel(comp_canvas, comp_inner)
        def _on_level_changed(*_):
            _refresh_comp_graying()
            _refresh_usage_badges()

        cb_niv.bind("<<ComboboxSelected>>", _on_level_changed)
        _refresh_comp_graying()
        _refresh_usage_badges()

        # Initialisation de la liste des connaissances avec l'état sauvegardé
        _refresh_conn()
        self.bind("<Leave>", _hide_tooltip)

    # ── Édition référentiels ─────────────────────────────────────────────────
    def _infer_niveaux(self):
        levels = []
        for co in self.ref_comp.get("competences", {}).values():
            for n in co.get("niveaux", {}).keys():
                n = str(n).strip()
                if n and n not in levels:
                    levels.append(n)
        if not levels:
            for chap in self.ref_conn.values():
                for sc in chap.get("sous_chapitres", {}).values():
                    for n in sc.get("taxonomie", {}).keys():
                        n = str(n).strip()
                        if n and n not in levels:
                            levels.append(n)
        return levels or ["IT", "I2D", "2I2D"]

    def _comp_json_to_rows(self, niveaux):
        rows = []
        comp_data = self.ref_comp.get("competences", {})

        def _norm_mark(v):
            t = str(v or "").strip().upper().replace(" ", "")
            if not t or t in ("0", "-", "NON", "NONE"):
                return ""
            if t in ("XX", "2", "X2"):
                return "XX"
            return "X"

        def _co_key(code):
            try:
                p = code[2:].split(".") if code.startswith("CO") else code.split(".")
                return int(p[0]), int(p[1]) if len(p) > 1 else 0
            except Exception:
                return (999, 999)

        # Si tous les niveaux sont vides dans le profil actif, on tente un
        # fallback depuis le référentiel historique data/referentiel_competences.json
        # pour restaurer les niveaux attendus (X/XX) quand disponibles.
        all_levels_empty = True
        for co in comp_data.values():
            niv_map = co.get("niveaux", {}) or {}
            for n in niveaux:
                if _norm_mark(niv_map.get(n, "")):
                    all_levels_empty = False
                    break
            if not all_levels_empty:
                break

        fallback_levels = {}
        if all_levels_empty:
            try:
                fallback_file = Path(__file__).parent / "data" / "referentiel_competences.json"
                if fallback_file.exists():
                    legacy = json.loads(fallback_file.read_text(encoding="utf-8"))
                    for code, co in (legacy.get("competences", {}) or {}).items():
                        fallback_levels[str(code).strip()] = co.get("niveaux", {}) or {}
            except Exception:
                fallback_levels = {}

        for code in sorted(comp_data.keys(), key=_co_key):
            co = comp_data.get(code, {})
            row = {
                "code": code,
                "libelle": co.get("libelle", ""),
                "connaissances_liees": ";".join(co.get("connaissances", [])),
                "confidence": "manual",
            }
            niv_map = co.get("niveaux", {})
            for n in niveaux:
                val = _norm_mark(niv_map.get(n, ""))
                if not val and fallback_levels:
                    val = _norm_mark((fallback_levels.get(code, {}) or {}).get(n, ""))
                row[n] = val
            rows.append(row)
        return rows

    def _conn_json_to_rows(self, niveaux):
        rows = []

        def _ref_key(ref):
            try:
                return tuple(int(x) for x in ref.split("-") if x.isdigit())
            except Exception:
                return (999,)

        for chap_id, chap in self.ref_conn.items():
            chap_titre = chap.get("titre", "")
            scs = chap.get("sous_chapitres", {})
            for ref in sorted(scs.keys(), key=_ref_key):
                sc = scs.get(ref, {})
                row = {
                    "ref": ref,
                    "chapitre_id": chap_id,
                    "chapitre_titre": chap_titre,
                    "sous_chapitre_titre": sc.get("titre", ""),
                    "detail": sc.get("detail", ""),
                    "confidence": "manual",
                }
                taxo = sc.get("taxonomie", {})
                for n in niveaux:
                    row[n] = str(taxo.get(n, 0))
                rows.append(row)
        return rows

    def _save_referentiels_files(self):
        self.comp_file_path.write_text(
            json.dumps(self.ref_comp, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.conn_file_path.write_text(
            json.dumps(self.ref_conn, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _open_referentiel_editor(self):
        niveaux = self._infer_niveaux()

        def _show_help_refs(parent):
            show_quick_help(
                parent,
                "Aide — Édition référentiels",
                [
                    "Double-cliquez une cellule pour modifier sa valeur.",
                    "Ajoutez une ligne avec « + Ligne » ou dupliquez avec Ctrl+D.",
                    "Codes attendus : COx.y pour compétences, x-y pour connaissances.",
                    "Les lignes invalides peuvent être ignorées à la sauvegarde.",
                ],
            )

        dlg = tk.Toplevel(self)
        dlg.title("Édition manuelle des référentiels")
        dlg.geometry("1180x700")
        dlg.configure(bg=BLANC)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.bind("<F1>", lambda e: _show_help_refs(dlg))

        def _close_dlg():
            try:
                dlg.grab_release()
            except Exception:
                pass
            dlg.destroy()

        dlg.protocol("WM_DELETE_WINDOW", _close_dlg)

        hdr = tk.Frame(dlg, bg=BLEU)
        hdr.pack(fill="x")
        tk.Label(hdr,
                 text="🛠 Édition manuelle des compétences et connaissances",
                 bg=BLEU, fg=BLANC, font=("Segoe UI", 11, "bold"), pady=8
                 ).pack(side="left", padx=10)
        tk.Button(hdr, text="?",
                  command=lambda: _show_help_refs(dlg),
                  bg="#2F5E9A", fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), width=3).pack(side="right", padx=8, pady=6)

        nb = ttk.Notebook(dlg)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        tab_comp = tk.Frame(nb, bg=BLANC)
        tab_conn = tk.Frame(nb, bg=BLANC)
        nb.add(tab_comp, text="Compétences")
        nb.add(tab_conn, text="Connaissances")

        tbl_comp = TableauEditable(tab_comp, niveaux, mode="comp")
        tbl_comp.pack(fill="both", expand=True, padx=6, pady=6)
        tbl_comp.set_rows(self._comp_json_to_rows(niveaux))

        tbl_conn = TableauEditable(tab_conn, niveaux, mode="conn")
        tbl_conn.pack(fill="both", expand=True, padx=6, pady=6)
        tbl_conn.set_rows(self._conn_json_to_rows(niveaux))

        frm_btn = tk.Frame(dlg, bg=BLANC, pady=8)
        frm_btn.pack(fill="x", padx=10)

        def _save_refs():
            comp_rows = tbl_comp.get_rows()
            conn_rows = tbl_conn.get_rows()

            normalized_comp_rows = []
            invalid_comp = []
            for idx, row in enumerate(comp_rows, start=1):
                new_row = dict(row)
                raw_code = str(new_row.get("code", "")).strip()
                norm_code = _normalize_comp_code(raw_code)
                if not re.match(r"^CO\d+(?:\.\d+)?$", norm_code, re.IGNORECASE):
                    invalid_comp.append((idx, raw_code))
                    continue
                new_row["code"] = norm_code
                normalized_comp_rows.append(new_row)

            normalized_conn_rows = []
            invalid_conn = []
            for idx, row in enumerate(conn_rows, start=1):
                new_row = dict(row)
                raw_ref = str(new_row.get("ref", "")).strip().replace(".", "-").replace(" ", "")
                if not re.match(r"^\d+-\d+$", raw_ref):
                    invalid_conn.append((idx, str(new_row.get("ref", "")).strip()))
                    continue
                new_row["ref"] = raw_ref
                if not str(new_row.get("chapitre_id", "")).strip():
                    new_row["chapitre_id"] = raw_ref.split("-")[0]
                normalized_conn_rows.append(new_row)

            if invalid_comp or invalid_conn:
                msg = []
                if invalid_comp:
                    sample = ", ".join(f"L{n}:{v}" for n, v in invalid_comp[:4])
                    msg.append(f"- Lignes compétences ignorées : {len(invalid_comp)} ({sample})")
                if invalid_conn:
                    sample = ", ".join(f"L{n}:{v}" for n, v in invalid_conn[:4])
                    msg.append(f"- Lignes connaissances ignorées : {len(invalid_conn)} ({sample})")
                msg.append("\nLes autres lignes valides seront sauvegardées.")
                if not messagebox.askyesno("Lignes invalides", "\n".join(msg), parent=dlg):
                    return

            new_comp = _rows_to_comp_json(normalized_comp_rows, niveaux)
            new_conn = _rows_to_conn_json(normalized_conn_rows, niveaux)

            if isinstance(self.ref_comp, dict):
                self.ref_comp.clear()
                self.ref_comp.update(new_comp)
            else:
                self.ref_comp = new_comp

            if isinstance(self.ref_conn, dict):
                self.ref_conn.clear()
                self.ref_conn.update(new_conn)
            else:
                self.ref_conn = new_conn

            self._save_referentiels_files()

            if self._sel_theme_idx is not None and self._sel_pb_idx is not None:
                self._build_pb_form()

            messagebox.showinfo(
                "Référentiels sauvegardés",
                f"Compétences : {len(self.ref_comp.get('competences', {}))}\n"
                f"Connaissances : {sum(len(v.get('sous_chapitres', {})) for v in self.ref_conn.values())}\n\n"
                f"Fichiers :\n{self.comp_file_path}\n{self.conn_file_path}",
                parent=dlg,
            )

        tk.Button(frm_btn, text="💾 Sauvegarder les référentiels",
                  command=_save_refs,
                  bg=VERT, fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), pady=6
                  ).pack(side="left")
        tk.Button(frm_btn, text="Fermer", command=_close_dlg,
                  bg="#DDD", fg=TEXTE, relief="flat",
                  font=("Segoe UI", 10)
                  ).pack(side="right")

    # ── CRUD séquences ────────────────────────────────────────────────────────
    def _nouveau_theme(self):
        tid = self._next_id()
        self.themes_custom.append({
            "id": tid, "titre": f"Nouvelle séquence {tid}", "problematiques": []
        })
        self._save_custom()
        self._refresh_themes_list()
        idx = len(self.themes_custom) - 1
        self.lb_themes.selection_clear(0, "end")
        self.lb_themes.selection_set(idx)
        self.lb_themes.see(idx)
        self._sel_theme_idx = idx
        self._sel_pb_idx    = None
        self._refresh_pbs_list()
        self._build_theme_form()

    def _suppr_theme(self):
        if self._sel_theme_idx is None:
            messagebox.showwarning("Aucune séquence", "Sélectionnez d'abord une séquence.")
            return
        theme = self.themes_custom[self._sel_theme_idx]
        if not messagebox.askyesno(
                "Supprimer", f"Supprimer la séquence « {theme['titre']} » ?\n"
                             "Toutes ses problématiques seront perdues."):
            return
        self.themes_custom.pop(self._sel_theme_idx)
        self._save_custom()
        self._sel_theme_idx = None
        self._sel_pb_idx    = None
        self._refresh_themes_list()
        self._refresh_pbs_list()
        self._build_right_empty()

    # ── CRUD problématiques ───────────────────────────────────────────────────
    def _nouvelle_pb(self):
        if self._sel_theme_idx is None:
            messagebox.showwarning("Aucune séquence",
                                   "Sélectionnez d'abord une séquence.")
            return
        pb = {
            "titre": "Nouvelle problématique",
            "niveau": self.classes_options[0] if self.classes_options else "",
            "competences": [],
            "connaissances": [],
        }
        self.themes_custom[self._sel_theme_idx]["problematiques"].append(pb)
        self._save_custom()
        self._refresh_pbs_list()
        idx = len(self.themes_custom[self._sel_theme_idx]["problematiques"]) - 1
        self.lb_pbs.selection_clear(0, "end")
        self.lb_pbs.selection_set(idx)
        self.lb_pbs.see(idx)
        self._sel_pb_idx = idx
        self._build_pb_form()

    def _suppr_pb(self):
        if self._sel_theme_idx is None or self._sel_pb_idx is None:
            messagebox.showwarning("Aucune sélection",
                                   "Sélectionnez d'abord une problématique.")
            return
        pbs   = self.themes_custom[self._sel_theme_idx]["problematiques"]
        titre = pbs[self._sel_pb_idx].get("titre", "")
        if not messagebox.askyesno("Supprimer",
                                   f"Supprimer la problématique « {titre} » ?"):
            return
        pbs.pop(self._sel_pb_idx)
        self._save_custom()
        self._sel_pb_idx = None
        self._refresh_pbs_list()
        self._build_theme_form()
