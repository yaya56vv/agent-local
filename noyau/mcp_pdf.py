"""MCP pdf d'Agent Local : lire ET ecrire des PDF, sans Internet (11/11/2026).
Bibliotheques : pypdf (lecture, assemblage, extraction, formulaires) et reportlab (creation), toutes deux sous licence BSD.
Securite : le fichier d'origine n'est jamais modifie et un fichier existant n'est jamais ecrase (on cree toujours un
nouveau fichier) ; seuls les dossiers passes en arguments au lancement sont accessibles (memes que l'outil fichiers).
Outils : lire_pdf, infos_pdf (lecture) ; creer_pdf, assembler_pdf, extraire_pages, remplir_formulaire (ecriture).
"""
import os
import sys
from xml.sax.saxutils import escape

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from langue import t as tr

serveur = FastMCP("pdf")
LECTURE = ToolAnnotations(readOnlyHint=True)
DOSSIERS = [os.path.normcase(os.path.abspath(os.path.expandvars(d))) for d in sys.argv[1:]]
LIMITE = 40000   # caracteres de texte renvoyes au modele
TYPES = {"/Tx": "texte", "/Btn": tr("mcp_pdf.case_ou_bouton"), "/Ch": tr("mcp_pdf.liste_de_choix"), "/Sig": "signature"}


def _verifier(chemin, sortie=False):
    """Chemin complet, dans les dossiers autorises ; en sortie : extension .pdf et fichier encore inexistant."""
    chemin = os.path.abspath(str(chemin or "").strip().strip('"'))
    normal = os.path.normcase(chemin)
    if not any(normal == d or normal.startswith(d.rstrip("\\") + "\\") for d in DOSSIERS):
        raise ValueError(tr("mcp_pdf.est_hors_des_dossiers_autorises", chemin=chemin, v1=', '.join(DOSSIERS)))
    if sortie:
        if not chemin.lower().endswith(".pdf"):
            raise ValueError(tr("mcp_pdf.le_fichier_a_creer_doit"))
        if os.path.exists(chemin):
            raise ValueError(tr("mcp_pdf.existe_deja_choisis_un_autre", chemin=chemin))
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
    elif not os.path.isfile(chemin):
        raise ValueError(tr("mcp_pdf.le_fichier_n_existe_pas", chemin=chemin))
    return chemin


def _pages(texte, total):
    """'1-3,5' -> [0,1,2,4] (numerotation humaine a partir de 1)."""
    if not str(texte or "").strip():
        return list(range(total))
    resultat = []
    for morceau in str(texte).replace(" ", "").split(","):
        debut, _, fin = morceau.partition("-")
        a, b = int(debut), int(fin or debut)
        resultat += [p - 1 for p in range(a, b + 1) if 1 <= p <= total]
    return resultat


def _erreur(e):
    return tr("commun.erreur_deux_points") + f"{e}"


def _champs_par_page(lecteur):
    """[(numero de page, nom complet du champ, annotation)] pour chaque widget de formulaire."""
    trouves = []
    for n, page in enumerate(lecteur.pages, start=1):
        for ref in page.get("/Annots") or []:
            annot = ref.get_object()
            if annot.get("/Subtype") != "/Widget":
                continue
            noeud, morceaux = annot, []
            while noeud is not None:
                if "/T" in noeud:
                    morceaux.insert(0, str(noeud["/T"]))
                noeud = noeud.get("/Parent").get_object() if "/Parent" in noeud else None
            if morceaux:
                trouves.append((n, ".".join(morceaux), annot))
    return trouves


@serveur.tool(annotations=LECTURE, description=tr("outil.pdf.lire_pdf"))
def lire_pdf(chemin: str, pages: str = "") -> str:
    try:
        lecteur = PdfReader(_verifier(chemin))
        total = len(lecteur.pages)
        morceaux = [f"--- Page {i + 1}/{total} ---\n{(lecteur.pages[i].extract_text() or '').strip()}"
                    for i in _pages(pages, total)]
        texte = "\n\n".join(morceaux)
        if all(not m.split("---\n", 1)[-1].strip() for m in morceaux):
            return texte + tr("mcp_pdf.aucun_texte_pdf_probablement_scanne")
        return texte if len(texte) <= LIMITE else texte[:LIMITE] + tr("mcp_pdf.texte_coupe_demande_moins_de")
    except Exception as e:
        return _erreur(e)


@serveur.tool(annotations=LECTURE, description=tr("outil.pdf.infos_pdf"))
def infos_pdf(chemin: str) -> str:
    try:
        lecteur = PdfReader(_verifier(chemin))
        meta = lecteur.metadata or {}
        lignes = [f"{len(lecteur.pages)} page(s) ; titre : {meta.get('/Title') or '-'} ; auteur : {meta.get('/Author') or '-'}"]
        champs = lecteur.get_fields() or {}
        pages = {nom: n for n, nom, _ in _champs_par_page(lecteur)}
        remplissables = {nom: c for nom, c in champs.items() if c.get("/FT") in TYPES}
        if remplissables:
            lignes.append(f"Formulaire : {len(remplissables)} champ(s) remplissable(s) :")
            for nom, c in remplissables.items():
                etats = [e for e in (c.get("/_States_") or []) if e != "/Off"]
                genre = TYPES[c.get("/FT")] + (f", coche = {etats[0]}" if etats else "")
                lignes.append(f"- page {pages.get(nom, '?')} : '{nom}' ({genre}) = '{c.get('/V') or ''}'")
        else:
            lignes.append(tr("mcp_pdf.aucun_champ_de_formulaire_remplissable"))
        return "\n".join(lignes)
    except Exception as e:
        return _erreur(e)


