/**
 * generateur.js — Générateur de documents STI2D
 * Modes : "preparation" (fiche prof) | "eleve" (document élève)
 * Usage : node generateur.js <payload.json>
 */

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
  VerticalAlign, LevelFormat, ImageRun, PageBreak
} = require('docx');
const fs   = require('fs');
const path = require('path');

// ── Payload ───────────────────────────────────────────────────────────────────
const payloadPath = process.argv[2];
if (!payloadPath || !fs.existsSync(payloadPath)) {
  process.stderr.write('Payload introuvable : ' + payloadPath + '\n');
  process.exit(1);
}
const payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
const {
  mode,           // "preparation" | "eleve"
  theme, problematique,
  classe, etablissement,
  competences_selectionnees,   // pour mode élève : [{code, connaissances:[]}]
  competences, connaissances,
  img_dir, output_dir,
  titre_seance,                // pour mode élève
  output_filename,             // nom fichier personnalisé (optionnel)
  logo_etablissement,          // chemin absolu ou "" pour le défaut (logoVH.png)
  logo_specialite,             // chemin absolu ou "" pour la détection automatique
} = payload;

// ── Couleurs ──────────────────────────────────────────────────────────────────
const BLEU   = "1A4D8F";
const ORANGE = "E8700A";
const GRIS   = "F0F4FA";
const GRIS2  = "E8EDF5";
const BLANC  = "FFFFFF";
const VERT   = "2E7D32";
const NOIR   = "1C1C2E";

// ── Dimensions A4 ─────────────────────────────────────────────────────────────
const PAGE_W   = 11906;
const PAGE_H   = 16838;
const MARGE    = 851;   // ~1.5cm
const CONTENT  = PAGE_W - 2 * MARGE;

// ── Helpers bordures ──────────────────────────────────────────────────────────
const brd  = (color = "CCCCCC", sz = 1) => ({ style: BorderStyle.SINGLE, size: sz, color });
const brds = (color, sz) => ({ top: brd(color,sz), bottom: brd(color,sz), left: brd(color,sz), right: brd(color,sz) });
const noBrd  = { style: BorderStyle.NONE, size: 0, color: BLANC };
const noBrds = { top: noBrd, bottom: noBrd, left: noBrd, right: noBrd };

// ── Lecture image (nom de fichier relatif à img_dir) ──────────────────────────
function readImg(filename) {
  const p = path.join(img_dir, filename);
  if (!fs.existsSync(p)) return null;
  return fs.readFileSync(p);
}

// ── Lecture image (chemin absolu ou relatif) ───────────────────────────────────
function readImgAny(filePath) {
  if (!filePath) return null;
  const p = path.isAbsolute(filePath) ? filePath : path.join(img_dir, filePath);
  if (!fs.existsSync(p)) return null;
  return fs.readFileSync(p);
}

// ── Logo STI2D selon classe (détection automatique) ───────────────────────────
function logoSpecialite() {
  if (classe.includes("2I2D") || classe.includes("Terminale")) return "2i2d.png";
  if (classe.includes("I2D")) return "I2D.png";
  return "IT.png";
}

// ── Cellule tableau ───────────────────────────────────────────────────────────
function cell(text, w, opts = {}) {
  const { bg = BLANC, bold = false, color = NOIR, fontSize = 20,
          align = AlignmentType.LEFT, borders = brds("CCCCCC"), vAlign = VerticalAlign.CENTER } = opts;
  return new TableCell({
    width: { size: w, type: WidthType.DXA },
    borders, shading: { fill: bg, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    verticalAlign: vAlign,
    children: [new Paragraph({
      alignment: align,
      children: [new TextRun({ text: String(text || ""), font: "Calibri", size: fontSize, bold, color })]
    })]
  });
}

// ── Cellule avec ImageRun ──────────────────────────────────────────────────────
function cellImg(imgData, w, imgW, imgH) {
  return new TableCell({
    width: { size: w, type: WidthType.DXA },
    borders: noBrds,
    shading: { fill: BLANC, type: ShadingType.CLEAR },
    margins: { top: 40, bottom: 40, left: 60, right: 60 },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: imgData ? [new ImageRun({ data: imgData, transformation: { width: imgW, height: imgH }, type: "png" })] : [new TextRun("")]
    })]
  });
}

