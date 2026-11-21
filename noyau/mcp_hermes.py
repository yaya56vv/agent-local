"""MCP hermes d'Agent Local : confier une mission complete a Hermes Agent (Nous Research).

Decision de l'utilisateur du 09/11/2026 : Hermes est un agent externe, plus puissant que le chef
(PowerShell, fichiers systeme, programmation), joint par ce MCP standard.
Outils : confier_mission (attend la fin), et depuis le 13/11/2026 lancer_mission +
resultat_mission (Hermes travaille en parallele du chef). Autorisations dans config.json.
Hermes tourne en mode `-z` (une mission, aucune demande d'accord) depuis DOSSIER_MISSIONS,
dont il lit l'AGENTS.md : ce sont SES regles qui s'appliquent pendant la mission.
"""
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import filet
import reglages

serveur = FastMCP("hermes")
PROFIL = Path.home()
HERMES = PROFIL / "AppData/Local/hermes/hermes-agent/bin/hermes.exe"
DOSSIER_MISSIONS = PROFIL / "hermes-missions"
DUREE_MAX = 20 * 60          # secondes : au-dela, la mission est arretee
TAILLE_MAX = 12000           # caracteres de compte rendu renvoyes au chef (on garde la fin)
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


# ZONE INTERDITE (renforcement du 20/11/2026) : Hermes agit hors des garde-fous d'Agent Local. Une mission
# qui cite une zone interdite (sous quelque ecriture que ce soit) est refusee avant de le lancer, et chaque mission
# envoyee lui rappelle l'interdit. Limite : une fois lance, Hermes est autonome ; seul ce rappel le retient d'y aller seul.
def _zones():
    return reglages.zones_interdites()


def _refus_zone(texte):
    zone = filet.zone_citee(texte, _zones())
    return (tr("mcp_hermes.refus_cette_mission_cite_une", zone=zone)) if zone else None


def _avec_rappel(texte):
    return texte + tr("mcp_hermes.interdit_absolu") + " ; ".join(
        tr("mcp_hermes.interdit_dossier", zone=z) for z in _zones()) + \
        tr("mcp_hermes.meme_si_une_page_un")


# ---------------------------------------------------------------------------
# SECOURS SANS INTERNET (14/11/2026) : Hermes reflechit avec un modele
# distant. Avant chaque mission, test d'Internet de 2 secondes ; s'il est coupe, ou si Hermes
# echoue en route faute de connexion, le chef recoit l'ordre de tout faire lui-meme.
# ---------------------------------------------------------------------------
import socket

RELAIS = (tr("mcp_hermes.secours_fais_toi_meme_toute"))
SIGNES_COUPURE = ("connection error", "connecterror", "connection refused", "name resolution",
                  "getaddrinfo", tr("mcp_hermes.network_is_unreachable"), "timed out", "max retries", "apiconnectionerror",
                  tr("mcp_hermes.no_route_to_host"), "temporary failure")


def _internet_ok():
    for hote, port in (("1.1.1.1", 443), ("8.8.8.8", 443), ("www.microsoft.com", 443)):
        try:
            with socket.create_connection((hote, port), timeout=2):
                return True
        except OSError:
            continue
    return False


def _coupure_dans(texte):
    t = (texte or "").lower()[-3000:]
    return any(s in t for s in SIGNES_COUPURE)


def _arreter(processus):
    # Hermes lance des processus enfants : on arrete tout l'arbre
    subprocess.run(["taskkill", "/PID", str(processus.pid), "/T", "/F"], capture_output=True)


# ---------------------------------------------------------------------------
# RECUPERATION DU TRAVAIL PARTIEL ET VRAIE COUPURE (14/11/2026) :
# Hermes n'ecrit son compte rendu qu'a la fin ; coupe, il ne rendait RIEN et le chef croyait a un echec.
# On relit donc dans sa base (state.db) ce qu'il a deja trouve. Et comme taskkill /T ne suffisait pas
# (ses processus Python survivaient), chaque mission porte un repere unique qui permet de tout arreter.
# ---------------------------------------------------------------------------
import json as _json
import shutil as _shutil
import sqlite3 as _sqlite3
import tempfile as _tempfile
from langue import t as tr