def _polices():
    """Arial de Windows si presente (accents, euro, alphabets non latins), sinon Helvetica integree a reportlab."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    dossier = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    normale, grasse = os.path.join(dossier, "arial.ttf"), os.path.join(dossier, "arialbd.ttf")
    if os.path.isfile(normale) and os.path.isfile(grasse):
        if "AgentArial" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("AgentArial", normale))
            pdfmetrics.registerFont(TTFont("AgentArial-Gras", grasse))
        return "AgentArial", "AgentArial-Gras"
    return "Helvetica", "Helvetica-Bold"


@serveur.tool(description=tr("outil.pdf.creer_pdf"))
def creer_pdf(chemin_sortie: str, texte: str, titre: str = "") -> str:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate
        sortie = _verifier(chemin_sortie, sortie=True)
        police, grasse = _polices()
        normal = ParagraphStyle("normal", fontName=police, fontSize=11, leading=15.4, spaceAfter=6)
        h1 = ParagraphStyle("h1", fontName=grasse, fontSize=18, leading=22, spaceBefore=6, spaceAfter=10)
        h2 = ParagraphStyle("h2", fontName=grasse, fontSize=14, leading=18, spaceBefore=6, spaceAfter=6)
        corps, liste = [], []

        def fermer_liste():
            if liste:
                corps.append(ListFlowable([ListItem(Paragraph(escape(e), normal)) for e in liste],
                                          bulletType="bullet", bulletFontName=police, leftIndent=14))
                liste.clear()
        if titre:
            corps.append(Paragraph(escape(titre), h1))
        for ligne in str(texte).splitlines():
            l = ligne.rstrip()
            if l.startswith("- "):
                liste.append(l[2:])
                continue
            fermer_liste()
            if l.startswith("## "):
                corps.append(Paragraph(escape(l[3:]), h2))
            elif l.startswith("# "):
                corps.append(Paragraph(escape(l[2:]), h1))
            elif l.strip():
                corps.append(Paragraph(escape(l), normal))
        fermer_liste()
        document = SimpleDocTemplate(sortie, pagesize=A4, leftMargin=50, rightMargin=50, topMargin=50, bottomMargin=50,
                                     title=titre or "", author=tr("mcp_pdf.agent_local"))
        document.build(corps)
        return tr("mcp_pdf.pdf_cree_page_s", sortie=sortie, v1=len(PdfReader(sortie).pages))
    except Exception as e:
        return _erreur(e)


@serveur.tool(description=tr("outil.pdf.assembler_pdf"))
def assembler_pdf(fichiers: list[str], chemin_sortie: str) -> str:
    try:
        sortie = _verifier(chemin_sortie, sortie=True)
        sources = [_verifier(f) for f in fichiers]
        ecrivain = PdfWriter()
        for f in sources:
            ecrivain.append(f)
        total = len(ecrivain.pages)
        with open(sortie, "xb") as flux:
            ecrivain.write(flux)
        return tr("mcp_pdf.pdf_assemble_pages_fichiers", sortie=sortie, total=total, v1=len(fichiers))
    except Exception as e:
        return _erreur(e)


@serveur.tool(description=tr("outil.pdf.extraire_pages"))
def extraire_pages(chemin: str, pages: str, chemin_sortie: str) -> str:
    try:
        sortie = _verifier(chemin_sortie, sortie=True)
        lecteur = PdfReader(_verifier(chemin))
        choix = _pages(pages, len(lecteur.pages))
        if not choix:
            return tr("mcp_pdf.erreur_aucune_page_valide_dans")
        ecrivain = PdfWriter()
        for i in choix:
            ecrivain.add_page(lecteur.pages[i])
        with open(sortie, "xb") as flux:
            ecrivain.write(flux)
        return tr("mcp_pdf.pages_extraites_page_s", sortie=sortie, v1=len(choix))
    except Exception as e:
        return _erreur(e)


@serveur.tool(description=tr("outil.pdf.remplir_formulaire"))
def remplir_formulaire(chemin: str, valeurs: dict, chemin_sortie: str) -> str:
    try:
        sortie = _verifier(chemin_sortie, sortie=True)
        lecteur = PdfReader(_verifier(chemin))
        champs = lecteur.get_fields() or {}
        a_ecrire, inconnus = {}, set()
        for nom, v in valeurs.items():
            champ = champs.get(nom)
            if champ is None:
                inconnus.add(nom)
            elif champ.get("/FT") == "/Btn":
                etats = [e for e in (champ.get("/_States_") or []) if e != "/Off"]
                coche = str(v).lower() in ("oui", "yes", "true", "1", "x")   # francais ou anglais
                a_ecrire[nom] = NameObject(etats[0] if coche and etats else "/Off")
            else:
                a_ecrire[nom] = str(v)
        ecrivain = PdfWriter(clone_from=lecteur)
        for page in ecrivain.pages:
            ecrivain.update_page_form_field_values(page, a_ecrire, auto_regenerate=False)
        ecrivain.set_need_appearances_writer(True)   # les lecteurs PDF redessinent les champs remplis
        with open(sortie, "xb") as flux:
            ecrivain.write(flux)
        texte = tr("mcp_pdf.formulaire_rempli_champ_s", sortie=sortie, v1=len(a_ecrire))
        if inconnus:
            texte += tr("mcp_pdf.champs_introuvables", v1=', '.join(sorted(inconnus)))
        return texte
    except Exception as e:
        return _erreur(e)


if __name__ == "__main__":
    serveur.run()
