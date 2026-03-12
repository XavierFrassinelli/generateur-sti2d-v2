"""Dialog for creating/editing one session."""

import tkinter as tk
from tkinter import ttk, messagebox
import uuid

from constants import BLEU, ORANGE, VERT, GRIS2, BLANC, TEXTE, SEUIL_MAITRISE, bind_mousewheel, show_quick_help
from planning_common import (
    JOURS_SEMAINE,
    _expand_comp_refs_for_pb,
    _slot_duration_hours,
    compute_competency_usage,
)
class SeanceDialog(tk.Toplevel):
    """Formulaire de création / édition d'une séance."""

    def __init__(self, parent, pb, ref_comp, ref_conn, sequences,
                 classe, seance=None, theme=None, sequence=None, callback=None):
        super().__init__(parent)
        self.title("Nouvelle séance" if not seance else "Modifier la séance")
        base_w, base_h = 760, 680
        max_w = max(640, self.winfo_screenwidth() - 120)
        max_h = max(540, self.winfo_screenheight() - 120)
        self.geometry(f"{min(base_w, max_w)}x{min(base_h, max_h)}")
        self.minsize(620, 540)
        self.configure(bg=BLANC)
        self.grab_set()
        self.resizable(True, True)

        self.pb        = pb
        self.ref_comp  = ref_comp
        self.ref_conn  = ref_conn
        self.sequences = sequences
        self.classe    = classe
        self.seance    = seance or {}
        self.theme     = theme if isinstance(theme, dict) else None
        self.sequence  = sequence if isinstance(sequence, dict) else {}
        self.callback  = callback

        if not self.pb and self.theme:
            pbs = self.theme.get("problematiques", []) if isinstance(self.theme, dict) else []
            wanted = str(self.seance.get("pb_titre") or self.sequence.get("pb_titre") or "").strip()
            if wanted:
                for pb_item in pbs:
                    if str(pb_item.get("titre", "")).strip() == wanted:
                        self.pb = pb_item
                        break
            if not self.pb and pbs:
                self.pb = pbs[0]

        self.comp_vars   = {}
        self.conn_vars   = {}
        self.conn_checks = {}

        self._build()
        self.bind("<F1>", lambda e: show_quick_help(
            self,
            "Aide — Séance",
            [
                "Choisissez type, durée et titre de la séance.",
                "Sélectionnez les compétences visées dans la liste.",
                "Les connaissances se filtrent selon les compétences cochées.",
            ],
        ))
        self.bind("<Escape>", lambda e: self.destroy())

    def _build(self):
        hdr = tk.Frame(self, bg=BLEU)
        hdr.pack(fill="x")
        tk.Label(hdr,
                 text="➕  Nouvelle séance" if not self.seance else "✏️  Modifier la séance",
                 bg=BLEU, fg=BLANC, font=("Segoe UI", 12, "bold"), pady=8
                 ).pack(side="left", padx=10)
        tk.Button(hdr, text="?",
                  command=lambda: show_quick_help(
                      self,
                      "Aide — Séance",
                      [
                          "Choisissez type, durée et titre de la séance.",
                          "Sélectionnez les compétences visées dans la liste.",
                          "Les connaissances se filtrent selon les compétences cochées.",
                      ],
                  ),
                  bg="#2F5E9A", fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), width=3).pack(side="right", padx=8, pady=6)

        frm = tk.Frame(self, bg=BLANC, padx=20, pady=8)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        # Type
        tk.Label(frm, text="Type :", bg=BLANC,
                 font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        self.var_type = tk.StringVar(value=self.seance.get("type", "Cours"))
        ttk.Combobox(frm, textvariable=self.var_type,
                     values=["Cours", "TP", "TD", "Évaluation", "Projet"],
                     state="readonly", font=("Segoe UI", 10), width=18
                     ).grid(row=0, column=1, sticky="w", padx=8)

        # Durée
        tk.Label(frm, text="Durée :", bg=BLANC,
                 font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=5)
        self.var_duree = tk.StringVar(value=str(self.seance.get("duree", 2)))
        frm_d = tk.Frame(frm, bg=BLANC)
        frm_d.grid(row=1, column=1, sticky="w", padx=8)
        tk.Spinbox(frm_d, from_=0.5, to=8, increment=0.5,
                   textvariable=self.var_duree,
                   width=5, font=("Segoe UI", 11)).pack(side="left")
        tk.Label(frm_d, text=" h", bg=BLANC, font=("Segoe UI", 10)).pack(side="left")

        # Créneau réel (optionnel)
        tk.Label(frm, text="Créneau :", bg=BLANC,
                 font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="w", pady=5)
        frm_slot = tk.Frame(frm, bg=BLANC)
        frm_slot.grid(row=2, column=1, columnspan=2, sticky="w", padx=8)
        self.var_jour = tk.StringVar(value=str(self.seance.get("jour", "")))
        self.var_heure_debut = tk.StringVar(value=str(self.seance.get("heure_debut", "")))
        self.var_heure_fin = tk.StringVar(value=str(self.seance.get("heure_fin", "")))

        ttk.Combobox(
            frm_slot,
            textvariable=self.var_jour,
            values=JOURS_SEMAINE,
            state="readonly",
            width=12,
            font=("Segoe UI", 10),
        ).pack(side="left")
        tk.Label(frm_slot, text="  ", bg=BLANC).pack(side="left")
        tk.Entry(frm_slot, textvariable=self.var_heure_debut,
                 font=("Consolas", 10), width=6).pack(side="left")
        tk.Label(frm_slot, text="  →  ", bg=BLANC, font=("Segoe UI", 10)).pack(side="left")
        tk.Entry(frm_slot, textvariable=self.var_heure_fin,
                 font=("Consolas", 10), width=6).pack(side="left")
        tk.Label(frm_slot, text="   (HH:MM)", bg=BLANC,
                 fg="#777", font=("Segoe UI", 8)).pack(side="left")

        # Titre
        tk.Label(frm, text="Titre :", bg=BLANC,
                 font=("Segoe UI", 10, "bold")).grid(row=3, column=0, sticky="w", pady=5)
        default_titre = self.seance.get("titre", self.pb.get("titre", "") if self.pb else "")
        self.var_titre = tk.StringVar(value=default_titre)
        tk.Entry(frm, textvariable=self.var_titre, font=("Segoe UI", 11), width=48
                 ).grid(row=3, column=1, columnspan=2, sticky="ew", padx=8)

        # Problématique
        pb_values = [pb_item.get("titre", "") for pb_item in (self.theme or {}).get("problematiques", [])
                     if pb_item.get("titre")]
        default_pb = self.seance.get("pb_titre") or (self.pb.get("titre", "") if self.pb else "")
        if pb_values and default_pb not in pb_values:
            default_pb = default_pb or pb_values[0]
        self.var_pb_titre = tk.StringVar(value=default_pb)

        tk.Label(frm, text="Problématique :", bg=BLANC,
                 font=("Segoe UI", 10, "bold")).grid(row=4, column=0, sticky="w", pady=5)
        if pb_values:
            ttk.Combobox(
                frm,
                textvariable=self.var_pb_titre,
                values=pb_values,
                state="readonly",
                font=("Segoe UI", 10),
                width=48,
            ).grid(row=4, column=1, columnspan=2, sticky="ew", padx=8)
            self.pb = self._find_pb_by_title(self.var_pb_titre.get()) or self.pb
        else:
            tk.Label(frm, text=self.var_pb_titre.get() or "—",
                     bg=BLANC, fg="#444", font=("Segoe UI", 10), anchor="w"
                     ).grid(row=4, column=1, columnspan=2, sticky="ew", padx=8)

        # Séparateur
        tk.Frame(frm, bg="#DADCE0", height=1).grid(
            row=5, column=0, columnspan=3, sticky="ew", pady=(10, 4))

        # En-tête compétences + toggle
        tk.Label(frm, text="Compétences :", bg=BLANC,
                 font=("Segoe UI", 10, "bold")).grid(row=6, column=0, sticky="nw", pady=(4, 0))
        self.var_show_all = tk.BooleanVar(value=False)
        self.var_show_outside = tk.BooleanVar(value=False)
        opts_row = tk.Frame(frm, bg=BLANC)
        opts_row.grid(row=6, column=1, columnspan=2, sticky="w", padx=8)
        tk.Checkbutton(opts_row, text="Afficher les compétences maîtrisées (≥ 3 vues)",
                       variable=self.var_show_all, bg=BLANC,
                       font=("Segoe UI", 8), fg="#888",
                       command=self._refresh_comp
                       ).pack(side="left")
        seq_codes, _ = self._sequence_constraints()
        if seq_codes is not None:
            tk.Checkbutton(opts_row, text="Afficher hors séquence",
                           variable=self.var_show_outside, bg=BLANC,
                           font=("Segoe UI", 8), fg=ORANGE,
                           command=self._refresh_comp
                           ).pack(side="left", padx=(14, 0))

        # Canvas compétences scrollable
        box = tk.Frame(frm, bg=BLANC, highlightbackground="#DADCE0", highlightthickness=1)
        box.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=(4, 0))
        box.grid_propagate(False)
        box.configure(height=200)
        frm.rowconfigure(7, weight=1)

        self.comp_canvas = tk.Canvas(box, bg=BLANC, bd=0, highlightthickness=0)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.comp_canvas.yview)
        self.comp_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.comp_canvas.pack(side="left", fill="both", expand=True)
        self.comp_canvas.bind(
            "<MouseWheel>",
            lambda e: self.comp_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        self.comp_inner = tk.Frame(self.comp_canvas, bg=BLANC)
        self._win_id = self.comp_canvas.create_window((0, 0), window=self.comp_inner, anchor="nw")
        self.comp_inner.bind("<Configure>",
            lambda e: self.comp_canvas.configure(scrollregion=self.comp_canvas.bbox("all")))
        self.comp_canvas.bind("<Configure>",
            lambda e: self.comp_canvas.itemconfig(self._win_id, width=e.width))

        if pb_values:
            def _on_pb_change(*_):
                selected = self._find_pb_by_title(self.var_pb_titre.get())
                if selected:
                    self.pb = selected
                    self._refresh_comp()
            self.var_pb_titre.trace_add("write", _on_pb_change)

        self._refresh_comp()

        # Boutons
        frm_btn = tk.Frame(self, bg=BLANC, pady=10)
        frm_btn.pack(side="bottom", fill="x", padx=20)
        tk.Button(frm_btn, text="Annuler", command=self.destroy,
                  bg="#DDD", fg=TEXTE, relief="flat",
                  font=("Segoe UI", 10)).pack(side="right", padx=5)
        tk.Button(frm_btn, text="✅  Valider", command=self._valider,
                  bg=VERT, fg=BLANC, relief="flat",
                  font=("Segoe UI", 11, "bold"), pady=6
                  ).pack(side="right", padx=5)

    def _refresh_comp(self):
        for w in self.comp_inner.winfo_children():
            w.destroy()
        self.comp_vars   = {}
        self.conn_vars   = {}
        self.conn_checks = {}

        if not self.pb:
            tk.Label(self.comp_inner, text="Problématique introuvable.",
                     bg=BLANC, fg="#999", font=("Segoe UI", 9, "italic")).pack(pady=10)
            return

        usage     = compute_competency_usage(self.sequences, self.classe)
        show_all  = self.var_show_all.get()
        exist_co  = set(self.seance.get("competences_visees", []))
        exist_cn  = set(self.seance.get("connaissances_abordees", []))
        seq_codes, seq_knowledge = self._sequence_constraints()
        show_outside = self.var_show_outside.get() if hasattr(self, "var_show_outside") else False
        comp_data = self.ref_comp.get("competences", {})
        row       = 0

        for code in self.pb.get("competences", []):
            if seq_codes is not None and code not in seq_codes and not show_outside and code not in exist_co:
                continue
            count    = usage.get(code, 0)
            mastered = count >= SEUIL_MAITRISE
            if mastered and not show_all:
                continue

            co      = comp_data.get(code, {})
            default = (code in exist_co) if exist_co else (not mastered)
            var_co  = tk.BooleanVar(value=default)
            self.comp_vars[code] = var_co

            filled   = min(count, SEUIL_MAITRISE)
            badge    = "█" * filled + "░" * (SEUIL_MAITRISE - filled)
            badge_fg = VERT if mastered else ORANGE

            frm_co = tk.Frame(self.comp_inner, bg=GRIS2,
                              highlightbackground="#DADCE0", highlightthickness=1)
            frm_co.grid(row=row, column=0, sticky="ew", padx=4, pady=(5, 1))
            tk.Checkbutton(frm_co, variable=var_co, bg=GRIS2, activebackground=GRIS2,
                           command=lambda c=code: self._toggle_co(c)
                           ).pack(side="left", padx=4)
            tk.Label(frm_co, text=code,
                     bg=BLEU, fg=BLANC, font=("Segoe UI", 9, "bold"),
                     padx=8, pady=3).pack(side="left")
            tk.Label(frm_co, text=f"  {co.get('libelle', '—')[:70]}",
                     bg=GRIS2, fg=TEXTE, font=("Segoe UI", 9),
                     anchor="w").pack(side="left", fill="x", expand=True, padx=4)
            tk.Label(frm_co, text=f" {badge} {count}/{SEUIL_MAITRISE} ",
                     bg=GRIS2, fg=badge_fg, font=("Consolas", 8)
                     ).pack(side="right", padx=4)
            if mastered:
                tk.Label(frm_co, text="✓", bg=GRIS2, fg=VERT,
                         font=("Segoe UI", 9, "bold")).pack(side="right")
            row += 1

            self.conn_vars[code]   = {}
            self.conn_checks[code] = {}
            refs = _expand_comp_refs_for_pb(co.get("connaissances", []), self.pb.get("connaissances", []))
            allowed_refs = seq_knowledge.get(code, set())
            if allowed_refs and not show_outside:
                refs = [ref for ref in refs if ref in allowed_refs or ref in exist_cn]
            for ref in refs:
                chap   = ref.split("-")[0]
                chap_d = self.ref_conn.get(chap, {})
                sc_d   = chap_d.get("sous_chapitres", {}).get(ref, {})
                titre  = sc_d.get("titre") or chap_d.get("titre", ref)
                default_cn = (ref in exist_cn) if exist_cn else True
                var_cn = tk.BooleanVar(value=default_cn and var_co.get())
                self.conn_vars[code][ref]   = var_cn
                frm_cn = tk.Frame(self.comp_inner, bg=BLANC)
                frm_cn.grid(row=row, column=0, sticky="ew", padx=28, pady=1)
                chk = tk.Checkbutton(frm_cn, variable=var_cn, bg=BLANC,
                                     activebackground=BLANC,
                                     state="normal" if var_co.get() else "disabled")
                chk.pack(side="left", padx=4)
                self.conn_checks[code][ref] = chk
                tk.Label(frm_cn, text=ref, bg=BLANC, fg=BLEU,
                         font=("Consolas", 9, "bold"), width=6).pack(side="left")
                tk.Label(frm_cn, text=titre, bg=BLANC, fg=TEXTE,
                         font=("Segoe UI", 9), anchor="w").pack(side="left", padx=4)
                row += 1

        self.comp_inner.columnconfigure(0, weight=1)

        if not self.comp_vars:
            tk.Label(self.comp_inner,
                     text="Toutes les compétences sont maîtrisées.\n"
                          "Cochez l'option ci-dessus pour les afficher quand même.",
                     bg=BLANC, fg=VERT, font=("Segoe UI", 9, "italic"),
                     justify="center", wraplength=460).pack(pady=16, padx=10)

        bind_mousewheel(self.comp_canvas, self.comp_inner)

    def _toggle_co(self, code):
        var_co = self.comp_vars.get(code)
        if not var_co:
            return
        enabled = var_co.get()
        for ref, chk in self.conn_checks.get(code, {}).items():
            chk.configure(state="normal" if enabled else "disabled")
            if not enabled:
                self.conn_vars[code][ref].set(False)

    def _find_pb_by_title(self, titre):
        titre = str(titre or "").strip()
        for pb_item in (self.theme or {}).get("problematiques", []):
            if str(pb_item.get("titre", "")).strip() == titre:
                return pb_item
        return None

    def _sequence_constraints(self):
        seq = self.sequence if isinstance(self.sequence, dict) else {}
        selections = seq.get("competences_selectionnees", [])
        if isinstance(selections, list) and selections:
            codes = set()
            knowledge_by_code = {}
            for item in selections:
                code = str(item.get("code", "")).strip()
                if not code:
                    continue
                codes.add(code)
                refs = {str(r).strip() for r in item.get("connaissances", []) if str(r).strip()}
                if refs:
                    knowledge_by_code[code] = refs
            return (codes if codes else None), knowledge_by_code

        raw = str(seq.get("competences_str", "")).strip()
        if raw:
            codes = {c.strip() for c in raw.split(",") if c.strip()}
            return (codes if codes else None), {}
        return None, {}

    def _valider(self):
        titre = self.var_titre.get().strip() or (
            self.pb.get("titre", "Séance") if self.pb else "Séance")
        try:
            duree = float(self.var_duree.get().replace(",", "."))
        except ValueError:
            duree = 2.0

        jour = self.var_jour.get().strip()
        heure_debut = self.var_heure_debut.get().strip()
        heure_fin = self.var_heure_fin.get().strip()
        has_slot_values = bool(jour or heure_debut or heure_fin)
        if has_slot_values:
            if not (jour and heure_debut and heure_fin):
                messagebox.showwarning(
                    "Créneau incomplet",
                    "Renseignez le jour, l'heure de début et l'heure de fin.",
                )
                return
            slot_hours = _slot_duration_hours(heure_debut, heure_fin)
            if slot_hours is None:
                messagebox.showwarning(
                    "Créneau invalide",
                    "Utilisez un format HH:MM valide et une heure de fin après l'heure de début.",
                )
                return
            duree = slot_hours

        co_visees   = [c for c, v in self.comp_vars.items() if v.get()]
        cn_abordees = []
        for code in co_visees:
            for ref, var in self.conn_vars.get(code, {}).items():
                if var.get() and ref not in cn_abordees:
                    cn_abordees.append(ref)

        if self.comp_vars and not co_visees:
            messagebox.showwarning("Sélection vide", "Sélectionnez au moins une compétence.")
            return

        seance = {
            "id":                     self.seance.get("id") or str(uuid.uuid4())[:8],
            "type":                   self.var_type.get(),
            "duree":                  duree,
            "titre":                  titre,
            "pb_titre":               self.var_pb_titre.get().strip() if hasattr(self, "var_pb_titre") else (self.pb.get("titre", "") if self.pb else ""),
            "jour":                   jour,
            "heure_debut":            heure_debut,
            "heure_fin":              heure_fin,
            "competences_visees":     co_visees,
            "connaissances_abordees": cn_abordees,
            "document_genere":        self.seance.get("document_genere"),
        }
        self.destroy()
        if self.callback:
            self.callback(seance)


# ─── Dialogue Détail Semaine ──────────────────────────────────────────────────
