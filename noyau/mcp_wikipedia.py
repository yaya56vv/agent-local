"""MCP wikipedia d'Agent Local : Wikipedia en francais HORS LIGNE (decision du 11/11/2026 : que l'agent reste
utile si Internet est coupe). Lit directement le fichier ZIM de Kiwix (texte integral, sans images) avec la
bibliotheque officielle libzim : ni serveur, ni Docker, ni Internet. Lecture seule.
Module FACULTATIF : libzim est sous licence GPL-3.0 (installee a part : requirements-wikipedia.txt).
Fichier ZIM : config.json, rubrique wikipedia.fichier_zim (ou premier argument).
Outils : chercher_wikipedia, lire_article.
"""
import html
import re
import sys
from html.parser import HTMLParser

from libzim.reader import Archive
from libzim.search import Query, Searcher
from libzim.suggestion import SuggestionSearcher
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

import reglages
from langue import t as tr

serveur = FastMCP("wikipedia")
LECTURE = ToolAnnotations(readOnlyHint=True)
ARCHIVE = Archive(sys.argv[1] if len(sys.argv) > 1 else reglages.charger()["wikipedia"]["fichier_zim"])
TRANCHE = 12000   # caracteres d'article renvoyes a la fois


class _Texte(HTMLParser):
    """HTML d'article -> texte lisible (titres et paragraphes sur leur ligne, sans scripts ni styles)."""
    IGNORES = {"script", "style", "sup", "table"}
    BLOCS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "dd", "dt"}

    def __init__(self):
        super().__init__()
        self.morceaux, self.ignore = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORES:
            self.ignore += 1
        elif tag in self.BLOCS:
            self.morceaux.append("\n")
        if tag in ("h2", "h3") and not self.ignore:
            self.morceaux.append("## " if tag == "h2" else "### ")
        if tag == "li" and not self.ignore:
            self.morceaux.append("- ")

    def handle_endtag(self, tag):
        if tag in self.IGNORES and self.ignore:
            self.ignore -= 1
        elif tag in self.BLOCS:
            self.morceaux.append("\n")

    def handle_data(self, data):
        if not self.ignore:
            self.morceaux.append(data)


def _en_texte(contenu):
    p = _Texte()
    p.feed(contenu)
    t = html.unescape("".join(p.morceaux))
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def _entree(titre_ou_chemin):
    """Trouve un article par son chemin exact, son titre exact, ou a defaut la meilleure suggestion de titre."""
    cle = titre_ou_chemin.strip()
    for essai in (cle, cle.replace(" ", "_"), "A/" + cle.replace(" ", "_")):
        if ARCHIVE.has_entry_by_path(essai):
            return ARCHIVE.get_entry_by_path(essai)
    if ARCHIVE.has_entry_by_title(cle):
        return ARCHIVE.get_entry_by_title(cle)
    resultats = list(SuggestionSearcher(ARCHIVE).suggest(cle).get_results(0, 1))
    return ARCHIVE.get_entry_by_path(resultats[0]) if resultats else None


@serveur.tool(annotations=LECTURE, description=tr("outil.wikipedia.chercher_wikipedia"))
def chercher_wikipedia(requete: str, nombre: int = 8) -> str:
    nombre = max(1, min(int(nombre or 8), 20))
    vus, lignes = set(), []
    for chemin in SuggestionSearcher(ARCHIVE).suggest(requete).get_results(0, 3):   # titres proches d'abord
        vus.add(chemin)
        lignes.append(f"- {ARCHIVE.get_entry_by_path(chemin).title}")
    recherche = Searcher(ARCHIVE).search(Query().set_query(requete))
    for resultat in recherche.get_results(0, nombre * 2):
        chemin = getattr(resultat, "path", resultat)   # libzim 3.x : objet SearchResult ; avant : chemin texte
        if chemin in vus or len(lignes) >= nombre:
            continue
        vus.add(chemin)
        entree = ARCHIVE.get_entry_by_path(chemin)
        try:
            debut = _en_texte(bytes(entree.get_item().content).decode("utf-8", "replace"))[:220]
        except Exception:
            debut = ""
        lignes.append(f"- {entree.title} : {debut.replace(chr(10), ' ')}...")
    if not lignes:
        return tr("mcp_wikipedia.aucun_article_trouve_pour_essaie", requete=requete)
    return (tr("mcp_wikipedia.wikipedia_hors_ligne_articles_resultats", v1=ARCHIVE.article_count, requete=requete) + "\n".join(lignes))


@serveur.tool(annotations=LECTURE, description=tr("outil.wikipedia.lire_article"))
def lire_article(titre: str, debut: int = 0) -> str:
    entree = _entree(titre)
    if entree is None:
        return tr("mcp_wikipedia.article_introuvable_utilise_d_abord", titre=titre)
    if entree.is_redirect:
        entree = entree.get_redirect_entry()
    texte = _en_texte(bytes(entree.get_item().content).decode("utf-8", "replace"))
    debut = max(0, int(debut or 0))
    morceau = texte[debut:debut + TRANCHE]
    suite = (tr("mcp_wikipedia.suite_de_l_article_rappelle", v1=debut + TRANCHE, v2=len(texte))) if debut + TRANCHE < len(texte) else tr("mcp_wikipedia.fin_de_l_article")
    return tr("mcp_wikipedia.wikipedia_hors_ligne", v1=entree.title, morceau=morceau, suite=suite)


if __name__ == "__main__":
    serveur.run()
