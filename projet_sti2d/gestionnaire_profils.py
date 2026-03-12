"""
gestionnaire_profils.py — Gestion des référentiels pédagogiques (V2)
─────────────────────────────────────────────────────────────────────────────
• ProfilSelecteur      : dialog de démarrage — choisir / importer un profil
• ImporteurReferentiel : assistant 5 étapes avec extraction PDF + revue interactive
• TableauEditable      : widget Treeview éditable par double-clic + CSV import/export
• _extract_from_pdf    : extraction pdfplumber (tables) + fallback regex

Formats supportés : STI2D (CO#.#, colonnes IT/I2D/2I2D), BTS (C#.#, savoirs S1-S11),
                    Générique (C#.# quelconque)
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json, csv, re, shutil, io, os, unicodedata
from pathlib import Path
from constants import BLEU, ORANGE, VERT, GRIS, GRIS2, BLANC, TEXTE, bind_mousewheel, show_quick_help
from core.referentiel_extraction import (
    build_bts_at_json as core_build_bts_at_json,
    comp_rows_to_csv_str as core_comp_rows_to_csv_str,
    conn_rows_to_csv_str as core_conn_rows_to_csv_str,
    crossref_to_comp_csv_str as core_crossref_to_comp_csv,
    crossref_to_savoir_csv_str as core_crossref_to_savoir_csv,
    enrich_bts_at_with_matrix as core_enrich_bts_at_with_matrix,
    extract_bts_crossref_matrix as core_extract_crossref_matrix,
    extract_bts_matrix_from_pdf as core_extract_bts_matrix_from_pdf,
    extract_from_pdf as core_extract_from_pdf,
    rows_to_comp_json as core_rows_to_comp_json,
    rows_to_conn_json as core_rows_to_conn_json,
)

ROUGE        = "#C62828"
VERT_CLAIR   = "#E8F5E9"
ORANGE_CLAIR = "#FFF8E1"
ROUGE_CLAIR  = "#FFF3E0"

PROFILS_DIR = Path(__file__).parent / "referentiels"


# ─── Utilitaires ──────────────────────────────────────────────────────────────

def list_profils():
    """Retourne [(id, nom, Path)] pour chaque profil valide dans referentiels/."""
    if not PROFILS_DIR.exists():
        return []
    result = []
    for d in sorted(PROFILS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("_"):
            pf = d / "profil.json"
            if pf.exists():
                try:
                    meta = json.loads(pf.read_text(encoding="utf-8"))
                    result.append((meta.get("id", d.name), meta.get("nom", d.name), d))
                except Exception:
                    pass
    return result


def load_profil_meta(profil_dir):
    """Charge profil.json depuis un dossier. Retourne {} si absent."""
    pf = Path(profil_dir) / "profil.json"
    if pf.exists():
        try:
            return json.loads(pf.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _normalize_ref(value):
    ref = str(value or "").strip().replace(" ", "").replace(".", "-")
    ref = re.sub(r"[^0-9A-Za-z\-]", "", ref)
    ref = re.sub(r"-+", "-", ref).strip("-")
    return ref


def _safe_int(value, default=0):
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _norm_text(s):
    """Normalise les espaces et tirets unicode."""
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("\u2022", " ").replace("\u00b7", " ")
    return " ".join(s.split()).strip()


def _strip_accents(s):
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def _key_tokens(s):
    stop = {"de", "des", "du", "la", "le", "les", "et", "en", "un", "une", "dans",
            "au", "aux", "pour", "sur", "par", "avec", "ou", "d", "l", "a"}
    return {t for t in re.findall(r"[a-z]{4,}", _strip_accents(s.lower())) if t not in stop}


def _normalize_comp_code(code):
    raw = str(code or "").strip().upper()
    m = re.match(r"^(?:C(?:O)?|O)0*(\d+)(?:\.(\d+))?(?:\.[A-Z0-9]+)?$", raw, re.IGNORECASE)
    if not m:
        return raw
    major = int(m.group(1))
    minor = m.group(2)
    if minor is None:
        return f"CO{major}"
    return f"CO{major}.{int(minor)}"


# ─── Détection du format PDF ──────────────────────────────────────────────────

def _detect_format(text):
    """Retourne 'STI2D', 'BTS' ou 'GENERIQUE' selon le contenu."""
    co_matches = re.findall(r'\bCO\d+\.\d+', text, re.IGNORECASE)
    # STI2D : codes CO#.# et spécialités enseignement
    if co_matches:
        if any(kw in text.upper() for kw in ["I2D", "2I2D", "ITEC", "ITEC", " EE", "SIN,", "AC,"]):
            return "STI2D"
        # Certains PDF n'exposent pas clairement les en-têtes de spécialité dans l'aperçu.
        # Un volume significatif de codes CO#.# est un bon indicateur STI2D.
        if len(co_matches) >= 6:
            return "STI2D"
    # BTS : savoirs S1…S11 en colonnes ou en en-têtes de chapitres
    s_matches = re.findall(r'\bS\d{1,2}\b', text)
    if len(s_matches) >= 6:
        return "BTS"
    # Générique : C#.# ou CO#.#
    if re.search(r'\b[CO]\d+\.\d+', text, re.IGNORECASE):
        return "GENERIQUE"
    return "GENERIQUE"


# ─── Extraction PDF ───────────────────────────────────────────────────────────

def _extract_from_pdf(pdf_path, niveaux):
    """
    Extrait compétences et connaissances depuis un PDF.

    Stratégie :
    1. Tente pdfplumber (extraction de tableaux structurés)
    2. Sinon, tente pypdf (texte brut)
    3. Parsing format-spécifique (STI2D / BTS / Générique)
    4. Complète par regex fallback si résultats insuffisants

    Retourne :
        comp_rows : list[dict]  — code, libelle, connaissances_liees, confidence, *niveaux
        conn_rows : list[dict]  — ref, chapitre_id, chapitre_titre, sous_chapitre_titre,
                                  detail, confidence, *niveaux
        fmt       : str         — 'STI2D' | 'BTS' | 'GENERIQUE'
    """
    use_pdfplumber = False
    try:
        import pdfplumber
        use_pdfplumber = True
    except ImportError:
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ImportError("pdfplumber_ou_pypdf")

    all_text_lines = []
    all_tables = []

    if use_pdfplumber:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                all_text_lines.extend(txt.splitlines())
                # Extraction de tableaux avec reconnaissance des lignes
                tbls = page.extract_tables({
                    "vertical_strategy":   "lines",
                    "horizontal_strategy": "lines",
                }) or []
                all_tables.extend(tbls)
    else:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        for page in reader.pages:
            txt = page.extract_text() or ""
            all_text_lines.extend(txt.splitlines())
        # Pas de tables structurées avec pypdf — fallback regex uniquement

    preview = "\n".join(all_text_lines[:200])
    fmt = _detect_format(preview)

    comp_rows, conn_rows = [], []

    # Parsing format-spécifique depuis les tables
    if all_tables:
        if fmt == "STI2D":
            c, k = _parse_tables_sti2d(all_tables, all_text_lines, niveaux)
        elif fmt == "BTS":
            c, k = _parse_tables_bts(all_tables, all_text_lines, niveaux)
        else:
            c, k = _parse_tables_generic(all_tables, all_text_lines, niveaux)
        comp_rows.extend(c)
        conn_rows.extend(k)

    # Fallback regex : complète les extractions partielles (tables incomplètes / texte non tabulaire)
    need_fallback = (
        len(comp_rows) < 3
        or not conn_rows
        or (fmt in ("STI2D", "GENERIQUE") and len(comp_rows) < 20)
    )
    if need_fallback:
        c_fb, k_fb = _parse_regex_fallback(all_text_lines, niveaux)
        existing_codes = {r["code"] for r in comp_rows}
        for row in c_fb:
            if row["code"] not in existing_codes:
                comp_rows.append(row)
        existing_refs = {r["ref"] for r in conn_rows}
        for row in k_fb:
            if row["ref"] not in existing_refs:
                conn_rows.append(row)

    # Tri
    def _comp_key(r):
        m = re.match(r"^C[O]?(\d+)(?:\.(\d+))?", r.get("code", ""), re.I)
        return (int(m.group(1)), int(m.group(2) or 0)) if m else (9999, 9999)

    def _conn_key(r):
        try:
            return tuple(int(x) for x in r.get("ref", "0").split("-") if x.isdigit())
        except Exception:
            return (9999,)

    comp_rows.sort(key=_comp_key)
    conn_rows.sort(key=_conn_key)

    return comp_rows, conn_rows, fmt


# ── Helpers tables ─────────────────────────────────────────────────────────────

def _header_str(header_row):
    return " ".join(str(c or "").upper() for c in header_row)


def _parse_tables_sti2d(tables, text_lines, niveaux):
    """Parse les tables STI2D : [Objectif | Compétence (CO#.#) | IT | I2D | 2I2D | Connaissances]"""
    comp_rows = []
    conn_rows = _extract_connaissances_sti2d(text_lines, niveaux)
    STI2D_NIV = {"IT", "I2D", "2I2D", "ITEC", "EE", "EE1", "EE2", "SIN", "AC", "AC1", "AC2"}

    for table in tables:
        if not table or len(table) < 2:
            continue
        header = table[0]
        h_str = _header_str(header)
        if not any(kw in h_str for kw in ("COMPÉTENCE", "COMPETENCE", "CO")):
            continue

        col_comp  = None
        col_obj   = None
        col_conns = None
        col_niv   = {}  # {nom: idx}

        for i, cell in enumerate(header):
            h = str(cell or "").strip().upper()
            if any(kw in h for kw in ("COMPÉTENCE", "COMPETENCE")) and col_comp is None:
                col_comp = i
            elif "OBJECTIF" in h and col_obj is None:
                col_obj = i
            elif h in STI2D_NIV:
                col_niv[h] = i
            elif "CONNAISSANCE" in h or "SAVOIR" in h:
                col_conns = i

        # Certains PDF fusionnent "Objectif" et "Compétence" dans une même colonne.
        # On n'utilise OBJECTIF comme fallback que si aucune colonne compétence n'a été trouvée.
        if col_comp is None and col_obj is not None:
            col_comp = col_obj

        if col_comp is None:
            continue

        for data_row in table[1:]:
            if not data_row or not any(str(c or "").strip() for c in data_row):
                continue
            cell_val = str(data_row[col_comp] if col_comp < len(data_row) else "").strip()

            # --- STI2D : une cellule peut contenir plusieurs CO#.# séparés par \n ---
            # Découper au début de chaque code CO (lookahead)
            segments = re.split(r'(?=\bCO\d+\.\d+\b)', cell_val, flags=re.IGNORECASE)
            segments = [s.strip() for s in segments if s.strip() and re.search(r'\bCO\d+\.\d+\b', s, re.IGNORECASE)]

            if not segments:
                continue

            # Niveaux : chaque colonne contient N valeurs séparées par \n (une par CO)
            niv_lines: dict[str, list[str]] = {}
            for niv, cidx in col_niv.items():
                raw = str(data_row[cidx] if cidx < len(data_row) else "")
                niv_lines[niv] = [v.strip() for v in raw.split('\n')]

            # Connaissances : N lignes séparées par \n (une par CO)
            conns_lines: list[str] = []
            if col_conns is not None and col_conns < len(data_row):
                raw_c = str(data_row[col_conns] or "")
                conns_lines = [l.strip() for l in raw_c.split('\n')]

            for seg_idx, seg in enumerate(segments):
                m = re.match(r'\b(CO\d+\.\d+)\b\s*[:\-.]?\s*(.*)', seg, re.IGNORECASE | re.DOTALL)
                if not m:
                    continue
                code    = m.group(1).upper()
                libelle = re.sub(r'\s+', ' ', m.group(2)).strip()[:260]

                # Niveaux : prendre la valeur à l'indice seg_idx dans chaque colonne
                niv_vals = {}
                for niv, lines in niv_lines.items():
                    v = lines[seg_idx].upper() if seg_idx < len(lines) else ""
                    niv_vals[niv] = v if v in ("X", "XX") else ""

                # Connaissances : prendre la ligne à l'indice seg_idx
                conns_str = ""
                if seg_idx < len(conns_lines):
                    refs = re.findall(r'\d+-\d+', conns_lines[seg_idx])
                    conns_str = ";".join(refs)
                elif not conns_lines and col_conns is not None:
                    # fallback: toute la cellule si non découpable
                    raw_c = str(data_row[col_conns] if col_conns < len(data_row) else "")
                    conns_str = ";".join(re.findall(r'\d+-\d+', raw_c))

                row = {"code": code, "libelle": libelle, "connaissances_liees": conns_str, "confidence": "high"}
                for n in niveaux:
                    row[n] = niv_vals.get(n, "")
                comp_rows.append(row)

    return comp_rows, conn_rows


def _extract_connaissances_sti2d(text_lines, niveaux):
    """Connaissances STI2D : S1 → chapitre 1, S1.2 → ref 1-2."""
    conn_map   = {}
    chap_titles = {}
    norm_lines = [_norm_text(l) for l in text_lines]

    for line in norm_lines:
        # Chapitre principal : S3 - Titre
        m = re.match(r'^(S\d{1,2})\s*[-:]\s*(.+)$', line, re.IGNORECASE)
        if m and "." not in m.group(1):
            chap_titles[m.group(1).upper()] = m.group(2).strip()[:180]

        # Sous-chapitre : S3.1 - Titre  ou  S3.1.2 - Titre
        m2 = re.match(r'^(S\d{1,2}(?:\.\d+)+)\s*[-:]\s*(.+)$', line, re.IGNORECASE)
        if not m2:
            m2 = re.match(r'^(S\d{1,2}(?:\.\d+)+)\s+(.{6,})$', line, re.IGNORECASE)
        if m2:
            s_code = m2.group(1).upper()
            titre  = m2.group(2).strip(" .;,-")[:220]
            nums   = s_code[1:].split(".")
            chap_id = nums[0]
            ref     = "-".join(nums)
            chap_titre = chap_titles.get(f"S{chap_id}", f"Chapitre {chap_id}")
            if len(titre) >= 4:
                conn_map.setdefault(ref, (chap_id, chap_titre, titre))

    def _ref_key(r):
        try:
            return tuple(int(x) for x in r.split("-") if x.isdigit())
        except Exception:
            return (9999,)

    conn_rows = []
    for ref in sorted(conn_map, key=_ref_key):
        chap_id, chap_titre, sc_titre = conn_map[ref]
        row = {"ref": ref, "chapitre_id": chap_id, "chapitre_titre": chap_titre,
               "sous_chapitre_titre": sc_titre, "detail": "", "confidence": "medium"}
        for n in niveaux:
            row[n] = "1"
        conn_rows.append(row)
    return conn_rows


def _parse_tables_bts(tables, text_lines, niveaux):
    """Parse les tables BTS : [Compétence | S1 | S2 | … | S11]"""
    comp_rows = []
    conn_rows = _extract_connaissances_bts(text_lines, niveaux)
    conn_refs = {r["ref"] for r in conn_rows}

    for table in tables:
        if not table or len(table) < 2:
            continue
        header = table[0]
        h_str  = _header_str(header)

        # Repérer colonnes S1…S11
        col_comp = None
        s_cols   = {}  # {num_str: idx}

        for i, cell in enumerate(header):
            h = str(cell or "").strip().upper()
            if any(kw in h for kw in ("COMPÉTENCE", "COMPETENCE")) and col_comp is None:
                col_comp = i
            ms = re.match(r'^S(\d{1,2})$', h)
            if ms:
                s_cols[ms.group(1)] = i

        if col_comp is None or not s_cols:
            continue

        for data_row in table[1:]:
            if not data_row:
                continue
            cell_val = str(data_row[col_comp] if col_comp < len(data_row) else "").strip()
            m = re.search(r'\b(C[O]?\d+\.\d+)\b\s*[:\-.]?\s*(.*)', cell_val, re.IGNORECASE | re.DOTALL)
            if not m:
                continue
            code    = m.group(1).upper()
            libelle = re.sub(r'\s+', ' ', m.group(2)).strip()[:260]

            # Savoirs cochés dans la ligne
            linked = []
            for s_num, s_idx in s_cols.items():
                v = str(data_row[s_idx] if s_idx < len(data_row) else "").strip()
                if v and v.upper() not in ("", "0", "NON", "-", "X"):
                    if s_num in conn_refs or s_num not in conn_refs:
                        linked.append(s_num)

            row = {"code": code, "libelle": libelle, "connaissances_liees": ";".join(linked),
                   "confidence": "high"}
            for n in niveaux:
                row[n] = ""
            comp_rows.append(row)

    return comp_rows, conn_rows


def _extract_connaissances_bts(text_lines, niveaux):
    """Savoirs BTS : S1 → chapitre, S1.1 → sous-chapitre."""
    conn_map   = {}
    chap_titles = {}
    norm_lines = [_norm_text(l) for l in text_lines]

    for line in norm_lines:
        # Chapitre : S4 - Culture technique
        m = re.match(r'^(S\d{1,2})\s*[-:]\s*(.{4,})$', line, re.IGNORECASE)
        if m and "." not in m.group(1):
            key = m.group(1).upper()
            chap_titles[key] = m.group(2).strip()[:180]
            chap_id = key[1:]
            conn_map.setdefault(chap_id, (chap_id, m.group(2).strip()[:180], m.group(2).strip()[:180]))

        # Sous-chapitre : S4.1 - ...
        m2 = re.match(r'^(S\d{1,2}(?:\.\d+)+)\s*[-:]\s*(.{4,})$', line, re.IGNORECASE)
        if not m2:
            m2 = re.match(r'^(S\d{1,2}(?:\.\d+)+)\s+(.{6,})$', line, re.IGNORECASE)
        if m2:
            s_code  = m2.group(1).upper()
            titre   = m2.group(2).strip(" .;,-")[:220]
            nums    = s_code[1:].split(".")
            chap_id = nums[0]
            ref     = "-".join(nums)
            chap_titre = chap_titles.get(f"S{chap_id}", f"S{chap_id}")
            if len(titre) >= 4:
                conn_map.setdefault(ref, (chap_id, chap_titre, titre))

    def _ref_key(r):
        try:
            return tuple(int(x) for x in r.split("-") if x.isdigit())
        except Exception:
            return (9999,)

    conn_rows = []
    for ref in sorted(conn_map, key=_ref_key):
        chap_id, chap_titre, sc_titre = conn_map[ref]
        row = {"ref": ref, "chapitre_id": chap_id, "chapitre_titre": chap_titre,
               "sous_chapitre_titre": sc_titre, "detail": "", "confidence": "medium"}
        for n in niveaux:
            row[n] = "1"
        conn_rows.append(row)
    return conn_rows


def _parse_tables_generic(tables, text_lines, niveaux):
    """Parser générique pour tables non identifiées."""
    comp_rows = []
    seen_codes = set()
    for table in tables:
        if not table or len(table) < 2:
            continue
        for data_row in table[1:]:
            for cell in data_row:
                m = re.search(r'\b(C[O]?\d+\.\d+)\b\s*[:\-.]?\s*(.*)', str(cell or ""),
                              re.IGNORECASE | re.DOTALL)
                if m:
                    code = m.group(1).upper()
                    lib  = re.sub(r'\s+', ' ', m.group(2)).strip()[:260]
                    if len(lib) >= 8 and code not in seen_codes:
                        row = {"code": code, "libelle": lib, "connaissances_liees": "",
                               "confidence": "medium"}
                        for n in niveaux:
                            row[n] = ""
                        comp_rows.append(row)
                        seen_codes.add(code)
                    break

    conn_rows = _extract_connaissances_sti2d(text_lines, niveaux)
    return comp_rows, conn_rows


def _parse_regex_fallback(text_lines, niveaux):
    """Extraction regex sur texte brut — fallback si tables non détectées."""
    comp_map   = {}
    comp_blocks = {}
    conn_map   = {}
    chap_titles = {}
    norm_lines = [_norm_text(l) for l in text_lines]

    def _looks_cont(s):
        if not s or len(s) < 3:
            return False
        if re.match(r"^(C[O]?\d|S\d|Page\s)", s, re.IGNORECASE):
            return False
        if re.match(r"^\d+\s*$", s):
            return False
        return True

    i = 0
    while i < len(norm_lines):
        line = norm_lines[i]
        m = re.match(r"^(C[O]?\d{1,2}(?:\.\d+)?)\s*[:\-.]?\s*(.*)$", line, re.IGNORECASE)
        if m:
            code  = m.group(1).upper()
            parts = [m.group(2).strip()] if m.group(2).strip() else []
            j     = i + 1
            while j < len(norm_lines) and len(" ".join(parts)) < 260:
                nxt = norm_lines[j]
                if not _looks_cont(nxt):
                    break
                parts.append(nxt)
                j += 1
            lib = " ".join(p for p in parts if p).strip()[:260]
            if len(lib) >= 8 and any(ch.isalpha() for ch in lib):
                if code not in comp_map or len(lib) > len(comp_map[code]):
                    comp_map[code] = lib
                    comp_blocks[code] = " ".join(norm_lines[i:min(j + 6, len(norm_lines))])
            i = j
            continue
        i += 1

    for line in norm_lines:
        m_ch = re.match(r"^(S\d{1,2})\s*[-:]\s*(.+)$", line, re.IGNORECASE)
        if m_ch and "." not in m_ch.group(1):
            chap_titles[m_ch.group(1).upper()] = m_ch.group(2).strip()[:180]
        m_c = re.match(r"^(S\d{1,2}(?:\.\d+)+)\s*[-:]\s*(.+)$", line, re.IGNORECASE)
        if not m_c:
            m_c = re.match(r"^(S\d{1,2}(?:\.\d+)+)\s+(.{6,})$", line, re.IGNORECASE)
        if m_c:
            s_code  = m_c.group(1).upper()
            titre   = m_c.group(2).strip(" .;,-")[:220]
            nums    = s_code[1:].split(".")
            chap_id = nums[0]
            ref     = "-".join(nums)
            chap_titre = chap_titles.get(f"S{chap_id}", f"Chapitre {chap_id}")
            if len(titre) >= 4:
                conn_map.setdefault(ref, (chap_id, chap_titre, titre))

    # Fallback additionnel : certaines versions STI2D listent uniquement des refs 1-2 / 5-3
    if not conn_map:
        all_text = "\n".join(norm_lines)
        raw_refs = set(re.findall(r"\b(\d+-\d+)\b", all_text))

        def _ref_key_local(r):
            try:
                return tuple(int(x) for x in r.split("-") if x.isdigit())
            except Exception:
                return (9999,)

        for ref in sorted(raw_refs, key=_ref_key_local):
            parts = ref.split("-")
            if len(parts) != 2 or not all(p.isdigit() for p in parts):
                continue
            chap_id = parts[0]
            chap_titre = chap_titles.get(f"S{chap_id}", f"Chapitre {chap_id}")
            sc_titre = f"Connaissance {ref}"
            conn_map.setdefault(ref, (chap_id, chap_titre, sc_titre))

    # Inférence des liens (heuristique lexicale)
    conn_rows_list = list(conn_map.items())

    def _infer(code, lib):
        block = comp_blocks.get(code, "")
        links = []
        for ref in re.findall(r"\b(\d+-\d+)\b", block):
            if ref in conn_map and ref not in links:
                links.append(ref)
        for ms in re.finditer(r"\bS(\d+(?:\.\d+)*)\b", block, re.IGNORECASE):
            ref = ms.group(1).replace(".", "-")
            if ref in conn_map and ref not in links:
                links.append(ref)
        if not links:
            comp_toks = _key_tokens(lib)
            scored = []
            for ref, (_, ct, sc) in conn_map.items():
                score = len(comp_toks & _key_tokens(f"{ct} {sc}"))
                if score > 0:
                    scored.append((score, ref))
            scored.sort(key=lambda t: (-t[0], t[1]))
            links = [r for _, r in scored[:3]]
        return ";".join(links)

    def _comp_key(c):
        m = re.match(r"^C[O]?(\d+)(?:\.(\d+))?", c, re.I)
        return (int(m.group(1)), int(m.group(2) or 0)) if m else (9999, 9999)

    comp_rows = []
    for code in sorted(comp_map, key=_comp_key):
        norm_code = _normalize_comp_code(code)
        row = {"code": norm_code, "libelle": comp_map[code],
               "connaissances_liees": _infer(code, comp_map[code]), "confidence": "low"}
        for n in niveaux:
            row[n] = ""
        comp_rows.append(row)

    def _ref_key(r):
        try:
            return tuple(int(x) for x in r.split("-") if x.isdigit())
        except Exception:
            return (9999,)

    conn_rows = []
    for ref in sorted(conn_map, key=_ref_key):
        chap_id, chap_titre, sc_titre = conn_map[ref]
        row = {"ref": ref, "chapitre_id": chap_id, "chapitre_titre": chap_titre,
               "sous_chapitre_titre": sc_titre, "detail": "", "confidence": "low"}
        for n in niveaux:
            row[n] = "1"
        conn_rows.append(row)

    return comp_rows, conn_rows


# ─── Convertisseurs données → JSON ────────────────────────────────────────────

def _rows_to_comp_json(comp_rows, niveaux):
    """Convertit comp_rows → referentiel_competences.json."""
    result = {"objectifs": {}, "competences": {}}
    for row in comp_rows:
        code = _normalize_comp_code(row.get("code", ""))
        if not code:
            continue
        libelle = str(row.get("libelle", "")).strip()
        m = re.match(r"^C[O]?(\d+)", code, re.IGNORECASE)
        num = m.group(1) if m else "1"
        obj_code = f"O{num}"
        if obj_code not in result["objectifs"]:
            result["objectifs"][obj_code] = f"Objectif {num}"
        conns_raw = str(row.get("connaissances_liees", ""))
        conns = []
        for c in re.split(r"[;,\s]+", conns_raw):
            r = _normalize_ref(c)
            if r and r not in conns:
                conns.append(r)
        niv_map = {n: str(row.get(n, "")).strip() for n in niveaux}
        if code not in result["competences"]:
            result["competences"][code] = {
                "objectif":      obj_code,
                "libelle":       libelle,
                "niveaux":       niv_map,
                "connaissances": conns,
            }
    return result


def _rows_to_conn_json(conn_rows, niveaux):
    """Convertit conn_rows → referentiel_connaissances.json."""
    result = {}
    for row in conn_rows:
        ref     = _normalize_ref(row.get("ref", ""))
        if not ref:
            continue
        chap_id    = str(row.get("chapitre_id", "") or ref.split("-")[0])
        chap_titre = str(row.get("chapitre_titre", "")).strip()
        sc_titre   = str(row.get("sous_chapitre_titre", "")).strip() or ref
        detail     = str(row.get("detail", "")).strip()
        taxo = {n: _safe_int(row.get(n, 0)) for n in niveaux}
        if chap_id not in result:
            result[chap_id] = {"titre": chap_titre, "sous_chapitres": {}}
        elif chap_titre and not result[chap_id].get("titre"):
            result[chap_id]["titre"] = chap_titre
        result[chap_id]["sous_chapitres"][ref] = {
            "titre":     sc_titre,
            "detail":    detail,
            "taxonomie": taxo,
        }
    return result


def _build_bts_at_json(comp_json, conn_json):
    """Construit un référentiel d'activités types BTS depuis CO/CN."""
    objectifs = dict(comp_json.get("objectifs", {}))
    competences = dict(comp_json.get("competences", {}))

    known_refs = set()
    for chap in conn_json.values():
        known_refs.update((chap.get("sous_chapitres") or {}).keys())

    by_obj = {}
    for code, data in competences.items():
        obj = str(data.get("objectif", "O1") or "O1")
        by_obj.setdefault(obj, []).append((code, data))

    def _obj_key(obj_code):
        m = re.search(r"(\d+)", str(obj_code))
        return int(m.group(1)) if m else 999

    def _co_key(code):
        m = re.match(r"^CO(\d+)(?:\.(\d+))?$", str(code), re.IGNORECASE)
        return (int(m.group(1)), int(m.group(2) or 0)) if m else (999, 999)

    correspondance = {}
    for co_code in competences.keys():
        m = re.match(r"^CO(\d+)(?:\.\d+)?$", str(co_code), re.IGNORECASE)
        if not m:
            continue
        c_code = f"C{int(m.group(1))}"
        correspondance.setdefault(c_code, []).append(co_code)
    for c_code in correspondance:
        correspondance[c_code].sort(key=_co_key)

    activites = {}
    for idx, obj in enumerate(sorted(by_obj.keys(), key=_obj_key), start=1):
        co_items = sorted(by_obj[obj], key=lambda t: _co_key(t[0]))
        co_codes = [code for code, _ in co_items]

        refs = []
        for _, cdata in co_items:
            for ref in cdata.get("connaissances", []):
                r = _normalize_ref(ref)
                if r and r in known_refs and r not in refs:
                    refs.append(r)

        raw_title = str(objectifs.get(obj, "")).strip()
        if not raw_title or raw_title.lower().startswith("objectif "):
            title = f"Activité type {idx}"
        else:
            title = raw_title

        activites[f"AT{idx}"] = {
            "titre": title,
            "description": f"Regroupement des compétences du bloc {obj}.",
            "objectif": obj,
            "competences": co_codes,
            "connaissances": refs,
        }

    return {
        "meta": {
            "schema": "bts_at_v1",
            "version": 1,
            "source": "auto_from_comp_conn",
        },
        "correspondance_competences": correspondance,
        "activites": activites,
    }


def _enrich_bts_at_with_matrix(at_json, matrix):
    """Injecte la matrice extraite et ajoute les compétences détaillées par tâche."""
    if not isinstance(at_json, dict) or not isinstance(matrix, dict):
        return at_json

    at_json["matrice_competences"] = matrix
    corr = at_json.get("correspondance_competences", {})
    taches = at_json.get("matrice_competences", {}).get("taches", {})

    for t_code, t_data in taches.items():
        detailed = []
        for c_code in t_data.get("competences", []):
            for co_code in corr.get(c_code, []):
                if co_code not in detailed:
                    detailed.append(co_code)
        t_data["competences_detaillees"] = detailed

    at_json.setdefault("meta", {})["source_matrice"] = "pdf_table"
    return at_json


def _extract_bts_matrix_from_pdf(pdf_path):
    """
    Extrait la matrice BTS (tâches A*-T* x compétences C1..C14) depuis le PDF.

    Retourne un bloc:
    {
      "source_page": <int>,
      "competences": ["C1", ...],
      "taches": {
        "A1-T1": {
          "activite": "A1",
          "competences": ["C3", "C5"],
          "niveaux": {"C3": "2", "C5": "2"}
        }
      }
    }
    """
    try:
        import pdfplumber
    except Exception:
        return {}

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return {}

    with pdfplumber.open(pdf_path) as pdf:
        best = None  # (score, page_no, table)

        for page_no, page in enumerate(pdf.pages, start=1):
            text = _norm_text(page.extract_text() or "")
            at_count = len(re.findall(r"\bA\d+-T\d+\b", text))
            c_count = len(re.findall(r"\bC(?:1[0-4]|[1-9])\b", text))
            if at_count == 0 or c_count < 8:
                continue

            tables = page.extract_tables({
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
            }) or []

            for table in tables:
                if not table:
                    continue
                rows = len(table)
                cols = max((len(r or []) for r in table), default=0)
                score = at_count * 20 + c_count * 5 + rows * cols
                if best is None or score > best[0]:
                    best = (score, page_no, table)

    if best is None:
        return {}

    _, source_page, table = best

    # Détection de la ligne d'en-tête compétences (contient C1..)
    header_row_idx = None
    header_map = {}  # col_idx -> Cx
    for ri, row in enumerate(table):
        cells = [str(c or "").strip() for c in (row or [])]
        tmp = {}
        for ci, cell in enumerate(cells):
            m = re.search(r"\bC(?:1[0-4]|[1-9])\b", cell)
            if m:
                tmp[ci] = m.group(0)
        if len(tmp) >= 6:
            header_row_idx = ri
            header_map = tmp
            break

    if header_row_idx is None or not header_map:
        return {}

    taches = {}
    for row in table[header_row_idx + 1:]:
        cells = [str(c or "").strip() for c in (row or [])]
        joined = " | ".join(cells)
        m_task = re.search(r"\b(A\d+-T\d+)\b", joined)
        if not m_task:
            continue

        task_code = m_task.group(1)
        m_act = re.match(r"^(A\d+)-T\d+$", task_code)
        activite = m_act.group(1) if m_act else ""

        niveaux = {}
        for col_idx, c_code in header_map.items():
            if col_idx >= len(cells):
                continue
            v = cells[col_idx].strip()
            if not v:
                continue
            # Les cellules de matrice contiennent en général 1/2/3; on garde toute valeur non vide.
            niveaux[c_code] = v

        if niveaux:
            taches[task_code] = {
                "activite": activite,
                "competences": sorted(niveaux.keys(), key=lambda c: int(re.search(r"\d+", c).group(0))),
                "niveaux": niveaux,
            }

    if not taches:
        return {}

    competences = sorted(
        {c for t in taches.values() for c in t.get("competences", [])},
        key=lambda c: int(re.search(r"\d+", c).group(0)),
    )

    return {
        "source_page": source_page,
        "competences": competences,
        "taches": taches,
    }


# ─── Helpers CSV ──────────────────────────────────────────────────────────────

def _comp_rows_to_csv_str(comp_rows, niveaux):
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["code", "libelle"] + niveaux + ["connaissances_liees"])
    for row in comp_rows:
        w.writerow([row.get("code", ""), row.get("libelle", "")]
                   + [row.get(n, "") for n in niveaux]
                   + [row.get("connaissances_liees", "")])
    return buf.getvalue()


def _conn_rows_to_csv_str(conn_rows, niveaux):
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["ref", "chapitre_id", "chapitre_titre", "sous_chapitre_titre", "detail"] + niveaux)
    for row in conn_rows:
        w.writerow([row.get("ref", ""), row.get("chapitre_id", ""),
                    row.get("chapitre_titre", ""), row.get("sous_chapitre_titre", ""),
                    row.get("detail", "")]
                   + [row.get(n, "") for n in niveaux])
    return buf.getvalue()


