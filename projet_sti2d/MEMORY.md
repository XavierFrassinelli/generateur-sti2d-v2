# Générateur STI2D V2 — Journal de travail

## Changelog express (2026-03-04)
- Extraction CO/CN fiabilisée + matching chapitre/sous-chapitre renforcé.
- Profil actif STI2D stabilisé (`config.json`) et référentiels éditables en UI.
- Aide contextuelle modernisée (`?` + `F1`) sur les fenêtres clés.
- Éditeur référentiel amélioré (lisibilité niveaux, normalisation cellules, anti-chevauchement).
- Niveaux taxonomiques STI2D réinjectés depuis la base de référence (`data/referentiel_competences.json`).

> Chemin projet : `C:/Users/xavie/Documents/Lycée Victor Hugo/Générateur_STI2D V2/projet_sti2d/`
> V1 référence  : `C:/Users/xavie/Documents/Lycée Victor Hugo/Générateur_STI2D/projet_sti2d/`
> Stack : Python 3 / Tkinter + Node.js (génération .docx)

---

## Fichiers du projet

| Fichier | Rôle |
|---|---|
| `main.py` | AppSTI2D (Tk.root), EleveDialog, _open_params |
| `planning.py` | PlanningTab (Gantt), SeanceDialog, WeekDetailDialog, SequenceDialog |
| `editeur_themes.py` | EditeurThemesTab — onglet « Mes thèmes » |
| `constants.py` | Couleurs, PERIODES, THEME_COLORS, dimensions Gantt, bind_mousewheel |
| `generateur.js` | Génération .docx via Node.js |
| `data/themes_problematiques.json` | Thèmes officiels T1–T7 |
| `data/themes_custom.json` | Thèmes personnalisés (créé à la demande) |
| `data/referentiel_competences.json` | CO1.1 … CO7.x avec niveaux et connaissances liées |
| `data/referentiel_connaissances.json` | Chapitres 1–7, sous-chapitres avec titres et taxonomie |
| `config.json` | Paramètres utilisateur (logo, dossier sortie, périodes) |

---

## Travaux terminés

### 1. `constants.py` — créé de zéro
- Couleurs : `BLEU=#1A4D8F`, `ORANGE=#E8700A`, `VERT=#2E7D32`, `GRIS=#F5F6FA`, `GRIS2=#E8EDF5`, `BLANC=#FFFFFF`, `TEXTE=#1C1C2E`
- `THEME_COLORS` : palette T1–T7
- `PERIODES` : `[("P1",1,7), ("P2",8,15), ("P3",16,22), ("P4",23,30), ("P5",31,36)]`
- Dimensions Gantt : `NB_SEMAINES=36`, `ROW_H=52`, `HEADER_H=56`, `LEFT_W=220`, `WEEK_W=28`
- `NIVEAU_GROUPE`, `SEUIL_MAITRISE=3`
- `bind_mousewheel(canvas, frame)` — propage `<MouseWheel>` récursivement sur tous les enfants d'une zone scrollable

### 2. `planning.py` — réécrit complet
- `PlanningTab` avec Gantt 36 semaines, canvas scrollable horizontal
- `SeanceDialog` — création/édition séance (type, durée, titre, compétences + connaissances cochables, filtre maîtrise)
- `WeekDetailDialog` — liste des séances d'une semaine avec cartes CRUD
- `SequenceDialog` — création/édition de séquence (thème, problématique, classe, couleur, semaines)
- `compute_competency_usage` — comptage occurrences compétences par niveau

### 3. Périodes académiques configurables
- `load_config()` dans `main.py` : défaut `[["P1",1,7],...["P5",31,36]]`
- `_open_params()` : éditeur P1–P5 avec Spinbox début/fin, validation (contigus, P1=S1, P5=S36)
- Stocké dans `config.json["periodes"]`
- Passé à `PlanningTab(periodes=...)` — remplace `PERIODES` dans le Gantt

### 4. Logo sélectionnable (`generateur.js`)
- Logo établissement et logo spécialité configurables dans Paramètres
- Vide = logo par défaut

### 5. Fix molette (`<MouseWheel>`)
- **`constants.py`** : `bind_mousewheel(canvas, frame)` — lie le scroll sur tous les descendants
- **`planning.py`** : appelée fin de `SeanceDialog._refresh_comp()` et `WeekDetailDialog._render_seances()`
- **`main.py`** : appelée fin de `EleveDialog._build()` après la boucle de construction

### 6. Onglet « Mes thèmes » (`editeur_themes.py`) — créé de zéro
Classe `EditeurThemesTab(tk.Frame)` :

