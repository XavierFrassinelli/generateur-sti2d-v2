from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

REQUIRED_ROOT_FILES = [
    ROOT / "main.py",
    ROOT / "generateur.js",
    ROOT / "constants.py",
    ROOT / "planning.py",
    ROOT / "editeur_themes.py",
    ROOT / "gestionnaire_profils.py",
    ROOT / "requirements.txt",
    ROOT / "package.json",
]

REQUIRED_DIRS = [
    ROOT / "data",
    ROOT / "img",
    ROOT / "output",
    ROOT / "referentiels",
]

REQUIRED_DATA_JSON = [
    ROOT / "data" / "themes_problematiques.json",
    ROOT / "data" / "themes_custom.json",
    ROOT / "data" / "referentiel_competences.json",
    ROOT / "data" / "referentiel_connaissances.json",
]


def _fail(msg: str) -> int:
    print(f"[FAIL] {msg}")
    return 1


def _check_exists() -> int:
    for p in REQUIRED_ROOT_FILES:
        if not p.exists():
            return _fail(f"Fichier manquant: {p.name}")
    for d in REQUIRED_DIRS:
        if not d.exists() or not d.is_dir():
            return _fail(f"Dossier manquant: {d.name}")
    return 0


def _check_json_files() -> int:
    for p in REQUIRED_DATA_JSON:
        if not p.exists():
            return _fail(f"JSON manquant: {p.relative_to(ROOT)}")
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            return _fail(f"JSON invalide: {p.relative_to(ROOT)} ({exc})")
    return 0


def _check_profiles() -> int:
    ref_root = ROOT / "referentiels"
    profiles = [d for d in ref_root.iterdir() if d.is_dir()]
    if not profiles:
        return _fail("Aucun profil dans referentiels/")

    for d in profiles:
        meta = d / "profil.json"
        if not meta.exists():
            return _fail(f"profil.json manquant pour {d.name}")
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except Exception as exc:
            return _fail(f"profil.json invalide pour {d.name} ({exc})")
        if not data.get("id"):
            return _fail(f"profil.json sans 'id' pour {d.name}")
        if not data.get("nom"):
            return _fail(f"profil.json sans 'nom' pour {d.name}")
    return 0


def main() -> int:
    checks = [_check_exists, _check_json_files, _check_profiles]
    for chk in checks:
        code = chk()
        if code != 0:
            return code

    print("[OK] Smoke test reussi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
