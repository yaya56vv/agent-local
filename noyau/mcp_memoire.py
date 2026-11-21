"""MCP memoire d'Agent Local : donne a l'agent l'acces a son carnet.

Outils : retenir, rechercher_souvenirs, lister_souvenirs (libres) ; oublier (sur autorisation).
"""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

import memoire
from langue import t as tr

serveur = FastMCP("memoire")
LECTURE = ToolAnnotations(readOnlyHint=True)


def _format(souvenirs):
    if not souvenirs:
        return tr("mcp_memoire.aucun_souvenir_trouve")
    return "\n".join(f"[{s['id']}] ({s['categorie']}{', essentiel' if s['essentiel'] else ''}) {s['texte']}"
                     for s in souvenirs)


@serveur.tool(description=tr("outil.memoire.retenir"))
def retenir(texte: str, categorie: str = "divers", essentiel: bool = False) -> str:
    id_s = memoire.retenir(texte, categorie, essentiel)
    return f"Souvenir {id_s} note : {texte}"


@serveur.tool(annotations=LECTURE, description=tr("outil.memoire.rechercher_souvenirs"))
def rechercher_souvenirs(question: str, limite: int = 8) -> str:
    return _format(memoire.rechercher(question, limite))


@serveur.tool(annotations=LECTURE, description=tr("outil.memoire.lister_souvenirs"))
def lister_souvenirs(categorie: str = "") -> str:
    return _format(memoire.lister(categorie or None))


@serveur.tool(description=tr("outil.memoire.oublier"))
def oublier(id_souvenir: int) -> str:
    texte = memoire.oublier(id_souvenir)
    return f"Souvenir {id_souvenir} efface : {texte}" if texte else tr("mcp_memoire.aucun_souvenir_numero", id_souvenir=id_souvenir)


if __name__ == "__main__":
    serveur.run()
