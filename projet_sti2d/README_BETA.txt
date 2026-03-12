Generateur STI2D - Version Beta (zip portable)

Lancement rapide
1) Decompresser le zip dans un dossier local (Documents, Bureau, etc.).
2) Ouvrir le dossier projet_sti2d.
3) Double-cliquer beta_test_oneclick.bat.

Ce que fait le script one-click
- installe les dependances Python (requirements.txt)
- installe les dependances Node (npm install)
- execute smoke_test.py
- lance main.py

Notes
- Prerequis: Python 3.10+ et Node.js 18+.
- Si un chemin de sortie est invalide, l'application permet de choisir/creer un dossier lors de la generation.
- En cas de probleme, relancer beta_test_oneclick.bat et verifier les messages [FAIL].

Creer un nouveau zip beta
- Double-cliquer create_beta_zip.bat
- L'archive est generee au niveau parent, sous le nom Beta_Generateur_STI2D_V3.zip
- L'arborescence complete du dossier projet_sti2d est conservee.
