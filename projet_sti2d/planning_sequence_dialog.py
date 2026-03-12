"""Dialog for creating/editing one sequence in planning."""

import tkinter as tk
from tkinter import ttk, messagebox

from constants import BLEU, VERT, GRIS2, BLANC, TEXTE, THEME_COLORS, show_quick_help
from planning_common import _expand_comp_refs_for_pb
class SequenceDialog(tk.Toplevel):

    def __init__(self, parent, themes, ref_comp, ref_conn, sequence=None, callback=None,
                 classes_options=None):
        super().__init__(parent)
        self.title("Séquence" if not sequence else "Modifier la séquence")
        base_w, base_h = 760, 700
        max_w = max(620, self.winfo_screenwidth() - 120)
        max_h = max(520, self.winfo_screenheight() - 120)
        self.geometry(f"{min(base_w, max_w)}x{min(base_h, max_h)}")
        self.minsize(640, 560)
        self.configure(bg=BLANC)
        self.grab_set()
        self.resizable(True, True)

        self.themes   = themes
        self.ref_comp = ref_comp
        self.ref_conn = ref_conn
        self.callback = callback
        self.seq      = sequence or {}
        opts = [str(c).strip() for c in (classes_options or []) if str(c).strip()]
        self.classes_options = opts or ["1ère IT", "1ère I2D", "1ère IT/I2D", "Terminale 2I2D"]
        self.comp_vars = {}
        self.conn_vars = {}
        self.conn_checks = {}

        self._build()
        self.bind("<F1>", lambda e: show_quick_help(
            self,
            "Aide — Séquence",
            [
                "Sélectionnez un thème puis une problématique.",
                "La classe définit le niveau associé à la séquence.",
                "Le type pédagogique se renseigne au niveau de chaque séance.",
                "Cochez les compétences visées puis les connaissances utiles.",
            ],
        ))
        self.bind("<Return>", lambda e: self._enregistrer())
        self.bind("<Escape>", lambda e: self.destroy())

    def _build(self):
        hdr = tk.Frame(self, bg=BLEU)
        hdr.pack(fill="x")
        tk.Label(hdr, text="➕  Nouvelle séquence" if not self.seq else "✏️  Modifier la séquence",
                 bg=BLEU, fg=BLANC, font=("Segoe UI", 12, "bold"), pady=8
                 ).pack(side="left", padx=10)
        tk.Button(hdr, text="?",
                  command=lambda: show_quick_help(
                      self,
                      "Aide — Séquence",
                      [
                          "Sélectionnez un thème puis une problématique.",
                          "La classe définit le niveau associé à la séquence.",
                          "Le type pédagogique se renseigne au niveau de chaque séance.",
                          "Cochez les compétences visées puis les connaissances utiles.",
                      ],
                  ),
                  bg="#2F5E9A", fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), width=3).pack(side="right", padx=8, pady=6)

        frm = tk.Frame(self, bg=BLANC, padx=20, pady=10)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        row = 0

        # Titre libre
        tk.Label(frm, text="Titre :", bg=BLANC, font=("Segoe UI", 10, "bold")
                 ).grid(row=row, column=0, sticky="w", pady=6)
        self.var_titre = tk.StringVar(value=self.seq.get("titre", ""))
        tk.Entry(frm, textvariable=self.var_titre, font=("Segoe UI", 11), width=45
                 ).grid(row=row, column=1, columnspan=3, sticky="ew", padx=8)
        row += 1

        # Thème
        tk.Label(frm, text="Thème :", bg=BLANC, font=("Segoe UI", 10, "bold")
                 ).grid(row=row, column=0, sticky="w", pady=6)
        theme_labels = [f"{t['id']} — {t['titre']}" for t in self.themes]
        self.var_theme = tk.StringVar(value=self._theme_label())
        cb_theme = ttk.Combobox(frm, textvariable=self.var_theme,
                                values=theme_labels, state="readonly",
                                font=("Segoe UI", 10), width=42)
        cb_theme.grid(row=row, column=1, columnspan=3, sticky="ew", padx=8)
        cb_theme.bind("<<ComboboxSelected>>", lambda e: self._refresh_pbs())
        row += 1

        # Problématique
        tk.Label(frm, text="Problématique :", bg=BLANC, font=("Segoe UI", 10, "bold")
                 ).grid(row=row, column=0, sticky="w", pady=6)
        self.var_pb = tk.StringVar(value=self.seq.get("pb_titre", ""))
        self.cb_pb = ttk.Combobox(frm, textvariable=self.var_pb,
                                   state="readonly", font=("Segoe UI", 10), width=42)
        self.cb_pb.grid(row=row, column=1, columnspan=3, sticky="ew", padx=8)
        self.cb_pb.bind("<<ComboboxSelected>>", lambda e: self._refresh_comp_selection())
        self._refresh_pbs()
        row += 1

        # Classe
        tk.Label(frm, text="Classe :", bg=BLANC, font=("Segoe UI", 10, "bold")
                 ).grid(row=row, column=0, sticky="w", pady=6)
        default_classe = self.seq.get("classe") or (self.classes_options[0] if self.classes_options else "")
        self.var_classe = tk.StringVar(value=default_classe)
        self.cb_classe = ttk.Combobox(frm, textvariable=self.var_classe,
                                      values=self.classes_options,
                                      state="readonly", font=("Segoe UI", 10), width=20)
        self.cb_classe.grid(row=row, column=1, sticky="w", padx=8)
        self.cb_classe.bind("<<ComboboxSelected>>", lambda e: self._refresh_comp_selection())
        row += 1

        # Semaines début / fin
        tk.Label(frm, text="Semaine début :", bg=BLANC, font=("Segoe UI", 10, "bold")
                 ).grid(row=row, column=0, sticky="w", pady=6)
        self.var_s_debut = tk.IntVar(value=self.seq.get("s_debut", 1))
        self.var_s_fin   = tk.IntVar(value=self.seq.get("s_fin",   2))
        frm_s = tk.Frame(frm, bg=BLANC)
        frm_s.grid(row=row, column=1, columnspan=3, sticky="w", padx=8)
        tk.Spinbox(frm_s, from_=1, to=36, textvariable=self.var_s_debut,
                   width=5, font=("Segoe UI", 11)).pack(side="left")
        tk.Label(frm_s, text="   Semaine fin :", bg=BLANC,
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=(12, 4))
        tk.Spinbox(frm_s, from_=1, to=36, textvariable=self.var_s_fin,
                   width=5, font=("Segoe UI", 11)).pack(side="left")
        row += 1

        # Heures
        tk.Label(frm, text="Volume horaire :", bg=BLANC, font=("Segoe UI", 10, "bold")
                 ).grid(row=row, column=0, sticky="w", pady=6)
        self.var_heures = tk.StringVar(value=self.seq.get("heures", ""))
        frm_h = tk.Frame(frm, bg=BLANC)
        frm_h.grid(row=row, column=1, sticky="w", padx=8)
        tk.Entry(frm_h, textvariable=self.var_heures,
                 font=("Segoe UI", 11), width=6).pack(side="left")
        tk.Label(frm_h, text=" heures", bg=BLANC, font=("Segoe UI", 10)).pack(side="left")
        row += 1

        # Compétences
        tk.Label(frm, text="Compétences :", bg=BLANC, font=("Segoe UI", 10, "bold")
                 ).grid(row=row, column=0, sticky="nw", pady=6)
        box = tk.Frame(frm, bg=BLANC, highlightbackground="#DADCE0", highlightthickness=1)
        box.grid(row=row, column=1, columnspan=3, sticky="nsew", padx=8)
        box.grid_propagate(False)
        box.configure(height=190)

        self.comp_canvas = tk.Canvas(box, bg=BLANC, bd=0, highlightthickness=0)
        sb_comp = ttk.Scrollbar(box, orient="vertical", command=self.comp_canvas.yview)
        self.comp_canvas.configure(yscrollcommand=sb_comp.set)
        sb_comp.pack(side="right", fill="y")
        self.comp_canvas.pack(side="left", fill="both", expand=True)

        self.comp_inner = tk.Frame(self.comp_canvas, bg=BLANC)
        self._comp_win_id = self.comp_canvas.create_window((0, 0), window=self.comp_inner, anchor="nw")
        self.comp_inner.bind(
            "<Configure>",
            lambda e: self.comp_canvas.configure(scrollregion=self.comp_canvas.bbox("all")))
        self.comp_canvas.bind(
            "<Configure>",
            lambda e: self.comp_canvas.itemconfig(self._comp_win_id, width=e.width))

        self.var_comp_summary = tk.StringVar(value="")
        tk.Label(frm, textvariable=self.var_comp_summary, bg=BLANC,
                 font=("Segoe UI", 8), fg="#666"
                 ).grid(row=row + 1, column=1, columnspan=3, sticky="w", padx=8, pady=(2, 0))
        row += 2

        # Couleur
        tk.Label(frm, text="Couleur :", bg=BLANC, font=("Segoe UI", 10, "bold")
                 ).grid(row=row, column=0, sticky="w", pady=6)
        theme_id = self._get_theme_id()
        default_color = self.seq.get("couleur", THEME_COLORS.get(theme_id, BLEU))
        self.var_couleur = tk.StringVar(value=default_color)
        frm_c = tk.Frame(frm, bg=BLANC)
        frm_c.grid(row=row, column=1, sticky="w", padx=8)
        self.btn_couleur = tk.Button(frm_c, bg=default_color, width=4,
                                     relief="flat", command=self._pick_color)
        self.btn_couleur.pack(side="left")
        tk.Label(frm_c, textvariable=self.var_couleur, bg=BLANC,
                 font=("Consolas", 9), fg="#555").pack(side="left", padx=6)
        row += 1

        # Boutons
        frm_btn = tk.Frame(self, bg=BLANC, pady=10)
        frm_btn.pack(side="bottom", fill="x", padx=20)
        self.update_idletasks()
        tk.Button(frm_btn, text="Annuler", command=self.destroy,
                  bg="#DDD", fg=TEXTE, relief="flat",
                  font=("Segoe UI", 10)).pack(side="right", padx=5)
        tk.Button(frm_btn, text="✅  Valider", command=self._enregistrer,
                  bg=VERT, fg=BLANC, relief="flat",
                  font=("Segoe UI", 11, "bold"), pady=7
                  ).pack(side="right", padx=5)
        self._refresh_comp_selection()

    def _theme_label(self):
        tid = self.seq.get("theme_id", "")
        for t in self.themes:
            if t["id"] == tid:
                return f"{t['id']} — {t['titre']}"
        return ""

    def _get_theme_id(self):
        val = self.var_theme.get()
        return val.split(" — ")[0] if " — " in val else ""

    def _refresh_pbs(self):
        tid = self._get_theme_id()
        pbs = []
        for t in self.themes:
            if t["id"] == tid:
                pbs = [pb["titre"] for pb in t["problematiques"]]
                break
        self.cb_pb["values"] = pbs
        if pbs and self.var_pb.get() not in pbs:
            self.var_pb.set(pbs[0])
        color = THEME_COLORS.get(tid, BLEU)
        if (hasattr(self, "var_couleur") and hasattr(self, "btn_couleur")
                and not self.seq.get("couleur")):
            self.var_couleur.set(color)
            self.btn_couleur.configure(bg=color)
        if hasattr(self, "comp_inner"):
            self._refresh_comp_selection()

    def _current_pb(self):
        tid      = self._get_theme_id()
        pb_titre = self.var_pb.get().strip()
        for t in self.themes:
            if t.get("id") != tid:
                continue
            for pb in t.get("problematiques", []):
                if pb.get("titre") == pb_titre:
                    return pb
            if t.get("problematiques"):
                return t["problematiques"][0]
        return None

    def _existing_selection_map(self):
        mapping = {}
        for item in self.seq.get("competences_selectionnees", []):
            code = item.get("code")
            if code:
                mapping[code] = set(item.get("connaissances", []))
        return mapping

    def _existing_codes(self):
        raw = self.seq.get("competences_str", "")
        return {c.strip() for c in raw.split(",") if c.strip()}

    def _level_candidates(self):
        raw = str(self.var_classe.get() or "").strip()
        if not raw:
            return []
        candidates = [raw]
        lower = raw.lower()

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

    @staticmethod
    def _is_level_zero(value):
        v = str(value or "").strip().lower().replace(" ", "")
        if not v or v in ("0", "-", "none", "non", "null"):
            return True
        return False

    def _is_comp_inactive_for_class(self, co):
        candidates = self._level_candidates()
        if not candidates:
            return False

        niveaux = co.get("niveaux", {}) or {}
        for key in candidates:
            if key in niveaux:
                return self._is_level_zero(niveaux.get(key))

        refs = co.get("connaissances", []) or []
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

    def _refresh_comp_selection(self):
        if not hasattr(self, "comp_inner"):
            return

        current_comp_state = {
            code: var.get() for code, var in (self.comp_vars or {}).items()
        }
        current_conn_state = {
            code: {ref: v.get() for ref, v in refs.items()}
            for code, refs in (self.conn_vars or {}).items()
        }

        for w in self.comp_inner.winfo_children():
            w.destroy()
        self.comp_vars   = {}
        self.conn_vars   = {}
        self.conn_checks = {}

        pb = self._current_pb()
        if not pb:
            self.var_comp_summary.set("Sélectionnez un thème et une problématique.")
            return

        existing_map   = self._existing_selection_map()
        existing_codes = self._existing_codes()
        comp_data      = self.ref_comp.get("competences", {})
        row = 0

        for code in pb.get("competences", []):
            co = comp_data.get(code, {})
            if code in current_comp_state:
                default_co = current_comp_state[code]
            elif existing_map:
                default_co = code in existing_map
            elif existing_codes:
                default_co = code in existing_codes
            else:
                default_co = True

            inactive = self._is_comp_inactive_for_class(co)
            fg_code = "#8D97A7" if inactive else BLANC
            fg_text = "#8D97A7" if inactive else TEXTE

            var_co = tk.BooleanVar(value=default_co)
            self.comp_vars[code] = var_co

            frm_co = tk.Frame(self.comp_inner, bg=GRIS2,
                              highlightbackground="#DADCE0", highlightthickness=1)
            frm_co.grid(row=row, column=0, sticky="ew", padx=4, pady=(6, 2))
            tk.Checkbutton(frm_co, variable=var_co, bg=GRIS2,
                           activebackground=GRIS2,
                           command=lambda c=code: self._toggle_comp(c)
                           ).pack(side="left", padx=6)
            tk.Label(frm_co, text=code,
                       bg=BLEU, fg=fg_code, font=("Segoe UI", 9, "bold"),
                     padx=8, pady=3).pack(side="left")
            tk.Label(frm_co, text=f"  {co.get('libelle', '—')[:80]}",
                       bg=GRIS2, fg=fg_text, font=("Segoe UI", 9),
                     anchor="w").pack(side="left", fill="x", expand=True, padx=6)
            row += 1

            self.conn_vars[code]   = {}
            self.conn_checks[code] = {}
            for ref in _expand_comp_refs_for_pb(co.get("connaissances", []), pb.get("connaissances", [])):
                chap   = ref.split("-")[0]
                chap_d = self.ref_conn.get(chap, {})
                sc_d   = chap_d.get("sous_chapitres", {}).get(ref, {})
                titre  = sc_d.get("titre") or chap_d.get("titre", ref)

                if code in current_conn_state and ref in current_conn_state[code]:
                    default_cn = current_conn_state[code][ref]
                elif code in existing_map:
                    default_cn = ref in existing_map[code]
                elif existing_codes:
                    default_cn = True
                else:
                    default_cn = True

                var_cn = tk.BooleanVar(value=default_cn)
                self.conn_vars[code][ref] = var_cn

                frm_cn = tk.Frame(self.comp_inner, bg=BLANC)
                frm_cn.grid(row=row, column=0, sticky="ew", padx=28, pady=1)
                chk = tk.Checkbutton(frm_cn, variable=var_cn, bg=BLANC,
                                     activebackground=BLANC,
                                     state=("normal" if var_co.get() else "disabled"),
                                     command=self._update_comp_summary)
                chk.pack(side="left", padx=4)
                self.conn_checks[code][ref] = chk
                tk.Label(frm_cn, text=ref, bg=BLANC, fg=BLEU,
                         font=("Consolas", 9, "bold"), width=6).pack(side="left")
                tk.Label(frm_cn, text=titre, bg=BLANC, fg=TEXTE,
                         font=("Segoe UI", 9), anchor="w").pack(side="left", padx=4)
                row += 1

        self.comp_inner.columnconfigure(0, weight=1)
        self._update_comp_summary()

    def _toggle_comp(self, code):
        var_co = self.comp_vars.get(code)
        if not var_co:
            return
        enabled = var_co.get()
        for ref, chk in self.conn_checks.get(code, {}).items():
            chk.configure(state=("normal" if enabled else "disabled"))
            if not enabled:
                self.conn_vars[code][ref].set(False)
        self._update_comp_summary()

    def _update_comp_summary(self):
        selected = [code for code, var in self.comp_vars.items() if var.get()]
        if not selected:
            self.var_comp_summary.set("Aucune compétence sélectionnée")
            return
        self.var_comp_summary.set(
            f"{len(selected)} compétence(s) sélectionnée(s) : {', '.join(selected)}")

    def _pick_color(self):
        from tkinter.colorchooser import askcolor
        result = askcolor(color=self.var_couleur.get(), title="Choisir une couleur")
        if result[1]:
            self.var_couleur.set(result[1])
            self.btn_couleur.configure(bg=result[1])

    def _enregistrer(self):
        if not self.var_titre.get().strip() and not self.var_pb.get().strip():
            messagebox.showwarning("Champ manquant", "Renseignez un titre ou une problématique.")
            return
        s_debut = self.var_s_debut.get()
        s_fin   = self.var_s_fin.get()
        if s_fin < s_debut:
            messagebox.showwarning("Semaines invalides",
                                   "La semaine de fin doit être ≥ à la semaine de début.")
            return

        selections = []
        for code, var_co in self.comp_vars.items():
            if not var_co.get():
                continue
            conns = [ref for ref, var in self.conn_vars.get(code, {}).items() if var.get()]
            selections.append({"code": code, "connaissances": conns})
        if self.comp_vars and not selections:
            messagebox.showwarning("Sélection vide", "Sélectionnez au moins une compétence.")
            return

        comp_str = ", ".join(item["code"] for item in selections)
        tid = self._get_theme_id()
        seq = {
            "id":                        self.seq.get("id", None),
            "titre":                     self.var_titre.get().strip() or self.var_pb.get().strip(),
            "theme_id":                  tid,
            "theme_titre":               self.var_theme.get().split(" — ", 1)[-1]
                                         if " — " in self.var_theme.get() else "",
            "pb_titre":                  self.var_pb.get(),
            "classe":                    self.var_classe.get(),
            "s_debut":                   s_debut,
            "s_fin":                     s_fin,
            "heures":                    self.var_heures.get().strip(),
            "competences_str":           comp_str,
            "competences_selectionnees": selections,
            "couleur":                   self.var_couleur.get(),
            "semaines":                  self.seq.get("semaines", {}),  # préserver les séances
        }
        self.destroy()
        if self.callback:
            self.callback(seq)


# ─── Onglet Planning ──────────────────────────────────────────────────────────
