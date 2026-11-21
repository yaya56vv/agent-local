"""MCP recherche d'Agent Local : la recherche web passe par ton SearXNG local (Docker, port 8080).

Aucune cle d'API, aucune requete envoyee a un service de recherche tiers en ton nom.
Outils (lecture seule, donc libres) : rechercher_web, lire_page.
"""
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from reseau import adresse_locale as _adresse_locale
from langue import t as tr


SEARXNG = "http://localhost:8080/search"
serveur = FastMCP("recherche")
LECTURE = ToolAnnotations(readOnlyHint=True)
DOCKER_ETEINT = (tr("mcp_recherche.erreur_le_moteur_de_recherche"))


@serveur.tool(annotations=LECTURE, description=tr("outil.recherche.rechercher_web"))
def rechercher_web(question: str, nombre: int = 6) -> str:
    try:
        r = httpx.get(SEARXNG, params={"q": question, "format": "json", "language": "fr"},
                      timeout=httpx.Timeout(45, connect=5))
        r.raise_for_status()
    except httpx.ConnectError:
        return DOCKER_ETEINT
    except httpx.TimeoutException:
        return (tr("mcp_recherche.erreur_searxng_tourne_mais_n"))
    except httpx.HTTPError as e:
        return tr("mcp_recherche.erreur_searxng_a_renvoye_une", e=e)
    resultats = r.json().get("results", [])[:max(1, min(nombre, 10))]
    if not resultats:
        return tr("mcp_recherche.aucun_resultat_essaie_une_formulation")
    return "\n\n".join(f"[{i}] {x.get('title', '').strip()}\nSource : {x.get('url', '')}\n"
                       f"{(x.get('content') or '').strip()[:400]}" for i, x in enumerate(resultats, 1))


class _Texte(HTMLParser):
    IGNORES = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"}

    def __init__(self):
        super().__init__()
        self.morceaux, self.profondeur_ignoree = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORES:
            self.profondeur_ignoree += 1
        elif tag in ("p", "br", "li", "h1", "h2", "h3", "h4", "tr", "div"):
            self.morceaux.append("\n")

    def handle_endtag(self, tag):
        if tag in self.IGNORES and self.profondeur_ignoree:
            self.profondeur_ignoree -= 1

    def handle_data(self, data):
        if not self.profondeur_ignoree:
            self.morceaux.append(data)


@serveur.tool(annotations=LECTURE, description=tr("outil.recherche.lire_page"))
def lire_page(adresse: str, longueur_max: int = 6000) -> str:
    if not adresse.startswith(("http://", "https://")):
        return tr("mcp_recherche.adresse_complete")
    if _adresse_locale(adresse):
        return (tr("mcp_recherche.refus_lire_page_ne_lit"))
    try:
        r = None
        for _ in range(5):  # redirections suivies a la main, chacune verifiee
            r = httpx.get(adresse, timeout=20, follow_redirects=False,
                          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AgentLocal/2"})
            if not r.is_redirect:
                break
            adresse = str(r.next_request.url) if r.next_request else urljoin(adresse, r.headers.get("location", ""))
            if _adresse_locale(adresse):
                return tr("mcp_recherche.refus_la_page_redirige_vers")
        r.raise_for_status()
    except httpx.HTTPError as e:
        return tr("mcp_recherche.erreur_page_inaccessible", e=e)
    if "html" not in r.headers.get("content-type", ""):
        return tr("mcp_recherche.erreur_ce_n_est_pas", v1=r.headers.get('content-type', 'type inconnu'))
    analyse = _Texte()
    analyse.feed(r.text)
    texte = unescape("".join(analyse.morceaux))
    texte = re.sub(r"[ \t\r\f\v]+", " ", texte)
    texte = re.sub(r"\n\s*\n+", "\n\n", texte).strip()
    limite = max(500, min(longueur_max, 20000))
    return texte[:limite] + (tr("mcp_recherche.texte_tronque") if len(texte) > limite else "")


if __name__ == "__main__":
    serveur.run()
