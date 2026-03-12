from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from core.referentiel_extraction import (
    comp_rows_to_csv_str,
    conn_rows_to_csv_str,
    crossref_to_comp_csv_str,
    crossref_to_savoir_csv_str,
    extract_bts_crossref_matrix,
    extract_from_pdf,
)


def _parse_levels(levels_raw: str | None) -> List[str]:
    if not levels_raw:
        return []
    return [part.strip() for part in levels_raw.split(",") if part.strip()]


def _levels_from_profile(profile_path: Path) -> List[str]:
    if not profile_path.exists():
        raise FileNotFoundError(f"profil.json introuvable: {profile_path}")

    data = json.loads(profile_path.read_text(encoding="utf-8"))
    levels = data.get("niveaux", [])
    if not isinstance(levels, list):
        raise ValueError("Champ 'niveaux' invalide dans profil.json")

    cleaned = [str(item).strip() for item in levels if str(item).strip()]
    if not cleaned:
        raise ValueError("Aucun niveau exploitable trouve dans profil.json")
    return cleaned


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bts_csv_generator",
        description=(
            "Extrait un referentiel BTS depuis un PDF et genere les CSV "
            "compatibles avec l'application de progression pedagogique."
        ),
    )
    parser.add_argument(
        "pdf",
        type=Path,
        help="Chemin du PDF a analyser",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output") / "bts_csv",
        help="Dossier de sortie pour les CSV (defaut: output/bts_csv)",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        help="Chemin d'un profil.json BTS pour recuperer automatiquement les niveaux",
    )
    parser.add_argument(
        "--levels",
        type=str,
        help="Liste des niveaux separes par des virgules (ex: '1re annee,2e annee')",
    )
    parser.add_argument(
        "--strict-bts",
        action="store_true",
        help="Echoue si le format detecte n'est pas BTS",
    )
    parser.add_argument(
        "--quality-report",
        nargs="?",
        const="auto",
        default=None,
        help=(
            "Genere un rapport qualite JSON. Sans chemin, le fichier "
            "est cree dans le dossier de sortie."
        ),
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Affiche un diagnostic court dans le terminal",
    )
    parser.add_argument(
        "--matrix-csv",
        action="store_true",
        help=(
            "Extrait la matrice croisee savoirs x competences et genere "
            "matrice_savoir_competence.csv et matrice_competence_savoir.csv"
        ),
    )
    return parser


def _quality_report(comp_rows, conn_rows, fmt, levels):
    conn_refs = {str(r.get("ref", "")).strip() for r in conn_rows if str(r.get("ref", "")).strip()}

    code_counts = {}
    for row in comp_rows:
        code = str(row.get("code", "")).strip().upper()
        if code:
            code_counts[code] = code_counts.get(code, 0) + 1

    ref_counts = {}
    for row in conn_rows:
        ref = str(row.get("ref", "")).strip()
        if ref:
            ref_counts[ref] = ref_counts.get(ref, 0) + 1

    duplicate_codes = sorted([code for code, n in code_counts.items() if n > 1])
    duplicate_refs = sorted([ref for ref, n in ref_counts.items() if n > 1])

    empty_links = []
    unknown_links = []
    for row in comp_rows:
        code = str(row.get("code", "")).strip()
        raw_links = str(row.get("connaissances_liees", "")).strip()
        if not raw_links:
            empty_links.append(code)
            continue
        refs = [p.strip() for p in raw_links.split(";") if p.strip()]
        missing = sorted([r for r in refs if r not in conn_refs])
        if missing:
            unknown_links.append({"code": code, "refs_inconnues": missing})

    missing_conn_titles = sorted([
        str(row.get("ref", "")).strip()
        for row in conn_rows
        if not str(row.get("sous_chapitre_titre", "")).strip()
    ])

    return {
        "format_detecte": fmt,
        "is_bts": fmt == "BTS",
        "niveaux": levels,
        "counts": {
            "competences": len(comp_rows),
            "connaissances": len(conn_rows),
        },
        "issues": {
            "duplicate_codes": duplicate_codes,
            "duplicate_refs": duplicate_refs,
            "competences_sans_liens": sorted([c for c in empty_links if c]),
            "liens_vers_refs_inconnues": unknown_links,
            "connaissances_sans_titre": missing_conn_titles,
        },
    }