// ── Niveaux ───────────────────────────────────────────────────────────────────
function niveauLabel(v) {
  if (v === "XX") return "Évalué ✓✓";
  if (v === "X")  return "Mobilisé ✓";
  return "—";
}

function getCO(code) { return (competences.competences || {})[code] || {}; }
function getConn(ref) {
  const chap = ref.split("-")[0];
  const cd = connaissances[chap] || {};
  const sc = (cd.sous_chapitres || {})[ref] || {};
  return { titre: sc.titre || cd.titre || ref, detail: sc.detail || "" };
}

// ════════════════════════════════════════════════════════════════════════════════
// EN-TÊTE COMMUN (logo VH | titre | logo spécialité)
// ════════════════════════════════════════════════════════════════════════════════
function buildEnTete(titrePrincipal, titreSecondaire = "") {
  const logoVH  = logo_etablissement ? readImgAny(logo_etablissement) : readImg("logoVH.png");
  const logoSpe = logo_specialite    ? readImgAny(logo_specialite)    : readImg(logoSpecialite());

  const colL = Math.round(CONTENT * 0.18);
  const colC = Math.round(CONTENT * 0.64);
  const colR = Math.round(CONTENT * 0.18);

  // Cellule centrale : titre
  const cellCentre = new TableCell({
    width: { size: colC, type: WidthType.DXA },
    borders: noBrds,
    shading: { fill: BLANC, type: ShadingType.CLEAR },
    margins: { top: 60, bottom: 60, left: 120, right: 120 },
    verticalAlign: VerticalAlign.CENTER,
    children: [
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: titrePrincipal, font: "Calibri", size: 28, bold: true, color: BLEU })]
      }),
      ...(titreSecondaire ? [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: titreSecondaire, font: "Calibri", size: 20, color: "555555" })]
      })] : [])
    ]
  });

  return new Table({
    width: { size: CONTENT, type: WidthType.DXA },
    columnWidths: [colL, colC, colR],
    rows: [new TableRow({ children: [
      cellImg(logoVH,  colL, 90, 60),
      cellCentre,
      cellImg(logoSpe, colR, 90, 50),
    ]})]
  });
}

// ── Ligne séparatrice ──────────────────────────────────────────────────────────
function separator(color = BLEU) {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 12, color, space: 2 } },
    spacing: { after: 120 },
    children: []
  });
}

function titre2(text) {
  return new Paragraph({
    spacing: { before: 200, after: 80 },
    children: [new TextRun({ text, font: "Calibri", size: 24, bold: true, color: ORANGE })]
  });
}

function para(text = "", opts = {}) {
  return new Paragraph({
    spacing: { after: 60 },
    children: [new TextRun({ text, font: "Calibri", size: 20, ...opts })]
  });
}

