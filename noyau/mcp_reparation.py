"""MCP reparation d'Agent Local : la trousse de reparation (14/11/2026).
Une LISTE FERMEE de gestes de depannage, executes en administrateur par la tache planifiee \\AgentLocal\\Reparation
(script protege C:\\ProgramData\\AgentLocal\\Reparation\\scripts\\repartiteur.ps1, non modifiable sans les droits admin).
L'agent ne fait que CHOISIR un geste ; il ne peut pas faire executer une commande de son invention.
Un point de restauration est cree automatiquement avant les gestes risques.
Outils : gestes_disponibles, points_de_restauration, resultat_reparation (libres) ; lancer_reparation (sur accord).
"""
import json
import os
import random
import string
import subprocess
import time

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from langue import t as tr

serveur = FastMCP("reparation")
LECTURE = ToolAnnotations(readOnlyHint=True)
BASE = r"C:\ProgramData\AgentLocal\Reparation"
TACHE = r"\AgentLocal\Reparation"   # dossier AgentLocal du Planificateur de taches

GESTES = {
    "point_restauration": ("", tr("mcp_reparation.cree_un_point_de_restauration")),
    "reparer_windows": ("", tr("mcp_reparation.repare_les_fichiers_de_windows")),
    "verifier_disque": (tr("mcp_reparation.lettre_d_un_disque_interne"), tr("mcp_reparation.verifie_le_disque_sans_redemarrer")),
    "reparer_reseau_leger": ("", tr("mcp_reparation.vide_le_cache_dns_redemarre")),
    "reparer_reseau_complet": ("", tr("mcp_reparation.reinitialise_toute_la_pile_reseau")),
    "redemarrer_service": (tr("mcp_reparation.nom_du_service"), tr("mcp_reparation.redemarre_un_service_bloque_parmi")),
    "nettoyer_temp": ("", tr("mcp_reparation.supprime_les_fichiers_temporaires_de")),
    "sauvegarder_pilotes": ("", tr("mcp_reparation.sauvegarde_les_pilotes_graphique_et")),
    "reinstaller_pilote": (tr("mcp_reparation.graphique_ou_audio"), tr("mcp_reparation.reinstalle_le_pilote_depuis_la")),
    "restaurer_point": (tr("mcp_reparation.numero_du_point"), tr("mcp_reparation.ramene_windows_a_un_point")),
}
SANS_CIBLE_AUTORISEE = {g for g, (c, _) in GESTES.items() if not c}


def _lire(id_):
    chemin = os.path.join(BASE, "resultats", f"{id_}.txt")
    if not os.path.exists(chemin):
        return None
    with open(chemin, encoding="utf-8-sig", errors="replace") as f:
        return f.read().strip()


def _attendre(id_, secondes):
    fin = time.time() + secondes
    while True:
        texte = _lire(id_)
        if texte and "=== TERMINE ===" in texte:
            return texte
        if time.time() >= fin:
            return texte
        time.sleep(3)


def _demander(geste, cible, attente):
    demande = os.path.join(BASE, "demande", "demande.json")
    if os.path.exists(demande):
        return None, tr("mcp_reparation.une_reparation_est_deja_en")
    id_ = time.strftime("%Y%m%d-%H%M%S") + "-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    with open(demande, "w", encoding="utf-8") as f:
        json.dump({"id": id_, "geste": geste, "cible": cible}, f)
    subprocess.run(["schtasks", "/run", "/tn", TACHE], capture_output=True, timeout=20)
    return id_, _attendre(id_, attente)


@serveur.tool(annotations=LECTURE, description=tr("outil.reparation.gestes_disponibles"))
def gestes_disponibles() -> str:
    return "\n".join(f"- {g}" + (f" (cible : {c})" if c else "") + f" : {d}" for g, (c, d) in GESTES.items())


@serveur.tool(description=tr("outil.reparation.lancer_reparation"))
def lancer_reparation(geste: str, cible: str = "") -> str:
    if geste not in GESTES:
        return tr("mcp_reparation.geste_inconnu_gestes_possibles", geste=geste) + ", ".join(GESTES)
    if geste in SANS_CIBLE_AUTORISEE:
        cible = ""
    elif not cible:
        return tr("mcp_reparation.le_geste_demande_une_cible", geste=geste, v1=GESTES[geste][0])
    id_, texte = _demander(geste, cible.strip(), 120)
    if id_ is None:
        return texte
    if not texte:
        return (tr("mcp_reparation.demande_n_envoyee_mais_la", id_=id_))
    if "=== TERMINE ===" not in texte:
        return tr("mcp_reparation.en_cours_demande_n_appelle", id_=id_, texte=texte)
    return texte


@serveur.tool(annotations=LECTURE, description=tr("outil.reparation.resultat_reparation"))
def resultat_reparation(numero: str, attendre_secondes: int = 0) -> str:
    texte = _attendre(numero, max(0, min(int(attendre_secondes), 600)))
    if not texte:
        return tr("mcp_reparation.aucun_resultat_pour_la_demande", numero=numero)
    return texte if "=== TERMINE ===" in texte else tr("mcp_reparation.toujours_en_cours", texte=texte)


@serveur.tool(annotations=LECTURE, description=tr("outil.reparation.points_de_restauration"))
def points_de_restauration() -> str:
    id_, texte = _demander("lister_points", "", 60)
    if id_ is None:
        return texte
    return texte or tr("mcp_reparation.la_tache_reparationagent_n_a")


if __name__ == "__main__":
    serveur.run()