def _print_summary(quality):
    issues = quality.get("issues", {})
    counts = quality.get("counts", {})

    duplicate_codes = issues.get("duplicate_codes", [])
    duplicate_refs = issues.get("duplicate_refs", [])
    empty_links = issues.get("competences_sans_liens", [])
    unknown_links = issues.get("liens_vers_refs_inconnues", [])
    missing_titles = issues.get("connaissances_sans_titre", [])

    print("\n=== Resume qualite ===")
    print(f"Format: {quality.get('format_detecte', 'INCONNU')}")
    print(f"Competences: {counts.get('competences', 0)} | Connaissances: {counts.get('connaissances', 0)}")
    print(
        "Issues: "
        f"codes_dupliques={len(duplicate_codes)}, "
        f"refs_dupliquees={len(duplicate_refs)}, "
        f"comp_sans_liens={len(empty_links)}, "
        f"liens_inconnus={len(unknown_links)}, "
        f"conn_sans_titre={len(missing_titles)}"
    )

    if duplicate_codes:
        print("- Codes dupliques (top 10): " + ", ".join(duplicate_codes[:10]))
    if duplicate_refs:
        print("- Refs dupliquees (top 10): " + ", ".join(duplicate_refs[:10]))
    if empty_links:
        print("- Competences sans liens (top 10): " + ", ".join(empty_links[:10]))
    if unknown_links:
        first = unknown_links[0]
        print(
            "- Exemple lien inconnu: "
            f"{first.get('code', '?')} -> {', '.join(first.get('refs_inconnues', [])[:10])}"
        )
    if missing_titles:
        print("- Connaissances sans titre (top 10): " + ", ".join(missing_titles[:10]))


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    pdf_path: Path = args.pdf
    output_dir: Path = args.output_dir

    if not pdf_path.exists():
        parser.error(f"PDF introuvable: {pdf_path}")

    levels = _parse_levels(args.levels)
    if args.profile:
        profile_levels = _levels_from_profile(args.profile)
        levels = profile_levels if not levels else levels

    if not levels:
        print("[WARN] Aucun niveau fourni: generation CSV sans colonnes de niveaux.")

    comp_rows, conn_rows, fmt = extract_from_pdf(pdf_path, levels)

    if args.strict_bts and fmt != "BTS":
        print(f"Format detecte: {fmt}")
        print("[ERREUR] Mode strict BTS active: extraction annulee car le PDF n'est pas detecte comme BTS.")
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)

    comp_csv = comp_rows_to_csv_str(comp_rows, levels)
    conn_csv = conn_rows_to_csv_str(conn_rows, levels)

    comp_path = output_dir / "competences_niveaux.csv"
    conn_path = output_dir / "connaissances_niveaux.csv"

    comp_path.write_text(comp_csv, encoding="utf-8", newline="")
    conn_path.write_text(conn_csv, encoding="utf-8", newline="")

    print(f"Format detecte: {fmt}")
    if fmt != "BTS":
        print("[WARN] Le PDF ne semble pas etre detecte comme BTS. Verifier les resultats.")

    print(f"Competences exportees: {len(comp_rows)} -> {comp_path}")
    print(f"Connaissances exportees: {len(conn_rows)} -> {conn_path}")

    quality = None
    if args.quality_report is not None or args.summary:
        quality = _quality_report(comp_rows, conn_rows, fmt, levels)

    if args.quality_report is not None and quality is not None:
        if args.quality_report == "auto":
            report_path = output_dir / "quality_report.json"
        else:
            report_path = Path(args.quality_report)
            if report_path.is_dir():
                report_path = report_path / "quality_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Rapport qualite: {report_path}")

    if args.summary and quality is not None:
        _print_summary(quality)

    if args.matrix_csv:
        matrix = extract_bts_crossref_matrix(pdf_path)
        if not matrix:
            print("[WARN] Matrice croisee savoirs x competences introuvable dans le PDF.")
        else:
            nb_savoirs = len(matrix.get("savoirs", []))
            nb_comp = len(matrix.get("competences", []))

            savoir_csv = crossref_to_savoir_csv_str(matrix)
            comp_csv_m = crossref_to_comp_csv_str(matrix)

            savoir_path = output_dir / "matrice_savoir_competence.csv"
            comp_path_m = output_dir / "matrice_competence_savoir.csv"

            savoir_path.write_text(savoir_csv, encoding="utf-8", newline="")
            comp_path_m.write_text(comp_csv_m, encoding="utf-8", newline="")

            print(
                f"Matrice savoir x competence: {nb_savoirs} savoirs x {nb_comp} competences"
                f" (page {matrix.get('source_page', '?')}) -> {savoir_path}"
            )
            print(f"Matrice competence x savoir (inverse) -> {comp_path_m}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
