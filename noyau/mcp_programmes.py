"""MCP programmes d'Agent Local : ouvrir, voir et fermer les programmes de Windows.

Catalogue = raccourcis des menus Demarrer et des Bureaux (utilisateur + commun) :
tout ce qui est installe y figure, sans avoir a connaitre de chemin.
Outils : lister_programmes, programmes_ouverts (libres), lancer_programme (libre),
fermer_programme (sur autorisation : un programme ferme peut perdre un travail non enregistre).
"""
import json
import os
import subprocess
import time
import unicodedata
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from langue import t as tr

serveur = FastMCP("programmes")
LECTURE = ToolAnnotations(readOnlyHint=True)
PROFIL = Path.home()
SOURCES = [
    Path(os.environ.get("ProgramData", r"C:\ProgramData")) / tr("mcp_programmes.microsoft_windows_start_menu_programs"),
    Path(os.environ.get("APPDATA", str(PROFIL / "AppData/Roaming"))) / tr("mcp_programmes.microsoft_windows_start_menu_programs"),
    PROFIL / "Desktop",
    Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
]
IGNORES = ("desinstall", "uninstall", "aide", "help", "readme", "lisez", "site web", "website")


def _simple(texte):
    t = unicodedata.normalize("NFKD", texte.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _catalogue():
    vus = {}
    for dossier in SOURCES:
        if dossier.exists():
            for lnk in dossier.rglob("*.lnk"):
                nom = lnk.stem
                if not any(m in _simple(nom) for m in IGNORES):
                    vus.setdefault(_simple(nom), (nom, lnk))
    return sorted(vus.values(), key=lambda x: x[0].lower())


def _trouver(nom):
    cible = _simple(nom).strip()
    cat = _catalogue()
    exacts = [x for x in cat if _simple(x[0]) == cible]
    if exacts:
        return exacts[0], []
    proches = [x for x in cat if cible in _simple(x[0])]
    proches.sort(key=lambda x: len(x[0]))
    return (proches[0] if proches else None), [p[0] for p in proches[1:6]]


def _powershell(script):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=30)
    return r.stdout.strip()


@serveur.tool(annotations=LECTURE, description=tr("outil.programmes.lister_programmes"))
def lister_programmes(filtre: str = "") -> str:
    noms = [n for n, _ in _catalogue() if _simple(filtre) in _simple(n)]
    return f"{len(noms)} programme(s) :\n" + "\n".join(noms) if noms else tr("mcp_programmes.aucun_programme_ne_correspond")


@serveur.tool(annotations=LECTURE, description=tr("outil.programmes.programmes_ouverts"))
def programmes_ouverts(filtre: str = "") -> str:
    if filtre:
        f = filtre.replace("'", "")
        script = (f"Get-Process | Where-Object {{ $_.ProcessName -like '*{f}*' -or $_.MainWindowTitle -like '*{f}*' }} | "
                  "Select-Object ProcessName, Id, MainWindowTitle | ConvertTo-Json -Compress")
    else:
        script = ("Get-Process | Where-Object { $_.MainWindowTitle } | "
                  "Select-Object ProcessName, Id, MainWindowTitle | ConvertTo-Json -Compress")
    brut = _powershell(script)
    if not brut:
        return tr("mcp_programmes.rien_de_correspondant_n_est")
    liste = json.loads(brut)
    liste = liste if isinstance(liste, list) else [liste]
    return "\n".join(f"{p['ProcessName']} (PID {p['Id']}) {p.get('MainWindowTitle') or '[arriere-plan]'}" for p in liste)


@serveur.tool(description=tr("outil.programmes.lancer_programme"))
def lancer_programme(nom: str) -> str:
    trouve, autres = _trouver(nom)
    if not trouve:
        return tr("mcp_programmes.erreur_aucun_programme_ne_correspond", nom=nom)
    os.startfile(str(trouve[1]))
    suite = tr("mcp_programmes.autres_correspondances", v1=', '.join(autres)) if autres else ""
    return f"Lance : {trouve[0]}{suite}"


@serveur.tool(description=tr("outil.programmes.fermer_programme"))
def fermer_programme(nom_processus: str) -> str:
    f = nom_processus.replace("'", "")
    brut = _powershell(f"$p = Get-Process -Name '{f}' -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }}; "
                       "foreach($x in $p){ [void]$x.CloseMainWindow() }; ($p | Measure-Object).Count")
    n = int(brut or 0)
    return tr("mcp_programmes.demande_de_fermeture_envoyee_a", n=n, f=f) if n else tr("mcp_programmes.aucune_fenetre_ouverte_pour", f=f)


@serveur.tool(annotations=LECTURE, description=tr("outil.programmes.patienter"))
def patienter(secondes: int = 30) -> str:
    duree = max(5, min(int(secondes), 120))
    time.sleep(duree)
    return tr("mcp_programmes.secondes_ecoulees", duree=duree)


if __name__ == "__main__":
    serveur.run()
