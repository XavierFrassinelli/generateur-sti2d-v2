"""Onglet recapitulatif de couverture des competences."""

import json
import re
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from constants import BLEU, ORANGE, VERT, GRIS, GRIS2, BLANC, TEXTE, NIVEAU_GROUPE


class CouvertureTab(tk.Frame):
    def __init__(self, parent, ref_comp, data_dir, classes_options=None):
        super().__init__(parent, bg=GRIS)
        self.ref_comp = ref_comp or {}
        self.data_dir = Path(data_dir)
        self.classes_options = [str(c).strip() for c in (classes_options or []) if str(c).strip()]

        self.var_niveau = tk.StringVar(value="")
        self.var_resume = tk.StringVar(value="")

        self._build()
        self._refresh_all()

    def _build(self):
        toolbar = tk.Frame(self, bg=BLEU, height=44)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        tk.Label(
            toolbar,
            text="Couverture des competences (planning reel)",
            bg=BLEU,
            fg=BLANC,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left", padx=12)

        tk.Label(toolbar, text="Niveau :", bg=BLEU, fg=BLANC,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(10, 4))

        self.cb_niveau = ttk.Combobox(
            toolbar,
            textvariable=self.var_niveau,
            values=[],
            state="readonly",
            width=18,
            font=("Segoe UI", 9),
        )
        self.cb_niveau.pack(side="left", padx=(0, 8), pady=6)
        self.cb_niveau.bind("<<ComboboxSelected>>", lambda e: self._refresh_table())

        tk.Button(
            toolbar,
            text="Rafraichir",
            command=self._refresh_all,
            bg=ORANGE,
            fg=BLANC,
            relief="flat",
            font=("Segoe UI", 9, "bold"),
            padx=10,
        ).pack(side="right", padx=10, pady=6)

        body = tk.Frame(self, bg=BLANC)
        body.pack(fill="both", expand=True, padx=8, pady=8)

        tk.Label(
            body,
            text="Vue: chaque ligne affiche le nombre de fois qu'une competence est vue en seance.",
            bg=BLANC,
            fg="#666",
            font=("Segoe UI", 9, "italic"),
            anchor="w",
        ).pack(fill="x", padx=8, pady=(6, 2))

        tk.Label(
            body,
            textvariable=self.var_resume,
            bg=BLANC,
            fg=TEXTE,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill="x", padx=8, pady=(0, 6))

        columns = ("code", "libelle", "vues", "statut")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", height=18)
        self.tree.heading("code", text="Code")
        self.tree.heading("libelle", text="Competence")
        self.tree.heading("vues", text="Vues")
        self.tree.heading("statut", text="Statut")

        self.tree.column("code", width=90, stretch=False, anchor="center")
        self.tree.column("libelle", width=640, stretch=True, anchor="w")
        self.tree.column("vues", width=80, stretch=False, anchor="center")
        self.tree.column("statut", width=140, stretch=False, anchor="center")

        sb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)

        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=6)
        sb.pack(side="right", fill="y", padx=(0, 8), pady=6)

        self.tree.tag_configure("low", foreground="#9C1C1C")
        self.tree.tag_configure("ok", foreground=VERT)
        self.tree.tag_configure("over", foreground="#1F5FA7")

    def _normalize_level(self, raw_level):
        txt = str(raw_level or "").strip()
        if not txt:
            return ""
        if txt in NIVEAU_GROUPE:
            return str(NIVEAU_GROUPE.get(txt, txt)).strip()

        low = txt.lower().replace("è", "e").replace("é", "e")
        if low in {
            "it", "i2d", "it/i2d", "1ere", "1ere it", "1ere i2d",
            "1ere it/i2d", "1ere it-i2d", "1ere it i2d",
        }:
            return "1ère"
        if low in {"2i2d", "terminale 2i2d", "terminale"}:
            return "Terminale"
        return txt

    def _planning_sequences(self):
        path = self.data_dir / "planning.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def _available_levels(self):
        ordered = []
        seen = set()

        for cls in self.classes_options:
            n = self._normalize_level(cls)
            if not n:
                continue
            key = n.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(n)

        for seq in self._planning_sequences():
            n = self._normalize_level((seq or {}).get("classe", ""))
            if not n:
                continue
            key = n.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(n)

        return ordered

    def _compute_usage(self, target_level):
        usage = {}
        target_key = str(target_level or "").strip().lower()
        if not target_key:
            return usage

        for seq in self._planning_sequences():
            if not isinstance(seq, dict):
                continue
            seq_level = self._normalize_level(seq.get("classe", ""))
            if seq_level.lower() != target_key:
                continue

            semaines = seq.get("semaines", {}) or {}
            if not isinstance(semaines, dict):
                continue

            for week_data in semaines.values():
                seances = (week_data or {}).get("seances", [])
                if not isinstance(seances, list):
                    continue
                for seance in seances:
                    for code in (seance or {}).get("competences_visees", []) or []:
                        code = str(code or "").strip()
                        if code:
                            usage[code] = usage.get(code, 0) + 1
        return usage

    def _comp_sort_key(self, code):
        txt = str(code or "")
        m = re.match(r"^CO?(\d+)(?:\.(\d+))?$", txt, flags=re.IGNORECASE)
        if m:
            return (int(m.group(1)), int(m.group(2) or 0), txt)
        return (999, 999, txt)

    def _refresh_all(self):
        levels = self._available_levels()
        self.cb_niveau.configure(values=levels)

        current = str(self.var_niveau.get() or "").strip()
        if not current and levels:
            self.var_niveau.set(levels[0])
        elif current and current not in levels:
            self.var_niveau.set(levels[0] if levels else "")

        self._refresh_table()

    def _refresh_table(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        level = str(self.var_niveau.get() or "").strip()
        if not level:
            self.var_resume.set("Aucun niveau detecte.")
            return

        usage = self._compute_usage(level)
        comp_data = (self.ref_comp or {}).get("competences", {})

        codes = sorted(comp_data.keys(), key=self._comp_sort_key)
        ok_count = 0
        for code in codes:
            co = comp_data.get(code, {}) or {}
            lib = str(co.get("libelle", "-")).strip()
            count = int(usage.get(code, 0))

            if count < 3:
                statut = "A renforcer"
                tag = "low"
            elif count == 3:
                statut = "Objectif atteint"
                tag = "ok"
                ok_count += 1
            else:
                statut = "Au-dela de 3"
                tag = "over"
                ok_count += 1

            self.tree.insert(
                "",
                "end",
                values=(code, lib, f"{count}/3", statut),
                tags=(tag,),
            )

        total = len(codes)
        self.var_resume.set(
            f"Niveau: {level}  |  Competences a 3 vues ou plus: {ok_count}/{total}"
        )
