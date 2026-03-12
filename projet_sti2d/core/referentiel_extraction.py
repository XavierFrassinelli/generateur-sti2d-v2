from __future__ import annotations

import csv
import io
import re
import unicodedata
from pathlib import Path


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
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("\u2022", " ").replace("\u00b7", " ")
    return " ".join(s.split()).strip()


def _strip_accents(s):
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def _key_tokens(s):
    stop = {
        "de", "des", "du", "la", "le", "les", "et", "en", "un", "une", "dans",
        "au", "aux", "pour", "sur", "par", "avec", "ou", "d", "l", "a",
    }
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


def detect_format(text):
    co_matches = re.findall(r"\bCO\d+\.\d+", text, re.IGNORECASE)
    if co_matches:
        if any(kw in text.upper() for kw in ["I2D", "2I2D", "ITEC", " EE", "SIN,", "AC,"]):
            return "STI2D"
        if len(co_matches) >= 6:
            return "STI2D"

    s_matches = re.findall(r"\bS\d{1,2}\b", text)
    if len(s_matches) >= 6:
        return "BTS"

    if re.search(r"\b[CO]\d+\.\d+", text, re.IGNORECASE):
        return "GENERIQUE"
    return "GENERIQUE"


def extract_from_pdf(pdf_path, niveaux):
    use_pdfplumber = False
    try:
        import pdfplumber
        use_pdfplumber = True
    except ImportError:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ImportError("pdfplumber_ou_pypdf") from exc

    all_text_lines = []
    all_tables = []

    if use_pdfplumber:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                all_text_lines.extend(txt.splitlines())
                tbls = page.extract_tables({
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                }) or []
                all_tables.extend(tbls)
    else:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        for page in reader.pages:
            txt = page.extract_text() or ""
            all_text_lines.extend(txt.splitlines())

    preview = "\n".join(all_text_lines[:200])
    fmt = detect_format(preview)

    comp_rows = []
    conn_rows = []

    if all_tables:
        if fmt == "STI2D":
            c_rows, k_rows = _parse_tables_sti2d(all_tables, all_text_lines, niveaux)
        elif fmt == "BTS":
            c_rows, k_rows = _parse_tables_bts(all_tables, all_text_lines, niveaux)
        else:
            c_rows, k_rows = _parse_tables_generic(all_tables, all_text_lines, niveaux)
        comp_rows.extend(c_rows)
        conn_rows.extend(k_rows)

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

    def _comp_key(row):
        m = re.match(r"^C[O]?(\d+)(?:\.(\d+))?", row.get("code", ""), re.I)
        return (int(m.group(1)), int(m.group(2) or 0)) if m else (9999, 9999)

    def _conn_key(row):
        try:
            return tuple(int(x) for x in row.get("ref", "0").split("-") if x.isdigit())
        except Exception:
            return (9999,)

    comp_rows.sort(key=_comp_key)
    conn_rows.sort(key=_conn_key)

    return comp_rows, conn_rows, fmt


def _header_str(header_row):
    return " ".join(str(c or "").upper() for c in header_row)