**Panneau gauche (280px fixe) :**
- Listbox thèmes custom + boutons ➕ / 🗑
- Listbox problématiques + boutons ➕ / 🗑

**Panneau droit (expandable) :**
- Vue vide → message d'accueil
- Thème sélectionné → formulaire titre + bouton Sauvegarder
- Problématique sélectionnée → formulaire en **deux zones** :
  - Haut (hauteur fixe 200px, scrollable) : toutes les compétences du référentiel, cochables, **groupées par objectif** (O1–O7)
  - Bas (expandable, scrollable) : connaissances **dynamiques** — apparaissent/disparaissent selon les compétences cochées, groupées par chapitre
  - Bas vide → message « Cochez une compétence… »
  - Bouton 💾 Sauvegarder (packagé `side="bottom"` pour rester visible)

**Persistence :** `data/themes_custom.json`
**Auto-ID :** max des T-numbers connus (officiels + custom) + 1 → T8, T9…

### 7. Intégration dans `main.py`
- `self.themes_officiels` = officiel, `self.themes_custom` = custom, `self.themes` = fusion
- 3e onglet notebook `"  🎨  Mes thèmes  "` — lazy init (`self.tab_themes`)
- `_on_tab_change` : détecte `"thème" in name` pour init `EditeurThemesTab`
- `_on_themes_updated(themes_custom)` : met à jour `self.themes`, rafraîchit Générateur + Planning

---

## Architecture de données

### `themes_custom.json`
```json
[
  {
    "id": "T8",
    "titre": "Mon thème",
    "problematiques": [
      {
        "titre": "Comment…",
        "niveau": "IT/I2D",
        "competences": ["CO1.1", "CO2.3"],
        "connaissances": ["1-3", "1-5", "2-1"]
      }
    ]
  }
]
```

### `referentiel_competences.json`
```json
{
  "objectifs": { "O1": "Caractériser…", … },
  "competences": {
    "CO1.1": {
      "objectif": "O1",
      "libelle": "Justifier les choix…",
      "niveaux": { "IT": "X", "I2D": "XX", "2I2D": "XX" },
      "connaissances": ["1-3", "1-4", "1-5", "2-1", "4-2"]
    }
  }
}
```

### `referentiel_connaissances.json`
```json
{
  "1": {
    "titre": "Principes de conception…",
    "sous_chapitres": {
      "1-1": { "titre": "La démarche de projet", "detail": "…", "taxonomie": {…} }
    }
  }
}
```

---

## En attente / décisions différées

| Tâche | Priorité | Notes |
|---|---|---|
| **Multi-profils** (gestionnaire_profils.py) | Différé | V1 avait ImporteurCSV + sélection profil au démarrage |
| **Export PDF** du planning | Non demandé | |
| **SequenceDialog amélioré** | Non demandé | |

---

## Reprise rapide

Si la session se coupe, les deux tâches majeures restantes connues sont :
1. **Multi-profils** — `gestionnaire_profils.py` V1 à consulter, non demandé pour l'instant
2. **Améliorations futures** à définir avec l'utilisateur

Toutes les fonctionnalités demandées à ce jour sont **implémentées et fonctionnelles**.

Pour relancer :
```bash
cd "C:/Users/xavie/Documents/Lycée Victor Hugo/Générateur_STI2D V2/projet_sti2d"
python main.py
```

---

## Mise à jour session — 2026-03-04

### Contexte de cette session
- Objectif principal : fiabiliser l'extraction référentiels, améliorer l'édition manuelle, et sécuriser le workflow de reprise.
- Profil actif confirmé dans `config.json` : `referentiels/sti2d`.

### Correctifs extraction / mapping (faits)
- `gestionnaire_profils.py`
  - parsing STI2D renforcé (priorité colonne COMPÉTENCE, fallback regex conservé même en extraction partielle),
  - normalisation des codes (`O4.1`, `C07.1`, `CO5.8.AC1`…),
  - extraction refs connaissances plus robuste (incluant formats numériques),
  - validation sauvegarde adoucie : lignes invalides ignorables avec confirmation.
- `main.py` + `planning.py`
  - matching CO↔CN assoupli (gestion des références chapitre/sous-chapitres),
  - expansion des refs chapitre vers sous-réfs dans les flux UI/génération.

### Profils / référentiels (faits)
- Création/usage du profil `referentiels/sti2d`.
- Synchronisation avec matrice Excel (croisement compétences/connaissances) réalisée pendant la session.
- Auto-chargement du profil actif au démarrage (`config.json["profil_actif"]`).
- Injection des niveaux taxonomiques dans le profil STI2D depuis la base historique `data/referentiel_competences.json` :
  - 28 compétences mises à jour,
  - 74 cellules de niveaux remplies,
  - 29 compétences totales dans le fichier cible.

