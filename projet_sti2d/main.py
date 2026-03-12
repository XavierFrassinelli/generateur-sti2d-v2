"""
Générateur STI2D — Application principale
Interface Tkinter — deux modes : Fiche de préparation | Document élève
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import json, os, subprocess, sys
from planning import PlanningTab
from couverture_tab import CouvertureTab
from editeur_themes import EditeurThemesTab
from eleve_dialog import EleveDialog
from gestionnaire_profils import ProfilSelecteur, load_profil_meta
from bts_matrice_dialog import MatriceBTSDialog
from pathlib import Path
from constants import BLEU, ORANGE, VERT, GRIS, GRIS2, BLANC, TEXTE, show_quick_help

# ─── Chemins ─────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
DATA_DIR    = BASE_DIR / "data"
IMG_DIR     = BASE_DIR / "img"
OUTPUT_DIR  = BASE_DIR / "output"
CONFIG_FILE = BASE_DIR / "config.json"
DEFAULT_OUTPUT = str(OUTPUT_DIR)


def load_json(filename):
    p = DATA_DIR / filename
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def load_config():
    defaults = {
        "output_dir":        DEFAULT_OUTPUT,
        "last_output_dir":   "",
        "ask_output_dir_each_generation": True,
        "classe":            "1ère IT/I2D",
        "etablissement":     "",
        "logo_etablissement": "",
        "logo_specialite":   "",
        "periodes":          [["P1",1,7],["P2",8,15],["P3",16,22],["P4",23,30],["P5",31,36]],
    }
    if CONFIG_FILE.exists():
        saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        defaults.update(saved)
    return defaults


def _knowledge_matches_competence(knowledge_ref, comp_knowledge_refs):
    ref = str(knowledge_ref or "").strip()
    if not ref:
        return False
    chap = ref.split("-", 1)[0]
    for co_ref in comp_knowledge_refs or []:
        co_ref = str(co_ref or "").strip()
        if not co_ref:
            continue
        if ref == co_ref:
            return True
        if "-" not in co_ref and chap == co_ref:
            return True
    return False


def _detect_profile_schema(meta, profil_dir):
    """Retourne le schema d'un profil: 'sti2d', 'bts' ou 'generic'."""
    schema = str(meta.get("schema", "")).strip().lower()
    if schema:
        return schema

    pid = str(meta.get("id", "")).strip().lower()
    pname = str(meta.get("nom", "")).strip().lower()
    dname = str(getattr(profil_dir, "name", "")).strip().lower()
    hint = " ".join([pid, pname, dname])
    if "sti2d" in hint:
        return "sti2d"
    if "bts" in hint:
        return "bts"
    return "generic"


