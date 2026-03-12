import json
import re
import tkinter as tk
from tkinter import ttk

from constants import BLEU, GRIS2, BLANC, TEXTE


def _c_code_key(code):
    m = re.search(r"(\d+)", str(code))
    return int(m.group(1)) if m else 999


def _task_code_key(code):
    m = re.match(r"^A(\d+)-T(\d+)$", str(code), re.IGNORECASE)
    if not m:
        return (999, 999)
    return (int(m.group(1)), int(m.group(2)))


def _co_code_key(code):
    m = re.match(r"^CO(\d+)(?:\.(\d+))?$", str(code), re.IGNORECASE)
    if not m:
        return (999, 999)
    return (int(m.group(1)), int(m.group(2) or 0))


def _build_c_to_co_map_from_comp(ref_comp):
    mapping = {}
    comp_data = (ref_comp or {}).get("competences", {})
    for co_code in comp_data.keys():
        m = re.match(r"^CO(\d+)(?:\.\d+)?$", str(co_code), re.IGNORECASE)
        if not m:
            continue
        c_code = f"C{int(m.group(1))}"
        mapping.setdefault(c_code, []).append(co_code)
    for c_code in mapping:
        mapping[c_code].sort(key=_co_code_key)
    return mapping


class MatriceBTSDialog(tk.Toplevel):
    def __init__(self, parent, ref_at, ref_comp, on_save):
        super().__init__(parent)
        self.title("Matrice BTS - Taches / Competences")
        self.geometry("1280x760")
        self.minsize(1080, 620)
        self.configure(bg=BLANC)
        self.grab_set()

        self._on_save = on_save
        # Copie defensive pour eviter toute mutation tant qu'on n'a pas sauvegarde.
        self.ref_at = json.loads(json.dumps(ref_at or {}, ensure_ascii=False))
        self.ref_comp = ref_comp or {}

        matrix = self.ref_at.get("matrice_competences", {})
        self.source_page = matrix.get("source_page")
        self.c_codes = list(matrix.get("competences", []))
        self.c_codes.sort(key=_c_code_key)
        self.task_data = dict(matrix.get("taches", {}))

        self.c_to_co = self.ref_at.get("correspondance_competences") or _build_c_to_co_map_from_comp(self.ref_comp)
        self.columns = ["task", "activite", "co_detaillees"] + self.c_codes

        self._edit_widget = None
        self._edit_item = None
        self._edit_col = None

        self._build()
        self._load_rows()

    def _build(self):
        hdr = tk.Frame(self, bg=BLEU)
        hdr.pack(fill="x")
        title = "Matrice BTS - Relations taches / competences"
        tk.Label(hdr, text=title, bg=BLEU, fg=BLANC, font=("Segoe UI", 12, "bold"), pady=8).pack(side="left", padx=10)

        if self.source_page:
            tk.Label(
                hdr,
                text=f"Source PDF: page {self.source_page}",
                bg=BLEU,
                fg="#D6E8FF",
                font=("Segoe UI", 9),
            ).pack(side="right", padx=12)

        info = tk.Label(
            self,
            text="Double-cliquez une cellule Cn pour modifier le niveau (1/2/3).",
            bg=BLANC,
            fg="#666",
            font=("Segoe UI", 9),
            anchor="w",
            padx=10,
            pady=6,
        )
        info.pack(fill="x")

        frm = tk.Frame(self, bg=BLANC)
        frm.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        sb_y = ttk.Scrollbar(frm, orient="vertical")
        sb_x = ttk.Scrollbar(frm, orient="horizontal")
        sb_y.pack(side="right", fill="y")
        sb_x.pack(side="bottom", fill="x")

        self.tree = ttk.Treeview(
            frm,
            columns=self.columns,
            show="headings",
            yscrollcommand=sb_y.set,
            xscrollcommand=sb_x.set,
        )
        self.tree.pack(fill="both", expand=True)
        sb_y.config(command=self.tree.yview)
        sb_x.config(command=self.tree.xview)

        self.tree.heading("task", text="Tache")
        self.tree.heading("activite", text="Activite")
        self.tree.heading("co_detaillees", text="CO detaillees")
        self.tree.column("task", width=90, stretch=False, anchor="w")
        self.tree.column("activite", width=70, stretch=False, anchor="center")
        self.tree.column("co_detaillees", width=340, stretch=True, anchor="w")

        for c in self.c_codes:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=54, minwidth=46, stretch=False, anchor="center")

        self.tree.bind("<Double-Button-1>", self._on_double_click)
        self.tree.bind("<Button-1>", self._close_editor)

        btns = tk.Frame(self, bg=GRIS2, pady=8)
        btns.pack(fill="x", side="bottom")
        tk.Button(
            btns,
            text="Sauvegarder",
            command=self._save,
            bg=BLEU,
            fg=BLANC,
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=5,
        ).pack(side="right", padx=(0, 10))
        tk.Button(
            btns,
            text="Fermer",
            command=self.destroy,
            bg="#DDD",
            fg=TEXTE,
            relief="flat",
            font=("Segoe UI", 10),
            padx=10,
            pady=5,
        ).pack(side="right", padx=8)

    def _load_rows(self):
        self.tree.delete(*self.tree.get_children())
        for t_code in sorted(self.task_data.keys(), key=_task_code_key):
            t = self.task_data.get(t_code, {})
            activite = t.get("activite", "")
            niveaux = t.get("niveaux", {})
            co_det = t.get("competences_detaillees", [])
            if not co_det:
                merged = []
                for c in t.get("competences", []):
                    for co in self.c_to_co.get(c, []):
                        if co not in merged:
                            merged.append(co)
                co_det = merged

            values = [t_code, activite, ", ".join(co_det)]
            for c in self.c_codes:
                values.append(str(niveaux.get(c, "")).strip())
            self.tree.insert("", "end", values=values)

    def _close_editor(self, _event=None):
        if self._edit_widget is not None:
            try:
                self._edit_widget.destroy()
            except Exception:
                pass
        self._edit_widget = None
        self._edit_item = None
        self._edit_col = None

    def _on_double_click(self, event):
        self._close_editor()
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        item = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if not item or not col_id:
            return
        col_idx = int(col_id[1:]) - 1
        if col_idx < 0 or col_idx >= len(self.columns):
            return
        col_name = self.columns[col_idx]
        if col_name not in self.c_codes:
            return

        bbox = self.tree.bbox(item, col_id)
        if not bbox:
            return
        x, y, w, h = bbox
        vals = list(self.tree.item(item, "values"))
        current = vals[col_idx] if col_idx < len(vals) else ""

        cb = ttk.Combobox(self.tree, values=["", "1", "2", "3"], state="readonly", font=("Segoe UI", 9, "bold"))
        cb.set(str(current).strip())
        cb.place(x=x, y=y, width=max(w, 54), height=h)
        cb.focus_set()

        self._edit_widget = cb
        self._edit_item = item
        self._edit_col = col_idx

        def _save(_event=None):
            if self._edit_widget is None:
                return
            if self._edit_item is None or self._edit_col is None:
                self._close_editor()
                return
            v = self._edit_widget.get().strip()
            vals2 = list(self.tree.item(self._edit_item, "values"))
            while len(vals2) <= self._edit_col:
                vals2.append("")
            vals2[self._edit_col] = v
            self.tree.item(self._edit_item, values=vals2)
            self._close_editor()

        cb.bind("<<ComboboxSelected>>", _save)
        cb.bind("<Return>", _save)
        cb.bind("<Escape>", lambda e: self._close_editor())
        cb.bind("<FocusOut>", _save)

    def _save(self):
        matrix = self.ref_at.get("matrice_competences", {})
        matrix["source_page"] = self.source_page
        matrix["competences"] = list(self.c_codes)
        matrix_taches = {}

        for item in self.tree.get_children():
            vals = list(self.tree.item(item, "values"))
            if len(vals) < 2:
                continue
            task_code = str(vals[0]).strip()
            activite = str(vals[1]).strip()
            if not task_code:
                continue

            niveaux = {}
            competences = []
            for idx, c in enumerate(self.c_codes, start=3):
                v = str(vals[idx]).strip() if idx < len(vals) else ""
                if v:
                    niveaux[c] = v
                    competences.append(c)

            co_det = []
            for c in competences:
                for co in self.c_to_co.get(c, []):
                    if co not in co_det:
                        co_det.append(co)

            matrix_taches[task_code] = {
                "activite": activite,
                "competences": competences,
                "niveaux": niveaux,
                "competences_detaillees": co_det,
            }

        matrix["taches"] = matrix_taches
        self.ref_at["matrice_competences"] = matrix
        self.ref_at["correspondance_competences"] = self.c_to_co
        self.ref_at.setdefault("meta", {})["schema"] = "bts_at_v1"

        if self._on_save:
            self._on_save(self.ref_at)
        self.destroy()
