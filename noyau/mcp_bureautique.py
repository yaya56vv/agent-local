"""MCP bureautique d'Agent Local : documents Word (.docx) et tableaux Excel (.xlsx), sans Internet ni Office
(decision du 14/11/2026 : CV, lettres, tableaux). Les outils de creation fabriquent toujours un NOUVEAU fichier
et refusent d'ecraser un fichier existant (il faut un autre nom).
Outils : lire_word, lire_excel (libres) ; creer_word, creer_excel.
"""
import os
import re

import docx
import openpyxl
from docx.shared import Pt
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from langue import t as tr

serveur = FastMCP("bureautique")
LECTURE = ToolAnnotations(readOnlyHint=True)
LIMITE = 15000


def _chemin_neuf(chemin, extension):
    chemin = os.path.abspath(chemin.strip().strip('"'))
    if not chemin.lower().endswith(extension):
        chemin += extension
    if os.path.exists(chemin):
        return None, tr("mcp_bureautique.refus_existe_deja_choisis_un", chemin=chemin)
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    return chemin, ""


@serveur.tool(annotations=LECTURE, description=tr("outil.bureautique.lire_word"))
def lire_word(chemin: str) -> str:
    try:
        d = docx.Document(chemin.strip().strip('"'))
    except Exception as e:
        return tr("mcp_bureautique.erreur_impossible_d_ouvrir_ce", e=e)
    lignes = []
    for p in d.paragraphs:
        if p.text.strip():
            style = (p.style.name or "").lower()
            prefixe = "# " if "heading 1" in style or "titre 1" in style or style == "title" else \
                      "## " if "heading" in style or "titre" in style else ""
            lignes.append(prefixe + p.text)
    for i, t in enumerate(d.tables, 1):
        lignes.append(f"\n[Tableau {i}]")
        for r in t.rows:
            lignes.append(" | ".join(c.text.strip() for c in r.cells))
    texte = "\n".join(lignes) or tr("mcp_bureautique.document_vide")
    return texte[:LIMITE] + ("\n[... coupe]" if len(texte) > LIMITE else "")


@serveur.tool(annotations=LECTURE, description=tr("outil.bureautique.lire_excel"))
def lire_excel(chemin: str, feuille: str = "", lignes_max: int = 200) -> str:
    try:
        cl = openpyxl.load_workbook(chemin.strip().strip('"'), data_only=True, read_only=True)
    except Exception as e:
        return tr("mcp_bureautique.erreur_impossible_d_ouvrir_ce_2", e=e)
    f = cl[feuille] if feuille and feuille in cl.sheetnames else cl[cl.sheetnames[0]]
    # formules jamais calculees par Excel : la valeur est vide, on montre alors la formule elle-meme
    brut = openpyxl.load_workbook(chemin.strip().strip('"'), data_only=False, read_only=True)[f.title]
    sortie = [f"Feuilles : {', '.join(cl.sheetnames)} | lue : {f.title}"]
    for n, (ligne, formules) in enumerate(zip(f.iter_rows(values_only=True), brut.iter_rows(values_only=True)), 1):
        if n > max(1, min(int(lignes_max), 2000)):
            sortie.append(tr("mcp_bureautique.lignes_suivantes_non_affichees"))
            break
        valeurs = [v if v is not None else (fo if isinstance(fo, str) and fo.startswith("=") else None)
                   for v, fo in zip(ligne, formules)]
        if any(v is not None for v in valeurs):
            sortie.append(f"{n}: " + " | ".join("" if v is None else str(v) for v in valeurs))
    texte = "\n".join(sortie)
    return texte[:LIMITE] + ("\n[... coupe]" if len(texte) > LIMITE else "")


def _ajouter_texte(paragraphe, texte):
    """Gere **gras** dans une ligne."""
    for i, morceau in enumerate(re.split(r"\*\*", texte)):
        if morceau:
            paragraphe.add_run(morceau).bold = (i % 2 == 1)


@serveur.tool(description=tr("outil.bureautique.creer_word"))
def creer_word(chemin: str, contenu: str) -> str:
    chemin, erreur = _chemin_neuf(chemin, ".docx")
    if erreur:
        return erreur
    d = docx.Document()
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(11)
    tableau = []

    def vider_tableau():
        if tableau:
            t = d.add_table(rows=len(tableau), cols=max(len(r) for r in tableau))
            t.style = tr("mcp_bureautique.table_grid")
            for i, r in enumerate(tableau):
                for j, v in enumerate(r):
                    t.cell(i, j).text = v
                    if i == 0:
                        for run in t.cell(i, j).paragraphs[0].runs:
                            run.bold = True
            tableau.clear()

    for ligne in contenu.splitlines():
        brut = ligne.rstrip()
        if brut.startswith("|"):
            cellules = [c.strip() for c in brut.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cellules if c):
                tableau.append(cellules)
            continue
        vider_tableau()
        if brut.startswith("## "):
            d.add_heading(brut[3:], level=2)
        elif brut.startswith("# "):
            d.add_heading(brut[2:], level=1)
        elif brut.lstrip().startswith(("- ", "* ")):
            _ajouter_texte(d.add_paragraph(style=tr("mcp_bureautique.list_bullet")), brut.lstrip()[2:])
        elif brut.strip():
            _ajouter_texte(d.add_paragraph(), brut)
    vider_tableau()
    d.save(chemin)
    return tr("mcp_bureautique.document_word_cree", chemin=chemin)


@serveur.tool(description=tr("outil.bureautique.creer_excel"))
def creer_excel(chemin: str, lignes: list[list], feuille: str = "Feuille1") -> str:
    chemin, erreur = _chemin_neuf(chemin, ".xlsx")
    if erreur:
        return erreur
    if not lignes:
        return tr("mcp_bureautique.erreur_aucune_ligne_a_ecrire")
    cl = openpyxl.Workbook()
    f = cl.active
    f.title = feuille[:31] or "Feuille1"
    for r in lignes:
        f.append([v for v in (r if isinstance(r, list) else [r])])
    for c in f[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="DDEBF7")
    for j, col in enumerate(f.columns, 1):
        largeur = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        f.column_dimensions[get_column_letter(j)].width = min(60, max(10, largeur + 2))
    f.freeze_panes = "A2"
    cl.save(chemin)
    return tr("mcp_bureautique.tableau_excel_cree_lignes", chemin=chemin, v1=len(lignes))


if __name__ == "__main__":
    serveur.run()