// ════════════════════════════════════════════════════════════════════════════════
// MODE PRÉPARATION DE COURS
// ════════════════════════════════════════════════════════════════════════════════
function buildPreparation() {
  const children = [];

  // En-tête
  children.push(buildEnTete(
    theme.titre,
    `${etablissement || ""}  —  ${classe}`
  ));
  children.push(separator());

  // Bloc problématique
  const pbColW = [Math.round(CONTENT * 0.22), Math.round(CONTENT * 0.78)];
  children.push(new Table({
    width: { size: CONTENT, type: WidthType.DXA },
    columnWidths: pbColW,
    rows: [new TableRow({ children: [
      cell("Problématique", pbColW[0], { bg: ORANGE, bold: true, color: BLANC, fontSize: 22 }),
      cell(problematique.titre, pbColW[1], { bold: true, fontSize: 22 }),
    ]})]
  }));
  children.push(para());

  // ── Compétences ────────────────────────────────────────────────────────────
  children.push(titre2("Compétences visées"));
  const cColW = [
    Math.round(CONTENT * 0.09),
    Math.round(CONTENT * 0.51),
    Math.round(CONTENT * 0.13),
    Math.round(CONTENT * 0.13),
    Math.round(CONTENT * 0.14),
  ];
  const cRows = [new TableRow({ children: [
    cell("Code",    cColW[0], { bg: BLEU, bold: true, color: BLANC }),
    cell("Libellé", cColW[1], { bg: BLEU, bold: true, color: BLANC }),
    cell("IT",      cColW[2], { bg: BLEU, bold: true, color: BLANC, align: AlignmentType.CENTER }),
    cell("I2D",     cColW[3], { bg: BLEU, bold: true, color: BLANC, align: AlignmentType.CENTER }),
    cell("2I2D",    cColW[4], { bg: BLEU, bold: true, color: BLANC, align: AlignmentType.CENTER }),
  ]})];

  let rowBg = true;
  for (const code of problematique.competences) {
    const co = getCO(code);
    const niv = co.niveaux || {};
    const bg = rowBg ? BLANC : GRIS;
    cRows.push(new TableRow({ children: [
      cell(code,              cColW[0], { bg, bold: true }),
      cell(co.libelle || "—", cColW[1], { bg }),
      cell(niveauLabel(niv.IT    || ""), cColW[2], { bg, color: niv.IT    === "XX" ? VERT : NOIR, align: AlignmentType.CENTER }),
      cell(niveauLabel(niv.I2D   || ""), cColW[3], { bg, color: niv.I2D   === "XX" ? VERT : NOIR, align: AlignmentType.CENTER }),
      cell(niveauLabel(niv["2I2D"] || ""), cColW[4], { bg, color: niv["2I2D"] === "XX" ? VERT : NOIR, align: AlignmentType.CENTER }),
    ]}));
    rowBg = !rowBg;
  }
  children.push(new Table({ width: { size: CONTENT, type: WidthType.DXA }, columnWidths: cColW, rows: cRows }));
  children.push(para());

  // ── Connaissances ──────────────────────────────────────────────────────────
  children.push(titre2("Connaissances associées"));
  const knColW = [Math.round(CONTENT * 0.1), Math.round(CONTENT * 0.3), Math.round(CONTENT * 0.6)];
  const knRows = [new TableRow({ children: [
    cell("Réf.",   knColW[0], { bg: BLEU, bold: true, color: BLANC }),
    cell("Thème",  knColW[1], { bg: BLEU, bold: true, color: BLANC }),
    cell("Contenu à développer", knColW[2], { bg: BLEU, bold: true, color: BLANC }),
  ]})];
  let knBg = true;
  for (const ref of problematique.connaissances) {
    const c = getConn(ref);
    const bg = knBg ? BLANC : GRIS;
    knRows.push(new TableRow({ children: [
      cell(ref,     knColW[0], { bg, bold: true }),
      cell(c.titre, knColW[1], { bg }),
      cell("",      knColW[2], { bg }),
    ]}));
    knBg = !knBg;
  }
  children.push(new Table({ width: { size: CONTENT, type: WidthType.DXA }, columnWidths: knColW, rows: knRows }));
  children.push(para());

  // ── Structure pédagogique ──────────────────────────────────────────────────
  children.push(titre2("Structure pédagogique"));
  const sColW = [
    Math.round(CONTENT * 0.07), Math.round(CONTENT * 0.2),
    Math.round(CONTENT * 0.43), Math.round(CONTENT * 0.15), Math.round(CONTENT * 0.15)
  ];
  const sRows = [new TableRow({ children: [
    cell("N°",      sColW[0], { bg: ORANGE, bold: true, color: BLANC }),
    cell("Type",    sColW[1], { bg: ORANGE, bold: true, color: BLANC }),
    cell("Contenu / Activité", sColW[2], { bg: ORANGE, bold: true, color: BLANC }),
    cell("Durée",   sColW[3], { bg: ORANGE, bold: true, color: BLANC }),
    cell("Éval.",   sColW[4], { bg: ORANGE, bold: true, color: BLANC }),
  ]})];
  const etapes = [
    ["1","Situation déclenchante (TP)","","2h",""],
    ["2","Cours co-construit","","1h",""],
    ["3","Exercices d'application","","1h",""],
    ["4","Auto-évaluation / Bilan","","0.5h","Formative"],
  ];
  etapes.forEach((e, i) => {
    const bg = i % 2 === 0 ? BLANC : GRIS;
    sRows.push(new TableRow({ children: [
      cell(e[0], sColW[0], { bg }),
      cell(e[1], sColW[1], { bg, bold: true }),
      cell(e[2], sColW[2], { bg }),
      cell(e[3], sColW[3], { bg }),
      cell(e[4], sColW[4], { bg }),
    ]}));
  });
  children.push(new Table({ width: { size: CONTENT, type: WidthType.DXA }, columnWidths: sColW, rows: sRows }));
  children.push(para());

  // ── Notes ──────────────────────────────────────────────────────────────────
  children.push(titre2("Notes / Ressources"));
  const noteRows = Array.from({ length: 6 }, () =>
    new TableRow({ children: [cell("", CONTENT, { bg: BLANC })] })
  );
  children.push(new Table({ width: { size: CONTENT, type: WidthType.DXA }, columnWidths: [CONTENT], rows: noteRows }));

  return children;
}