def _parse_tables_sti2d(tables, text_lines, niveaux):
    comp_rows = []
    conn_rows = _extract_connaissances_sti2d(text_lines, niveaux)
    sti2d_niv = {"IT", "I2D", "2I2D", "ITEC", "EE", "EE1", "EE2", "SIN", "AC", "AC1", "AC2"}

    for table in tables:
        if not table or len(table) < 2:
            continue

        header = table[0]
        h_str = _strip_accents(_header_str(header)).upper()
        if not any(kw in h_str for kw in ("COMPETENCE", "CO")):
            continue

        col_comp = None
        col_obj = None
        col_conns = None
        col_niv = {}

        for i, cell in enumerate(header):
            h = _strip_accents(str(cell or "").strip()).upper()
            if "COMPETENCE" in h and col_comp is None:
                col_comp = i
            elif "OBJECTIF" in h and col_obj is None:
                col_obj = i
            elif h in sti2d_niv:
                col_niv[h] = i
            elif "CONNAISSANCE" in h or "SAVOIR" in h:
                col_conns = i

        if col_comp is None and col_obj is not None:
            col_comp = col_obj

        if col_comp is None:
            continue

        for data_row in table[1:]:
            if not data_row or not any(str(c or "").strip() for c in data_row):
                continue

            cell_val = str(data_row[col_comp] if col_comp < len(data_row) else "").strip()
            segments = re.split(r"(?=\bCO\d+\.\d+\b)", cell_val, flags=re.IGNORECASE)
            segments = [
                s.strip()
                for s in segments
                if s.strip() and re.search(r"\bCO\d+\.\d+\b", s, re.IGNORECASE)
            ]
            if not segments:
                continue

            niv_lines = {}
            for niv, cidx in col_niv.items():
                raw = str(data_row[cidx] if cidx < len(data_row) else "")
                niv_lines[niv] = [v.strip() for v in raw.split("\n")]

            conns_lines = []
            if col_conns is not None and col_conns < len(data_row):
                raw_c = str(data_row[col_conns] or "")
                conns_lines = [l.strip() for l in raw_c.split("\n")]

            for seg_idx, seg in enumerate(segments):
                m = re.match(r"\b(CO\d+\.\d+)\b\s*[:\-.]?\s*(.*)", seg, re.IGNORECASE | re.DOTALL)
                if not m:
                    continue

                code = m.group(1).upper()
                libelle = re.sub(r"\s+", " ", m.group(2)).strip()[:260]

                niv_vals = {}
                for niv, lines in niv_lines.items():
                    v = lines[seg_idx].upper() if seg_idx < len(lines) else ""
                    niv_vals[niv] = v if v in ("X", "XX") else ""

                conns_str = ""
                if seg_idx < len(conns_lines):
                    refs = re.findall(r"\d+-\d+", conns_lines[seg_idx])
                    conns_str = ";".join(refs)
                elif not conns_lines and col_conns is not None:
                    raw_c = str(data_row[col_conns] if col_conns < len(data_row) else "")
                    conns_str = ";".join(re.findall(r"\d+-\d+", raw_c))

                row = {
                    "code": code,
                    "libelle": libelle,
                    "connaissances_liees": conns_str,
                    "confidence": "high",
                }
                for n in niveaux:
                    row[n] = niv_vals.get(n, "")
                comp_rows.append(row)

    return comp_rows, conn_rows


def _extract_connaissances_sti2d(text_lines, niveaux):
    conn_map = {}
    chap_titles = {}
    norm_lines = [_norm_text(l) for l in text_lines]

    for line in norm_lines:
        m = re.match(r"^(S\d{1,2})\s*[-:]\s*(.+)$", line, re.IGNORECASE)
        if m and "." not in m.group(1):
            chap_titles[m.group(1).upper()] = m.group(2).strip()[:180]

        m2 = re.match(r"^(S\d{1,2}(?:\.\d+)+)\s*[-:]\s*(.+)$", line, re.IGNORECASE)
        if not m2:
            m2 = re.match(r"^(S\d{1,2}(?:\.\d+)+)\s+(.{6,})$", line, re.IGNORECASE)
        if m2:
            s_code = m2.group(1).upper()
            titre = m2.group(2).strip(" .;,-")[:220]
            nums = s_code[1:].split(".")
            chap_id = nums[0]
            ref = "-".join(nums)
            chap_titre = chap_titles.get(f"S{chap_id}", f"Chapitre {chap_id}")
            if len(titre) >= 4:
                conn_map.setdefault(ref, (chap_id, chap_titre, titre))

    def _ref_key_local(ref):
        try:
            return tuple(int(x) for x in ref.split("-") if x.isdigit())
        except Exception:
            return (9999,)

    conn_rows = []
    for ref in sorted(conn_map, key=_ref_key_local):
        chap_id, chap_titre, sc_titre = conn_map[ref]
        row = {
            "ref": ref,
            "chapitre_id": chap_id,
            "chapitre_titre": chap_titre,
            "sous_chapitre_titre": sc_titre,
            "detail": "",
            "confidence": "medium",
        }
        for n in niveaux:
            row[n] = "1"
        conn_rows.append(row)
    return conn_rows


