"""
constants.py — Constantes partagées de l'application STI2D
"""

import tkinter as tk
from tkinter import ttk

# ── Couleurs ──────────────────────────────────────────────────────────────────
BLEU   = "#1A4D8F"
ORANGE = "#E8700A"
VERT   = "#2E7D32"
GRIS   = "#F5F6FA"
GRIS2  = "#E8EDF5"
BLANC  = "#FFFFFF"
TEXTE  = "#1C1C2E"

# ── Palette par thème (T1→T7) ─────────────────────────────────────────────────
THEME_COLORS = {
    "T1": "#1565C0",  # bleu foncé
    "T2": "#2E7D32",  # vert
    "T3": "#E65100",  # orange foncé
    "T4": "#6A1B9A",  # violet
    "T5": "#00838F",  # cyan
    "T6": "#AD1457",  # rose
    "T7": "#558B2F",  # vert olive
}

# ── Périodes académiques ───────────────────────────────────────────────────────
PERIODES = [
    ("P1",  1,  7),
    ("P2",  8, 15),
    ("P3", 16, 22),
    ("P4", 23, 30),
    ("P5", 31, 36),
]

# ── Dimensions Gantt ──────────────────────────────────────────────────────────
NB_SEMAINES  = 36
ROW_H        = 52     # hauteur d'une ligne séquence
HEADER_H     = 56     # hauteur en-tête semaines
LEFT_W       = 220    # largeur colonne info gauche
WEEK_W       = 28     # largeur d'une cellule semaine
CANVAS_W     = LEFT_W + NB_SEMAINES * WEEK_W + 20
CANVAS_H_MIN = HEADER_H + 8 * ROW_H

# ── Couverture des compétences ────────────────────────────────────────────────
NIVEAU_GROUPE = {
    "1ère IT":        "1ère",
    "1ère I2D":       "1ère",
    "1ère IT/I2D":    "1ère",
    "Terminale 2I2D": "Terminale",
}

SEUIL_MAITRISE = 3  # nb d'occurrences pour considérer une compétence maîtrisée


def bind_mousewheel(canvas, frame):
    """Lie <MouseWheel> sur `canvas` et tous les descendants de `frame`.

    Appeler après chaque reconstruction du contenu scrollable pour que
    la molette fonctionne même quand la souris survole un widget enfant.
    """
    handler = lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
    canvas.bind("<MouseWheel>", handler)

    def _do(w):
        w.bind("<MouseWheel>", handler, add="+")
        for c in w.winfo_children():
            _do(c)

    _do(frame)


def show_quick_help(parent, title, items):
    """Affiche une aide contextuelle en fenêtre de lecture type "wiki"."""
    if isinstance(items, str):
        lines = [s.strip() for s in items.splitlines() if s.strip()]
    else:
        lines = [str(it).strip() for it in (items or []) if str(it).strip()]

    if not lines:
        lines = ["Aucune aide disponible pour cette fenêtre."]

    root = parent.winfo_toplevel() if hasattr(parent, "winfo_toplevel") else parent

    dlg = tk.Toplevel(root)
    dlg.title(title)
    dlg.geometry("760x520")
    dlg.minsize(560, 380)
    dlg.configure(bg=BLANC)
    dlg.transient(root)
    dlg.grab_set()

    # Centrage relatif à la fenêtre parente
    try:
        root.update_idletasks()
        dlg.update_idletasks()
        px, py = root.winfo_rootx(), root.winfo_rooty()
        pw, ph = root.winfo_width(), root.winfo_height()
        ww, wh = 760, 520
        x = max(20, px + (pw - ww) // 2)
        y = max(20, py + (ph - wh) // 2)
        dlg.geometry(f"{ww}x{wh}+{x}+{y}")
    except Exception:
        pass

    hdr = tk.Frame(dlg, bg=BLEU)
    hdr.pack(fill="x")
    tk.Label(hdr, text=f"📘  {title}", bg=BLEU, fg=BLANC,
             font=("Segoe UI", 12, "bold"), pady=8).pack(side="left", padx=10)
    tk.Button(hdr, text="✕", command=dlg.destroy,
              bg=BLEU, fg=BLANC, relief="flat",
              font=("Segoe UI", 10, "bold"), padx=10).pack(side="right", padx=8, pady=5)

    body = tk.Frame(dlg, bg=BLANC, padx=12, pady=10)
    body.pack(fill="both", expand=True)

    tk.Label(body, text="Guide rapide", bg=BLANC, fg=BLEU,
             font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))

    txt_frm = tk.Frame(body, bg=BLANC,
                       highlightbackground=GRIS2, highlightthickness=1)
    txt_frm.pack(fill="both", expand=True)

    sb = ttk.Scrollbar(txt_frm, orient="vertical")
    sb.pack(side="right", fill="y")

    txt = tk.Text(
        txt_frm,
        wrap="word",
        bg=BLANC,
        fg=TEXTE,
        relief="flat",
        bd=0,
        yscrollcommand=sb.set,
        font=("Segoe UI", 10),
        padx=12,
        pady=10,
    )
    txt.pack(side="left", fill="both", expand=True)
    sb.config(command=txt.yview)

    txt.tag_config("title", font=("Segoe UI", 11, "bold"), foreground=BLEU)
    txt.tag_config("bullet", lmargin1=8, lmargin2=24, spacing1=4, spacing3=4)
    txt.tag_config("note", font=("Segoe UI", 9, "italic"), foreground="#555555")

    txt.insert("end", "Aide contextuelle\n\n", "title")
    for line in lines:
        if line.startswith(("•", "-", "—")):
            clean = line.lstrip("•-— ").strip()
        else:
            clean = line
        txt.insert("end", f"• {clean}\n", "bullet")

    txt.insert("end", "\nAstuce : appuyez sur F1 pour afficher cette aide.", "note")
    txt.configure(state="disabled")

    frm_btn = tk.Frame(dlg, bg=GRIS, pady=8)
    frm_btn.pack(fill="x")
    tk.Button(frm_btn, text="Fermer", command=dlg.destroy,
              bg="#DDD", fg=TEXTE, relief="flat",
              font=("Segoe UI", 10), padx=12, pady=4).pack(side="right", padx=10)

    dlg.bind("<Escape>", lambda e: dlg.destroy())
