"""MCP competences d'Agent Local : l'agent lit, cree et ameliore ses fiches de savoir-faire.

Libres : lister_competences, lire_competence, creer_competence, ameliorer_competence.
Sur autorisation : supprimer_competence (la fiche part dans la corbeille du classeur).
"""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

import competences
from langue import t as tr

serveur = FastMCP("competences")
LECTURE = ToolAnnotations(readOnlyHint=True)


def _assembler(quand, etapes, pieges):
    texte = f"## Quand l'utiliser\n{quand.strip()}\n\n## Etapes\n"
    texte += "\n".join(f"{i}. {e.strip()}" for i, e in enumerate(etapes, 1) if str(e).strip())
    if pieges:
        texte += "\n\n## Pieges a eviter\n" + "\n".join(f"- {p.strip()}" for p in pieges if str(p).strip())
    return texte


@serveur.tool(annotations=LECTURE, description=tr("outil.competences.lister_competences"))
def lister_competences() -> str:
    fiches = competences.lister()
    if not fiches:
        return tr("mcp_competences.aucune_competence_pour_l_instant")
    return "\n".join(f"- {f['nom']} : {f['description']}" for f in fiches)


@serveur.tool(annotations=LECTURE, description=tr("outil.competences.lire_competence"))
def lire_competence(nom: str) -> str:
    f = competences.lire(nom)
    return f"# {f['nom']}\n{f['description']}\n\n{f['contenu']}" if f else tr("mcp_competences.aucune_competence_nommee", nom=nom)


@serveur.tool(description=tr("outil.competences.creer_competence"))
def creer_competence(nom: str, description: str, quand: str, etapes: list[str], pieges: list[str] = []) -> str:
    existante = competences.lire(nom)
    if existante:
        return tr("mcp_competences.la_competence_existe_deja_utilise", v1=existante['nom'])
    try:
        n, _ = competences.ecrire(nom, description, _assembler(quand, etapes, pieges))
    except ValueError as e:
        return tr("commun.erreur_deux_points") + f"{e}"
    return f"Competence '{n}' creee."


@serveur.tool(description=tr("outil.competences.ameliorer_competence"))
def ameliorer_competence(nom: str, description: str, quand: str, etapes: list[str], pieges: list[str] = []) -> str:
    if not competences.lire(nom):
        return tr("mcp_competences.aucune_competence_nommee_utilise_creer", nom=nom)
    n, _ = competences.ecrire(nom, description, _assembler(quand, etapes, pieges))
    return f"Competence '{n}' amelioree."


@serveur.tool(description=tr("outil.competences.supprimer_competence"))
def supprimer_competence(nom: str) -> str:
    return f"Competence '{nom}' retiree (corbeille)." if competences.supprimer(nom) else tr("mcp_competences.aucune_competence_nommee_2", nom=nom)


if __name__ == "__main__":
    serveur.run()