// ════════════════════════════════════════════════════════════════════════════════
// MODE DOCUMENT ÉLÈVE
// ════════════════════════════════════════════════════════════════════════════════
function buildEleve() {
  const children = [];

  // En-tête avec titre de séance
  children.push(buildEnTete(
    titre_seance || "Document élève",
    classe
  ));
  children.push(separator());

  // Infos séance
  const infoColW = [Math.round(CONTENT * 0.5), Math.round(CONTENT * 0.5)];
  children.push(new Table({
    width: { size: CONTENT, type: WidthType.DXA },
    columnWidths: infoColW,
    rows: [new TableRow({ children: [
      cell(`Nom : ___________________________`, infoColW[0], { borders: noBrds }),
      cell(`Date : _______________  Note : ___/___`, infoColW[1], { borders: noBrds, align: AlignmentType.RIGHT }),
    ]})]
  }));
  children.push(separator(ORANGE));

  // Thème / Problématique (compact)
  children.push(new Table({
    width: { size: CONTENT, type: WidthType.DXA },
    columnWidths: [Math.round(CONTENT * 0.22), Math.round(CONTENT * 0.78)],
    rows: [
      new TableRow({ children: [
        cell("Thème", Math.round(CONTENT * 0.22), { bg: BLEU, bold: true, color: BLANC }),
        cell(theme.titre, Math.round(CONTENT * 0.78), { bold: true }),
      ]}),
      new TableRow({ children: [
        cell("Problématique", Math.round(CONTENT * 0.22), { bg: ORANGE, bold: true, color: BLANC }),
        cell(problematique.titre, Math.round(CONTENT * 0.78), { bold: true }),
      ]}),
    ]
  }));
  children.push(para());

  // ── Pour chaque compétence sélectionnée ───────────────────────────────────
  for (const sel of (competences_selectionnees || [])) {
    const co = getCO(sel.code);
    const niv = co.niveaux || {};

    // Bandeau compétence
    children.push(new Table({
      width: { size: CONTENT, type: WidthType.DXA },
      columnWidths: [Math.round(CONTENT * 0.12), Math.round(CONTENT * 0.73), Math.round(CONTENT * 0.15)],
      rows: [new TableRow({ children: [
        cell(sel.code, Math.round(CONTENT * 0.12), { bg: BLEU, bold: true, color: BLANC, fontSize: 22, align: AlignmentType.CENTER }),
        cell(co.libelle || "—", Math.round(CONTENT * 0.73), { bg: GRIS2, bold: true, fontSize: 20 }),
        cell(
          classe.includes("2I2D") ? niveauLabel(niv["2I2D"] || "") :
          classe.includes("I2D")  ? niveauLabel(niv.I2D     || "") :
                                    niveauLabel(niv.IT       || ""),
          Math.round(CONTENT * 0.15),
          { bg: GRIS2, bold: true, color: VERT, align: AlignmentType.CENTER }
        ),
      ]})]
    }));

    // Connaissances sélectionnées pour cette compétence
    if (sel.connaissances && sel.connaissances.length > 0) {
      const knColW2 = [Math.round(CONTENT * 0.1), Math.round(CONTENT * 0.35), Math.round(CONTENT * 0.55)];
      const knRows2 = [new TableRow({ children: [
        cell("Réf.",       knColW2[0], { bg: BLEU, bold: true, color: BLANC, fontSize: 18 }),
        cell("Connaissance", knColW2[1], { bg: BLEU, bold: true, color: BLANC, fontSize: 18 }),
        cell("Critères de réussite / Ce que je dois savoir faire", knColW2[2], { bg: BLEU, bold: true, color: BLANC, fontSize: 18 }),
      ]})];
      let knBg = true;
      for (const ref of sel.connaissances) {
        const c = getConn(ref);
        const bg = knBg ? BLANC : GRIS;
        knRows2.push(new TableRow({ children: [
          cell(ref,     knColW2[0], { bg, bold: true, fontSize: 18 }),
          cell(c.titre, knColW2[1], { bg, fontSize: 18 }),
          cell("",      knColW2[2], { bg }),
        ]}));
        knBg = !knBg;
      }
      children.push(new Table({ width: { size: CONTENT, type: WidthType.DXA }, columnWidths: knColW2, rows: knRows2 }));
    }

    // Zone de travail élève (5 lignes vides)
    children.push(para());
    const lignesVides = Array.from({ length: 5 }, () =>
      new TableRow({ children: [cell("", CONTENT, { bg: BLANC })] })
    );
    children.push(new Table({ width: { size: CONTENT, type: WidthType.DXA }, columnWidths: [CONTENT], rows: lignesVides }));
    children.push(para());
  }

  return children;
}