def _parse_tables_bts(tables, text_lines, niveaux):
    comp_rows = []
    conn_rows = _extract_connaissances_bts(text_lines, niveaux)
    conn_refs = {r["ref"] for r in conn_rows}

    for table in tables:
        if not table or len(table) < 2:
            continue
        header = table[0]

        col_comp = None
        s_cols = {}

        for i, cell in enumerate(header):
            h = str(cell or "").strip().upper()
            if any(kw in h for kw in ("COMPETENCE", "COMPTENCE")) and col_comp is None:
                col_comp = i
            ms = re.match(r"^S(\d{1,2})$", h)
            if ms:
                s_cols[ms.group(1)] = i

        if col_comp is None or not s_cols:
            continue

        for data_row in table[1:]:
            if not data_row:
                continue

            cell_val = str(data_row[col_comp] if col_comp < len(data_row) else "").strip()
            m = re.search(r"\b(C[O]?\d+\.\d+)\b\s*[:\-.]?\s*(.*)", cell_val, re.IGNORECASE | re.DOTALL)
            if not m:
                continue

            code = m.group(1).upper()
            libelle = re.sub(r"\s+", " ", m.group(2)).strip()[:260]

            linked = []
            for s_num, s_idx in s_cols.items():
                v = str(data_row[s_idx] if s_idx < len(data_row) else "").strip()
                if v and v.upper() not in ("", "0", "NON", "-", "X"):
                    if s_num in conn_refs or s_num not in conn_refs:
                        linked.append(s_num)

            row = {
                "code": code,
                "libelle": libelle,
                "connaissances_liees": ";".join(linked),
                "confidence": "high",
            }
            for n in niveaux:
                row[n] = ""
            comp_rows.append(row)

    return comp_rows, conn_rows


def _extract_connaissances_bts(text_lines, niveaux):
    conn_map = {}
    chap_titles = {}
    norm_lines = [_norm_text(l) for l in text_lines]

    for line in norm_lines:
        m = re.match(r"^(S\d{1,2})\s*[-:]\s*(.{4,})$", line, re.IGNORECASE)
        if m and "." not in m.group(1):
            key = m.group(1).upper()
            chap_titles[key] = m.group(2).strip()[:180]
            chap_id = key[1:]
            conn_map.setdefault(chap_id, (chap_id, m.group(2).strip()[:180], m.group(2).strip()[:180]))

        m2 = re.match(r"^(S\d{1,2}(?:\.\d+)+)\s*[-:]\s*(.{4,})$", line, re.IGNORECASE)
        if not m2:
            m2 = re.match(r"^(S\d{1,2}(?:\.\d+)+)\s+(.{6,})$", line, re.IGNORECASE)
        if m2:
            s_code = m2.group(1).upper()
            titre = m2.group(2).strip(" .;,-")[:220]
            nums = s_code[1:].split(".")
            chap_id = nums[0]
            ref = "-".join(nums)
            chap_titre = chap_titles.get(f"S{chap_id}", f"S{chap_id}")
            if len(titre) >= 4:
                conn_map.setdefault(ref, (chap_id, chap_titre, titre))

    def _ref_key_local(ref):
        try:
            return tuple(int(x) for x in ref.split("-") if x.isdigit())
        except Exception:
            return (9999,)

    conn_rows = []
    for ref in sorted(conn_map, key=_ref_key_local):
        chap_id, chap_titre, sc_titre = conn_map[ref]
        row = {
            "ref": ref,
            "chapitre_id": chap_id,
            "chapitre_titre": chap_titre,
            "sous_chapitre_titre": sc_titre,
            "detail": "",
            "confidence": "medium",
        }
        for n in niveaux:
            row[n] = "1"
        conn_rows.append(row)
    return conn_rows


def _parse_tables_generic(tables, text_lines, niveaux):
    comp_rows = []
    seen_codes = set()

    for table in tables:
        if not table or len(table) < 2:
            continue
        for data_row in table[1:]:
            for cell in data_row:
                m = re.search(r"\b(C[O]?\d+\.\d+)\b\s*[:\-.]?\s*(.*)", str(cell or ""), re.IGNORECASE | re.DOTALL)
                if m:
                    code = m.group(1).upper()
                    lib = re.sub(r"\s+", " ", m.group(2)).strip()[:260]
                    if len(lib) >= 8 and code not in seen_codes:
                        row = {
                            "code": code,
                            "libelle": lib,
                            "connaissances_liees": "",
                            "confidence": "medium",
                        }
                        for n in niveaux:
                            row[n] = ""
                        comp_rows.append(row)
                        seen_codes.add(code)
                    break

    conn_rows = _extract_connaissances_sti2d(text_lines, niveaux)
    return comp_rows, conn_rows


