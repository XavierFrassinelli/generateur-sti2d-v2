import tkinter as tk
from tkinter import ttk, messagebox

from constants import BLEU, VERT, GRIS2, BLANC, TEXTE, bind_mousewheel, show_quick_help


def _expand_comp_refs_for_pb(comp_knowledge_refs, pb_knowledge_refs):
    pb_list = list(pb_knowledge_refs or [])
    pb_set = set(pb_list)
    result = []
    for co_ref in comp_knowledge_refs or []:
        co_ref = str(co_ref or "").strip()
        if not co_ref:
            continue
        if co_ref in pb_set and co_ref not in result:
            result.append(co_ref)
            continue
        if "-" not in co_ref:
            prefix = f"{co_ref}-"
            for pb_ref in pb_list:
                if pb_ref.startswith(prefix) and pb_ref not in result:
                    result.append(pb_ref)
    return result


class EleveDialog(tk.Toplevel):
    def __init__(self, parent, pb, ref_comp, ref_conn, classe, callback):
        super().__init__(parent)
        self.title("Document eleve - Selection")
        self.geometry("820x640")
        self.configure(bg=BLANC)
        self.grab_set()
        self.resizable(True, True)
        self.pb = pb
        self.ref_comp = ref_comp
        self.ref_conn = ref_conn
        self.classe = classe
        self.callback = callback
        self.sel_co = {}
        self.sel_conn = {}
        self._build()
        self.bind("<F1>", lambda e: show_quick_help(
            self,
            "Aide - Document eleve",
            [
                "Le titre sera utilise dans le document eleve.",
                "Le nom du fichier est optionnel : laisse vide pour nom auto.",
                "Decochez les competences ou connaissances a exclure.",
                "Au moins une competence doit rester selectionnee.",
            ],
        ))

    def _build(self):
        hdr = tk.Frame(self, bg=BLEU)
        hdr.pack(fill="x")
        tk.Label(
            hdr,
            text="Configurer le document eleve",
            bg=BLEU,
            fg=BLANC,
            font=("Segoe UI", 12, "bold"),
            pady=8,
        ).pack(side="left", padx=10)
        tk.Button(
            hdr,
            text="?",
            command=lambda: show_quick_help(
                self,
                "Aide - Document eleve",
                [
                    "Le titre sera utilise dans le document eleve.",
                    "Le nom du fichier est optionnel : laisse vide pour nom auto.",
                    "Decochez les competences ou connaissances a exclure.",
                    "Au moins une competence doit rester selectionnee.",
                ],
            ),
            bg="#2F5E9A",
            fg=BLANC,
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            width=3,
        ).pack(side="right", padx=8, pady=6)

        frm_titre = tk.Frame(self, bg=BLANC, padx=15, pady=8)
        frm_titre.pack(fill="x")
        tk.Label(frm_titre, text="Titre de la seance :", bg=BLANC, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.var_titre = tk.StringVar(value=self.pb["titre"])
        tk.Entry(frm_titre, textvariable=self.var_titre, font=("Segoe UI", 11), width=52).pack(side="left", padx=10)

        frm_file = tk.Frame(self, bg=BLANC, padx=15, pady=2)
        frm_file.pack(fill="x")
        tk.Label(frm_file, text="Nom du fichier (.docx) :", bg=BLANC, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.var_filename = tk.StringVar(value="")
        tk.Entry(frm_file, textvariable=self.var_filename, font=("Segoe UI", 10), width=52).pack(side="left", padx=10)
        tk.Label(
            frm_file,
            text="(optionnel)",
            bg=BLANC,
            fg="#666",
            font=("Segoe UI", 9),
        ).pack(side="left")

        tk.Label(
            self,
            text="Selectionnez les competences et connaissances a inclure :",
            bg=BLANC,
            font=("Segoe UI", 10),
            fg="#555",
            pady=4,
        ).pack(anchor="w", padx=15)

        canvas_frm = tk.Frame(self, bg=BLANC)
        canvas_frm.pack(fill="both", expand=True, padx=15, pady=5)
        canvas = tk.Canvas(canvas_frm, bg=BLANC, bd=0, highlightthickness=0)
        sb = ttk.Scrollbar(canvas_frm, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=BLANC)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_configure(_e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(win_id, width=canvas.winfo_width())

        inner.bind("<Configure>", on_configure)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))

        comp_data = self.ref_comp.get("competences", {})

        for code in self.pb["competences"]:
            co = comp_data.get(code, {})

            frm_co = tk.Frame(inner, bg=GRIS2, highlightbackground="#DADCE0", highlightthickness=1)
            frm_co.pack(fill="x", pady=(6, 2), padx=4)
            var_co = tk.BooleanVar(value=True)
            self.sel_co[code] = var_co
            tk.Checkbutton(frm_co, variable=var_co, bg=GRIS2, activebackground=GRIS2).pack(side="left", padx=6)
            tk.Label(
                frm_co,
                text=f"{code}",
                bg=BLEU,
                fg=BLANC,
                font=("Segoe UI", 10, "bold"),
                padx=8,
                pady=4,
            ).pack(side="left")
            tk.Label(
                frm_co,
                text=f"  {co.get('libelle', '---')[:80]}",
                bg=GRIS2,
                fg=TEXTE,
                font=("Segoe UI", 10),
                anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=8)

            self.sel_conn[code] = {}
            for ref in _expand_comp_refs_for_pb(co.get("connaissances", []), self.pb.get("connaissances", [])):
                chap = ref.split("-")[0]
                chap_d = self.ref_conn.get(chap, {})
                sc_d = chap_d.get("sous_chapitres", {}).get(ref, {})
                titre = sc_d.get("titre") or chap_d.get("titre", ref)
                var_cn = tk.BooleanVar(value=True)
                self.sel_conn[code][ref] = var_cn
                frm_cn = tk.Frame(inner, bg=BLANC)
                frm_cn.pack(fill="x", padx=28, pady=1)
                tk.Checkbutton(frm_cn, variable=var_cn, bg=BLANC, activebackground=BLANC).pack(side="left", padx=4)
                tk.Label(
                    frm_cn,
                    text=f"{ref}",
                    bg=BLANC,
                    fg=BLEU,
                    font=("Consolas", 9, "bold"),
                    width=6,
                ).pack(side="left")
                tk.Label(frm_cn, text=titre, bg=BLANC, fg=TEXTE, font=("Segoe UI", 9), anchor="w").pack(side="left", padx=4)

        bind_mousewheel(canvas, inner)

        frm_btn = tk.Frame(self, bg=BLANC, pady=10)
        frm_btn.pack(fill="x", padx=15)
        tk.Button(
            frm_btn,
            text="Tout selectionner",
            command=self._select_all,
            bg="#EEE",
            fg=TEXTE,
            relief="flat",
            font=("Segoe UI", 10),
        ).pack(side="left", padx=5)
        tk.Button(
            frm_btn,
            text="Tout decocher",
            command=self._deselect_all,
            bg="#EEE",
            fg=TEXTE,
            relief="flat",
            font=("Segoe UI", 10),
        ).pack(side="left", padx=5)
        tk.Button(
            frm_btn,
            text="Generer le document eleve",
            command=self._confirmer,
            bg=VERT,
            fg=BLANC,
            relief="flat",
            font=("Segoe UI", 11, "bold"),
            pady=7,
        ).pack(side="right", padx=5)
        tk.Button(
            frm_btn,
            text="Annuler",
            command=self.destroy,
            bg="#DDD",
            fg=TEXTE,
            relief="flat",
            font=("Segoe UI", 10),
        ).pack(side="right", padx=5)

    def _select_all(self):
        for v in self.sel_co.values():
            v.set(True)
        for d in self.sel_conn.values():
            for v in d.values():
                v.set(True)

    def _deselect_all(self):
        for v in self.sel_co.values():
            v.set(False)
        for d in self.sel_conn.values():
            for v in d.values():
                v.set(False)

    def _confirmer(self):
        selections = []
        for code, var_co in self.sel_co.items():
            if not var_co.get():
                continue
            conns = [ref for ref, var in self.sel_conn.get(code, {}).items() if var.get()]
            selections.append({"code": code, "connaissances": conns})
        if not selections:
            messagebox.showwarning("Selection vide", "Selectionnez au moins une competence.")
            return
        titre = self.var_titre.get().strip() or self.pb["titre"]
        output_filename = self.var_filename.get().strip()
        self.destroy()
        self.callback(titre, selections, output_filename)