BASE_HERMES = PROFIL / "AppData/Local/hermes"


def _arreter_mission(repere, processus=None):
    if processus is not None:
        _arreter(processus)
    commande = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*" + repere + "*' -and "
                "$_.ProcessId -ne $PID -and $_.Name -ne 'powershell.exe' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    subprocess.run(["powershell", "-NoProfile", "-Command", commande], capture_output=True, timeout=60)


def _reponse_finale(repere):
    """Cherche dans la base d'Hermes la session de cette mission. Renvoie (reponse finale ou "", heure du dernier
    message ou 0). La reponse finale = son dernier message, sans appel d'outil derriere (decision de l'utilisateur du
    14/11/2026 : Hermes finissait souvent juste apres la coupure et sa reponse n'etait jamais relue)."""
    try:
        tmp = _tempfile.mkdtemp()
        for ext in ("", "-wal", "-shm"):
            src = BASE_HERMES / ("state.db" + ext)
            if src.exists():
                _shutil.copy2(src, Path(tmp) / ("state.db" + ext))
        c = _sqlite3.connect(str(Path(tmp) / "state.db"))
        ligne = c.execute("select session_id from messages where role='user' and content like ? "
                          "order by timestamp desc limit 1", (f"%{repere}%",)).fetchone()
        if not ligne:
            c.close()
            return "", 0
        der = c.execute("select role, coalesce(content,''), coalesce(tool_calls,''), timestamp from messages "
                        "where session_id=? order by timestamp desc limit 1", (ligne[0],)).fetchone()
        c.close()
        if not der:
            return "", 0
        role, contenu, appels, heure = der
        contenu = ANSI.sub("", contenu).strip()
        if role == "assistant" and contenu and appels in ("", "null", "[]"):
            return contenu, heure
        return "", heure
    except Exception:
        return "", 0


