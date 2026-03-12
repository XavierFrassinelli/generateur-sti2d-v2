# Generateur STI2D - Guide d'utilisation

Ce guide explique l'utilisation quotidienne de l'application pour un enseignant.

## 1. Lancer l'application

Option simple (recommandee):
1. Ouvrir le dossier `projet_sti2d`.
2. Double-cliquer sur `beta_test_oneclick.bat`.

Option directe (si deja installe):
1. Double-cliquer sur `lancer.bat`.
2. Ou lancer `python main.py` dans un terminal.

## 2. Demarrage rapide (ordre conseille)

1. Choisir le profil (STI2D, CIEL, BTS, etc.).
2. Verifier les themes et problematiques.
3. Completer les informations de classe/eleves.
4. Construire la progression/planning.
5. Generer les documents dans le dossier de sortie.

## 3. Utilisation par onglet (vue pratique)

### Couverture
- Renseigner les informations generales de la seance/sequence.
- Verifier les metadonnees avant generation.

### Themes / Problematiques
- Choisir les themes proposes.
- Ajouter ou adapter des elements selon votre progression.

### Eleves
- Saisir/importer les eleves.
- Verifier l'orthographe et l'uniformite des noms/prenoms.

### Planning
- Organiser les sequences et seances par periode.
- Ajuster les semaines et charges horaires.

### BTS / Matrice (si profil BTS)
- Utiliser la matrice de croisement competences/savoirs.
- Verifier la coherence des niveaux avant export CSV.

## 4. Generation des documents

1. Choisir un dossier de sortie valide.
2. Lancer la generation.
3. Verifier les fichiers produits dans `output/`.

Conseil: utiliser un sous-dossier date (ex: `output/2026-03-12`) pour garder un historique clair.

## 5. Sauvegarde et partage

- Le projet est versionne sur GitHub.
- Sauvegarder vos modifications regulierement avec des commits clairs.
- Pour partager: envoyer l'URL du repository public.

## 6. Depannage rapide

Si l'application ne se lance pas:
1. Relancer `beta_test_oneclick.bat`.
2. Verifier Python 3.10+ et Node.js 18+.
3. Executer `python smoke_test.py` dans `projet_sti2d`.

Si la generation echoue:
1. Verifier que le dossier de sortie existe et est accessible en ecriture.
2. Verifier que les fichiers JSON de referentiel ne sont pas corrompus.

## 7. Bonnes pratiques

- Faire une generation test en debut de sequence.
- Eviter de renommer manuellement les fichiers internes de `referentiels/`.
- Conserver les exports importants dans un dossier archive date.

---

Pour l'installation detaillee, voir `INSTALLATION.md`.
Pour les tests beta, voir `README_BETA.txt`.