def _parse_regex_fallback(text_lines, niveaux):
    comp_map = {}
    comp_blocks = {}
    conn_map = {}
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
            code = m.group(1).upper()
            parts = [m.group(2).strip()] if m.group(2).strip() else []
            j = i + 1
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
            s_code = m_c.group(1).upper()
            titre = m_c.group(2).strip(" .;,-")[:220]
            nums = s_code[1:].split(".")
            chap_id = nums[0]
            ref = "-".join(nums)
            chap_titre = chap_titles.get(f"S{chap_id}", f"Chapitre {chap_id}")
            if len(titre) >= 4:
                conn_map.setdefault(ref, (chap_id, chap_titre, titre))

    if not conn_map:
        all_text = "\n".join(norm_lines)
        raw_refs = set(re.findall(r"\b(\d+-\d+)\b", all_text))

        def _ref_key_local(ref):
            try:
                return tuple(int(x) for x in ref.split("-") if x.isdigit())
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

    def _comp_key(code):
        m = re.match(r"^C[O]?(\d+)(?:\.(\d+))?", code, re.I)
        return (int(m.group(1)), int(m.group(2) or 0)) if m else (9999, 9999)

    comp_rows = []
    for code in sorted(comp_map, key=_comp_key):
        norm_code = _normalize_comp_code(code)
        row = {
            "code": norm_code,
            "libelle": comp_map[code],
            "connaissances_liees": _infer(code, comp_map[code]),
            "confidence": "low",
        }
        for n in niveaux:
            row[n] = ""
        comp_rows.append(row)

    def _ref_key(ref):
        try:
            return tuple(int(x) for x in ref.split("-") if x.isdigit())
        except Exception:
            return (9999,)

    conn_rows = []
    for ref in sorted(conn_map, key=_ref_key):
        chap_id, chap_titre, sc_titre = conn_map[ref]
        row = {
            "ref": ref,
            "chapitre_id": chap_id,
            "chapitre_titre": chap_titre,
            "sous_chapitre_titre": sc_titre,
            "detail": "",
            "confidence": "low",
        }
        for n in niveaux:
            row[n] = "1"
        conn_rows.append(row)

    return comp_rows, conn_rows


def rows_to_comp_json(comp_rows, niveaux):
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
            ref = _normalize_ref(c)
            if ref and ref not in conns:
                conns.append(ref)

        niv_map = {n: str(row.get(n, "")).strip() for n in niveaux}
        if code not in result["competences"]:
            result["competences"][code] = {
                "objectif": obj_code,
                "libelle": libelle,
                "niveaux": niv_map,
                "connaissances": conns,
            }
    return result


def rows_to_conn_json(conn_rows, niveaux):
    result = {}
    for row in conn_rows:
        ref = _normalize_ref(row.get("ref", ""))
        if not ref:
            continue

        chap_id = str(row.get("chapitre_id", "") or ref.split("-")[0])
        chap_titre = str(row.get("chapitre_titre", "")).strip()
        sc_titre = str(row.get("sous_chapitre_titre", "")).strip() or ref
        detail = str(row.get("detail", "")).strip()
        taxo = {n: _safe_int(row.get(n, 0)) for n in niveaux}

        if chap_id not in result:
            result[chap_id] = {"titre": chap_titre, "sous_chapitres": {}}
        elif chap_titre and not result[chap_id].get("titre"):
            result[chap_id]["titre"] = chap_titre

        result[chap_id]["sous_chapitres"][ref] = {
            "titre": sc_titre,
            "detail": detail,
            "taxonomie": taxo,
        }
    return result


