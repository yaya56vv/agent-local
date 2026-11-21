"""MCP logiciels d'Agent Local : chercher, installer, mettre a jour, desinstaller des programmes.

Tout passe par winget (gestionnaire officiel de Windows), source "winget" uniquement : chaque logiciel
vient du site de son editeur et son empreinte est verifiee. Jamais de .exe telecharge au hasard.
Outils libres : chercher_logiciel, fiche_logiciel, logiciels_installes.
Sur autorisation (par defaut) : installer_logiciel, mettre_a_jour_logiciel, desinstaller_logiciel.
"""
import re
import subprocess

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from langue import t as tr

serveur = FastMCP("logiciels")
LECTURE = ToolAnnotations(readOnlyHint=True)
COMMUN = ["--source", "winget", "--accept-source-agreements", "--disable-interactivity"]
ID_VALIDE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_+]{1,120}$")


def _winget(arguments, delai=120):
    try:
        r = subprocess.run(["winget", *arguments], capture_output=True, timeout=delai)
    except subprocess.TimeoutExpired:
        return 1, tr("mcp_logiciels.winget_n_a_pas_termine", delai=delai)
    sortie = r.stdout.decode("utf-8", errors="replace")
    # retire l'animation de progression de winget (rotation - \ | /, barres de blocs, compteurs d'octets)
    lignes = [l.split("\r")[-1].rstrip() for l in sortie.splitlines()]
    lignes = [l for l in lignes if l.strip() and not re.fullmatch(r"\s*[-\\|/]\s*", l)
              and "█" not in l and "▒" not in l and not re.match(r"^\s*[\d.,]+\s*[KMG]?[Bo]\s*/", l)]
    return r.returncode, "\n".join(lignes)


def _tableau(texte, limite=12):
    """Transforme le tableau texte de winget (Nom / ID / Version...) en lignes lisibles."""
    lignes = texte.splitlines()
    sep = next((i for i, l in enumerate(lignes) if set(l.strip()) == {"-"}), None)
    if sep is None or sep == 0:
        return texte
    entete = lignes[sep - 1]
    debuts = [m.start() for m in re.finditer(r"\S+", entete)]
    sortie = []
    for l in lignes[sep + 1:sep + 1 + limite]:
        cols = [l[a:b].strip() for a, b in zip(debuts, debuts[1:] + [None])]
        if len(cols) >= 3:
            sortie.append(f"{cols[0]}  |  identifiant : {cols[1]}  |  version : {cols[2]}")
    return "\n".join(sortie) or texte


def _verifier(identifiant):
    return None if ID_VALIDE.match(identifiant or "") else \
        tr("mcp_logiciels.erreur_identifiant_winget_invalide_utilise")


@serveur.tool(annotations=LECTURE, description=tr("outil.logiciels.chercher_logiciel"))
def chercher_logiciel(nom: str) -> str:
    code, texte = _winget(["search", "--name", nom, *COMMUN])
    if "No package found" in texte or "Aucun package" in texte or code != 0 and "---" not in texte:
        return tr("mcp_logiciels.aucun_logiciel_trouve_pour_essaie", nom=nom)
    return _tableau(texte)


@serveur.tool(annotations=LECTURE, description=tr("outil.logiciels.fiche_logiciel"))
def fiche_logiciel(identifiant: str) -> str:
    if (e := _verifier(identifiant)):
        return e
    return _winget(["show", "--id", identifiant, "--exact", *COMMUN])[1][:3000]


@serveur.tool(annotations=LECTURE, description=tr("outil.logiciels.logiciels_installes"))
def logiciels_installes(filtre: str = "") -> str:
    args = ["list", "--accept-source-agreements", "--disable-interactivity"] + (["--name", filtre] if filtre else [])
    return _tableau(_winget(args)[1], limite=40)


@serveur.tool(description=tr("outil.logiciels.installer_logiciel"))
def installer_logiciel(identifiant: str) -> str:
    if (e := _verifier(identifiant)):
        return e
    code, texte = _winget(["install", "--id", identifiant, "--exact", "--silent",
                           "--accept-package-agreements", *COMMUN], delai=1200)
    return (tr("mcp_logiciels.installation_reussie") if code == 0 else tr("mcp_logiciels.echec_de_l_installation_code", code=code)) + \
        "\n" + "\n".join(texte.splitlines()[-8:])


@serveur.tool(description=tr("outil.logiciels.mettre_a_jour_logiciel"))
def mettre_a_jour_logiciel(identifiant: str) -> str:
    if (e := _verifier(identifiant)):
        return e
    code, texte = _winget(["upgrade", "--id", identifiant, "--exact", "--silent",
                           "--accept-package-agreements", *COMMUN], delai=1200)
    return (tr("mcp_logiciels.mise_a_jour_reussie") if code == 0 else tr("mcp_logiciels.pas_de_mise_a_jour", code=code)) + \
        "\n" + "\n".join(texte.splitlines()[-8:])


@serveur.tool(description=tr("outil.logiciels.desinstaller_logiciel"))
def desinstaller_logiciel(identifiant: str) -> str:
    if (e := _verifier(identifiant)):
        return e
    code, texte = _winget(["uninstall", "--id", identifiant, "--exact", "--silent",
                           "--accept-source-agreements", "--disable-interactivity"], delai=900)
    return (tr("mcp_logiciels.desinstallation_reussie") if code == 0 else tr("mcp_logiciels.echec_de_la_desinstallation_code", code=code)) + \
        "\n" + "\n".join(texte.splitlines()[-8:])


if __name__ == "__main__":
    serveur.run()
