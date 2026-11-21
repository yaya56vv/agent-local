"""Reglages d'Agent Local : la seule porte d'entree de la configuration.

Lit noyau/config.json (ecrit par l'assistant de premier lancement et la page Reglages ; a defaut, config.example.json),
remplace les marqueurs de chemins, ne garde que les modules actives et applique le niveau d'autonomie choisi.
Les cles et jetons ne sont JAMAIS dans config.json : ils vivent dans le dossier de secrets (SECRETS), hors du dossier
d'installation, lisible par le seul compte de l'utilisateur.

Marqueurs reconnus dans les chaines de config.json :
  {INSTALLATION}  dossier d'Agent Local          {NOYAU}    dossier noyau        {DONNEES}  noyau\\donnees
  {PYTHON}        Python de l'environnement      {SECRETS}  dossier de secrets   {SORTIE}   dossier de sortie
  %VARIABLE%      variables d'environnement Windows (%USERPROFILE%, %APPDATA%...)
"""
import json
import os
import sys
from pathlib import Path

NOYAU = Path(__file__).resolve().parent
INSTALLATION = NOYAU.parent
DONNEES = NOYAU / "donnees"
CONFIG = NOYAU / "config.json"
EXEMPLE = NOYAU / "config.example.json"
SECRETS = Path(os.environ.get("APPDATA") or Path.home()) / "AgentLocal" / "secrets"
PYTHON_VENV = NOYAU / ".venv" / "Scripts" / "python.exe"
SORTIE_PAR_DEFAUT = r"%USERPROFILE%\Documents\Agent Local"
DOSSIERS_PERSONNELS = [rf"%USERPROFILE%\{d}" for d in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music")]

# Regles communes aux trois niveaux : ce qui envoie des donnees a un tiers ou efface demande toujours l'accord.
_TOUJOURS = {
    "cloud__demander_au_cloud": "demander",
    "n8n__execute_workflow": "demander",
    "planificateur__supprimer_tache": "demander",
    "memoire__oublier": "demander",
    "terminal__executer_powershell": "demander",
    "terminal__mettre_a_la_corbeille": "demander",
    "terminal__executer_en_administrateur": "demander",
    "programmes__fermer_programme": "demander",
    "logiciels__installer_logiciel": "demander",
    "logiciels__mettre_a_jour_logiciel": "demander",
    "logiciels__desinstaller_logiciel": "demander",
    "competences__supprimer_competence": "demander",
    "hermes__confier_mission": "demander",
    "hermes__lancer_mission": "demander",
    "reparation__lancer_reparation": "demander",
    "memoire__retenir": "auto",
    # Windows-MCP : outils qui ne font que regarder ou attendre
    "windows__Snapshot": "auto", "windows__Screenshot": "auto", "windows__Wait": "auto", "windows__WaitFor": "auto",
    "windows__DisplayInventory": "auto", "windows__Scroll": "auto", "windows__Move": "auto",
    "windows__Notification": "auto",
    # Windows-MCP : tries mode par mode dans agent.py (garde-fou 10) : lecture libre, modification sur accord
    "windows__FileSystem": "auto", "windows__Registry": "auto", "windows__Clipboard": "auto", "windows__Process": "auto",
    # Navigateur : se deplacer et lire est libre ; cliquer et taper dependent du niveau
    "navigateur__browser_navigate": "auto", "navigateur__browser_navigate_back": "auto",
    "navigateur__browser_tabs": "auto", "navigateur__browser_wait_for": "auto", "navigateur__browser_resize": "auto",
}

NIVEAUX = {
    # Prudent (par defaut) : il lit librement ; il demande avant de modifier, de cliquer pour l'utilisateur ou
    # d'envoyer quoi que ce soit.
    "prudent": {
        "serveurs_libres": [],
        "dossiers_personnels": ["{SORTIE}"],
        "suppression_windows": "interdit",
        "taches_planifiees_lecture_seule": True,
        "regles": {
            "windows__PowerShell": "interdit",   # doublon de terminal__executer_powershell
            "windows__Scrape": "interdit",       # doublon de recherche__lire_page
            "fichiers__write_file": "demander", "fichiers__edit_file": "demander",
            "fichiers__create_directory": "demander", "fichiers__move_file": "demander",
            "programmes__lancer_programme": "demander",
            "competences__creer_competence": "demander", "competences__ameliorer_competence": "demander",
        },
    },
    # Equilibre : il ecrit seul dans son dossier de sortie et pilote le navigateur ; il demande pour le reste.
    "equilibre": {
        "serveurs_libres": ["navigateur"],
        "dossiers_personnels": ["{SORTIE}"],
        "suppression_windows": "corbeille",
        "taches_planifiees_lecture_seule": True,
        "regles": {
            "fichiers__write_file": "auto", "fichiers__edit_file": "auto",
            "fichiers__create_directory": "auto", "fichiers__move_file": "auto",
            "programmes__lancer_programme": "demander",
            "competences__creer_competence": "demander", "competences__ameliorer_competence": "demander",
        },
    },
    # Autonome : il agit seul dans les dossiers personnels et les logiciels ; il demande pour supprimer, agir en
    # administrateur ou envoyer des donnees.
    "autonome": {
        "serveurs_libres": ["navigateur", "windows"],
        "dossiers_personnels": DOSSIERS_PERSONNELS,
        "suppression_windows": "corbeille",
        "taches_planifiees_lecture_seule": False,
        "regles": {
            "fichiers__write_file": "auto", "fichiers__edit_file": "auto",
            "fichiers__create_directory": "auto", "fichiers__move_file": "auto",
            "programmes__lancer_programme": "auto",
            "competences__creer_competence": "auto", "competences__ameliorer_competence": "auto",
        },
    },
}


def brut():
    """La configuration telle qu'elle est ecrite (pour la page Reglages et l'assistant)."""
    chemin = CONFIG if CONFIG.exists() else EXEMPLE
    return json.loads(chemin.read_text(encoding="utf-8"))


def enregistrer(conf):
    """Ecrit config.json (page Reglages, assistant). Jamais de secret ici : voir enregistrer_secret."""
    temporaire = CONFIG.with_suffix(".json.tmp")
    temporaire.write_text(json.dumps(conf, ensure_ascii=False, indent=2), encoding="utf-8")
    temporaire.replace(CONFIG)


def _developper(valeur, marques):
    if isinstance(valeur, str):
        for cle, remplacement in marques.items():
            valeur = valeur.replace(cle, remplacement)
        return os.path.expandvars(valeur)
    if isinstance(valeur, list):
        return [_developper(v, marques) for v in valeur]
    if isinstance(valeur, dict):
        return {k: _developper(v, marques) for k, v in valeur.items()}
    return valeur


_PROGRAMDATA = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
_PROGRAMFILES = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
OUTILS_ADMIN = {   # module -> fichier ecrit par son script d'installation (dossiers proteges, lisibles par tous)
    "sante": _PROGRAMFILES / "AgentLocal" / "Outils" / "lancer_autoruns.ps1",
    "reparation": _PROGRAMDATA / "AgentLocal" / "Reparation" / "scripts" / "repartiteur.ps1",
}


def charger() -> dict:
    """Configuration prete a l'emploi : chemins developpes, modules filtres, niveau d'autonomie applique."""
    conf = brut()
    utilisateur = conf.setdefault("utilisateur", {})
    sortie = os.path.expandvars(utilisateur.get("dossier_sortie") or SORTIE_PAR_DEFAUT)
    utilisateur["dossier_sortie"] = sortie
    marques = {"{INSTALLATION}": str(INSTALLATION), "{NOYAU}": str(NOYAU), "{DONNEES}": str(DONNEES),
               "{SECRETS}": str(SECRETS), "{SORTIE}": sortie,
               "{PYTHON}": str(PYTHON_VENV if PYTHON_VENV.exists() else Path(sys.executable))}
    modules = dict(conf.get("modules", {}))
    # Outils administrateur : installes = actifs. Leur installation passe par un script administrateur qui ne peut pas
    # ecrire dans votre config.json, et la page Modules n'a pas de case pour eux (test du 21/11/2026 : MCP absents).
    for module, temoin in OUTILS_ADMIN.items():
        if temoin.exists():
            modules[module] = True
    conf["mcp_servers"] = {nom: serveur for nom, serveur in conf.get("mcp_servers", {}).items()
                           if "module" not in serveur or modules.get(serveur["module"]) is True}
    auth = conf.setdefault("autorisations", {})
    niveau = NIVEAUX.get(auth.get("mode"), NIVEAUX["prudent"])
    auth["mode"] = next(n for n, v in NIVEAUX.items() if v is niveau)
    # Regles ecrites dans config.json (interdits de la messagerie, de n8n...) : elles l'emportent sur le niveau.
    auth["regles"] = {**_TOUJOURS, **niveau["regles"], **auth.get("regles", {})}
    for cle in ("serveurs_libres", "dossiers_personnels", "suppression_windows", "taches_planifiees_lecture_seule"):
        auth[cle] = niveau[cle]
    auth.setdefault("zones_interdites", ["{INSTALLATION}"])
    return {cle: _developper(valeur, marques) for cle, valeur in conf.items()}


def zones_interdites():
    return charger()["autorisations"]["zones_interdites"]


def chemin_secret(nom):
    """Chemin d'un fichier du dossier de secrets (ex. chemin_secret("openrouter.env"))."""
    return SECRETS / nom


def lire_env(nom):
    """Lit un fichier CLE=valeur du dossier de secrets ; {} s'il n'existe pas."""
    valeurs = {}
    chemin = chemin_secret(nom)
    if chemin.exists():
        for ligne in chemin.read_text(encoding="utf-8").splitlines():
            if "=" in ligne and not ligne.lstrip().startswith("#"):
                cle, valeur = ligne.split("=", 1)
                valeurs[cle.strip()] = valeur.strip().strip('"')
    return valeurs


def enregistrer_secret(nom, contenu):
    """Ecrit un secret dans SECRETS, dossier reserve au compte de l'utilisateur (heritage coupe par icacls)."""
    neuf = not SECRETS.exists()
    SECRETS.mkdir(parents=True, exist_ok=True)
    if neuf and os.name == "nt":
        import subprocess
        utilisateur = os.environ.get("USERNAME", "")
        subprocess.run(["icacls", str(SECRETS), "/inheritance:r", "/grant:r", f"{utilisateur}:(OI)(CI)F",
                        "*S-1-5-18:(OI)(CI)F"], capture_output=True)
    chemin = chemin_secret(nom)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin
