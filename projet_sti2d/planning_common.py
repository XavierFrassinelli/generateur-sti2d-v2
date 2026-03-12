"""Shared helpers for planning dialogs and tab rendering."""

from tkinter import font as tkfont

from constants import NIVEAU_GROUPE


# Coverage of competencies by class level.
def compute_competency_usage(sequences, classe_cible):
    """
    Retourne {code_co: nb_occurrences} pour le niveau de classe donne.
    Regroupement : 1ere IT / I2D / IT+I2D -> "1ere", Terminale 2I2D -> "Terminale".
    """
    niveau_cible = NIVEAU_GROUPE.get(classe_cible, classe_cible)
    usage = {}
    for seq in sequences:
        niv = NIVEAU_GROUPE.get(seq.get("classe", ""), seq.get("classe", ""))
        if niv != niveau_cible:
            continue
        for sem_data in seq.get("semaines", {}).values():
            for seance in sem_data.get("seances", []):
                for co in seance.get("competences_visees", []):
                    usage[co] = usage.get(co, 0) + 1
    return usage


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


JOURS_SEMAINE = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]


def _parse_hhmm(value):
    txt = str(value or "").strip()
    if not txt or ":" not in txt:
        return None
    hh, mm = txt.split(":", 1)
    if not (hh.isdigit() and mm.isdigit()):
        return None
    h = int(hh)
    m = int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def _slot_duration_hours(start_txt, end_txt):
    start_m = _parse_hhmm(start_txt)
    end_m = _parse_hhmm(end_txt)
    if start_m is None or end_m is None or end_m <= start_m:
        return None
    return round((end_m - start_m) / 60.0, 2)


def _seance_sort_key(seance):
    day = str(seance.get("jour", "")).strip()
    try:
        day_idx = JOURS_SEMAINE.index(day)
    except ValueError:
        day_idx = 99
    start_m = _parse_hhmm(seance.get("heure_debut"))
    return (day_idx, start_m if start_m is not None else 24 * 60 + 59, seance.get("titre", ""))


def _darken_hex(hex_color, amount=40):
    try:
        r = max(0, int(hex_color[1:3], 16) - amount)
        g = max(0, int(hex_color[3:5], 16) - amount)
        b = max(0, int(hex_color[5:7], 16) - amount)
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return "#000000"


def _truncate_text_px(text, max_px, font_spec):
    txt = str(text or "")
    if not txt:
        return ""
    fnt = tkfont.Font(font=font_spec)
    if fnt.measure(txt) <= max_px:
        return txt
    ell = "..."
    lo, hi = 0, len(txt)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if fnt.measure(txt[:mid].rstrip() + ell) <= max_px:
            lo = mid
        else:
            hi = mid - 1
    return txt[:lo].rstrip() + ell