### Éditeur « Mes thèmes » / référentiels (faits)
- `editeur_themes.py`
  - classes/niveaux pilotés par le profil actif (plus de hardcode STI2D),
  - filtrage dynamique des connaissances selon compétences cochées,
  - éditeur manuel des référentiels intégré dans l'onglet Thèmes,
  - tooltip sur libellés compétences tronqués,
  - fallback niveaux : si profil vide, reprise des niveaux depuis `data/referentiel_competences.json` (plus de « tout X » automatique).
- `gestionnaire_profils.py` (`TableauEditable`)
  - ajout/duplication lignes fiabilisés,
  - raccourci `Ctrl+D` (duplication),
  - normalisation des cellules (suppression retours à la ligne) pour éviter chevauchement visuel,
  - style tableau renforcé (contraste, largeur colonnes niveaux, centrage),
  - édition des colonnes taxonomiques en liste contrôlée (`X/XX` ou `0..3`).

### Aide utilisateur (faits)
- Ajout d'une aide contextuelle sur les fenêtres principales et dialogues (`?` + raccourci `F1`).
- `constants.py` : `show_quick_help(...)` convertie en fenêtre dédiée (lecture confortable, scroll, fermeture `Esc`).

### Correctifs stabilité / typage (faits)
- `main.py`
  - correction des avertissements de typage sur l'aperçu (`Text.insert`, garde `current_theme`).
- `gestionnaire_profils.py`
  - fermeture du sélecteur/importeur ne ferme plus l'app parente.

### Fichiers modifiés clés (session)
- `constants.py`
- `main.py`
- `planning.py`
- `editeur_themes.py`
- `gestionnaire_profils.py`
- `referentiels/sti2d/referentiel_competences.json`
- `config.json`

### État actuel attendu
- Les colonnes taxonomiques sont visibles dans l'éditeur référentiel.
- Les valeurs de niveaux STI2D ne sont plus uniformément `X` ; elles reflètent les niveaux de référence récupérés.
- L'édition manuelle de libellés ne crée plus de chevauchements de lignes.

### Points de vigilance prochaine session
1. Vérifier visuellement 2-3 compétences modifiées manuellement (ex. `CO7.4`, `CO7.5`) après sauvegarde/réouverture.
2. Si nouvelle importation STI2D, contrôler que `niveaux` ne repart pas vide avant validation finale.
3. Garder `data/referentiel_competences.json` comme référence de secours tant que la source d'import ne reconstruit pas les niveaux de manière fiable.

### Check-list de reprise rapide
1. Lancer `python main.py`.
2. Ouvrir `Mes thèmes` → `🛠 Référentiels`.
3. Vérifier l'affichage des colonnes `IT/I2D/2I2D`.
4. Sauvegarder si corrections manuelles effectuées.
5. Générer un document test (préparation + élève) pour valider la chaîne complète.

---

## Mise à jour session — 2026-03-06

### Contexte de cette session
- Objectif principal : industrialiser le support BTS (profil CPI), extraire la matrice AT↔compétences depuis PDF, puis stabiliser une version bêta distribuable.
- Validation finale demandée : corriger l'absence de choix BTS dans la création de séquence (onglet Planning).

### Données BTS CPI (faits)
- `referentiels/bts_cpi/bts_cpi.txt`
  - normalisé avec colonne `LIENS_CROISES`,
  - liens compétences/connaissances rendus réciproques,
  - format préparé pour conversion automatisée.
- Génération des CSV intermédiaires :
  - `competences.csv`, `connaissances.csv`,
  - `competences_niveaux.csv`, `connaissances_niveaux.csv` (pré-remplissage 1re/2e année).

### Architecture profil BTS (faits)
- `profil.json` BTS enrichi avec `schema: "bts"`.
- Ajout du support `activites_types` dans la chaîne de chargement profil.
- `main.py`
  - payload Node enrichi avec `schema` et `activites_types`,
  - bouton/flux "Matrice BTS" conditionné au schéma BTS et à la présence d'une matrice.

### Extraction matrice BTS depuis PDF (faits)
- `gestionnaire_profils.py`
  - extraction de tables candidates via `pdfplumber` (+ fallback),
  - reconstruction de la matrice `A*-T*` x `C1..C14`,
  - injection dans `referentiel_activites_types.json`.
