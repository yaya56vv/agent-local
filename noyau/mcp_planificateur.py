"""MCP planificateur d'Agent Local : programmer des taches qui se lancent toutes seules.

Sur autorisation : planifier_tache (une tache programmee agit plus tard sans surveillance : l'utilisateur valide).
Libres : lister_taches, supprimer_tache.
"""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

import planificateur
from langue import t as tr

serveur = FastMCP("planificateur")
LECTURE = ToolAnnotations(readOnlyHint=True)


@serveur.tool(description=tr("outil.planificateur.planifier_tache"))
def planifier_tache(titre: str, consigne: str, rythme: str, heure: str = "", jour: str = "",
                    toutes_les_minutes: int = 0, date: str = "") -> str:
    try:
        id_t, prochaine = planificateur.ajouter(titre, consigne, rythme, heure or None, jour or None,
                                                toutes_les_minutes or None, date or None)
    except (ValueError, TypeError) as e:
        return tr("commun.erreur_deux_points") + f"{e}"
    return (tr("mcp_planificateur.tache_programmee_premiere_execution", id_t=id_t, titre=titre, v1=planificateur.JOURS[prochaine.weekday()], prochaine=prochaine))


@serveur.tool(annotations=LECTURE, description=tr("outil.planificateur.lister_taches"))
def lister_taches() -> str:
    taches = planificateur.lister()
    if not taches:
        return tr("mcp_planificateur.aucune_tache_programmee")
    return "\n".join(f"[{t['id']}] {t['titre']} : {t['rythme_lisible']} (prochaine : {t['prochaine']}) -> {t['consigne']}"
                     for t in taches)


@serveur.tool(description=tr("outil.planificateur.supprimer_tache"))
def supprimer_tache(id_tache: int) -> str:
    titre = planificateur.supprimer(id_tache)
    return f"Tache {id_tache} '{titre}' retiree." if titre else tr("mcp_planificateur.aucune_tache_active_numero", id_tache=id_tache)


if __name__ == "__main__":
    serveur.run()
