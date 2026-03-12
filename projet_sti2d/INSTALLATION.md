# Generateur STI2D - Installation

## Prerequis
- Python 3.10+ (Tkinter inclus)
- Node.js 18+

## Installation rapide
Option la plus simple (beta test):
1. Double-cliquer `beta_test_oneclick.bat`
2. Attendre la fin des 4 etapes automatiques
3. L'application se lance automatiquement

Option manuelle:
1. Ouvrir un terminal dans `projet_sti2d/`.
2. Installer les dependances Python:
   ```bash
   pip install -r requirements.txt
   ```
3. Installer les dependances Node (locales au projet):
   ```bash
   npm install
   ```
4. Lancer un controle de sante:
   ```bash
   python smoke_test.py
   ```
5. Lancer l'application:
   ```bash
   python main.py
   ```
   ou double-cliquer sur `lancer.bat`.

## Notes beta test
- `beta_test_oneclick.bat` automatise installation + verification + lancement.
- Le controle `smoke_test.py` valide la presence et la structure des profils/referentiels JSON.
- Les fonctions d'import PDF BTS gagnent en qualite si `pdfplumber` est installe.
- Le bouton `Matrice BTS` est actif uniquement pour les profils `schema=bts` avec matrice extraite.

## Structure (extrait)
```
projet_sti2d/
|- main.py
|- planning.py
|- editeur_themes.py
|- eleve_dialog.py
|- bts_matrice_dialog.py
|- gestionnaire_profils.py
|- generateur.js
|- referentiels/
|- data/
|- output/
|- requirements.txt
`- smoke_test.py
```