- Enrichissement du JSON AT avec :
  - `matrice_competences`,
  - `correspondance_competences`,
  - `competences_detaillees` (quand détectables).

### Refactoring interface (faits)
- `main.py` allégé par extraction de dialogs en modules dédiés :
  - `bts_matrice_dialog.py`,
  - `eleve_dialog.py`.

### Stabilité / diffusion bêta (faits)
- Ajout `requirements.txt`.
- Ajout `smoke_test.py` (contrôle minimal des profils/référentiels).
- `lancer.bat` renforcé (fallback `py`/`python`).
- Scripts livraison :
  - `beta_test_oneclick.bat`,
  - `create_beta_zip.bat`,
  - `README_BETA.txt`.
- `INSTALLATION.md` mis à jour pour parcours utilisateur simplifié.

### Correctif fonctionnel final (fait)
- Bug résolu : en création/édition de séquence, la liste des classes n'était pas BTS mais restait STI2D hardcodée.
- `planning.py`
  - `SequenceDialog` reçoit `classes_options` dynamiques,
  - `PlanningTab` stocke et transmet ces options à l'ajout/modification.
- `main.py`
  - transmission de `classes_options=list(self.cb_classe["values"])` à l'initialisation lazy de `PlanningTab`.

### Amélioration UX finale (fait)
- Titre planning rendu dynamique selon profil actif (plus de "Planning annuel STI2D" en dur).

### Extension planning hebdomadaire réel (fait)
- `planning.py`
  - `SeanceDialog` accepte désormais un créneau réel optionnel (`jour`, `heure_debut`, `heure_fin`),
  - validation format `HH:MM` + cohérence début/fin,
  - recalcul automatique de `duree` depuis le créneau quand présent,
  - `WeekDetailDialog` affiche un mini emploi du temps hebdomadaire (Lundi→Vendredi, 08:00→18:00) avec blocs colorés,
  - tri des séances par jour/heure et affichage du créneau sur chaque carte.
- Compatibilité conservée avec les anciennes séances (durée seule, sans créneau).

### Extension séance depuis planning (fait)
- Création/modification de séance : sélection explicite de la problématique (quand le thème de la séquence est connu).
- Filtrage des compétences proposé dans la séance selon le périmètre de la séquence (`competences_selectionnees` / `competences_str`).
- Filtrage des connaissances par compétence selon les connaissances déjà associées à la séquence (quand présentes).
- Persistance de `pb_titre` au niveau séance pour conserver le choix réel.
- Génération document depuis séance : priorité à `seance.pb_titre` (fallback sur `seq.pb_titre`).
- Option UI ajoutée : `Afficher hors séquence` dans la séance pour élargir volontairement la sélection CO/CN.

### Ajustement visuel planning (fait)
- `planning_tab.py` : rendu final sans pointillés internes; la distinction hebdomadaire se fait via un voile de luminosité alterné par semaine uniquement quand une séquence est sélectionnée.

### Refactoring structure planning (fait)
- Découpage du monolithe planning en modules :
  - `planning_common.py` : helpers partagés (couverture compétences, horaires, tris, rendu texte/couleur),
  - `planning_seance_dialog.py` : `SeanceDialog`,
  - `planning_week_detail_dialog.py` : `WeekDetailDialog`,
  - `planning_sequence_dialog.py` : `SequenceDialog`,
  - `planning_dialogs.py` : agrégateur de compatibilité (ré-export des dialogs),
  - `planning_tab.py` : `PlanningTab` (Gantt + CRUD séquences),
  - `planning.py` : façade de compatibilité (ré-export des symboles historiques).
- Objectif : réduire le risque de régression UI et faciliter les correctifs ciblés (boutons/hauteurs/layout).

### Vérifications réalisées
- Vérification statique : `No errors found` sur `main.py` et `planning.py` après patch final.
- Génération package bêta : `create_beta_zip.bat` exécuté avec code retour `0`.
- Exécution application : `python main.py` lancée avec code retour `0`.

### État actuel attendu
- Le profil BTS CPI peut être chargé avec schéma BTS reconnu.
- Le bouton "Matrice BTS" est actif quand la matrice AT↔compétences est présente.
- Dans "Planning" > "Ajouter une séquence", la liste des classes reflète bien le profil actif (BTS inclus).

### Points de vigilance prochaine session
1. Valider visuellement, côté UI, la création d'une séquence BTS et l'enregistrement dans `data/planning.json`.
2. Affiner la correspondance CO détaillées si un référentiel BTS plus complet est fourni.
3. Garder le smoke test dans le parcours avant chaque export bêta.