def build_bts_at_json(comp_json, conn_json):
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
                norm_ref = _normalize_ref(ref)
                if norm_ref and norm_ref in known_refs and norm_ref not in refs:
                    refs.append(norm_ref)

        raw_title = str(objectifs.get(obj, "")).strip()
        title = raw_title if raw_title and not raw_title.lower().startswith("objectif ") else f"Activite type {idx}"

        activites[f"AT{idx}"] = {
            "titre": title,
            "description": f"Regroupement des competences du bloc {obj}.",
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


def enrich_bts_at_with_matrix(at_json, matrix):
    if not isinstance(at_json, dict) or not isinstance(matrix, dict):
        return at_json

    at_json["matrice_competences"] = matrix
    corr = at_json.get("correspondance_competences", {})
    taches = at_json.get("matrice_competences", {}).get("taches", {})

    for _, t_data in taches.items():
        detailed = []
        for c_code in t_data.get("competences", []):
            for co_code in corr.get(c_code, []):
                if co_code not in detailed:
                    detailed.append(co_code)
        t_data["competences_detaillees"] = detailed

    at_json.setdefault("meta", {})["source_matrice"] = "pdf_table"
    return at_json


def extract_bts_matrix_from_pdf(pdf_path):
    try:
        import pdfplumber
    except Exception:
        return {}

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return {}

    with pdfplumber.open(pdf_path) as pdf:
        best = None
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

    header_row_idx = None
    header_map = {}
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

    def _comp_num(label):
        match = re.search(r"\d+", str(label))
        return int(match.group(0)) if match else 999

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
            niveaux[c_code] = v

        if niveaux:
            taches[task_code] = {
                "activite": activite,
                "competences": sorted(niveaux.keys(), key=_comp_num),
                "niveaux": niveaux,
            }

    if not taches:
        return {}

    competences = sorted(
        {c for t in taches.values() for c in t.get("competences", [])},
        key=_comp_num,
    )

    return {
        "source_page": source_page,
        "competences": competences,
        "taches": taches,
    }


def comp_rows_to_csv_str(comp_rows, niveaux):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["code", "libelle"] + niveaux + ["connaissances_liees"])
    for row in comp_rows:
        w.writerow([row.get("code", ""), row.get("libelle", "")] + [row.get(n, "") for n in niveaux] + [row.get("connaissances_liees", "")])
    return buf.getvalue()


def conn_rows_to_csv_str(conn_rows, niveaux):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ref", "chapitre_id", "chapitre_titre", "sous_chapitre_titre", "detail"] + niveaux)
    for row in conn_rows:
        w.writerow([
            row.get("ref", ""),
            row.get("chapitre_id", ""),
            row.get("chapitre_titre", ""),
            row.get("sous_chapitre_titre", ""),
            row.get("detail", ""),
        ] + [row.get(n, "") for n in niveaux])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Matrice croisée savoirs × compétences (pages "Relations principales")
# ---------------------------------------------------------------------------

def _is_section_header(ref_cell: str) -> bool:
    """True si la cellule est un en-tête de section (ex: 'S1- DÉMARCHE...') et non un savoir."""
    ref = ref_cell.strip()
    # En-têtes de section : S#- ou S## sans point, ou cellule vide
    if not ref:
        return True
    if re.match(r"^S\d+[-\s]", ref):
        return True
    # Lignes chapitre sans numéro de sous-savoir (ex: "S8")
    if re.match(r"^S\d+$", ref):
        return True
    return False