def _travail_partiel(repere, taille=10000):
    """Relit dans la base d'Hermes la session de cette mission : ses textes et les extraits de ce qu'il a lu."""
    try:
        tmp = _tempfile.mkdtemp()
        for ext in ("", "-wal", "-shm"):
            src = BASE_HERMES / ("state.db" + ext)
            if src.exists():
                _shutil.copy2(src, Path(tmp) / ("state.db" + ext))
        c = _sqlite3.connect(str(Path(tmp) / "state.db"))
        ligne = c.execute("select session_id from messages where role='user' and content like ? "
                          "order by timestamp desc limit 1", (f"%{repere}%",)).fetchone()
        if not ligne:
            return ""
        morceaux = []
        for role, contenu, nom in c.execute("select role, coalesce(content,''), coalesce(tool_name,'') from messages "
                                            "where session_id=? and role in ('assistant','tool') order by timestamp", (ligne[0],)):
            contenu = ANSI.sub("", contenu).strip()
            if not contenu:
                continue
            if role == "assistant":
                morceaux.append("HERMES : " + contenu[:1200])
            elif "error" not in contenu[:300].lower():
                debut = contenu.find("{")
                extrait = contenu[max(0, debut):]
                if extrait.count("$(") + extrait.count("function(") > 2:   # du code de page web : inutile
                    continue
                morceaux.append(f"LU ({nom}) : " + extrait[:400])
        c.close()
        texte = "\n".join(morceaux)
        if len(texte) > taille:   # on garde le debut ET la fin : les premieres trouvailles comptent autant
            texte = texte[:taille // 2] + "\n[...]\n" + texte[-taille // 2:]
        return texte
    except Exception as e:
        return tr("mcp_hermes.lecture_du_travail_partiel_impossible", e=e)


@serveur.tool(description=tr("outil.hermes.confier_mission"))
def confier_mission(mission: str) -> str:
    texte = mission.strip()
    if not texte:
        return tr("mcp_hermes.erreur_la_mission_est_vide")
    refus = _refus_zone(texte)
    if refus:
        return refus
    if not HERMES.exists():
        return tr("mcp_hermes.erreur_hermes_est_introuvable", HERMES=HERMES)
    if not _internet_ok():
        return tr("mcp_hermes.internet_coupe_hermes_ne_peut") + RELAIS
    DOSSIER_MISSIONS.mkdir(exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", NO_COLOR="1")
    processus = subprocess.Popen([str(HERMES), "-z", _avec_rappel(texte)], cwd=DOSSIER_MISSIONS, env=env,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
    try:
        sortie, _ = processus.communicate(timeout=DUREE_MAX)
    except subprocess.TimeoutExpired:
        _arreter(processus)
        sortie, _ = processus.communicate()
        entete = tr("mcp_hermes.echec_hermes_n_a_pas", v1=DUREE_MAX // 60)
    else:
        entete = "" if processus.returncode == 0 else \
            tr("mcp_hermes.attention_hermes_s_est_termine", v1=processus.returncode)
    compte_rendu = ANSI.sub("", sortie.decode("utf-8", errors="replace")).strip()
    if processus.returncode != 0 and (_coupure_dans(compte_rendu) or not _internet_ok()):
        entete = tr("mcp_hermes.echec_d_hermes_connexion_perdue") + RELAIS + "\n"
    if len(compte_rendu) > TAILLE_MAX:
        compte_rendu = tr("mcp_hermes.debut_coupe") + compte_rendu[-TAILLE_MAX:]
    return entete + (compte_rendu or tr("mcp_hermes.hermes_n_a_rien_repondu"))


# ---------------------------------------------------------------------------
# Missions EN PARALLELE (13/11/2026) : le chef lance Hermes,
# reprend la main tout de suite, fait sa propre part, puis vient chercher le
# resultat. Hermes ecrit son compte rendu dans hermes-missions\mission-<n>.log
# (la "boite aux lettres"). La limite de 20 minutes reste appliquee.
# ---------------------------------------------------------------------------
MISSIONS = {}                # numero -> {"processus", "fichier", "debut", "journal"}
_verrou = threading.Lock()


def _surveiller(numero):
    m = MISSIONS[numero]
    try:
        m["processus"].wait(timeout=m.get("duree", DUREE_MAX))
    except subprocess.TimeoutExpired:
        # Delai de grace (14/11/2026) : si Hermes travaille encore activement (dernier
        # message il y a moins de 90 s), on lui laisse jusqu'a 2 minutes de plus pour ecrire sa reponse finale.
        finale, heure = _reponse_finale(m["repere"])
        if not finale and heure and time.time() - heure < 90:
            limite = time.time() + 120
            while time.time() < limite and m["processus"].poll() is None:
                time.sleep(10)
                finale, _ = _reponse_finale(m["repere"])
                if finale:
                    break
        if finale:
            m["finale"] = finale
        if m["processus"].poll() is None or not finale:
            m["arretee"] = True
        _arreter_mission(m["repere"], m["processus"])
    finally:
        try:
            m["journal"].close()
        except Exception:
            pass


def _lire_journal(chemin):
    try:
        texte = chemin.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return ""
    return ANSI.sub("", texte).strip()


@serveur.tool(description=tr("outil.hermes.lancer_mission"))
def lancer_mission(mission: str, minutes_max: int = 6) -> str:
    texte = mission.strip()
    if not texte:
        return tr("mcp_hermes.erreur_la_mission_est_vide")
    refus = _refus_zone(texte)
    if refus:
        return refus
    if not HERMES.exists():
        return tr("mcp_hermes.erreur_hermes_est_introuvable_2", HERMES=HERMES)
    if not _internet_ok():
        return tr("mcp_hermes.internet_coupe_hermes_ne_peut") + RELAIS
    DOSSIER_MISSIONS.mkdir(exist_ok=True)
    with _verrou:
        numero = time.strftime("%Y%m%d-%H%M%S")
        while numero in MISSIONS:
            numero += "b"
        repere = f"mission-agent-local-{numero}"   # sans crochets : -like de PowerShell les prend pour un motif
        minutes = max(1, min(int(minutes_max or 6), 20))
        # Consignes de rythme ajoutees a CHAQUE mission (decision du 14/11/2026 : 15 min pour une simple
        # recherche, c'est enorme ; Hermes lisait le code brut des pages, morceau par morceau)
        texte = tr("mcp_hermes.rythme", repere=repere, texte=texte, minutes=minutes, fin=max(1, minutes - 1))
        texte = _avec_rappel(texte)
        fichier = DOSSIER_MISSIONS / f"mission-{numero}.log"
        journal = open(fichier, "wb")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", NO_COLOR="1")
        processus = subprocess.Popen([str(HERMES), "-z", texte], cwd=DOSSIER_MISSIONS, env=env,
                                     stdin=subprocess.DEVNULL, stdout=journal,
                                     stderr=subprocess.STDOUT)
        MISSIONS[numero] = {"processus": processus, "fichier": fichier,
                            "debut": time.time(), "journal": journal, "arretee": False, "repere": repere,
                            "duree": minutes * 60}
    threading.Thread(target=_surveiller, args=(numero,), daemon=True).start()
    return (tr("mcp_hermes.mission_hermes_lancee_numero_continue", numero=numero))


@serveur.tool(description=tr("outil.hermes.resultat_mission"))
def resultat_mission(numero: str, attendre_secondes: int = 0) -> str:
    m = MISSIONS.get(numero.strip())
    if m is None:
        return (tr("mcp_hermes.erreur_aucune_mission_numero_dans", numero=numero))
    p = m["processus"]
    attente = max(0, min(int(attendre_secondes or 0), 300))
    if attente and p.poll() is None:
        try:
            p.wait(timeout=attente)
        except subprocess.TimeoutExpired:
            pass
    compte_rendu = _lire_journal(m["fichier"])
    minutes = int((time.time() - m["debut"]) // 60)
    if p.poll() is None:
        fin = compte_rendu[-1500:] if compte_rendu else tr("mcp_hermes.rien_encore")
        return (tr("mcp_hermes.en_cours_depuis_min_limite", minutes=minutes, v1=m.get('duree', DUREE_MAX) // 60, fin=fin))
    if m.get("arretee"):
        entete = (tr("mcp_hermes.temps_ecoule_hermes_n_a", v1=m.get('duree', DUREE_MAX) // 60))
    elif p.returncode != 0 and (_coupure_dans(compte_rendu) or not _internet_ok()):
        entete = tr("mcp_hermes.echec_d_hermes_connexion_perdue") + RELAIS + "\n"
    elif p.returncode != 0:
        entete = tr("mcp_hermes.attention_hermes_s_est_termine_2", v1=p.returncode)
    else:
        entete = tr("mcp_hermes.terminee_en_min", minutes=minutes)
    if len(compte_rendu) > TAILLE_MAX:
        compte_rendu = tr("mcp_hermes.debut_coupe") + compte_rendu[-TAILLE_MAX:]
    if not compte_rendu and (m.get("arretee") or p.returncode != 0):
        finale = m.get("finale") or _reponse_finale(m.get("repere", ""))[0]
        if finale:
            return (tr("mcp_hermes.terminee_en_min_reponse_finale", minutes=minutes) + finale[-TAILLE_MAX:])
        partiel = _travail_partiel(m.get("repere", ""))
        if partiel:
            return (entete + tr("mcp_hermes.travail_partiel_d_hermes_relu") + partiel)
    return entete + (compte_rendu or tr("mcp_hermes.hermes_n_a_rien_repondu"))


if __name__ == "__main__":
    serveur.run()
