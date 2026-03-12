# Outil dedie BTS -> CSV

Ce script genere uniquement les CSV necessaires a l'application de progression pedagogique.

## Fichier

- `bts_csv_generator.py`

## Prerequis

- Environnement Python du projet
- Dependances deja presentes dans `requirements.txt` (`pdfplumber` ou `pypdf`)

## Usage rapide

```powershell
python bts_csv_generator.py "C:\chemin\vers\referentiel_bts.pdf" --profile "referentiels\bts_cpi\profil.json"
```

## Options

- `--output-dir` : dossier de sortie (defaut `output/bts_csv`)
- `--profile` : charge les niveaux depuis un `profil.json` (champ `niveaux`)
- `--levels` : niveaux explicites, separes par virgules
- `--strict-bts` : echoue si le PDF n'est pas detecte comme BTS
- `--quality-report [CHEMIN]` : genere un rapport JSON de qualite (doublons, liens invalides, champs vides)
- `--summary` : affiche un diagnostic court dans le terminal

Exemple avec niveaux explicites:

```powershell
python bts_csv_generator.py "C:\chemin\ref.pdf" --levels "1re annee,2e annee"
```

## Sorties generees

- `competences_niveaux.csv`
- `connaissances_niveaux.csv`
- `quality_report.json` (si `--quality-report` est active)

## Note

Le script et l'interface principale consomment maintenant le module partage `core/referentiel_extraction.py`.