// ════════════════════════════════════════════════════════════════════════════════
// ASSEMBLAGE & EXPORT
// ════════════════════════════════════════════════════════════════════════════════
(async () => {
  try {
    const children = mode === "eleve" ? buildEleve() : buildPreparation();

    const doc = new Document({
      styles: {
        default: { document: { run: { font: "Calibri", size: 20 } } },
        paragraphStyles: [
          { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal",
            run: { size: 28, bold: true, font: "Calibri", color: BLEU },
            paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 } },
          { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal",
            run: { size: 24, bold: true, font: "Calibri", color: ORANGE },
            paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 1 } },
        ]
      },
      sections: [{
        properties: {
          page: {
            size: { width: PAGE_W, height: PAGE_H },
            margin: { top: MARGE, right: MARGE, bottom: MARGE, left: MARGE }
          }
        },
        children
      }]
    });

    const buffer = await Packer.toBuffer(doc);
    const safe = s => String(s || "").replace(/[^a-zA-Z0-9\u00C0-\u024F_\- ]/g, "_").trim().slice(0, 80);
    const prefix = mode === "eleve" ? "ELEVE" : "PREP";
    const autoFilename = `${prefix}_${theme.id}_${problematique.id}_${safe(classe)}.docx`;
    const customRaw = safe(output_filename);
    const filename = customRaw
      ? (customRaw.toLowerCase().endsWith(".docx") ? customRaw : `${customRaw}.docx`)
      : autoFilename;
    const outPath = path.join(output_dir, filename);
    fs.writeFileSync(outPath, buffer);
    process.stdout.write(outPath + '\n');
    process.exit(0);
  } catch (err) {
    process.stderr.write('Erreur : ' + err.stack + '\n');
    process.exit(1);
  }
})();