def extract_bts_crossref_matrix(pdf_path):
    """Extrait la matrice croisée savoirs × compétences depuis un PDF BTS.

    Recherche une page contenant "relations" + "savoirs" dans le texte, puis
    y localise le tableau dont l'en-tête contient au moins 6 codes C1..C14.

    Retourne un dict::

        {
            "source_page": int,          # numéro de page (1-based)
            "competences": ["C1", ...],  # liste ordonnée des compétences
            "savoirs": [
                {
                    "ref":   "S1.1",
                    "titre": "...",
                    "C1": "X", "C2": "", ...
                },
                ...
            ]
        }

    Retourne ``{}`` si la matrice est introuvable ou en cas d'erreur.
    """
    try:
        import pdfplumber
    except Exception:
        return {}

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return {}

    def _comp_num(label):
        match = re.search(r"\d+", str(label))
        return int(match.group(0)) if match else 999

    with pdfplumber.open(pdf_path) as pdf:
        candidates = []

        for page_no, page in enumerate(pdf.pages, start=1):
            text = _strip_accents(_norm_text(page.extract_text() or "")).upper()
            # Heuristique : page qui mentionne les relations entre savoirs et compétences
            if "RELATION" not in text and "SAVOIR" not in text:
                continue
            # Il faut aussi des codes compétences C1..C14
            if not re.search(r"\bC(?:1[0-4]|[1-9])\b", text):
                continue

            tables = page.extract_tables({
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
            }) or []

            for table in tables:
                if not table or len(table) < 3:
                    continue
                # Chercher la ligne d'en-tête contenant C1..C14
                header_row_idx = None
                comp_cols = {}  # col_index -> "C#"
                for ri, row in enumerate(table):
                    cells = [str(c or "").strip() for c in (row or [])]
                    tmp = {}
                    for ci, cell in enumerate(cells):
                        m = re.match(r"^(C(?:1[0-4]|[1-9]))$", cell)
                        if m:
                            tmp[ci] = m.group(1)
                    if len(tmp) >= 6:
                        header_row_idx = ri
                        comp_cols = tmp
                        break

                if header_row_idx is None:
                    continue

                # Calculer un score de confiance : nb de lignes de données × nb colonnes compétences
                data_rows = [
                    r for r in table[header_row_idx + 1:]
                    if r and str(r[0] or "").strip() and not _is_section_header(str(r[0] or "").strip())
                ]
                score = len(data_rows) * len(comp_cols)
                candidates.append((score, page_no, header_row_idx, comp_cols, table))

    if not candidates:
        return {}

    # Garder le meilleur candidat (score maximal)
    candidates.sort(key=lambda t: t[0], reverse=True)
    _, source_page, header_row_idx, comp_cols, table = candidates[0]

    # --- Extraction des lignes de savoirs ---
    competences = sorted(comp_cols.values(), key=_comp_num)
    savoirs = []

    for row in table[header_row_idx + 1:]:
        cells = [str(c or "").strip() for c in (row or [])]
        if not cells:
            continue
        ref = cells[0] if len(cells) > 0 else ""
        titre = cells[1] if len(cells) > 1 else ""

        if _is_section_header(ref):
            continue

        # La cellule ref doit ressembler à un code savoir BTS (S#.# ou S##.##)
        if not re.match(r"^S\d+\.\d+$", ref):
            continue

        entry = {"ref": ref, "titre": titre}
        for col_idx, c_code in comp_cols.items():
            val = cells[col_idx] if col_idx < len(cells) else ""
            entry[c_code] = "X" if val.upper() == "X" else ""
        savoirs.append(entry)

    if not savoirs:
        return {}

    return {
        "source_page": source_page,
        "competences": competences,
        "savoirs": savoirs,
    }


def crossref_to_savoir_csv_str(matrix: dict) -> str:
    """Génère un CSV savoir × compétence depuis la matrice croisée.

    Colonnes : ref, titre, C1, C2, ..., C14
    Lignes   : un savoir par ligne, "X" si lié à la compétence, "" sinon.
    """
    competences = matrix.get("competences", [])
    savoirs = matrix.get("savoirs", [])

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ref", "titre"] + competences)
    for savoir in savoirs:
        row = [savoir.get("ref", ""), savoir.get("titre", "")]
        row += [savoir.get(c, "") for c in competences]
        w.writerow(row)
    return buf.getvalue()


def crossref_to_comp_csv_str(matrix: dict) -> str:
    """Génère un CSV compétence × savoir (vue inverse) depuis la matrice croisée.

    Colonnes : competence, S1.1, S1.2, ..., Sn.m
    Lignes   : une compétence par ligne, "X" si liée au savoir, "" sinon.
    """
    competences = matrix.get("competences", [])
    savoirs = matrix.get("savoirs", [])
    savoir_refs = [s.get("ref", "") for s in savoirs]

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["competence"] + savoir_refs)
    for c_code in competences:
        row = [c_code]
        for savoir in savoirs:
            row.append(savoir.get(c_code, ""))
        w.writerow(row)
    return buf.getvalue()