# ─── App principale ───────────────────────────────────────────────────────────
class AppSTI2D(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Générateur STI2D")
        self.geometry("1200x760")
        self.minsize(960, 620)
        self.configure(bg=GRIS)

        self.cfg              = load_config()
        self.themes_officiels = load_json("themes_problematiques.json") or []
        _tc = load_json("themes_custom.json")
        self.themes_custom    = _tc if isinstance(_tc, list) else []
        self.themes           = list(self.themes_officiels) + self.themes_custom
        self.ref_comp         = load_json("referentiel_competences.json")
        self.ref_conn         = load_json("referentiel_connaissances.json")
        self.ref_at           = {}
        self.ref_comp_path    = DATA_DIR / "referentiel_competences.json"
        self.ref_conn_path    = DATA_DIR / "referentiel_connaissances.json"
        self.ref_at_path      = DATA_DIR / "referentiel_activites_types.json"
        self.themes_custom_path = DATA_DIR / "themes_custom.json"
        self.profil_schema    = "sti2d"
        self.profil_nom       = "STI2D"
        self.current_theme = None
        self.current_pb    = None

        self._build_ui()
        self.bind("<F1>", lambda e: self._show_help_main())
        self._load_active_profile_on_startup()
        self._refresh_themes()

    def _load_active_profile_on_startup(self):
        profil_path = self.cfg.get("profil_actif", "")
        if not profil_path:
            return
        p = Path(profil_path)
        if not p.exists():
            return
        try:
            self._on_profil_selected(p)
        except Exception:
            pass

    def _build_ui(self):
        # Bandeau
        header = tk.Frame(self, bg=BLEU, height=58)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="🎓  Générateur STI2D",
                 bg=BLEU, fg=BLANC, font=("Segoe UI", 17, "bold")).pack(side="left", padx=20, pady=8)
        tk.Button(header, text="?", command=self._show_help_main,
              bg="#2F5E9A", fg=BLANC, relief="flat",
              font=("Segoe UI", 10, "bold"), width=3, pady=5
              ).pack(side="right", padx=(0, 8), pady=10)
        tk.Button(header, text="⚙  Paramètres", command=self._open_params,
                  bg=ORANGE, fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10, pady=5
                  ).pack(side="right", padx=8, pady=10)
        self.btn_matrice_bts = tk.Button(
            header,
            text="🧩  Matrice BTS",
            command=self._open_matrice_bts,
            bg="#6A1B9A", fg=BLANC, relief="flat",
            font=("Segoe UI", 10, "bold"), padx=10, pady=5,
            state="disabled",
        )
        self.btn_matrice_bts.pack(side="right", padx=(0, 8), pady=10)
        tk.Button(header, text="📚  Référentiels", command=self._open_gestionnaire,
                  bg="#2A6DB5", fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10, pady=5
                  ).pack(side="right", padx=(0, 0), pady=10)

        # ── Notebook (onglets) ─────────────────────────────────────────────────
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(4,8))

        # Onglet Séquence
        self.tab_themes = None    # initialisé au premier affichage
        self._tab_themes_frame = tk.Frame(self.notebook, bg=GRIS)
        self.notebook.add(self._tab_themes_frame, text="  🎨  Séquence  ")

        # Onglet Planning
        self.tab_planning = None  # initialisé au premier affichage
        self._tab_planning_frame = tk.Frame(self.notebook, bg=GRIS)
        self.notebook.add(self._tab_planning_frame, text="  📅  Planning  ")

        # Onglet Générateur
        tab_gen = tk.Frame(self.notebook, bg=GRIS)
        self.notebook.add(tab_gen, text="  🎓  Générateur  ")

        # Onglet Couverture
        self.tab_couverture = None  # initialisé au premier affichage
        self._tab_couverture_frame = tk.Frame(self.notebook, bg=GRIS)
        self.notebook.add(self._tab_couverture_frame, text="  📊  Couverture  ")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

        body = tab_gen
        body.configure(bg=GRIS)
        # Layout interne de l'onglet générateur
        body_inner = tk.Frame(body, bg=GRIS)
        body_inner.pack(fill="both", expand=True, padx=12, pady=12)
        body = body_inner

        # ── Colonne gauche ─────────────────────────────────────────────────────
        left = tk.Frame(body, bg=BLANC,
                        highlightbackground="#DADCE0", highlightthickness=1)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)
        left.configure(width=300)

        tk.Label(left, text="Sélection séquence",
                 bg=BLEU, fg=BLANC, font=("Segoe UI", 10, "bold"), pady=7
                 ).pack(fill="x")

        frm_niv = tk.LabelFrame(left, text=" Niveau ", bg=BLANC,
                                font=("Segoe UI", 9), fg=TEXTE, pady=5)
        frm_niv.pack(fill="x", padx=8, pady=(8, 4))
        self.var_classe = tk.StringVar(value=self.cfg.get("classe", "1ère IT/I2D"))
        classes = ["1ère IT", "1ère I2D", "1ère IT/I2D", "Terminale 2I2D"]
        self.cb_classe = ttk.Combobox(frm_niv, textvariable=self.var_classe,
                                      values=classes, state="readonly", font=("Segoe UI", 10))
        self.cb_classe.pack(fill="x", padx=6)
        self.cb_classe.bind("<<ComboboxSelected>>", lambda e: self._on_theme_select())

        frm_t = tk.LabelFrame(left, text=" Séquence ", bg=BLANC,
                               font=("Segoe UI", 9), fg=TEXTE, pady=5)
        frm_t.pack(fill="x", padx=8, pady=4)
        self.lb_themes = tk.Listbox(frm_t, height=8, selectmode="single",
                                    font=("Segoe UI", 10), bg="#FAFAFA",
                                    selectbackground=BLEU, selectforeground=BLANC,
                                    relief="flat", bd=0, activestyle="none")
        self.lb_themes.pack(fill="x", padx=4, pady=4)
        self.lb_themes.bind("<<ListboxSelect>>", lambda e: self._on_theme_select())

        frm_p = tk.LabelFrame(left, text=" Problématique ", bg=BLANC,
                               font=("Segoe UI", 9), fg=TEXTE, pady=5)
        frm_p.pack(fill="x", padx=8, pady=4)
        self.lb_pbs = tk.Listbox(frm_p, height=5, selectmode="single",
                                  font=("Segoe UI", 10), bg="#FAFAFA",
                                  selectbackground=ORANGE, selectforeground=BLANC,
                                  relief="flat", bd=0, activestyle="none")
        self.lb_pbs.pack(fill="x", padx=4, pady=4)
        self.lb_pbs.bind("<<ListboxSelect>>", lambda e: self._on_pb_select())

        tk.Label(left, text="Type de document", bg=BLANC,
                 font=("Segoe UI", 9, "bold"), fg=TEXTE).pack(pady=(8, 2))
        tk.Button(left, text="📋  Fiche de préparation",
                  command=lambda: self._generer("preparation"),
                  bg=BLEU, fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), pady=7
                  ).pack(fill="x", padx=8, pady=2)
        tk.Button(left, text="📄  Document élève",
                  command=self._open_eleve_dialog,
                  bg=VERT, fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), pady=7
                  ).pack(fill="x", padx=8, pady=(2, 10))

        # ── Colonne droite ─────────────────────────────────────────────────────
        right = tk.Frame(body, bg=BLANC,
                         highlightbackground="#DADCE0", highlightthickness=1)
        right.pack(side="left", fill="both", expand=True)
        tk.Label(right, text="Aperçu de la séquence",
                 bg=BLEU, fg=BLANC, font=("Segoe UI", 10, "bold"), pady=7
                 ).pack(fill="x")

        frm_txt = tk.Frame(right, bg=BLANC)
        frm_txt.pack(fill="both", expand=True, padx=10, pady=10)
        sb = ttk.Scrollbar(frm_txt)
        sb.pack(side="right", fill="y")
        self.txt = tk.Text(frm_txt, font=("Consolas", 10), bg="#FAFAFA", fg=TEXTE,
                           wrap="word", relief="flat", yscrollcommand=sb.set,
                           state="disabled", padx=12, pady=10)
        self.txt.pack(fill="both", expand=True)
        sb.config(command=self.txt.yview)
        self.txt.tag_config("titre",   font=("Segoe UI", 13, "bold"),  foreground=BLEU)
        self.txt.tag_config("section", font=("Segoe UI", 11, "bold"),  foreground=ORANGE)
        self.txt.tag_config("label",   font=("Segoe UI", 10, "bold"),  foreground=TEXTE)
        self.txt.tag_config("code",    font=("Consolas", 10),          foreground="#555555")
        self.txt.tag_config("niv",     font=("Segoe UI", 9, "italic"), foreground=VERT)
        self.txt.tag_config("info",    font=("Segoe UI", 9, "italic"), foreground="#888888")

        self.status = tk.StringVar(value="Sélectionnez une séquence puis une problématique")
        tk.Label(self, textvariable=self.status, bg="#E8EAF0", fg="#555",
                 font=("Segoe UI", 9), anchor="w", pady=3, padx=10
                 ).pack(fill="x", side="bottom")

    # ── Données ───────────────────────────────────────────────────────────────
    def _refresh_themes(self):
        self.lb_themes.delete(0, "end")
        for t in self.themes:
            self.lb_themes.insert("end", f"  {t['id']}  {t['titre']}")

    def _on_theme_select(self):
        sel = self.lb_themes.curselection()
        if not sel:
            return
        self.current_theme = self.themes[sel[0]]
        self.lb_pbs.delete(0, "end")
        classe = self.var_classe.get()
        for pb in self.current_theme["problematiques"]:
            niv = pb.get("niveau", "")
            if "Terminale" in classe and niv not in ("2I2D", "IT/I2D", ""):
                continue
            if classe == "1ère IT" and niv == "I2D":
                continue
            if classe == "1ère I2D" and niv == "IT":
                continue
            badge = f"[{niv}] " if niv else ""
            self.lb_pbs.insert("end", f"  {badge}{pb['titre']}")
        self._write_apercu([("titre", f"🎯  {self.current_theme['titre']}\n\n"),
                            ("info",  "Cliquez sur une problématique...\n")])

    def _on_pb_select(self):
        sel = self.lb_pbs.curselection()
        if not sel or not self.current_theme:
            return
        txt = self.lb_pbs.get(sel[0]).strip()
        for pb in self.current_theme["problematiques"]:
            if pb["titre"] in txt:
                self.current_pb = pb
                break
        self._show_apercu()

    def _show_apercu(self):
        if not self.current_pb or not self.current_theme:
            return
        t  = self.current_theme
        pb = self.current_pb
        comp_data = self.ref_comp.get("competences", {})
        lines = [
            ("titre",   f"🎯  {t['titre']}\n\n"),
            ("section", f"Problématique\n"),
            ("label",   f"  {pb['titre']}\n\n"),
            ("section", f"Compétences  [{pb.get('niveau','')}]\n"),
        ]
        for code in pb["competences"]:
            co = comp_data.get(code, {})
            niv = co.get("niveaux", {})
            niv_str = "  ".join(f"{k}:{v}" for k, v in niv.items() if v)
            lines += [
                ("code",  f"  {code}  "),
                ("niv",   f"[{niv_str}]\n"),
                ("",      f"    {co.get('libelle','—')}\n\n"),
            ]
        lines.append(("section", "Connaissances associées\n"))
        for ref in pb["connaissances"]:
            chap = ref.split("-")[0]
            chap_d = self.ref_conn.get(chap, {})
            sc_d   = chap_d.get("sous_chapitres", {}).get(ref, {})
            titre  = sc_d.get("titre") or chap_d.get("titre", "—")
            lines += [("code", f"  {ref}  "), ("", f"{titre}\n")]
        lines.append(("info", f"\n  Classe : {self.var_classe.get()}"))
        self._write_apercu(lines)
        self.status.set(f"Prêt — {pb['titre']}")

    def _write_apercu(self, lines):
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        for tag, txt in lines:
            if tag:
                self.txt.insert("end", txt, tag)
            else:
                self.txt.insert("end", txt)
        self.txt.config(state="disabled")

    # ── Génération ────────────────────────────────────────────────────────────
    def _resolve_last_output_dir(self):
        out_raw = str(self.cfg.get("last_output_dir", "")).strip()
        if not out_raw:
            return None
        out_path = Path(out_raw).expanduser()
        if not out_path.is_absolute():
            out_path = (BASE_DIR / out_path).resolve()
        return out_path

    def _resolve_default_output_dir(self):
        out_raw = str(self.cfg.get("output_dir", DEFAULT_OUTPUT)).strip() or DEFAULT_OUTPUT
        out_path = Path(out_raw).expanduser()
        if not out_path.is_absolute():
            out_path = (BASE_DIR / out_path).resolve()
        return out_path

    def _remember_last_output_dir(self, output_dir):
        path_str = str(output_dir or "").strip()
        if not path_str:
            return
        if self.cfg.get("last_output_dir") == path_str:
            return
        self.cfg["last_output_dir"] = path_str
        save_config(self.cfg)

    def _choose_output_dir_for_generation(self):
        configured_default = self._resolve_default_output_dir()
        default_path = self._resolve_last_output_dir() or configured_default

        def _pick_custom_target(initial_base):
            selected = filedialog.askdirectory(
                title="Choisir le dossier parent",
                initialdir=str(initial_base if initial_base.exists() else BASE_DIR),
                parent=self,
            )
            if not selected:
                return None

            sub_path = simpledialog.askstring(
                "Arborescence (optionnelle)",
                "Sous-dossier à créer dans ce parent (optionnel).\n"
                "Exemple : Terminale/2i2d/Réseau/TD",
                parent=self,
            )
            if sub_path is None:
                return None
            sub_path = sub_path.strip().replace("\\", "/")
            return Path(selected) / sub_path if sub_path else Path(selected)

        ask_each_generation = bool(self.cfg.get("ask_output_dir_each_generation", True))

        if ask_each_generation:
            use_default = messagebox.askyesnocancel(
                "Dossier de sortie",
                "Utiliser le dernier dossier de sortie pour ce document ?\n\n"
                f"{default_path}\n\n"
                "Oui = utiliser ce dossier\n"
                "Non = choisir/créer un autre dossier\n"
                "Annuler = annuler la génération",
                parent=self,
            )
            if use_default is None:
                return None
            target = default_path if use_default else _pick_custom_target(default_path)
            if target is None:
                return None
        else:
            target = default_path

        try:
            target.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            if not ask_each_generation:
                messagebox.showwarning(
                    "Dossier indisponible",
                    f"Le dossier mémorisé est inaccessible :\n{target}\n\n"
                    "Sélectionnez un autre dossier pour continuer.",
                    parent=self,
                )
                target = _pick_custom_target(configured_default)
                if target is None:
                    return None
                try:
                    target.mkdir(parents=True, exist_ok=True)
                except Exception as exc2:
                    messagebox.showerror(
                        "Dossier invalide",
                        f"Impossible de créer/accéder au dossier :\n{target}\n\n{exc2}",
                        parent=self,
                    )
                    return None
            else:
                messagebox.showerror(
                    "Dossier invalide",
                    f"Impossible de créer/accéder au dossier :\n{target}\n\n{exc}",
                    parent=self,
                )
                return None
        target_str = str(target)
        self._remember_last_output_dir(target_str)
        return target_str

    def _build_payload(self, mode, extra=None):
        if not self.current_pb:
            messagebox.showwarning("Sélection manquante",
                                   "Sélectionnez d'abord une séquence et une problématique.")
            return None
        output_dir = self.cfg.get("output_dir", DEFAULT_OUTPUT)
        payload = {
            "mode":               mode,
            "schema":             self.profil_schema,
            "theme":              self.current_theme,
            "problematique":      self.current_pb,
            "classe":             self.var_classe.get(),
            "etablissement":      self.cfg.get("etablissement", ""),
            "competences":        self.ref_comp,
            "connaissances":      self.ref_conn,
            "activites_types":    self.ref_at,
            "img_dir":            str(IMG_DIR),
            "output_dir":         output_dir,
            "logo_etablissement": self.cfg.get("logo_etablissement", ""),
            "logo_specialite":    self.cfg.get("logo_specialite", ""),
        }
        if extra:
            payload.update(extra)
        return payload

    def _run_node(self, payload):
        pfile = BASE_DIR / "_payload.json"
        pfile.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        gen = str(BASE_DIR / "generateur.js")
        try:
            r = subprocess.run(["node", gen, str(pfile)],
                               capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                out = r.stdout.strip()
                self.status.set(f"✅  {out}")
                if messagebox.askyesno("Succès", f"Document généré !\n\n{out}\n\nOuvrir le dossier ?"):
                    self._open_folder(payload["output_dir"])
            else:
                messagebox.showerror("Erreur", r.stderr or "Erreur inconnue")
        except FileNotFoundError:
            messagebox.showerror("Node.js manquant", "Node.js introuvable.\nhttps://nodejs.org")
        except subprocess.TimeoutExpired:
            messagebox.showerror("Timeout", "Génération trop longue.")
        finally:
            pfile.unlink(missing_ok=True)

    def _generer(self, mode):
        output_dir = self._choose_output_dir_for_generation()
        if not output_dir:
            return
        extra = {"output_dir": output_dir}
        if mode == "preparation":
            suggested_name = str(self.current_pb.get("titre", "")).strip() if self.current_pb else ""
            filename_input = simpledialog.askstring(
                "Nom du fichier",
                "Nom du fichier .docx (optionnel) :\n"
                "Laisser vide pour utiliser le nom automatique.",
                initialvalue=suggested_name,
                parent=self,
            )
            if filename_input is None:
                return
            extra["output_filename"] = filename_input.strip()
        p = self._build_payload(mode, extra)
        if p:
            self._run_node(p)

    def _open_eleve_dialog(self):
        if not self.current_pb:
            messagebox.showwarning("Sélection manquante",
                                   "Sélectionnez d'abord une séquence et une problématique.")
            return
        EleveDialog(self, self.current_pb, self.ref_comp, self.ref_conn,
                    self.var_classe.get(), self._generer_eleve)

    def _generer_eleve(self, titre_seance, selections, output_filename=""):
        output_dir = self._choose_output_dir_for_generation()
        if not output_dir:
            return
        extra = {
            "titre_seance":              titre_seance,
            "competences_selectionnees": selections,
            "output_filename":           output_filename,
            "output_dir":                output_dir,
        }
        p = self._build_payload("eleve", extra)
        if p:
            self._run_node(p)

    def _open_folder(self, path):
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _on_tab_change(self, event):
        """Initialise les onglets au premier affichage (lazy init)."""
        tab  = self.notebook.select()
        name = self.notebook.tab(tab, "text")

        if "Planning" in name and self.tab_planning is None:
            self.tab_planning = PlanningTab(
                self._tab_planning_frame,
                self.themes, self.ref_comp, self.ref_conn,
                str(DATA_DIR),
                generer_callback=self._generer_depuis_seance,
                periodes=self.cfg.get("periodes"),
                classes_options=list(self.cb_classe["values"]),
                profile_name=self.profil_nom,
            )
            self.tab_planning.pack(fill="both", expand=True)

        elif "couverture" in name.lower() and self.tab_couverture is None:
            self.tab_couverture = CouvertureTab(
                self._tab_couverture_frame,
                self.ref_comp,
                str(DATA_DIR),
                classes_options=list(self.cb_classe["values"]),
            )
            self.tab_couverture.pack(fill="both", expand=True)

        elif ("sequence" in name.lower() or "séquence" in name.lower()) and self.tab_themes is None:
            self.tab_themes = EditeurThemesTab(
                self._tab_themes_frame,
                self.themes_officiels,
                self.ref_comp,
                self.ref_conn,
                str(DATA_DIR),
                classes_options=list(self.cb_classe["values"]),
                custom_file_path=str(self.themes_custom_path),
                comp_file_path=str(self.ref_comp_path),
                conn_file_path=str(self.ref_conn_path),
                on_themes_updated=self._on_themes_updated,
            )
            self.tab_themes.pack(fill="both", expand=True)

    def _on_themes_updated(self, themes_custom):
        """Rafraîchit la liste fusionnée après modification des séquences custom."""
        self.themes_custom = themes_custom
        self.themes = list(self.themes_officiels) + self.themes_custom
        self._refresh_themes()
        if self.tab_planning is not None:
            self.tab_planning.themes = self.themes

    def _generer_depuis_seance(self, seq, week, seance):
        """Génère un document élève depuis une séance du planning."""
        theme = next((t for t in self.themes if t["id"] == seq.get("theme_id")), None)
        pb    = None
        pb_titre = str(seance.get("pb_titre", "")).strip() or str(seq.get("pb_titre", "")).strip()
        if theme:
            pb = next(
                (p for p in theme["problematiques"] if p["titre"] == pb_titre),
                None,
            )
        if not theme or not pb:
            messagebox.showerror(
                "Données manquantes",
                "Séquence ou problématique introuvable dans le référentiel.",
            )
            return

        comp_data  = self.ref_comp.get("competences", {})
        selections = []
        for co_code in seance.get("competences_visees", []):
            co    = comp_data.get(co_code, {})
            conns = [cn for cn in seance.get("connaissances_abordees", [])
                     if _knowledge_matches_competence(cn, co.get("connaissances", []))]
            selections.append({"code": co_code, "connaissances": conns})

        if not selections:
            messagebox.showwarning(
                "Séance vide", "Cette séance n'a aucune compétence associée."
            )
            return

        # Optional custom output file name for planning-triggered generation.
        suggested_name = str(seance.get("titre", "")).strip()
        filename_input = simpledialog.askstring(
            "Nom du fichier",
            "Nom du fichier .docx (optionnel) :\n"
            "Laisser vide pour utiliser le nom automatique.",
            initialvalue=suggested_name,
            parent=self,
        )
        if filename_input is None:
            return
        output_filename = filename_input.strip()

        output_dir = self._choose_output_dir_for_generation()
        if not output_dir:
            return
        payload = {
            "mode":                      "eleve",
            "schema":                    self.profil_schema,
            "theme":                     theme,
            "problematique":             pb,
            "classe":                    seq.get("classe", ""),
            "etablissement":             self.cfg.get("etablissement", ""),
            "competences":               self.ref_comp,
            "connaissances":             self.ref_conn,
            "activites_types":           self.ref_at,
            "img_dir":                   str(IMG_DIR),
            "output_dir":                output_dir,
            "logo_etablissement":        self.cfg.get("logo_etablissement", ""),
            "logo_specialite":           self.cfg.get("logo_specialite", ""),
            "titre_seance":              seance.get("titre", pb["titre"]),
            "competences_selectionnees": selections,
            "output_filename":           output_filename,
        }
        self._run_node(payload)

    def _open_gestionnaire(self):
        """Ouvre le gestionnaire de référentiels (import / sélection de profil)."""
        ProfilSelecteur(self, on_select=self._on_profil_selected)

    def _update_matrice_button_state(self):
        matrix = (self.ref_at or {}).get("matrice_competences", {})
        has_matrix = isinstance(matrix, dict) and bool(matrix.get("taches"))
        is_bts = (self.profil_schema == "bts")
        state = "normal" if (is_bts and has_matrix) else "disabled"
        self.btn_matrice_bts.configure(state=state)

    def _open_matrice_bts(self):
        if self.profil_schema != "bts":
            messagebox.showinfo("Matrice BTS", "Le profil actif n'est pas un profil BTS.")
            return
        matrix = (self.ref_at or {}).get("matrice_competences", {})
        if not matrix or not matrix.get("taches"):
            messagebox.showwarning(
                "Matrice BTS",
                "Aucune matrice tâches/compétences n'est disponible dans ce profil.",
            )
            return

        dlg = MatriceBTSDialog(
            self,
            ref_at=self.ref_at,
            ref_comp=self.ref_comp,
            on_save=self._on_matrice_bts_saved,
        )
        dlg.focus_set()

    def _on_matrice_bts_saved(self, updated_ref_at):
        self.ref_at = updated_ref_at
        try:
            self.ref_at_path.write_text(
                json.dumps(self.ref_at, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            n_tasks = len((self.ref_at.get("matrice_competences") or {}).get("taches", {}))
            self.status.set(f"Matrice BTS sauvegardée ({n_tasks} tâches).")
        except Exception as e:
            messagebox.showerror("Erreur sauvegarde", str(e))

    def _show_help_main(self):
        show_quick_help(
            self,
            "Aide — Générateur STI2D",
            [
                "Choisissez d'abord un niveau, puis une séquence et une problématique.",
                "Utilisez « Fiche de préparation » pour le document enseignant.",
                "Utilisez « Document élève » pour sélectionner CO/CN à distribuer.",
                    "À chaque génération, vous pouvez choisir/créer le dossier de sortie.",
                "L'onglet Planning sert à répartir les séquences sur les semaines.",
                "Le bouton « Référentiels » permet de changer/importer un profil.",
            ],
        )

    def _on_profil_selected(self, profil_dir):
        """Charge les données d'un profil sélectionné dans le gestionnaire."""
        from pathlib import Path
        profil_dir = Path(profil_dir)
        meta = load_profil_meta(profil_dir)

        def _load(fname):
            p = profil_dir / fname
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

        fich = meta.get("fichiers", {})
        ref_comp = _load(fich.get("competences",   "referentiel_competences.json"))
        ref_conn = _load(fich.get("connaissances",  "referentiel_connaissances.json"))
        ref_at   = _load(fich.get("activites_types", "referentiel_activites_types.json"))
        themes_off = _load(fich.get("themes",       "themes_problematiques.json"))
        if not isinstance(themes_off, list):
            themes_off = []
        _tc = _load("themes_custom.json")
        themes_custom = _tc if isinstance(_tc, list) else []

        self.ref_comp        = ref_comp
        self.ref_conn        = ref_conn
        self.ref_at          = ref_at if isinstance(ref_at, dict) else {}
        self.ref_comp_path   = profil_dir / fich.get("competences", "referentiel_competences.json")
        self.ref_conn_path   = profil_dir / fich.get("connaissances", "referentiel_connaissances.json")
        self.ref_at_path     = profil_dir / fich.get("activites_types", "referentiel_activites_types.json")
        self.themes_custom_path = profil_dir / "themes_custom.json"
        self.themes_officiels = themes_off
        self.themes_custom   = themes_custom
        self.themes          = list(themes_off) + themes_custom
        self.profil_schema   = _detect_profile_schema(meta, profil_dir)

        # Mise à jour de la liste des classes selon le profil
        classes = meta.get("classes", meta.get("niveaux", []))
        if classes:
            self.var_classe.set(classes[0])
            self.cb_classe.configure(values=classes)

        # Titre de la fenêtre
        nom = meta.get("nom", profil_dir.name)
        self.profil_nom = str(nom).strip() or profil_dir.name
        self.title(f"Générateur — {nom}")

        # Reset des onglets lazy-init
        for w in self._tab_planning_frame.winfo_children():
            w.destroy()
        self.tab_planning = None

        for w in self._tab_couverture_frame.winfo_children():
            w.destroy()
        self.tab_couverture = None

        for w in self._tab_themes_frame.winfo_children():
            w.destroy()
        self.tab_themes = None

        self.current_theme = None
        self.current_pb    = None
        self._refresh_themes()
        self._update_matrice_button_state()
        self.status.set(
            f"Référentiel chargé : {nom} (schema: {self.profil_schema}, "
            f"AT: {len(self.ref_at.get('activites', {})) if isinstance(self.ref_at, dict) else 0})"
        )

        # Sauvegarder le profil actif dans la config
        self.cfg["profil_actif"] = str(profil_dir)
        save_config(self.cfg)

    def _open_params(self):
        win = tk.Toplevel(self)
        win.title("Paramètres")
        win.geometry("580x590")
        win.configure(bg=BLANC)
        win.grab_set()

        def _show_help_params():
            show_quick_help(
                win,
                "Aide — Paramètres",
                [
                    "Renseignez établissement et logos si nécessaire.",
                    "Choisissez ou créez le dossier de sortie des documents générés.",
                    "Option possible : demander le dossier à chaque génération.",
                    "Les périodes doivent être continues de S1 à S36.",
                    "Un redémarrage est nécessaire après modification des périodes.",
                ],
            )

        win.bind("<F1>", lambda e: _show_help_params())
        hdr = tk.Frame(win, bg=BLEU)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Paramètres", bg=BLEU, fg=BLANC,
                 font=("Segoe UI", 12, "bold"), pady=8).pack(side="left", padx=10)
        tk.Button(hdr, text="?",
                  command=_show_help_params,
                  bg="#2F5E9A", fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), width=3).pack(side="right", padx=8, pady=6)
        frm = tk.Frame(win, bg=BLANC, padx=20, pady=15)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        def _browse_file(var):
            path = filedialog.askopenfilename(
                title="Choisir un logo",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp"), ("Tous", "*.*")],
                initialdir=str(IMG_DIR),
            )
            if path:
                var.set(path)

        def _reset(var):
            var.set("")

        # ── Ligne 0 : Établissement ──────────────────────────────────────────
        tk.Label(frm, text="Établissement :", bg=BLANC,
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", pady=8)
        var_etab = tk.StringVar(value=self.cfg.get("etablissement", ""))
        tk.Entry(frm, textvariable=var_etab, width=36,
                 font=("Segoe UI", 10)).grid(row=0, column=1, columnspan=2, sticky="ew", padx=10)

        # ── Ligne 1 : Logo établissement ─────────────────────────────────────
        tk.Label(frm, text="Logo établissement :", bg=BLANC,
                 font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w", pady=(8, 0))
        var_logo_etab = tk.StringVar(value=self.cfg.get("logo_etablissement", ""))
        tk.Entry(frm, textvariable=var_logo_etab, width=28,
                 font=("Segoe UI", 9), fg="#555").grid(row=1, column=1, sticky="ew", padx=10)
        frm_btn_etab = tk.Frame(frm, bg=BLANC)
        frm_btn_etab.grid(row=1, column=2, sticky="w")
        tk.Button(frm_btn_etab, text="📂", font=("Segoe UI", 10),
                  command=lambda: _browse_file(var_logo_etab)).pack(side="left")
        tk.Button(frm_btn_etab, text="✕", font=("Segoe UI", 9), fg="#999", relief="flat",
                  command=lambda: _reset(var_logo_etab)).pack(side="left", padx=(4, 0))
        tk.Label(frm, text="Vide = logoVH.png par défaut", bg=BLANC,
                 font=("Segoe UI", 8), fg="#999").grid(row=2, column=1, sticky="w", padx=10)

        # ── Ligne 3 : Logo spécialité ─────────────────────────────────────────
        tk.Label(frm, text="Logo spécialité :", bg=BLANC,
                 font=("Segoe UI", 10)).grid(row=3, column=0, sticky="w", pady=(8, 0))
        var_logo_spe = tk.StringVar(value=self.cfg.get("logo_specialite", ""))
        tk.Entry(frm, textvariable=var_logo_spe, width=28,
                 font=("Segoe UI", 9), fg="#555").grid(row=3, column=1, sticky="ew", padx=10)
        frm_btn_spe = tk.Frame(frm, bg=BLANC)
        frm_btn_spe.grid(row=3, column=2, sticky="w")
        tk.Button(frm_btn_spe, text="📂", font=("Segoe UI", 10),
                  command=lambda: _browse_file(var_logo_spe)).pack(side="left")
        tk.Button(frm_btn_spe, text="✕", font=("Segoe UI", 9), fg="#999", relief="flat",
                  command=lambda: _reset(var_logo_spe)).pack(side="left", padx=(4, 0))
        tk.Label(frm, text="Vide = détection automatique selon la classe", bg=BLANC,
                 font=("Segoe UI", 8), fg="#999").grid(row=4, column=1, sticky="w", padx=10)

        # ── Ligne 5 : Dossier de sortie ───────────────────────────────────────
        tk.Label(frm, text="Dossier de sortie :", bg=BLANC,
                 font=("Segoe UI", 10)).grid(row=5, column=0, sticky="w", pady=8)
        var_out = tk.StringVar(value=self.cfg.get("output_dir", DEFAULT_OUTPUT))
        tk.Entry(frm, textvariable=var_out, width=28,
                 font=("Segoe UI", 10)).grid(row=5, column=1, sticky="ew", padx=10)

        def _browse_output_dir():
            current = var_out.get().strip()
            if os.path.isdir(current):
                initial = current
            elif current:
                initial = os.path.dirname(current)
            else:
                initial = str(BASE_DIR)
            if not os.path.isdir(initial):
                initial = str(BASE_DIR)
            chosen = filedialog.askdirectory(
                title="Choisir le dossier de sortie",
                initialdir=initial,
                parent=win,
            )
            if chosen:
                var_out.set(chosen)

        def _create_output_dir():
            parent_dir = filedialog.askdirectory(
                title="Choisir le dossier parent",
                initialdir=var_out.get().strip() or str(BASE_DIR),
                parent=win,
            )
            if not parent_dir:
                return
            folder_name = simpledialog.askstring(
                "Créer un dossier",
                "Nom du nouveau dossier :",
                parent=win,
            )
            if folder_name is None:
                return
            folder_name = folder_name.strip()
            if not folder_name:
                messagebox.showwarning("Nom manquant", "Entrez un nom de dossier valide.", parent=win)
                return
            target = Path(parent_dir) / folder_name
            try:
                target.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                messagebox.showerror("Création impossible", str(exc), parent=win)
                return
            var_out.set(str(target))
            messagebox.showinfo("Dossier prêt", f"Dossier sélectionné :\n{target}", parent=win)

        out_btns = tk.Frame(frm, bg=BLANC)
        out_btns.grid(row=5, column=2, sticky="w")
        tk.Button(out_btns, text="📂", font=("Segoe UI", 10),
                  command=_browse_output_dir).pack(side="left")
        tk.Button(out_btns, text="➕", font=("Segoe UI", 10),
                  command=_create_output_dir).pack(side="left", padx=(4, 0))

        var_ask_out = tk.BooleanVar(
            value=bool(self.cfg.get("ask_output_dir_each_generation", True))
        )
        tk.Checkbutton(
            frm,
            text="Demander le dossier à chaque génération",
            variable=var_ask_out,
            onvalue=True,
            offvalue=False,
            bg=BLANC,
            activebackground=BLANC,
            font=("Segoe UI", 9),
            anchor="w",
        ).grid(row=6, column=1, columnspan=2, sticky="w", padx=10, pady=(2, 8))

        # ── Séparateur + Périodes académiques ─────────────────────────────────
        ttk.Separator(frm, orient="horizontal").grid(
            row=7, column=0, columnspan=3, sticky="ew", pady=(12, 4))
        tk.Label(frm, text="Périodes académiques", bg=BLANC,
                 font=("Segoe UI", 10, "bold"), fg=BLEU,
                 ).grid(row=8, column=0, columnspan=3, sticky="w", pady=(0, 6))

        _periodes_cfg = self.cfg.get(
            "periodes",
            [["P1",1,7],["P2",8,15],["P3",16,22],["P4",23,30],["P5",31,36]],
        )
        period_vars = []  # list of (nom, IntVar_start, IntVar_end)
        for i, (nom, s, e) in enumerate(_periodes_cfg):
            row = 9 + i
            tk.Label(frm, text=f"{nom} :", bg=BLANC,
                     font=("Segoe UI", 10, "bold")).grid(row=row, column=0, sticky="w", pady=2)
            cell = tk.Frame(frm, bg=BLANC)
            cell.grid(row=row, column=1, columnspan=2, sticky="w", padx=10)
            tk.Label(cell, text="Sem. début", bg=BLANC,
                     font=("Segoe UI", 9), fg="#555").pack(side="left")
            var_s = tk.IntVar(value=s)
            tk.Spinbox(cell, from_=1, to=36, textvariable=var_s, width=4,
                       font=("Segoe UI", 10)).pack(side="left", padx=(4, 12))
            tk.Label(cell, text="Sem. fin", bg=BLANC,
                     font=("Segoe UI", 9), fg="#555").pack(side="left")
            var_e = tk.IntVar(value=e)
            tk.Spinbox(cell, from_=1, to=36, textvariable=var_e, width=4,
                       font=("Segoe UI", 10)).pack(side="left", padx=(4, 0))
            period_vars.append((nom, var_s, var_e))

        tk.Label(frm,
                 text="⚠ Un redémarrage de l'application est nécessaire pour appliquer les changements de périodes.",
                 bg=BLANC, font=("Segoe UI", 8), fg="#888", wraplength=460,
                 ).grid(row=14, column=0, columnspan=3, sticky="w", pady=(4, 0))

        def sauvegarder():
            # Validation des périodes
            periodes_new = []
            for nom, vs, ve in period_vars:
                try:
                    s, e = vs.get(), ve.get()
                except tk.TclError:
                    messagebox.showerror("Périodes invalides",
                                         f"{nom} : valeur non numérique.")
                    return
                periodes_new.append([nom, s, e])
            if periodes_new[0][1] != 1:
                messagebox.showerror("Périodes invalides",
                                     f"P1 doit commencer à S1 (actuellement S{periodes_new[0][1]}).")
                return
            for i in range(len(periodes_new)):
                nom, s, e = periodes_new[i]
                if s > e:
                    messagebox.showerror("Périodes invalides",
                                         f"{nom} : début S{s} > fin S{e}.")
                    return
                if i > 0 and s != periodes_new[i-1][2] + 1:
                    messagebox.showerror(
                        "Périodes invalides",
                        f"{nom} doit commencer à S{periodes_new[i-1][2]+1} "
                        f"(actuellement S{s}).",
                    )
                    return
            if periodes_new[-1][2] != 36:
                messagebox.showerror(
                    "Périodes invalides",
                    f"P5 doit se terminer à S36 (actuellement S{periodes_new[-1][2]}).")
                return

            out_raw = var_out.get().strip()
            if not out_raw:
                messagebox.showerror("Dossier manquant", "Choisissez un dossier de sortie.")
                return
            out_path = Path(out_raw).expanduser()
            if not out_path.is_absolute():
                out_path = (BASE_DIR / out_path).resolve()
            if out_path.exists() and not out_path.is_dir():
                messagebox.showerror(
                    "Dossier invalide",
                    "Le chemin indiqué existe mais ce n'est pas un dossier.",
                )
                return
            if not out_path.exists():
                if not messagebox.askyesno(
                    "Créer le dossier ?",
                    f"Le dossier n'existe pas :\n{out_path}\n\nLe créer maintenant ?",
                    parent=win,
                ):
                    return
                try:
                    out_path.mkdir(parents=True, exist_ok=True)
                except Exception as exc:
                    messagebox.showerror("Création impossible", str(exc), parent=win)
                    return

            self.cfg["etablissement"]      = var_etab.get()
            self.cfg["logo_etablissement"] = var_logo_etab.get()
            self.cfg["logo_specialite"]    = var_logo_spe.get()
            self.cfg["output_dir"]         = str(out_path)
            self.cfg["ask_output_dir_each_generation"] = bool(var_ask_out.get())
            self.cfg["periodes"]           = periodes_new
            save_config(self.cfg)
            win.destroy()
            self.status.set("Paramètres sauvegardés.")

        tk.Button(win, text="💾  Sauvegarder", command=sauvegarder,
                  bg=BLEU, fg=BLANC, relief="flat",
                  font=("Segoe UI", 11, "bold"), pady=8
                  ).pack(fill="x", padx=20, pady=8)


if __name__ == "__main__":
    app = AppSTI2D()
    app.mainloop()
