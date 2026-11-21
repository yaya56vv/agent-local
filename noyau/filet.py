"""Le filet de securite d'Agent Local (12/11/2026).

Avant chaque action qui modifie des fichiers, une copie de chaque fichier vise est rangee dans UN seul dossier
(donnees/copies), jamais a cote des fichiers de l'utilisateur. Le bouton « Annuler la derniere modification » remet les
fichiers dans leur etat d'avant ; un fichier que l'action a cree part a la Corbeille.
Regles : copies gardees 7 jours, fichiers de plus de 50 Mo jamais copies (l'agent demande alors l'accord de l'utilisateur),
dossier plafonne a 5 Go (les copies les plus anciennes partent d'abord). Nettoyage a chaque lancement.
"""
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from langue import t as tr

DOSSIER = Path(__file__).parent / "donnees" / "copies"
TAILLE_MAX_FICHIER = 50 * 2**20
TAILLE_MAX_DOSSIER = 5 * 2**30
JOURS_GARDES = 7


def chemins(valeur):
    """Les chaines des arguments qui ressemblent a un chemin Windows (casse d'origine conservee)."""
    if isinstance(valeur, str):
        if len(valeur) > 2 and "\n" not in valeur and (valeur[1:3] in (":\\", ":/") or valeur.startswith("\\\\")):
            yield os.path.abspath(valeur)
    elif isinstance(valeur, dict):
        for v in valeur.values():
            yield from chemins(v)
    elif isinstance(valeur, list):
        for v in valeur:
            yield from chemins(v)


def _nom_court(chemin):
    """Nom court Windows (8.3) d'un dossier, ex. C:\\Users\\NOM\\DOCUME~1\\AGENTL~1 ; "" s'il n'existe pas."""
    try:
        import ctypes
        tampon = ctypes.create_unicode_buffer(1024)
        return tampon.value if ctypes.windll.kernel32.GetShortPathNameW(str(chemin), tampon, 1024) else ""
    except Exception:
        return ""


def zone_citee(texte, zones):
    """La zone interdite citee dans un texte libre (commande PowerShell, mission d'Hermes), ou None (20/11/2026,
    renforcement du 20/11/2026). Reconnait les majuscules, / ou \\, les barres doublees, %USERPROFILE%, $env:USERPROFILE,
    $HOME, ~\\, le nom court Windows (PROJET~1) et le nom du dossier ecrit avec _ ou - au lieu de l'espace."""
    profil = os.environ.get("USERPROFILE", "").lower()
    t = str(texte or "").lower().replace("/", "\\")
    for forme in ("${env:userprofile}", "$env:userprofile", "%userprofile%", "${home}", "$home",
                  "%homedrive%%homepath%"):
        t = t.replace(forme, profil)
    t = t.replace("%homepath%", profil[2:])
    t = " ".join(t.replace("~\\", profil + "\\").split())   # ~\ en debut de chemin ; espaces repetes ramenes a un seul
    while "\\\\" in t:
        t = t.replace("\\\\", "\\")
    for z in zones:
        zone = os.path.normcase(os.path.abspath(z)).rstrip("\\")
        nom = os.path.basename(zone)
        formes = {zone, nom, nom.replace(" ", "_"), nom.replace(" ", "-")}
        court = _nom_court(zone).lower()
        if court:
            formes.add(court)
            formes.add("\\".join(court.split("\\")[-2:]))   # ex. docume~1\projet~1
        if any(f and f in t for f in formes):
            return z
    return None


def trop_gros(arguments):
    """Les fichiers vises de plus de 50 Mo : ils ne seront pas copies."""
    return [c for c in chemins(arguments) if os.path.isfile(c) and os.path.getsize(c) > TAILLE_MAX_FICHIER]


def copier_avant(id_appel, outil, arguments):
    """Copie les fichiers existants vises par l'action et note ceux qu'elle pourrait creer."""
    vus, notes = set(), []
    for c in chemins(arguments):
        if c.lower() in vus:
            continue
        vus.add(c.lower())
        if os.path.isfile(c):
            if os.path.getsize(c) <= TAILLE_MAX_FICHIER:
                notes.append({"chemin": c, "existait": True})
        elif not os.path.exists(c) and os.path.isdir(os.path.dirname(c)):
            notes.append({"chemin": c, "existait": False})
    if not notes:
        return
    dossier = DOSSIER / f"{datetime.now():%Y%m%d-%H%M%S}_{str(id_appel)[-8:]}"
    dossier.mkdir(parents=True, exist_ok=True)
    for i, n in enumerate(notes):
        if n["existait"]:
            n["copie"] = f"{i}_{os.path.basename(n['chemin'])}"
            shutil.copy2(n["chemin"], dossier / n["copie"])
    (dossier / "action.json").write_text(json.dumps(
        {"quand": datetime.now().isoformat(timespec="seconds"), "outil": outil, "fichiers": notes},
        ensure_ascii=False, indent=1), encoding="utf-8")


def _actions():
    """Les actions sauvegardees, la plus recente d'abord."""
    if not DOSSIER.is_dir():
        return []
    return sorted((d for d in DOSSIER.iterdir() if (d / "action.json").is_file()), key=lambda d: d.name, reverse=True)


def _decrire(dossier):
    action = json.loads((dossier / "action.json").read_text(encoding="utf-8"))
    fichiers = [f"{f['chemin']}{'' if f['existait'] else ' (cree par l action)'}" for f in action["fichiers"]]
    return {"quand": action["quand"], "outil": action["outil"], "fichiers": fichiers}


def derniere_action():
    actions = _actions()
    return _decrire(actions[0]) if actions else None


def _corbeille(chemin):
    commande = (tr("filet.add_type_assemblyname_microsoft_visualbasic"))
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", commande], timeout=30,
                   env={**os.environ, "FICHIER_A_JETER": chemin}, capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def annuler_derniere():
    """Remet les fichiers de la derniere action dans leur etat d'avant. Renvoie un compte rendu lisible."""
    actions = _actions()
    if not actions:
        return {"ok": False, "texte": tr("filet.aucune_modification_a_annuler_rien")}
    dossier = actions[0]
    action = json.loads((dossier / "action.json").read_text(encoding="utf-8"))
    faits = []
    for f in action["fichiers"]:
        if f["existait"]:
            os.makedirs(os.path.dirname(f["chemin"]), exist_ok=True)
            shutil.copy2(dossier / f["copie"], f["chemin"])
            faits.append(tr("filet.remis_comme_avant", v1=f['chemin']))
        elif os.path.isfile(f["chemin"]):
            _corbeille(f["chemin"])
            faits.append(tr("filet.envoye_a_la_corbeille_cree", v1=f['chemin']))
    shutil.rmtree(dossier, ignore_errors=True)
    return {"ok": True, "texte": tr("filet.action_annulee", v1=action['outil'], v2=action['quand']) +
                                 ("\n".join(faits) or tr("filet.aucun_fichier_a_remettre_deja"))}


def nettoyer():
    """Au lancement : retire les copies de plus de 7 jours, puis les plus anciennes au-dela de 5 Go."""
    limite = time.time() - JOURS_GARDES * 86400
    restantes = []
    for d in reversed(_actions()):   # de la plus ancienne a la plus recente
        if d.stat().st_mtime < limite:
            shutil.rmtree(d, ignore_errors=True)
        else:
            restantes.append((d, sum(f.stat().st_size for f in d.iterdir() if f.is_file())))
    total = sum(t for _, t in restantes)
    for d, taille in restantes:
        if total <= TAILLE_MAX_DOSSIER:
            break
        shutil.rmtree(d, ignore_errors=True)
        total -= taille