def _comp_csv_str_to_rows(csv_text, niveaux):
    rows = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for r in reader:
        row = {
            "code":              r.get("code", "").strip(),
            "libelle":           r.get("libelle", "").strip(),
            "connaissances_liees": r.get("connaissances_liees", "").strip(),
            "confidence":        "manual",
        }
        for n in niveaux:
            row[n] = r.get(n, "").strip()
        if row["code"]:
            rows.append(row)
    return rows


def _conn_csv_str_to_rows(csv_text, niveaux):
    rows = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for r in reader:
        row = {
            "ref":                 _normalize_ref(r.get("ref", "")),
            "chapitre_id":         r.get("chapitre_id", "").strip(),
            "chapitre_titre":      r.get("chapitre_titre", "").strip(),
            "sous_chapitre_titre": r.get("sous_chapitre_titre", "").strip(),
            "detail":              r.get("detail", "").strip(),
            "confidence":          "manual",
        }
        for n in niveaux:
            row[n] = r.get(n, "").strip()
        if row["ref"]:
            rows.append(row)
    return rows


# ─── Widget table éditable ────────────────────────────────────────────────────

class TableauEditable(tk.Frame):
    """
    Treeview éditable par double-clic.

    mode='comp' : colonnes [code, libelle, *niveaux, connaissances_liees]
    mode='conn' : colonnes [ref, chapitre_id, chapitre_titre, sous_chapitre_titre, detail, *niveaux]

    Couleurs de confiance :
        high   = vert  (extrait depuis un tableau structuré)
        medium = jaune (extrait par regex depuis texte)
        low    = orange (heuristique, à vérifier)
        manual = blanc (saisi / importé CSV manuellement)
    """

    CONF_BG = {
        "high":   "#E8F5E9",  # vert
        "medium": "#FFF8E1",  # jaune
        "low":    "#FFF3E0",  # orange clair
        "manual": "#FFFFFF",
    }

    def __init__(self, parent, niveaux, mode="comp", **kw):
        super().__init__(parent, bg=BLANC, **kw)
        self.niveaux = niveaux
        self.mode    = mode
        self._edit_widget  = None
        self._edit_row_id  = None
        self._edit_col_idx = None

        if mode == "comp":
            self._columns = ["code", "libelle"] + niveaux + ["connaissances_liees"]
            self._headers = {"code": "Code", "libelle": "Libellé",
                             "connaissances_liees": "Connaissances liées",
                             **{n: n for n in niveaux}}
            self._widths  = {"code": 80, "libelle": 300, "connaissances_liees": 130,
                             **{n: 72 for n in niveaux}}
        else:
            self._columns = ["ref", "chapitre_id", "chapitre_titre",
                             "sous_chapitre_titre", "detail"] + niveaux
            self._headers = {"ref": "Réf.", "chapitre_id": "Ch.",
                             "chapitre_titre": "Chapitre",
                             "sous_chapitre_titre": "Sous-chapitre",
                             "detail": "Détail",
                             **{n: n for n in niveaux}}
            self._widths  = {"ref": 60, "chapitre_id": 35, "chapitre_titre": 150,
                             "sous_chapitre_titre": 220, "detail": 100,
                             **{n: 64 for n in niveaux}}

        self._build()

    def _build(self):
        style = ttk.Style(self)
        style.configure(
            "RefEditor.Treeview",
            background=BLANC,
            fieldbackground=BLANC,
            foreground=TEXTE,
            font=("Segoe UI", 9),
            rowheight=24,
        )
        style.configure(
            "RefEditor.Treeview.Heading",
            font=("Segoe UI", 9, "bold"),
            foreground=TEXTE,
        )
        style.map(
            "RefEditor.Treeview",
            background=[("selected", BLEU)],
            foreground=[("selected", BLANC)],
        )

        # ── Barre d'outils ────────────────────────────────────────────────────
        toolbar = tk.Frame(self, bg=GRIS2, pady=4)
        toolbar.pack(fill="x")

        # Légende confiance
        leg = tk.Frame(toolbar, bg=GRIS2)
        leg.pack(side="left", padx=10)
        tk.Label(leg, text="Confiance :", bg=GRIS2, font=("Segoe UI", 8),
                 fg="#666").pack(side="left")
        for label, color in [("Tableau", "#E8F5E9"), ("Texte", "#FFF8E1"),
                              ("Heuristique", "#FFF3E0"), ("Manuel", "#FFFFFF")]:
            fr = tk.Frame(leg, bg=color, highlightbackground="#CCC", highlightthickness=1)
            fr.pack(side="left", padx=2)
            tk.Label(fr, text=label, bg=color, font=("Segoe UI", 7), padx=4, pady=2).pack()

        # Boutons d'action
        btn = tk.Frame(toolbar, bg=GRIS2)
        btn.pack(side="right", padx=10)

        def _mk_btn(text, cmd, bg):
            tk.Button(btn, text=text, command=cmd, bg=bg, fg=BLANC, relief="flat",
                      font=("Segoe UI", 9), padx=8, pady=3).pack(side="left", padx=2)

        _mk_btn("➕ Ajouter",       self._add_row,    VERT)
        _mk_btn("📄 Dupliquer",     self._dup_row,    BLEU)
        _mk_btn("🗑 Supprimer",     self._del_row,    ROUGE)
        _mk_btn("📂 Importer CSV",  self._import_csv, "#555")
        _mk_btn("💾 Exporter CSV",  self._export_csv, "#555")

        # ── Treeview ──────────────────────────────────────────────────────────
        tree_frm = tk.Frame(self, bg=BLANC)
        tree_frm.pack(fill="both", expand=True)

        sb_y = ttk.Scrollbar(tree_frm, orient="vertical")
        sb_y.pack(side="right", fill="y")
        sb_x = ttk.Scrollbar(tree_frm, orient="horizontal")
        sb_x.pack(side="bottom", fill="x")

        self.tree = ttk.Treeview(
            tree_frm, columns=self._columns, show="headings",
            yscrollcommand=sb_y.set, xscrollcommand=sb_x.set,
            selectmode="extended",
            style="RefEditor.Treeview",
        )
        self.tree.pack(fill="both", expand=True)
        sb_y.config(command=self.tree.yview)
        sb_x.config(command=self.tree.xview)

        for col in self._columns:
            lbl = self._headers.get(col, col)
            w   = self._widths.get(col, 100)
            stretch = col in ("libelle", "sous_chapitre_titre", "detail")
            is_level_col = col in self.niveaux
            anchor = "center" if is_level_col else "w"
            self.tree.heading(col, text=lbl, anchor=anchor)
            self.tree.column(col, width=w, minwidth=(56 if is_level_col else 30),
                             stretch=stretch, anchor=anchor)

        for conf, color in self.CONF_BG.items():
            self.tree.tag_configure(conf, background=color, foreground=TEXTE)

        self.tree.bind("<Double-Button-1>", self._on_double_click)
        self.tree.bind("<Delete>", lambda e: self._del_row())
        self.tree.bind("<Control-d>", lambda e: self._dup_row())
        self.tree.bind("<Control-D>", lambda e: self._dup_row())
        self.tree.bind("<Button-1>", self._close_edit)

        # Compteur
        self.lbl_count = tk.Label(self, text="0 ligne", bg=BLANC,
                                  font=("Segoe UI", 8), fg="#888", anchor="e", padx=6)
        self.lbl_count.pack(fill="x")

    def _normalize_level_value(self, col_name, value):
        v = str(value or "").strip()
        if col_name not in self.niveaux:
            return v

        if self.mode == "comp":
            vu = v.upper().replace(" ", "")
            if vu in ("", "0", "-", "NON", "NONE"):
                return ""
            if vu in ("XX", "X2", "2"):
                return "XX"
            return "X"

        # mode == "conn"
        if not v:
            return "0"
        if v.isdigit():
            n = max(0, min(3, int(v)))
            return str(n)
        return "0"

    def _normalize_cell_value(self, col_name, value):
        v = str(value or "")
        v = v.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        v = re.sub(r"\s+", " ", v).strip()
        return self._normalize_level_value(col_name, v)

    def set_rows(self, rows):
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            values = [self._normalize_cell_value(c, row.get(c, "")) for c in self._columns]
            conf   = row.get("confidence", "manual")
            self.tree.insert("", "end", values=values, tags=(conf,))
        self._update_count()

    def get_rows(self):
        """Retourne les données actuelles sous forme de liste de dicts."""
        rows = []
        for item in self.tree.get_children():
            values = self.tree.item(item, "values")
            tags   = self.tree.item(item, "tags")
            row = {col: str(values[i]) if i < len(values) else ""
                   for i, col in enumerate(self._columns)}
            row["confidence"] = tags[0] if tags else "manual"
            rows.append(row)
        return rows

    def _update_count(self):
        n = len(self.tree.get_children())
        self.lbl_count.config(text=f"{n} ligne{'s' if n != 1 else ''}")

    def _close_edit(self, event=None):
        if self._edit_widget:
            try:
                self._edit_widget.destroy()
            except Exception:
                pass
            self._edit_widget = None

    def _on_double_click(self, event):
        """Ouvre un widget d'édition inline sur la cellule double-cliquée."""
        self._close_edit()

        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if not row_id or not col_id:
            return

        col_idx = int(col_id[1:]) - 1
        if col_idx < 0 or col_idx >= len(self._columns):
            return
        col_name = self._columns[col_idx]

        bbox = self.tree.bbox(row_id, col_id)
        if not bbox:
            return
        bx, by, bw, bh = bbox

        values  = list(self.tree.item(row_id, "values"))
        current = values[col_idx] if col_idx < len(values) else ""

        # Widget adapté au type de colonne
        is_niv_comp = (self.mode == "comp" and col_name in self.niveaux)
        is_niv_conn = (self.mode == "conn" and col_name in self.niveaux)

        if is_niv_comp:
            widget = ttk.Combobox(self.tree, values=["", "X", "XX"],
                                  font=("Segoe UI", 9, "bold"), state="readonly")
            widget.set(current)
        elif is_niv_conn:
            widget = ttk.Combobox(self.tree, values=["0", "1", "2", "3"],
                                  font=("Segoe UI", 9, "bold"), state="normal")
            widget.set(self._normalize_level_value(col_name, current))
        else:
            widget = tk.Entry(self.tree, font=("Segoe UI", 9), bd=1, relief="solid",
                              bg="#FFFDE7")
            widget.insert(0, current)
            widget.select_range(0, "end")

        widget.place(x=bx, y=by, width=max(bw, 60), height=bh)
        widget.focus_set()

        self._edit_widget  = widget
        self._edit_row_id  = row_id
        self._edit_col_idx = col_idx

        def _save(event=None):
            if not self._edit_widget:
                return
            v = self._edit_widget.get().strip()
            v = self._normalize_cell_value(col_name, v)
            vals = list(self.tree.item(self._edit_row_id, "values"))
            while len(vals) <= self._edit_col_idx:
                vals.append("")
            vals[self._edit_col_idx] = v
            self.tree.item(self._edit_row_id, values=vals)
            # Passer à la cellule suivante sur Tab
            if event and getattr(event, "keysym", "") == "Tab":
                next_idx = self._edit_col_idx + 1
                self._edit_widget.destroy()
                self._edit_widget = None
                if next_idx < len(self._columns):
                    col_next = f"#{next_idx + 1}"
                    self._simulate_edit(self._edit_row_id, col_next, next_idx)
            else:
                self._edit_widget.destroy()
                self._edit_widget = None

        def _cancel(event=None):
            self._close_edit()

        widget.bind("<Return>",   _save)
        widget.bind("<Tab>",      _save)
        widget.bind("<Escape>",   _cancel)
        widget.bind("<FocusOut>", _save)

    def _simulate_edit(self, row_id, col_id, col_idx):
        """Ouvre l'édition sur une cellule spécifique (après Tab)."""
        bbox = self.tree.bbox(row_id, col_id)
        if not bbox:
            return
        bx, by, bw, bh = bbox
        col_name = self._columns[col_idx]
        values  = list(self.tree.item(row_id, "values"))
        current = values[col_idx] if col_idx < len(values) else ""
        is_niv_comp = (self.mode == "comp" and col_name in self.niveaux)
        is_niv_conn = (self.mode == "conn" and col_name in self.niveaux)
        if is_niv_comp:
            widget = ttk.Combobox(self.tree, values=["", "X", "XX"],
                                  font=("Segoe UI", 9, "bold"), state="readonly")
            widget.set(self._normalize_level_value(col_name, current))
        elif is_niv_conn:
            widget = ttk.Combobox(self.tree, values=["0", "1", "2", "3"],
                                  font=("Segoe UI", 9, "bold"), state="normal")
            widget.set(self._normalize_level_value(col_name, current))
        else:
            widget = tk.Entry(self.tree, font=("Segoe UI", 9), bd=1, relief="solid", bg="#FFFDE7")
            widget.insert(0, current)
            widget.select_range(0, "end")
        widget.place(x=bx, y=by, width=max(bw, 60), height=bh)
        widget.focus_set()
        self._edit_widget  = widget
        self._edit_row_id  = row_id
        self._edit_col_idx = col_idx

        def _save(event=None):
            if not self._edit_widget:
                return
            v = self._edit_widget.get().strip()
            v = self._normalize_cell_value(col_name, v)
            vals = list(self.tree.item(self._edit_row_id, "values"))
            while len(vals) <= self._edit_col_idx:
                vals.append("")
            vals[self._edit_col_idx] = v
            self.tree.item(self._edit_row_id, values=vals)
            self._edit_widget.destroy()
            self._edit_widget = None

        widget.bind("<Return>",   _save)
        widget.bind("<Escape>",   self._close_edit)
        widget.bind("<FocusOut>", _save)

    def _add_row(self):
        self._close_edit()

        def _next_comp_code():
            used = set()
            for item in self.tree.get_children():
                vals = self.tree.item(item, "values")
                code = str(vals[0]).strip().upper() if vals else ""
                m = re.match(r"^CO(\d+)\.(\d+)$", code)
                if m:
                    used.add((int(m.group(1)), int(m.group(2))))
            major = 1
            while major <= 99:
                minor = 1
                while minor <= 99:
                    if (major, minor) not in used:
                        return f"CO{major}.{minor}"
                    minor += 1
                major += 1
            return "CO1.1"

        def _next_conn_ref():
            used = set()
            for item in self.tree.get_children():
                vals = self.tree.item(item, "values")
                ref = str(vals[0]).strip() if vals else ""
                m = re.match(r"^(\d+)-(\d+)$", ref)
                if m:
                    used.add((int(m.group(1)), int(m.group(2))))
            chap = 1
            while chap <= 99:
                sub = 1
                while sub <= 99:
                    if (chap, sub) not in used:
                        return f"{chap}-{sub}", str(chap)
                    sub += 1
                chap += 1
            return "1-1", "1"

        if self.mode == "comp":
            vals = {"code": _next_comp_code(), "libelle": "", "connaissances_liees": "",
                    "confidence": "manual", **{n: "" for n in self.niveaux}}
        else:
            new_ref, chap_id = _next_conn_ref()
            vals = {"ref": new_ref, "chapitre_id": chap_id, "chapitre_titre": f"Chapitre {chap_id}",
                    "sous_chapitre_titre": f"Connaissance {new_ref}", "detail": "",
                    "confidence": "manual", **{n: "0" for n in self.niveaux}}
        values = [str(vals.get(c, "")) for c in self._columns]
        item   = self.tree.insert("", "end", values=values, tags=("manual",))
        self.tree.see(item)
        self.tree.selection_set(item)
        self._update_count()

    def _dup_row(self):
        self._close_edit()
        selected = self.tree.selection()
        if not selected:
            return

        def _next_comp_code(exclude_item=None):
            used = set()
            for item in self.tree.get_children():
                if exclude_item is not None and item == exclude_item:
                    continue
                vals = self.tree.item(item, "values")
                code = str(vals[0]).strip().upper() if vals else ""
                m = re.match(r"^CO(\d+)\.(\d+)$", code)
                if m:
                    used.add((int(m.group(1)), int(m.group(2))))
            major = 1
            while major <= 99:
                minor = 1
                while minor <= 99:
                    if (major, minor) not in used:
                        return f"CO{major}.{minor}"
                    minor += 1
                major += 1
            return "CO1.1"

        def _next_conn_ref(exclude_item=None):
            used = set()
            for item in self.tree.get_children():
                if exclude_item is not None and item == exclude_item:
                    continue
                vals = self.tree.item(item, "values")
                ref = str(vals[0]).strip() if vals else ""
                m = re.match(r"^(\d+)-(\d+)$", ref)
                if m:
                    used.add((int(m.group(1)), int(m.group(2))))
            chap = 1
            while chap <= 99:
                sub = 1
                while sub <= 99:
                    if (chap, sub) not in used:
                        return f"{chap}-{sub}", str(chap)
                    sub += 1
                chap += 1
            return "1-1", "1"

        new_items = []
        for item in selected:
            values = list(self.tree.item(item, "values"))
            while len(values) < len(self._columns):
                values.append("")

            if self.mode == "comp":
                values[0] = _next_comp_code()
            else:
                new_ref, chap_id = _next_conn_ref()
                values[0] = new_ref
                chap_idx = self._columns.index("chapitre_id") if "chapitre_id" in self._columns else None
                chap_t_idx = self._columns.index("chapitre_titre") if "chapitre_titre" in self._columns else None
                sc_t_idx = self._columns.index("sous_chapitre_titre") if "sous_chapitre_titre" in self._columns else None
                if chap_idx is not None:
                    values[chap_idx] = chap_id
                if chap_t_idx is not None and not str(values[chap_t_idx]).strip():
                    values[chap_t_idx] = f"Chapitre {chap_id}"
                if sc_t_idx is not None and not str(values[sc_t_idx]).strip():
                    values[sc_t_idx] = f"Connaissance {new_ref}"

            new_item = self.tree.insert("", "end", values=values, tags=("manual",))
            new_items.append(new_item)

        if new_items:
            self.tree.selection_set(new_items)
            self.tree.see(new_items[-1])
            self._update_count()

    def _del_row(self):
        self._close_edit()
        selected = self.tree.selection()
        if not selected:
            return
        n = len(selected)
        if not messagebox.askyesno("Supprimer", f"Supprimer {n} ligne{'s' if n > 1 else ''} ?",
                                   parent=self):
            return
        for item in selected:
            self.tree.delete(item)
        self._update_count()

    def _export_csv(self):
        self._close_edit()
        rows  = self.get_rows()
        fname = "competences.csv" if self.mode == "comp" else "connaissances.csv"
        csv_str = (core_comp_rows_to_csv_str(rows, self.niveaux) if self.mode == "comp"
               else core_conn_rows_to_csv_str(rows, self.niveaux))
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=fname, title=f"Exporter {fname}", parent=self,
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            f.write(csv_str)
        messagebox.showinfo("Export CSV", f"Fichier enregistré :\n{path}", parent=self)

    def _import_csv(self):
        self._close_edit()
        path = filedialog.askopenfilename(
            filetypes=[("CSV", "*.csv"), ("Tous", "*.*")],
            title="Importer un fichier CSV", parent=self,
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig") as f:
                csv_text = f.read()
            if self.mode == "comp":
                rows = _comp_csv_str_to_rows(csv_text, self.niveaux)
            else:
                rows = _conn_csv_str_to_rows(csv_text, self.niveaux)
            self.set_rows(rows)
            messagebox.showinfo("Import CSV", f"{len(rows)} lignes importées.", parent=self)
        except Exception as e:
            messagebox.showerror("Erreur CSV", str(e), parent=self)


# ─── Assistant d'import ───────────────────────────────────────────────────────

class ImporteurReferentiel(tk.Toplevel):
    """
    Assistant 5 étapes pour créer un nouveau référentiel pédagogique.

    Étape 1 : Métadonnées (nom, niveaux, classes)
    Étape 2 : Source — PDF (extraction auto) ou CSV (import direct)
    Étape 3 : Revue interactive des compétences (TableauEditable)
    Étape 4 : Revue interactive des connaissances (TableauEditable)
    Étape 5 : Récapitulatif + confirmation → création du profil
    """

    def __init__(self, parent, on_success=None):
        super().__init__(parent)
        self.on_success  = on_success
        self.title("Importer un référentiel")
        self.geometry("960x640")
        self.minsize(820, 560)
        self.configure(bg=BLANC)
        self.grab_set()
        self.resizable(True, True)

        # Variables de saisie
        self.var_nom     = tk.StringVar()
        self.var_id      = tk.StringVar()
        self.var_desc    = tk.StringVar()
        self.var_niv     = tk.StringVar(value="IT;I2D;2I2D")
        self.var_classes = tk.StringVar()
        self.var_couleur = tk.StringVar(value=BLEU)
        self.var_fmt     = tk.StringVar(value="Non déterminé")
        self.var_source  = tk.StringVar(value="")
        self._source_pdf_path = None

        self._comp_rows = []
        self._conn_rows = []
        self._tableau_comp = None
        self._tableau_conn = None

        self._crossref_matrix = {}
        self._quality_summary = None

        self.step   = 0
        self._steps = [self._step1, self._step2, self._step3, self._step4, self._step5]

        self._container = tk.Frame(self, bg=BLANC)
        self._container.pack(fill="both", expand=True)

        self._build_nav()
        self._show_step(0)
        self.bind("<F1>", lambda e: show_quick_help(
            self,
            "Aide — Import de référentiel",
            [
                "Étape 1 : renseignez nom, niveaux et classes.",
                "Étape 2 : importez un PDF ou des CSV.",
                "Étapes 3-4 : corrigez les lignes si nécessaire.",
                "Étape 5 : vérifiez le résumé puis créez le profil.",
            ],
        ))

    # ── Navigation ────────────────────────────────────────────────────────────

    def _build_nav(self):
        nav = tk.Frame(self, bg=GRIS2, pady=7)
        nav.pack(fill="x", side="bottom")

        # Indicateur d'étapes
        steps_frm = tk.Frame(nav, bg=GRIS2)
        steps_frm.pack(side="left", padx=14)
        self._step_labels = []
        for i, lbl in enumerate(["Informations", "Source", "Compétences", "Connaissances", "Confirmation"]):
            lb = tk.Label(steps_frm, text=f"{i+1}. {lbl}", bg=GRIS2,
                          font=("Segoe UI", 8), fg="#999", padx=5)
            lb.pack(side="left")
            self._step_labels.append(lb)

        btn_frm = tk.Frame(nav, bg=GRIS2)
        btn_frm.pack(side="right", padx=14)
        tk.Button(btn_frm, text="?",
                  command=lambda: show_quick_help(
                      self,
                      "Aide — Import de référentiel",
                      [
                          "Étape 1 : renseignez nom, niveaux et classes.",
                          "Étape 2 : importez un PDF ou des CSV.",
                          "Étapes 3-4 : corrigez les lignes si nécessaire.",
                          "Étape 5 : vérifiez le résumé puis créez le profil.",
                      ],
                  ),
                  bg="#2F5E9A", fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), width=3, pady=5).pack(side="left", padx=(0, 8))
        self.btn_prev = tk.Button(btn_frm, text="◀  Précédent", command=self._prev,
                                  bg="#DDD", fg=TEXTE, relief="flat",
                                  font=("Segoe UI", 10), state="disabled", padx=10, pady=5)
        self.btn_prev.pack(side="left", padx=6)
        self.btn_next = tk.Button(btn_frm, text="Suivant  ▶", command=self._next,
                                  bg=BLEU, fg=BLANC, relief="flat",
                                  font=("Segoe UI", 10, "bold"), padx=12, pady=5)
        self.btn_next.pack(side="left")

    def _show_step(self, n):
        for w in self._container.winfo_children():
            w.destroy()
        self._tableau_comp = None
        self._tableau_conn = None
        self.step = n
        self._steps[n]()
        self.btn_prev.configure(state="normal" if n > 0 else "disabled")
        last = (n == len(self._steps) - 1)
        self.btn_next.configure(
            text="✅  Créer le référentiel" if last else "Suivant  ▶",
            bg=VERT if last else BLEU,
            command=self._creer if last else self._next,
        )
        for i, lb in enumerate(self._step_labels):
            if i < n:
                lb.configure(fg=VERT,  font=("Segoe UI", 8, "bold"))
            elif i == n:
                lb.configure(fg=BLEU,  font=("Segoe UI", 8, "bold"))
            else:
                lb.configure(fg="#999", font=("Segoe UI", 8))

    def _niveaux(self):
        return [n.strip() for n in self.var_niv.get().split(";") if n.strip()]

    def _prev(self):
        self._sync_tableau()
        if self.step > 0:
            self._show_step(self.step - 1)

    def _next(self):
        if self._valider():
            self._sync_tableau()
            self._show_step(self.step + 1)

    def _sync_tableau(self):
        if self.step == 2 and self._tableau_comp:
            self._comp_rows = self._tableau_comp.get_rows()
        elif self.step == 3 and self._tableau_conn:
            self._conn_rows = self._tableau_conn.get_rows()

    def _valider(self):
        if self.step == 0:
            if not self.var_nom.get().strip():
                messagebox.showwarning("Champ requis", "Entrez le nom du référentiel.", parent=self)
                return False
            if not self._niveaux():
                messagebox.showwarning("Champ requis", "Entrez au moins un niveau (ex: IT;I2D).",
                                       parent=self)
                return False
            if not self.var_id.get().strip():
                self.var_id.set(re.sub(r"[^a-z0-9]+", "_",
                                       self.var_nom.get().strip().lower())[:20].strip("_"))
        return True

    # ── Helpers UI ────────────────────────────────────────────────────────────

    def _section(self, parent, titre, color=BLEU):
        tk.Label(parent, text=titre, bg=color, fg=BLANC,
                 font=("Segoe UI", 12, "bold"), pady=9, padx=14, anchor="w",
                 ).pack(fill="x", pady=(0, 14))

    def _field(self, parent, label, var, hint="", required=False):
        frm = tk.Frame(parent, bg=BLANC)
        frm.pack(fill="x", pady=3)
        tk.Label(frm, text=f"{label} *" if required else label, bg=BLANC,
                 font=("Segoe UI", 10, "bold"), width=22, anchor="w").pack(side="left")
        tk.Entry(frm, textvariable=var, font=("Segoe UI", 10),
                 width=40).pack(side="left", fill="x", expand=True, padx=6)
        if hint:
            tk.Label(parent, text=hint, bg=BLANC, fg="#666",
                     font=("Segoe UI", 8), anchor="w").pack(anchor="w", padx=24)
            if ";" in hint:
                tk.Label(parent, text="Séparateur attendu :  ;",
                         bg=BLANC, fg="#BF360C", font=("Segoe UI", 8, "bold"),
                         anchor="w").pack(anchor="w", padx=24)

    # ── Étapes ────────────────────────────────────────────────────────────────

    def _step1(self):
        pad = tk.Frame(self._container, bg=BLANC, padx=28, pady=14)
        pad.pack(fill="both", expand=True)
        self._section(pad, "1.  Informations du référentiel")
        self._field(pad, "Nom *", self.var_nom, required=True,
                    hint="Ex : BTS Conception des Produits Industriels")
        self._field(pad, "Identifiant", self.var_id,
                    hint="Généré automatiquement si vide (ex : bts_cpi)")
        self._field(pad, "Description", self.var_desc,
                    hint="Description courte (optionnel)")
        self._field(pad, "Niveaux *", self.var_niv, required=True,
                    hint="Séparés par «;» — ex : 1re année;2e année  ou  IT;I2D;2I2D")
        self._field(pad, "Classes", self.var_classes,
                    hint="Séparées par «;» — laisser vide pour utiliser les niveaux comme classes")
        tk.Label(pad, text="* Champs obligatoires", bg=BLANC,
                 fg="#AAA", font=("Segoe UI", 8)).pack(anchor="w", pady=(10, 0))

    def _step2(self):
        pad = tk.Frame(self._container, bg=BLANC, padx=28, pady=14)
        pad.pack(fill="both", expand=True)
        self._section(pad, "2.  Source du référentiel")

        # Bandeau état courant
        if self._comp_rows or self._conn_rows:
            info = tk.Label(pad,
                            text=f"✅  Données déjà chargées : {len(self._comp_rows)} compétences, "
                                 f"{len(self._conn_rows)} connaissances  — Format : {self.var_fmt.get()}\n"
                                 f"     Source : {self.var_source.get() or 'inconnue'}",
                            bg=VERT_CLAIR, fg=VERT, font=("Segoe UI", 9, "bold"),
                            padx=10, pady=8, anchor="w", justify="left")
            info.pack(fill="x", pady=(0, 6))

            if self._quality_summary:
                q = self._quality_summary
                issues = q.get("issues", [])
                n_matrix = len(self._crossref_matrix.get("savoirs", []))
                n_matrix_c = len(self._crossref_matrix.get("competences", []))
                bg_q = VERT_CLAIR if not issues else ORANGE_CLAIR
                fg_q = VERT if not issues else "#E65100"
                lines = [f"Qualité  ·  {q['n_comp']} compétences  ·  {q['n_conn']} connaissances"]
                if n_matrix:
                    lines.append(f"✅ Matrice croisée : {n_matrix} savoirs × {n_matrix_c} compétences")
                if issues:
                    lines.extend([f"⚠  {i}" for i in issues])
                    lines.append("→ Vérifiez les lignes surlignées à l'étape suivante")
                else:
                    lines.append("✅ Aucune anomalie détectée")
                tk.Label(pad, text="\n".join(lines),
                         bg=bg_q, fg=fg_q, font=("Segoe UI", 9),
                         padx=10, pady=7, anchor="w", justify="left").pack(fill="x", pady=(0, 12))

        # Option A : PDF
        frm_a = tk.LabelFrame(pad, text=" 📄  Extraction automatique depuis un PDF ",
                               bg=BLANC, font=("Segoe UI", 10, "bold"), fg=BLEU,
                               padx=14, pady=10)
        frm_a.pack(fill="x", pady=(0, 10))
        tk.Label(frm_a,
                 text="Le PDF est analysé pour extraire compétences et connaissances.\n"
                      "pdfplumber est utilisé si installé (résultats nettement meilleurs) ;\n"
                      "sinon pypdf est utilisé en fallback (texte brut + regex).\n"
                      "Pour les BTS : si le tableau compétences est en mise en page multi-colonnes,\n"
                      "les libellés peuvent être imprécis → vérifiez et corrigez à l'étape 3.\n"
                      "La matrice croisée savoirs × compétences est importée automatiquement.",
                 bg=BLANC, fg="#555", font=("Segoe UI", 9), justify="left").pack(anchor="w")
        tk.Button(frm_a, text="📂  Choisir un PDF et lancer l'extraction",
                  command=self._extraire_pdf,
                  bg=BLEU, fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=12, pady=6).pack(anchor="w", pady=(8, 2))
        tk.Label(frm_a,
                 text="Installer pdfplumber (recommandé) :  pip install pdfplumber",
                 bg=BLANC, fg="#888", font=("Segoe UI", 8)).pack(anchor="w")

        # Option B : CSV
        frm_b = tk.LabelFrame(pad, text=" 📊  Import de fichiers CSV (saisie manuelle) ",
                               bg=BLANC, font=("Segoe UI", 10, "bold"), fg=ORANGE,
                               padx=14, pady=10)
        frm_b.pack(fill="x", pady=(0, 10))
        tk.Label(frm_b,
                 text="Importez des fichiers CSV compétences et/ou connaissances existants.\n"
                      "Utilisez les modèles vides ci-dessous pour préparer vos données.",
                 bg=BLANC, fg="#555", font=("Segoe UI", 9), justify="left").pack(anchor="w")

        btn_row = tk.Frame(frm_b, bg=BLANC)
        btn_row.pack(anchor="w", pady=(8, 0))
        tk.Button(btn_row, text="⬇  Télécharger modèles CSV vides",
                  command=self._export_templates,
                  bg="#EEE", fg=TEXTE, relief="flat",
                  font=("Segoe UI", 9), padx=8, pady=4).pack(side="left")
        tk.Button(btn_row, text="📂  Importer CSV",
                  command=self._importer_csv,
                  bg=ORANGE, fg=BLANC, relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=8, pady=4).pack(side="left", padx=(8, 0))

    def _compute_quality_summary(self, comp_rows, conn_rows, fmt):
        """Calcule un résumé qualité rapide pour affichage dans le wizard."""
        conn_refs = {str(r.get("ref", "")).strip() for r in conn_rows if str(r.get("ref", "")).strip()}
        code_counts = {}
        for row in comp_rows:
            code = str(row.get("code", "")).strip().upper()
            if code:
                code_counts[code] = code_counts.get(code, 0) + 1
        duplicate_codes = [c for c, n in code_counts.items() if n > 1]
        empty_links = [
            str(r.get("code", "")).strip() for r in comp_rows
            if not str(r.get("connaissances_liees", "")).strip()
        ]
        unknown_count = sum(
            1 for row in comp_rows
            for ref in str(row.get("connaissances_liees", "")).split(";")
            if ref.strip() and ref.strip() not in conn_refs
        )
        issues = []
        if duplicate_codes:
            issues.append(f"{len(duplicate_codes)} code(s) dupliqué(s) : {', '.join(duplicate_codes[:5])}")
        if empty_links:
            issues.append(f"{len(empty_links)} compétence(s) sans liens vers savoirs")
        if unknown_count:
            issues.append(f"{unknown_count} lien(s) vers savoirs inconnus")
        return {"fmt": fmt, "n_comp": len(comp_rows), "n_conn": len(conn_rows), "issues": issues}

    def _extraire_pdf(self):
        niveaux = self._niveaux()
        if not niveaux:
            messagebox.showwarning("Niveaux requis",
                                   "Définissez les niveaux à l'étape 1 avant l'extraction.",
                                   parent=self)
            return
        path = filedialog.askopenfilename(
            filetypes=[("PDF", "*.pdf"), ("Tous", "*.*")],
            title="Sélectionner un référentiel PDF", parent=self,
        )
        if not path:
            return

        # Fenêtre de progression
        prog = tk.Toplevel(self)
        prog.title("Extraction en cours…")
        prog.geometry("380x110")
        prog.configure(bg=BLANC)
        prog.grab_set()
        tk.Label(prog, text=f"Analyse de : {Path(path).name}",
                 bg=BLANC, font=("Segoe UI", 10), pady=12).pack()
        bar = ttk.Progressbar(prog, mode="indeterminate", length=320)
        bar.pack(padx=30)
        bar.start(10)
        prog.update()

        try:
            comp_rows, conn_rows, fmt = core_extract_from_pdf(path, niveaux)
            prog.destroy()
            self._comp_rows = comp_rows
            self._conn_rows = conn_rows
            self._source_pdf_path = str(path)
            self.var_fmt.set(fmt)
            self.var_source.set(Path(path).name)

            self._quality_summary = self._compute_quality_summary(comp_rows, conn_rows, fmt)
            if fmt == "BTS":
                self._crossref_matrix = core_extract_crossref_matrix(path) or {}
            else:
                self._crossref_matrix = {}

            n_high = sum(1 for r in comp_rows if r.get("confidence") == "high")
            n_low  = sum(1 for r in comp_rows if r.get("confidence") == "low")
            n_matrix = len(self._crossref_matrix.get("savoirs", []))
            n_matrix_c = len(self._crossref_matrix.get("competences", []))
            matrix_line = (
                f"Matrice croisée : {n_matrix} savoirs × {n_matrix_c} compétences ✅"
                if n_matrix else "Matrice croisée : non détectée dans ce PDF"
            )
            issues = self._quality_summary["issues"]
            issues_txt = "\n".join(f"  ⚠ {i}" for i in issues) if issues else "  ✅ Aucune anomalie détectée"
            msg = (f"Format détecté : {fmt}\n\n"
                   f"Compétences extraites : {len(comp_rows)}\n"
                   f"  ✅ Depuis tableaux    : {n_high}\n"
                   f"  ⚠  Heuristique regex : {n_low}\n\n"
                   f"Connaissances extraites : {len(conn_rows)}\n"
                   f"{matrix_line}\n\n"
                   f"Qualité :\n{issues_txt}\n\n"
                   f"Vérifiez et corrigez les données aux étapes 3 et 4.\n"
                   f"Les lignes colorées en orange/rouge méritent une vérification.")
            messagebox.showinfo("Extraction terminée", msg, parent=self)
            self._show_step(self.step)

        except ImportError:
            prog.destroy()
            messagebox.showerror(
                "Module manquant",
                "Aucun module d'extraction PDF disponible.\n\n"
                "Recommandé :\n"
                "  pip install pdfplumber\n\n"
                "Alternative (résultats moindres) :\n"
                "  pip install pypdf",
                parent=self,
            )
        except Exception as e:
            prog.destroy()
            messagebox.showerror("Erreur PDF", str(e), parent=self)

    def _export_templates(self):
        niveaux = self._niveaux() or ["NIVEAU_1", "NIVEAU_2"]
        dossier = filedialog.askdirectory(title="Choisir le dossier de destination", parent=self)
        if not dossier:
            return
        comp_path = Path(dossier) / "competences_modele.csv"
        conn_path = Path(dossier) / "connaissances_modele.csv"

        with open(comp_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["code", "libelle"] + niveaux + ["connaissances_liees"])
            w.writerow(["CO1.1", "Libellé de la compétence…"]
                       + ["X" if i == 0 else "" for i in range(len(niveaux))]
                       + ["1-1;1-2"])

        with open(conn_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["ref", "chapitre_id", "chapitre_titre",
                        "sous_chapitre_titre", "detail"] + niveaux)
            w.writerow(["1-1", "1", "Titre du chapitre", "Titre du sous-chapitre", ""]
                       + ["1"] * len(niveaux))

        if messagebox.askyesno("Modèles créés",
                               f"Modèles créés :\n{comp_path}\n{conn_path}\n\n"
                               "Ouvrir le dossier ?", parent=self):
            try:
                os.startfile(str(dossier))
            except Exception:
                pass

    def _importer_csv(self):
        niveaux = self._niveaux()
        paths = filedialog.askopenfilenames(
            filetypes=[("CSV", "*.csv"), ("Tous", "*.*")],
            title="Sélectionner CSV compétences et/ou connaissances", parent=self,
        )
        if not paths:
            return
        for path in paths:
            name = Path(path).name.lower()
            try:
                with open(path, encoding="utf-8-sig") as f:
                    txt = f.read()
                if any(kw in name for kw in ("conn", "savoir", "connai")):
                    rows = _conn_csv_str_to_rows(txt, niveaux)
                    self._conn_rows = rows
                    messagebox.showinfo("Import", f"{len(rows)} connaissances importées.", parent=self)
                else:
                    rows = _comp_csv_str_to_rows(txt, niveaux)
                    self._comp_rows = rows
                    messagebox.showinfo("Import", f"{len(rows)} compétences importées.", parent=self)
                self._source_pdf_path = None
                self.var_source.set(Path(path).name)
            except Exception as e:
                messagebox.showerror("Erreur CSV", f"{Path(path).name} : {e}", parent=self)
        self._show_step(self.step)

    def _step3(self):
        pad = tk.Frame(self._container, bg=BLANC)
        pad.pack(fill="both", expand=True)

        hdr = tk.Frame(pad, bg=BLEU, padx=14, pady=9)
        hdr.pack(fill="x")
        tk.Label(hdr, text="3.  Compétences — Vérification et correction",
                 bg=BLEU, fg=BLANC, font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Label(hdr, text="Double-cliquez sur une cellule pour la modifier • Tab = cellule suivante",
                 bg=BLEU, fg="#BBDDFF", font=("Segoe UI", 8)).pack(side="right")

        self._tableau_comp = TableauEditable(pad, self._niveaux(), mode="comp")
        self._tableau_comp.pack(fill="both", expand=True)
        self._tableau_comp.set_rows(self._comp_rows)

    def _step4(self):
        pad = tk.Frame(self._container, bg=BLANC)
        pad.pack(fill="both", expand=True)

        hdr = tk.Frame(pad, bg=ORANGE, padx=14, pady=9)
        hdr.pack(fill="x")
        tk.Label(hdr, text="4.  Connaissances — Vérification et correction",
                 bg=ORANGE, fg=BLANC, font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Label(hdr, text="Double-cliquez sur une cellule pour la modifier",
                 bg=ORANGE, fg="#FFDDBB", font=("Segoe UI", 8)).pack(side="right")

        self._tableau_conn = TableauEditable(pad, self._niveaux(), mode="conn")
        self._tableau_conn.pack(fill="both", expand=True)
        self._tableau_conn.set_rows(self._conn_rows)

    def _step5(self):
        pad = tk.Frame(self._container, bg=BLANC, padx=28, pady=14)
        pad.pack(fill="both", expand=True)
        self._section(pad, "5.  Récapitulatif — Prêt à créer le référentiel", VERT)

        niveaux = self._niveaux()
        classes = [c.strip() for c in self.var_classes.get().split(";") if c.strip()]
        infos   = [
            ("Nom",                     self.var_nom.get()),
            ("Identifiant (dossier)",   self.var_id.get() or "(auto)"),
            ("Description",             self.var_desc.get() or "—"),
            ("Niveaux",                 ", ".join(niveaux)),
            ("Classes",                 ", ".join(classes) if classes else "(= niveaux)"),
            ("Compétences",             f"{len(self._comp_rows)} lignes"),
            ("Connaissances",           f"{len(self._conn_rows)} lignes"),
            ("Format détecté",          self.var_fmt.get()),
        ]
        for k, v in infos:
            frm = tk.Frame(pad, bg=BLANC)
            frm.pack(fill="x", pady=3)
            tk.Label(frm, text=f"{k} :", bg=BLANC, width=22, anchor="w",
                     font=("Segoe UI", 10, "bold")).pack(side="left")
            tk.Label(frm, text=v, bg=BLANC, anchor="w", fg=TEXTE,
                     font=("Segoe UI", 10)).pack(side="left", padx=6)

        if not self._comp_rows and not self._conn_rows:
            tk.Label(pad,
                     text="⚠  Aucune donnée chargée. Retournez à l'étape 2 pour importer des données.",
                     bg=ORANGE_CLAIR, fg="#BF360C",
                     font=("Segoe UI", 9), padx=10, pady=8, anchor="w").pack(fill="x", pady=(14, 0))
        else:
            tk.Label(pad,
                     text="✅  Les données seront enregistrées dans referentiels/<identifiant>/\n"
                         "     Vous pourrez créer les séquences depuis l'onglet «Séquence».",
                     bg=VERT_CLAIR, fg=VERT,
                     font=("Segoe UI", 9), padx=10, pady=8, anchor="w").pack(fill="x", pady=(14, 0))

    def _creer(self):
        """Validation finale et création du profil."""
        self._sync_tableau()

        niveaux   = self._niveaux()
        classes   = [c.strip() for c in self.var_classes.get().split(";") if c.strip()]
        profil_id = re.sub(r"[^a-z0-9]+", "_",
                           (self.var_id.get().strip() or self.var_nom.get().strip()).lower()
                           )[:20].strip("_")

        if not profil_id:
            messagebox.showwarning("ID invalide", "L'identifiant du profil est vide.", parent=self)
            return

        comp_rows = (self._tableau_comp.get_rows() if self._tableau_comp
                     else self._comp_rows)
        conn_rows = (self._tableau_conn.get_rows() if self._tableau_conn
                     else self._conn_rows)

        try:
            nom_ref = self.var_nom.get().strip().lower()
            schema = "bts" if "bts" in nom_ref else "sti2d"

            profil_dir = PROFILS_DIR / profil_id
            profil_dir.mkdir(parents=True, exist_ok=True)

            profil = {
                "id":          profil_id,
                "nom":         self.var_nom.get().strip(),
                "description": self.var_desc.get().strip(),
                "schema":      schema,
                "niveaux":     niveaux,
                "classes":     classes if classes else niveaux,
                "couleur":     self.var_couleur.get(),
                "fichiers": {
                    "competences":   "referentiel_competences.json",
                    "connaissances": "referentiel_connaissances.json",
                    "activites_types": "referentiel_activites_types.json",
                    "themes":        "themes_problematiques.json",
                },
            }
            (profil_dir / "profil.json").write_text(
                json.dumps(profil, ensure_ascii=False, indent=2), encoding="utf-8")

            comp_json = core_rows_to_comp_json(comp_rows, niveaux)
            (profil_dir / "referentiel_competences.json").write_text(
                json.dumps(comp_json, ensure_ascii=False, indent=2), encoding="utf-8")

            conn_json = core_rows_to_conn_json(conn_rows, niveaux)
            (profil_dir / "referentiel_connaissances.json").write_text(
                json.dumps(conn_json, ensure_ascii=False, indent=2), encoding="utf-8")

            if schema == "bts":
                at_json = core_build_bts_at_json(comp_json, conn_json)
                if self._source_pdf_path:
                    matrix = core_extract_bts_matrix_from_pdf(self._source_pdf_path)
                    if matrix:
                        at_json = core_enrich_bts_at_with_matrix(at_json, matrix)
            else:
                at_json = {
                    "meta": {
                        "schema": "bts_at_v1",
                        "version": 1,
                    },
                    "activites": {},
                }
            (profil_dir / "referentiel_activites_types.json").write_text(
                json.dumps(at_json, ensure_ascii=False, indent=2), encoding="utf-8")

            (profil_dir / "themes_problematiques.json").write_text("[]", encoding="utf-8")
            (profil_dir / "themes_custom.json").write_text("[]", encoding="utf-8")

            n_matrix = 0
            if getattr(self, "_crossref_matrix", {}):
                n_matrix = len(self._crossref_matrix.get("savoirs", []))
                if n_matrix:
                    (profil_dir / "matrice_savoir_competence.csv").write_text(
                        core_crossref_to_savoir_csv(self._crossref_matrix),
                        encoding="utf-8", newline="")
                    (profil_dir / "matrice_competence_savoir.csv").write_text(
                        core_crossref_to_comp_csv(self._crossref_matrix),
                        encoding="utf-8", newline="")

            n_comp = len(comp_json.get("competences", {}))
            n_conn = sum(len(v.get("sous_chapitres", {})) for v in conn_json.values())
            matrix_line = f"  Matrice croisée : {n_matrix} savoirs\n" if n_matrix else ""
            messagebox.showinfo(
                "Référentiel créé ✔",
                f"Référentiel « {profil['nom']} » créé avec succès !\n\n"
                f"  Compétences importées : {n_comp}\n"
                f"  Connaissances importées : {n_conn}\n"
                f"{matrix_line}\n"
                f"Dossier : {profil_dir}\n\n"
                f"Créez vos séquences depuis l'onglet «Séquence» après avoir sélectionné ce profil.",
                parent=self,
            )
            self.destroy()
            if self.on_success:
                self.on_success()

        except Exception as e:
            messagebox.showerror("Erreur de création", str(e), parent=self)


# ─── Sélecteur de profil ──────────────────────────────────────────────────────

class ProfilSelecteur(tk.Toplevel):
    """
    Dialog modale : choisir ou importer un référentiel pédagogique.
    Appelle on_select(profil_dir: Path) quand un profil est confirmé.
    Fermer la fenêtre sans choisir ne ferme pas l'application parente.
    """

    def __init__(self, parent, on_select):
        super().__init__(parent)
        self.on_select = on_select
        self.title("Choisir un référentiel")
        self.geometry("600x490")
        self.resizable(False, False)
        self.configure(bg=BLANC)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._profils = []
        self._build()
        self._refresh()
        self.bind("<F1>", lambda e: show_quick_help(
            self,
            "Aide — Référentiels",
            [
                "Sélectionnez un référentiel puis cliquez Ouvrir.",
                "Le bouton Importer lance l'assistant 5 étapes.",
                "Supprimer efface définitivement le profil choisi.",
            ],
        ))

    def _build(self):
        hdr = tk.Frame(self, bg=BLEU)
        hdr.pack(fill="x")
        tk.Button(hdr, text="?",
                  command=lambda: show_quick_help(
                      self,
                      "Aide — Référentiels",
                      [
                          "Sélectionnez un référentiel puis cliquez Ouvrir.",
                          "Le bouton Importer lance l'assistant 5 étapes.",
                          "Supprimer efface définitivement le profil choisi.",
                      ],
                  ),
                  bg="#2F5E9A", fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), width=3).pack(side="right", padx=8, pady=8)
        tk.Label(hdr, text="🎓  Générateur de documents pédagogiques",
                 bg=BLEU, fg=BLANC, font=("Segoe UI", 14, "bold"), pady=14).pack()
        tk.Label(hdr, text="Sélectionnez ou importez un référentiel pédagogique",
                 bg=BLEU, fg="#BBDDFF", font=("Segoe UI", 10)).pack(pady=(0, 12))

        body = tk.Frame(self, bg=BLANC, padx=28, pady=16)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Référentiels disponibles :",
                 bg=BLANC, font=("Segoe UI", 10, "bold"), fg=TEXTE).pack(anchor="w")

        frm_list = tk.Frame(body, bg=BLANC,
                            highlightbackground="#DADCE0", highlightthickness=1)
        frm_list.pack(fill="both", expand=True, pady=(6, 8))
        sb = ttk.Scrollbar(frm_list, orient="vertical")
        sb.pack(side="right", fill="y")
        self.lb = tk.Listbox(frm_list, font=("Segoe UI", 11), bg="#FAFAFA",
                             selectbackground=BLEU, selectforeground=BLANC,
                             relief="flat", bd=0, activestyle="none", height=5,
                             yscrollcommand=sb.set)
        self.lb.pack(fill="both", expand=True, padx=2, pady=2)
        sb.config(command=self.lb.yview)
        self.lb.bind("<Double-Button-1>", lambda e: self._ouvrir())
        self.lb.bind("<<ListboxSelect>>", lambda e: self._on_sel())

        self.lbl_info = tk.Label(body, text="", bg=GRIS2, fg="#555",
                                 font=("Segoe UI", 9, "italic"),
                                 anchor="w", padx=10, pady=7,
                                 wraplength=520, justify="left")
        self.lbl_info.pack(fill="x", pady=(0, 10))

        tk.Button(body, text="➕  Importer un nouveau référentiel",
                  command=self._importer,
                  bg=ORANGE, fg=BLANC, relief="flat",
                  font=("Segoe UI", 10, "bold"), pady=7).pack(fill="x", pady=(0, 6))

        self.btn_suppr = tk.Button(body, text="🗑  Supprimer ce référentiel",
                                   command=self._supprimer,
                                   bg=ROUGE, fg=BLANC, relief="flat",
                                   font=("Segoe UI", 10, "bold"), pady=7,
                                   state="disabled")
        self.btn_suppr.pack(fill="x", pady=(0, 6))

        self.btn_ouvrir = tk.Button(body, text="✅  Ouvrir ce référentiel",
                                    command=self._ouvrir,
                                    bg=BLEU, fg=BLANC, relief="flat",
                                    font=("Segoe UI", 11, "bold"), pady=9,
                                    state="disabled")
        self.btn_ouvrir.pack(fill="x")

    def _refresh(self):
        self.lb.delete(0, "end")
        self._profils = list_profils()
        for pid, pnom, _ in self._profils:
            self.lb.insert("end", f"   {pnom}   ({pid})")
        if self._profils:
            self.lb.selection_set(0)
            self._on_sel()

    def _on_sel(self):
        sel = self.lb.curselection()
        if not sel:
            self.btn_ouvrir.configure(state="disabled")
            self.btn_suppr.configure(state="disabled")
            self.lbl_info.configure(text="")
            return
        self.btn_ouvrir.configure(state="normal")
        _, _, pdir = self._profils[sel[0]]
        meta = load_profil_meta(pdir)
        pid  = str(meta.get("id", "")).lower()
        is_protected = (pid == "sti2d" or pdir.name.lower() == "sti2d")
        self.btn_suppr.configure(state="disabled" if is_protected else "normal")

        lines = []
        if meta.get("description"):
            lines.append(meta["description"])
        niv = ", ".join(meta.get("niveaux", []))
        cls = ", ".join(meta.get("classes", []))
        if niv:
            lines.append(f"Niveaux : {niv}")
        if cls:
            lines.append(f"Classes : {cls}")
        if is_protected:
            lines.append("⚠  Référentiel protégé — ne peut pas être supprimé")
        self.lbl_info.configure(text="   " + "\n   ".join(lines) if lines else "")

    def _ouvrir(self):
        sel = self.lb.curselection()
        if not sel:
            return
        _, _, pdir = self._profils[sel[0]]
        self.destroy()
        self.on_select(pdir)

    def _importer(self):
        w = ImporteurReferentiel(self, on_success=self._refresh)
        self.wait_window(w)

    def _supprimer(self):
        sel = self.lb.curselection()
        if not sel:
            return
        pid, pnom, pdir = self._profils[sel[0]]
        if str(pid).lower() == "sti2d" or pdir.name.lower() == "sti2d":
            messagebox.showwarning("Protégé",
                                   "Le référentiel STI2D ne peut pas être supprimé.",
                                   parent=self)
            return
        if not messagebox.askyesno("Confirmer la suppression",
                                   f"Supprimer définitivement :\n\n{pnom}  ({pid})\n\n"
                                   "Cette action est irréversible.",
                                   parent=self):
            return
        try:
            shutil.rmtree(pdir)
            self._refresh()
        except Exception as e:
            messagebox.showerror("Erreur", str(e), parent=self)
