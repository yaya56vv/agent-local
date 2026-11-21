"""Assistant de premier lancement et page Reglages d'Agent Local (cote noyau).

Expose a la fenetre (via app.py) : detection du materiel, paliers de modeles conseilles, telechargements verifies avec
progression, installation des composants externes (apres acceptation de leur licence), outils administrateur (UAC),
rubrique « Mes donnees », verification des mises a jour, test du modele.
Regles : rien n'est telecharge sans un clic de l'utilisateur ; uniquement depuis la source officielle (Hugging Face,
GitHub ggml-org, download.kiwix.org, PyPI, winget) ; chaque fichier est verifie (empreinte SHA-256 publiee) quand la
source en publie une ; les cles vont dans le dossier de secrets, jamais dans config.json.
"""
import asyncio
import base64
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import langue
import reglages
from langue import t as tr

INSTALLATION = reglages.INSTALLATION
MODELES = INSTALLATION / "modeles"
MOTEUR = INSTALLATION / "moteur"
VERSION = (INSTALLATION / "VERSION").read_text(encoding="utf-8").strip() if (INSTALLATION / "VERSION").exists() else "0.0.0"
SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ENTETES = {"User-Agent": "agent-local-installateur"}

# Paliers « Votre PC peut-il faire tourner Agent Local ? » (memes chiffres que le README).
# Tailles : mesurees sur Hugging Face (depots Unsloth). Memoire de conversation et verdicts : estimes, sauf mention.
PALIERS = [
    {"id": "24", "memoire_min": 22, "titre": tr("assistant.24_go_et_plus"), "verdict": "complet",
     "depot": "unsloth/Qwen3.8-27B-GGUF", "fichier": "Qwen3.8-27B-UD-Q4_K_M.gguf", "mmproj": "mmproj-F16.gguf",
     "nom": "Qwen3.8-27B (UD-Q4_K_M)", "taille_go": 16.6, "mmproj_go": 0.9, "contexte": 65536,
     "bien": tr("assistant.missions_longues_en_plusieurs_etapes"),
     "mal": tr("assistant.reponses_plus_lentes_qu_un")},
    {"id": "16", "memoire_min": 14, "titre": "16 Go", "verdict": "utilisable",
     "depot": "unsloth/Qwen3.5-9B-GGUF", "fichier": "Qwen3.5-9B-Q6_K.gguf", "mmproj": "mmproj-F16.gguf",
     "nom": "Qwen3.5-9B (Q6_K)", "taille_go": 7.5, "mmproj_go": 0.9, "contexte": 65536,
     "bien": tr("assistant.taches_courantes_fichiers_recherche_vision"),
     "mal": tr("assistant.se_trompe_plus_souvent_sur")},
    {"id": "12", "memoire_min": 10, "titre": "12 Go", "verdict": "limite",
     "depot": "unsloth/Qwen3.5-9B-GGUF", "fichier": "Qwen3.5-9B-Q4_K_M.gguf", "mmproj": "mmproj-F16.gguf",
     "nom": "Qwen3.5-9B (Q4_K_M)", "taille_go": 5.7, "mmproj_go": 0.9, "contexte": 65536,
     "bien": tr("assistant.questions_fichiers_recherches_simples"),
     "mal": tr("assistant.missions_en_plusieurs_etapes_peu")},
    {"id": "8", "memoire_min": 7, "titre": "8 Go", "verdict": "deconseille",
     "depot": "unsloth/Qwen3.5-4B-GGUF", "fichier": "Qwen3.5-4B-Q4_K_M.gguf", "mmproj": "mmproj-F16.gguf",
     "nom": "Qwen3.5-4B (Q4_K_M)", "taille_go": 2.7, "mmproj_go": 0.7, "contexte": 65536,
     "bien": tr("assistant.petites_questions_lecture_de_fichiers"),
     "mal": tr("assistant.choisit_souvent_mal_ses_outils")},
]
CONTEXTES = [65536, 131072, 262144]

# Composants externes que le depot ne distribue pas : installes depuis la source officielle apres acceptation.
COMPOSANTS = {
    "windows_mcp": {"nom": tr("assistant.windows_mcp_0_8_5"), "licence": "MIT",
                    "texte": tr("assistant.logiciel_libre_licence_mit_de"),
                    "lien": "https://github.com/CursorTouch/Windows-MCP", "taille_go": 0.1, "module": "windows"},
    "dictee": {"nom": tr("assistant.dictee_whisper_faster_whisper_modele"), "licence": tr("assistant.mit_bibliotheques_nvidia"),
               "texte": tr("assistant.faster_whisper_et_le_modele"),
               "lien": "https://github.com/SYSTRAN/faster-whisper", "taille_go": 4.5, "module": "dictee"},
    "xtts": {"nom": tr("assistant.voix_de_secours_hors_ligne"), "licence": tr("assistant.cpml_non_commercial"),
             "texte": tr("assistant.le_modele_xtts_v2_de"),
             "case": tr("assistant.usage_personnel_et_non_commercial"),
             "lien": "https://huggingface.co/coqui/XTTS-v2", "taille_go": 6.0, "module": "voix"},
    "wikipedia": {"nom": tr("assistant.wikipedia_en_francais_hors_ligne"), "licence": tr("assistant.cc_by_sa_4_0"),
                  "texte": tr("assistant.le_contenu_de_wikipedia_est"),
                  "lien": "https://download.kiwix.org/zim/wikipedia/", "module": "wikipedia",
                  # taille mesuree sur download.kiwix.org (fichiers sans images de 2026) : 12 Go en francais, 49 Go en anglais
                  "taille_go": {"fr": 12.0, "en": 49.0}.get(langue.code(), 20.0)},
    "docker": {"nom": tr("assistant.docker_desktop_searxng_recherche_web"), "licence": tr("assistant.docker_subscription_agpl_3_0"),
               "texte": tr("assistant.docker_desktop_est_gratuit_pour"),
               "lien": "https://www.docker.com/legal/docker-subscription-service-agreement/", "taille_go": 4.0,
               "module": "recherche"},
    "n8n": {"nom": tr("n8n.nom"), "licence": "Sustainable Use License", "texte": tr("n8n.licence_texte"),
            "case": tr("n8n.case"), "lien": "https://docs.n8n.io/sustainable-use-license/", "taille_go": 0.7,
            "module": "n8n"},
    "sante": {"nom": tr("assistant.sante_du_pc_autoruns_librehardwaremonitor"), "licence": tr("assistant.eula_microsoft_mpl_2_0"),
              "texte": tr("assistant.autoruns_est_un_logiciel_microsoft"),
              "lien": "https://learn.microsoft.com/sysinternals/license-terms", "taille_go": 0.1, "module": "sante",
              "admin": "installer_sante.ps1"},
    "reparation": {"nom": tr("assistant.trousse_de_reparation_gestes_administrateur"), "licence": tr("assistant.mit_agent_local"),
                   "texte": tr("assistant.aucun_logiciel_tiers_cree_une"),
                   "lien": "", "taille_go": 0.0, "module": "reparation", "admin": "installer_reparation.ps1"},
}

_travaux = {}          # identifiant -> {"etat", "fait", "total", "message"}
_verrou = threading.Lock()


# ---------------------------------------------------------------------------------------------------------------
# Detection
def _ram_go():
    class Etat(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    e = Etat(); e.dwLength = ctypes.sizeof(Etat)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(e))
    return round(e.ullTotalPhys / 2**30)


def cartes():
    """Toutes les cartes NVIDIA du PC : numero, UUID, nom, memoire totale et libre (Go), pilote."""
    try:
        sortie = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid,name,memory.total,memory.free,driver_version",
                                 "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=15,
                                creationflags=SANS_FENETRE).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    liste = []
    for ligne in sortie.strip().splitlines():
        champs = [c.strip() for c in ligne.split(",")]
        if len(champs) == 6:
            liste.append({"index": int(champs[0]), "uuid": champs[1], "nom": champs[2],
                          "memoire_go": round(int(champs[3]) / 1024, 1), "libre_go": round(int(champs[4]) / 1024, 1),
                          "pilote": champs[5]})
    return liste


def _fichier_local(chemin):
    """Vrai si le chemin designe un fichier present sur un disque local. Chemin reseau (UNC) ou relatif : ignore, sans
    toucher au reseau ; chemin mal forme : faux, sans jamais faire echouer la detection."""
    try:
        p = Path(str(chemin or ""))
        return bool(chemin) and p.is_absolute() and not str(p).startswith("\\\\") and p.is_file()
    except (OSError, TypeError, ValueError):
        return False


def palier_pour(memoire_go):
    return next((p for p in PALIERS if memoire_go >= p["memoire_min"]), None)


def detecter():
    """Ce que l'ecran 2 affiche : cartes, memoire vive, disque libre, palier conseille, ou refus honnete."""
    liste = cartes()
    principale = max(liste, key=lambda c: c["memoire_go"], default=None)
    lanceur = reglages.charger().get("lanceur", {})
    palier = palier_pour(principale["memoire_go"]) if principale else None
    if not principale:
        refus = (tr("assistant.aucune_carte_graphique_nvidia_n"))
    elif not palier:
        refus = (tr("assistant.votre_carte_graphique_a_go", v1=principale['nom'], v2=principale['memoire_go']))
    else:
        refus = ""
    return {"cartes": liste, "principale": principale, "ram_go": _ram_go(),
            "disque_libre_go": round(shutil.disk_usage(INSTALLATION).free / 2**30), "palier": palier,
            "paliers": PALIERS, "contextes": CONTEXTES, "refus": refus,
            # deja installe (assistant interrompu puis repris) : ne jamais faire retelecharger 17 Go pour rien
            "modele_present": _fichier_local(lanceur.get("modele")),
            "moteur_present": _fichier_local(lanceur.get("llama_server"))}


def choisir_dictee(carte_modele, palier, toutes):
    """Ou faire tourner Whisper : sur une autre carte si possible, sinon sur la meme si la memoire suffit, sinon un
    modele plus petit ou le processeur. Renvoie le choix et la phrase d'explication (estimations, a mesurer)."""
    # Mesure du 21/11/2026 (Qwen3.8-27B + vision, 65 536 jetons, cache q8_0, llama.cpp b12193, une RTX 3090) : 18,9 Gio
    # occupes = fichiers (Go convertis en Gio) + 2,6 Gio. Whisper large-v3 ajoute 2,2 Gio, small 0,6 Gio.
    besoin_modele = (palier["taille_go"] + palier["mmproj_go"]) * 0.931 + 2.6
    # memoire TOTALE des autres cartes : la memoire libre a l'instant depend de ce qui tourne pendant l'installation
    autres = sorted((c for c in toutes if c["uuid"] != carte_modele["uuid"]), key=lambda c: -c["memoire_go"])
    if autres and autres[0]["memoire_go"] >= 6:
        return {"carte": autres[0]["uuid"], "modele": "large-v3",
                "explication": tr("assistant.la_dictee_utilisera_la_carte", v1=autres[0]['nom'])}
    reste = carte_modele["memoire_go"] - besoin_modele
    if reste >= 3.0:
        return {"carte": carte_modele["uuid"], "modele": "large-v3",
                "explication": tr("assistant.la_dictee_partagera_la_carte")}
    if reste >= 1.0:
        return {"carte": carte_modele["uuid"], "modele": "small",
                "explication": tr("assistant.la_carte_n_a_pas")}
    return {"carte": "cpu", "modele": "small",
            "explication": tr("assistant.la_carte_n_a_plus")}


async def _voix_francaises(langue_voix):
    import edge_tts
    voix = await edge_tts.list_voices()
    return {v["ShortName"]: f"{v['FriendlyName'].split(' - ')[0].replace('Microsoft ', '').replace(' Online (Natural)', '')}"
                            f" ({v['Locale']}, {tr('assistant.voix_femme') if v['Gender'] == 'Female' else tr('assistant.voix_homme')})"
            for v in sorted(voix, key=lambda v: v["Locale"] != {"en": "en-US"}.get(langue_voix, f"{langue_voix}-{langue_voix.upper()}"))
            if v["Locale"].startswith(langue_voix + "-")}


def voix_disponibles(langue_voix=""):
    """Toutes les voix francaises d'edge-tts (France, Belgique, Canada, Suisse) ; hors ligne : celles de config.json."""
    try:
        import langue
        return asyncio.run(_voix_francaises(langue_voix or langue.code()))
    except Exception:
        return reglages.brut().get("voix", {}).get("choix", {})


def tester_voix(nom, phrase=tr("assistant.bonjour_je_suis_agent_local")):
    """MP3 en base64, joue par la fenetre. Le texte est envoye au service de Microsoft (comme pour la vraie voix)."""
    import edge_tts

    async def synthese():
        morceaux = []
        async for m in edge_tts.Communicate(phrase, nom).stream():
            if m["type"] == "audio":
                morceaux.append(m["data"])
        return b"".join(morceaux)
    return base64.b64encode(asyncio.run(synthese())).decode()


def tester_dictee(secondes=4):
    """Enregistre quelques secondes au micro et les transcrit avec le module dictee installe."""
    conf = reglages.charger().get("dictee", {})
    script = INSTALLATION / "modules" / "dictee" / "tester.py"
    if not Path(conf.get("python", "")).exists():
        return {"ok": False, "texte": tr("assistant.la_dictee_n_est_pas")}
    env = {**os.environ, "DICTEE_MODELE": conf.get("modele", "large-v3"), "DICTEE_CARTE": str(conf.get("carte", "")),
           "DICTEE_LANGUE": conf.get("langue", "fr")}
    r = subprocess.run([conf["python"], str(script), str(secondes)], capture_output=True, encoding="utf-8",
                       errors="replace", timeout=600, env=env, creationflags=SANS_FENETRE)
    lignes = r.stdout.strip().splitlines()
    return {"ok": r.returncode == 0, "texte": (lignes[-1] if lignes else r.stderr.strip()[-400:])}


# ---------------------------------------------------------------------------------------------------------------
# Telechargements verifies, avec progression
def progression():
    with _verrou:
        return json.loads(json.dumps(_travaux))


def _noter(ident, **champs):
    with _verrou:
        _travaux.setdefault(ident, {"etat": "en cours", "fait": 0, "total": 0, "message": ""}).update(champs)


def _lire_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=ENTETES), timeout=30) as r:
        return json.load(r)


def _telecharger(ident, url, destination, sha256=None):
    """Telecharge (reprise possible), puis verifie l'empreinte SHA-256 si la source en publie une.
    url peut etre une liste de miroirs (du plus rapide au plus lent) : si l'un coupe ou se bloque 30 s, on reprend
    sur le suivant, a l'octet pres (Range). L'empreinte, elle, vient toujours de la source officielle."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partiel = destination.with_suffix(destination.suffix + ".partiel")
    sources = [url] if isinstance(url, str) else list(url)
    for n, source in enumerate(sources):
        deja = partiel.stat().st_size if partiel.exists() else 0
        requete = urllib.request.Request(source, headers={**ENTETES, **({"Range": f"bytes={deja}-"} if deja else {})})
        try:
            with urllib.request.urlopen(requete, timeout=30) as r:
                if deja and r.status != 206:
                    deja = 0
                total = deja + int(r.headers.get("Content-Length") or 0)
                _noter(ident, total=total, fait=deja, message=tr("assistant.telechargement_de", v1=destination.name))
                with open(partiel, "ab" if deja else "wb") as f:
                    while True:
                        bloc = r.read(1 << 20)
                        if not bloc:
                            break
                        f.write(bloc)
                        deja += len(bloc)
                        _noter(ident, fait=deja)
            if total and deja < total:
                raise ConnectionError(f"{deja}/{total}")
            break
        except (OSError, ConnectionError):   # coupure, delai depasse (30 s sans donnees), miroir indisponible
            if n == len(sources) - 1:
                raise
    if sha256:
        _noter(ident, message=tr("assistant.verification_de", v1=destination.name))
        h = hashlib.sha256()
        with open(partiel, "rb") as f:
            for bloc in iter(lambda: f.read(1 << 22), b""):
                h.update(bloc)
        if h.hexdigest().lower() != sha256.lower():
            partiel.unlink()
            raise RuntimeError(tr("assistant.empreinte_differente_de_celle_publiee", v1=destination.name))
    partiel.replace(destination)
    return destination


def _miroirs_kiwix(url):
    """Miroirs officiels d'un fichier Kiwix (liste .meta4 publiee par download.kiwix.org), du plus rapide au plus lent.
    Kiwix redirige parfois vers un miroir tres lent (0,5 Mo/s mesure, contre 50 a 70 Mo/s pour d'autres) : on mesure
    chacun quelques secondes. L'adresse officielle reste en dernier recours."""
    try:
        xml = urllib.request.urlopen(urllib.request.Request(url + ".meta4", headers=ENTETES), timeout=30
                                     ).read().decode("utf-8", "replace")
    except OSError:
        return [url]
    nom = url.rsplit("/", 1)[1]
    candidats = [u for u in dict.fromkeys(re.findall(r"<url[^>]*>(https://[^<]+)</url>", xml)) if u.endswith("/" + nom)]
    mesures = []
    for u in candidats[:12]:
        try:
            debut, recu = time.monotonic(), 0
            with urllib.request.urlopen(urllib.request.Request(u, headers={**ENTETES, "Range": "bytes=0-16777215"}),
                                        timeout=8) as r:
                while recu < (16 << 20) and time.monotonic() - debut < 4:
                    bloc = r.read(1 << 18)
                    if not bloc:
                        break
                    recu += len(bloc)
            mesures.append((recu / max(time.monotonic() - debut, 0.01), u))
        except OSError:
            continue
    return [u for _, u in sorted(mesures, reverse=True)] + [url]


def _en_fond(ident, travail):
    def tourner():
        try:
            _noter(ident, etat=tr("assistant.en_cours"), message="Demarrage")
            message = travail()
            _noter(ident, etat="termine", message=message or "Termine")
        except Exception as e:
            _noter(ident, etat="erreur", message=str(e))
    threading.Thread(target=tourner, daemon=True).start()
    return {"ok": True, "id": ident}


def _empreinte_hf(depot, fichier):
    for f in _lire_json(f"https://huggingface.co/api/models/{depot}/tree/main"):
        if f.get("path") == fichier:
            return (f.get("lfs") or {}).get("oid")
    raise RuntimeError(tr("assistant.introuvable_dans_sur_hugging_face", fichier=fichier, depot=depot))


def telecharger_modele(id_palier, avec_vision=True):
    """Modele conseille (et son fichier de vision) depuis Hugging Face, verifie, puis inscrit dans config.json."""
    palier = next(p for p in PALIERS if p["id"] == id_palier)

    def travail():
        dossier = MODELES / palier["depot"].split("/")[1]
        url = f"https://huggingface.co/{palier['depot']}/resolve/main/"
        modele = _telecharger("modele", url + palier["fichier"], dossier / palier["fichier"],
                              _empreinte_hf(palier["depot"], palier["fichier"]))
        vision = None
        if avec_vision:
            vision = _telecharger("modele", url + palier["mmproj"], dossier / palier["mmproj"],
                                  _empreinte_hf(palier["depot"], palier["mmproj"]))
        conf = reglages.brut()
        conf["lanceur"].update({"modele": str(modele), "mmproj": str(vision or ""), "contexte": palier["contexte"]})
        reglages.enregistrer(conf)
        return f"{palier['nom']} pret."
    return _en_fond("modele", travail)


# llama.cpp officiel, version FIGEE (publiee le 07/11/2026), Windows CUDA 12.4 ; empreintes publiees par GitHub.
LLAMA_VERSION = "b12193"
LLAMA_ARCHIVES = [
    ("llama-b12193-bin-win-cuda-12.4-x64.zip", "47a323350494d0d37b0f75580d51c3734fb394f587b6a3850fbecec95386469c"),
    ("cudart-llama-bin-win-cuda-12.4-x64.zip", "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6"),
]
PILOTE_MINIMUM = (551, 61)   # pilote NVIDIA minimal pour CUDA 12.4 sous Windows


def verifier_pilote():
    """Avant de telecharger llama.cpp : le pilote NVIDIA doit etre assez recent pour CUDA 12.4."""
    liste = cartes()
    if not liste:
        return {"ok": False, "message": tr("assistant.pilote_aucune_carte")}
    version = liste[0]["pilote"]
    morceaux = tuple(int(x) for x in re.findall(r"\d+", version)[:2])
    if morceaux < PILOTE_MINIMUM:
        return {"ok": False, "message": tr("assistant.pilote_trop_ancien", version=version,
                                            minimum="{}.{}".format(*PILOTE_MINIMUM)),
                "lien": tr("assistant.lien_pilotes_nvidia")}
    return {"ok": True, "message": tr("assistant.pilote_compatible", version=version)}


def telecharger_moteur():
    """llama.cpp officiel (ggml-org), version figee, les deux archives Windows CUDA 12.4 verifiees par SHA-256."""
    pilote = verifier_pilote()
    if not pilote["ok"]:
        return pilote

    def travail():
        MOTEUR.mkdir(parents=True, exist_ok=True)
        for nom, empreinte in LLAMA_ARCHIVES:
            url = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_VERSION}/{nom}"
            archive = _telecharger("moteur", url, MODELES / "_archives" / nom, empreinte)
            with zipfile.ZipFile(archive) as z:
                z.extractall(MOTEUR)
            archive.unlink()   # l'archive verifiee n'est plus utile une fois extraite
        exe = next(MOTEUR.rglob("llama-server.exe"))
        conf = reglages.brut()
        conf["lanceur"]["llama_server"] = str(exe)
        reglages.enregistrer(conf)
        return tr("assistant.moteur_installe", version=LLAMA_VERSION)
    return _en_fond("moteur", travail)


# ---------------------------------------------------------------------------------------------------------------
# Composants externes (licence acceptee dans la fenetre)
def _pip(python, *arguments):
    r = subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", *arguments],
                       capture_output=True, encoding="utf-8", errors="replace", creationflags=SANS_FENETRE)
    if r.returncode:
        raise RuntimeError("pip : " + (r.stderr or r.stdout).strip()[-600:])


def _venv(dossier):
    python = Path(dossier) / "Scripts" / "python.exe"
    if not python.exists():
        subprocess.run([str(reglages.PYTHON_VENV), "-m", "venv", str(dossier)], check=True, creationflags=SANS_FENETRE)
    return python


def _activer_module(module, **rubriques):
    conf = reglages.brut()
    conf.setdefault("modules", {})[module] = True
    for cle, valeurs in rubriques.items():
        conf.setdefault(cle, {}).update(valeurs)
    reglages.enregistrer(conf)


def installer_composant(ident, licence_acceptee, options=None):
    """Bouton « Installer » de l'assistant et des Reglages. Refuse si la case « J'accepte » n'est pas cochee."""
    if not licence_acceptee:
        return {"ok": False, "message": tr("assistant.cochez_d_abord_la_case")}
    options = options or {}
    composant = COMPOSANTS[ident]
    if composant.get("admin"):
        return lancer_admin(composant["admin"], licences=True)
    if ident == "docker":
        return installer_docker(options.get("etape", "modules"))
    if ident == "n8n":
        return installer_n8n()

    def windows_mcp():
        python = _venv(INSTALLATION / "outils" / "windows-mcp")
        _noter(ident, message=tr("assistant.installation_de_windows_mcp_depuis"))
        _pip(python, "-r", str(INSTALLATION / "requirements-windows-mcp.txt"))
        _activer_module("windows")
        return tr("assistant.windows_mcp_installe")

    def dictee():
        python = _venv(INSTALLATION / "modules" / "dictee" / ".venv")
        _noter(ident, message=tr("assistant.installation_de_faster_whisper_et"))
        _pip(python, "-r", str(INSTALLATION / "modules" / "dictee" / "requirements.txt"))
        choix = options.get("choix") or {}
        _noter(ident, message=tr("assistant.telechargement_du_modele_whisper_depuis"))
        env = {**os.environ, "DICTEE_MODELE": choix.get("modele", "large-v3"), "DICTEE_CARTE": str(choix.get("carte", ""))}
        r = subprocess.run([str(python), str(INSTALLATION / "modules" / "dictee" / "tester.py"), "--charger"],
                           capture_output=True, encoding="utf-8", errors="replace", env=env, creationflags=SANS_FENETRE)
        if r.returncode:
            raise RuntimeError(tr("assistant.modele_whisper") + r.stderr.strip()[-400:])
        _activer_module("dictee", dictee={"modele": choix.get("modele", "large-v3"), "carte": choix.get("carte", ""),
                                          "python": str(python)})
        return tr("assistant.dictee_installee") + choix.get("explication", "")

    def xtts():
        dossier = INSTALLATION / "modules" / "voix-xtts"
        python = _venv(dossier / ".venv")
        _noter(ident, message=tr("assistant.installation_de_pytorch_cuda_depuis"))
        # versions figees : a partir de torch 2.9, coqui-tts exige torchcodec, donc FFmpeg installe sur Windows
        _pip(python, "torch==2.8.0", "torchaudio==2.8.0", "--index-url", "https://download.pytorch.org/whl/cu126")
        _noter(ident, message=tr("assistant.installation_de_coqui_tts_depuis"))
        _pip(python, "-r", str(dossier / "requirements.txt"))
        _activer_module("voix", voix={"xtts": {"url": "http://127.0.0.1:8771/", "serveur": str(dossier / "serveur_xtts.py"),
                                               "python": str(dossier / ".venv" / "Scripts" / "pythonw.exe"),
                                               "licence_acceptee": True}})
        return tr("assistant.voix_de_secours_installee_le")

    def wikipedia():
        _noter(ident, message=tr("assistant.installation_de_libzim_gpl_3"))
        _pip(reglages.PYTHON_VENV, "-r", str(INSTALLATION / "requirements-wikipedia.txt"))
        liste = urllib.request.urlopen(urllib.request.Request("https://download.kiwix.org/zim/wikipedia/", headers=ENTETES),
                                       timeout=30).read().decode("utf-8", "replace")
        code_langue = langue.code()
        noms = sorted(set(re.findall(rf'href="(wikipedia_{code_langue}_all_nopic_\d{{4}}-\d{{2}}\.zim)"', liste)))
        if not noms:
            raise RuntimeError(tr("assistant.aucun_fichier_wikipedia_en_francais", langue=code_langue))
        url = "https://download.kiwix.org/zim/wikipedia/" + noms[-1]
        empreinte = urllib.request.urlopen(urllib.request.Request(url + ".sha256", headers=ENTETES), timeout=30
                                           ).read().decode().split()[0]
        _noter(ident, message=tr("assistant.choix_du_miroir"))
        zim = _telecharger(ident, _miroirs_kiwix(url), MODELES / "wikipedia" / noms[-1], empreinte)
        _activer_module("wikipedia", wikipedia={"fichier_zim": str(zim)})
        return tr("assistant.wikipedia_hors_ligne_installe", v1=noms[-1])

    travaux = {"windows_mcp": windows_mcp, "dictee": dictee, "xtts": xtts, "wikipedia": wikipedia}
    return _en_fond(ident, travaux[ident])


def _preparer_searxng():
    """Reglages de SearXNG (format JSON necessaire a l'outil recherche) ; le conteneur est cree par le lanceur."""
    dossier = reglages.DONNEES / "searxng"
    dossier.mkdir(parents=True, exist_ok=True)
    reglages_searxng = dossier / "settings.yml"
    if not reglages_searxng.exists():
        modele = (INSTALLATION / "outils" / "searxng" / "settings.yml").read_text(encoding="utf-8")
        reglages_searxng.write_text(modele.replace("__CLE_SECRETE__", os.urandom(24).hex()), encoding="utf-8")


def enregistrer_cle(nom_fichier, contenu):
    """Cles et jetons saisis dans la fenetre : dossier de secrets uniquement (jamais config.json)."""
    permis = {"openrouter.env", "telegram.env", "gmail.env", "yahoo.env", "n8n-cle-mcp.txt"}
    if nom_fichier not in permis:
        return {"ok": False, "message": tr("assistant.fichier_de_secret_inconnu")}
    reglages.enregistrer_secret(nom_fichier, contenu)
    return {"ok": True}


def cles_enregistrees():
    """Pour Reglages > Cles et comptes : noms et dates seulement, jamais les valeurs."""
    if not reglages.SECRETS.exists():
        return []
    return [{"nom": f.name, "date": time.strftime("%d/%m/%Y", time.localtime(f.stat().st_mtime))}
            for f in sorted(reglages.SECRETS.iterdir()) if f.is_file()]


# ---------------------------------------------------------------------------------------------------------------
# Outils administrateur (confirmation Windows)
def _compte():
    return f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip("\\")


def lancer_admin(script, licences=False, options=""):
    """Ouvre le script d'outils-admin dans un PowerShell administrateur : Windows affiche sa confirmation (UAC)."""
    chemin = INSTALLATION / "outils-admin" / script
    if script not in ("installer_sante.ps1", "installer_reparation.ps1", "desinstaller.ps1", "ajouter_docker_users.ps1") \
            or not chemin.exists():
        return {"ok": False, "message": tr("assistant.script_inconnu")}
    arguments = f"-NoProfile -ExecutionPolicy Bypass -File \"{chemin}\" -Utilisateur \"{_compte()}\""
    import langue
    arguments += f" -Langue {langue.code()}"
    if licences:
        arguments += " -LicencesAcceptees"
    arguments += options
    commande = ["powershell", "-NoProfile", "-Command",
                f"Start-Process powershell -Verb RunAs -ArgumentList '{arguments.replace(chr(39), chr(39) * 2)}'"]
    r = subprocess.run(commande, capture_output=True, encoding="utf-8", errors="replace", creationflags=SANS_FENETRE)
    if r.returncode:
        return {"ok": False, "message": tr("assistant.confirmation_windows_refusee_ou_impossible")}
    return {"ok": True, "message": tr("assistant.suivez_la_fenetre_administrateur_qui")}


# ---------- Docker Desktop (recherche web, messagerie, n8n) ----------
# Parcours : absent -> installation (licence acceptee, WSL 2, winget, groupe docker-users ; une seule confirmation
# Windows) -> redemarrage annonce, puis reprise automatique de l'assistant a la meme etape -> Docker demarre -> conteneurs.
MODULES_DOCKER = ("recherche", "messagerie", "n8n")
RESULTAT_DOCKER = reglages.DONNEES / "docker-installation.json"


def _ps_docker(commande, delai=120):
    """Execute une fonction de outils/docker.ps1 (memes regles que le lanceur) et renvoie sa sortie."""
    script = f". '{INSTALLATION / 'outils' / 'langue.ps1'}'; . '{INSTALLATION / 'outils' / 'docker.ps1'}'; {commande}"
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], timeout=delai,
                       capture_output=True, encoding="utf-8", errors="replace", creationflags=SANS_FENETRE)
    return (r.stdout or "").strip()


def _demarrage_windows():
    """Heure du dernier demarrage de Windows (secondes depuis 1970)."""
    ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
    return time.time() - ctypes.windll.kernel32.GetTickCount64() / 1000


def etat_docker():
    """absent | sans_droits | a_reconnecter | redemarrage | arrete | pret (Docker repond)."""
    etat = _ps_docker("Etat-Docker", 60) or "inconnu"
    if etat != "pret" and RESULTAT_DOCKER.exists() and RESULTAT_DOCKER.stat().st_mtime > _demarrage_windows():
        try:
            if json.loads(RESULTAT_DOCKER.read_text(encoding="utf-8-sig")).get("redemarrage"):
                etat = "redemarrage"   # installation faite depuis le dernier demarrage : Windows doit redemarrer
        except ValueError:
            pass
    return {"etat": etat}


def installer_docker(etape="modules"):
    """WSL 2 + Docker Desktop (winget, source officielle) + groupe docker-users, dans UNE fenetre administrateur.
    Appele seulement par installer_composant, donc apres la case « J'accepte » sous la licence de Docker."""
    def travail():
        _noter("docker", message=tr("docker.fenetre_admin"))
        try:
            RESULTAT_DOCKER.unlink(missing_ok=True)
        except OSError:
            pass
        script = INSTALLATION / "outils-admin" / "installer_docker.ps1"
        arguments = (f'-NoProfile -ExecutionPolicy Bypass -File "{script}" -Utilisateur "{_compte()}" '
                     f'-Langue {langue.code()} -LicencesAcceptees -Resultat "{RESULTAT_DOCKER}"')
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"Start-Process powershell -Verb RunAs -Wait -ArgumentList '{arguments.replace(chr(39), chr(39) * 2)}'"],
                           capture_output=True, encoding="utf-8", errors="replace", creationflags=SANS_FENETRE)
        if r.returncode:
            raise RuntimeError(tr("assistant.confirmation_windows_refusee_ou_impossible"))
        try:
            resultat = json.loads(RESULTAT_DOCKER.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            resultat = {}
        if not resultat.get("ok"):
            raise RuntimeError(resultat.get("message") or tr("docker.installation_interrompue"))
        _preparer_searxng()
        return tr("docker.fin_redemarrage") if resultat.get("redemarrage") else tr("docker.fin_ok")
    return _en_fond("docker", travail)


CLE_RUNONCE = r"Software\Microsoft\Windows\CurrentVersion\RunOnce"


def redemarrer_windows(etape, mode):
    """Redemarrage annonce (60 s, annulable) : Agent Local se relancera une fois a l'ouverture de session et rouvrira
    l'assistant (ou les Reglages) a la meme etape."""
    import winreg
    conf = reglages.brut()
    conf["reprise_assistant"] = {"mode": "reglages" if mode == "reglages" else "assistant", "etape": str(etape)}
    reglages.enregistrer(conf)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CLE_RUNONCE) as cle:
        winreg.SetValueEx(cle, "AgentLocalReprise", 0, winreg.REG_SZ,
                          f'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File '
                          f'"{INSTALLATION / "lancer_agent_local.ps1"}"')
    r = subprocess.run(["shutdown", "/r", "/t", "60", "/c", tr("docker.message_redemarrage")], creationflags=SANS_FENETRE)
    return {"ok": r.returncode == 0}


def annuler_redemarrage():
    import winreg
    subprocess.run(["shutdown", "/a"], creationflags=SANS_FENETRE)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_RUNONCE, 0, winreg.KEY_SET_VALUE) as cle:
            winreg.DeleteValue(cle, "AgentLocalReprise")
    except OSError:
        pass
    effacer_reprise()
    return {"ok": True}


def effacer_reprise():
    conf = reglages.brut()
    if conf.pop("reprise_assistant", None) is not None:
        reglages.enregistrer(conf)
    return {"ok": True}


def demarrer_docker(modules):
    """Demarre Docker Desktop (si le compte en a le droit), puis les conteneurs des modules choisis."""
    choisis = [m for m in (modules or []) if m in MODULES_DOCKER]

    def travail():
        _noter("docker_demarrage", message=tr("lanceur.docker_lancement"))
        if "recherche" in choisis:
            _preparer_searxng()
        liste = ",".join(f"'{m}'" for m in choisis) or "''"
        sortie = _ps_docker(f"if (Demarrer-Docker) {{ Demarrer-Conteneurs '{reglages.DONNEES}' @({liste}) }} "
                            f"else {{ 'docker=echec' }}", 1200)
        lignes = dict(l.split("=", 1) for l in sortie.splitlines() if "=" in l)
        if lignes.get("docker") == "echec":
            raise RuntimeError(tr("lanceur.docker_pas_pret"))
        echecs = [m for m, e in lignes.items() if e not in ("ok", "occupe")]
        if echecs:
            raise RuntimeError(tr("docker.conteneurs_echec", v1=", ".join(tr("as.module_" + m) for m in echecs)))
        return tr("docker.tout_pret")
    return _en_fond("docker_demarrage", travail)


# ---------- n8n (automatisations), dans Docker ----------
N8N = "http://127.0.0.1:5678"


def _n8n_repond():
    try:
        urllib.request.urlopen(N8N + "/healthz", timeout=3)
        return True
    except Exception:
        return False


def installer_n8n():
    """Apres la case « J'accepte » (Sustainable Use License) : conteneur n8n (image officielle figee, volume persistant,
    port 5678 sur 127.0.0.1 seulement). Docker doit etre pret : sinon, le parcours Docker est propose au-dessus."""
    def travail():
        if etat_docker()["etat"] not in ("pret", "arrete"):
            raise RuntimeError(tr("n8n.docker_d_abord"))
        _noter("n8n", message=tr("n8n.telechargement"))
        sortie = _ps_docker(f"if (Demarrer-Docker) {{ Demarrer-Conteneurs '{reglages.DONNEES}' @('n8n') }} else {{ 'docker=echec' }}", 1800)
        if "n8n=ok" not in sortie and "n8n=occupe" not in sortie:
            raise RuntimeError(tr("lanceur.docker_pas_pret") if "docker=echec" in sortie else tr("n8n.echec_conteneur"))
        for _ in range(60):   # premier demarrage : n8n prepare sa base, jusqu'a 2 minutes
            if _n8n_repond():
                return tr("n8n.pret")
            time.sleep(2)
        raise RuntimeError(tr("n8n.ne_repond_pas"))
    return _en_fond("n8n", travail)


def etat_n8n():
    cle = Path(reglages.chemin_secret("n8n-cle-mcp.txt"))
    return {"repond": _n8n_repond(), "cle": cle.is_file() and bool(cle.read_text(encoding="utf-8").strip()),
            "actif": reglages.brut().get("modules", {}).get("n8n") is True}


def ouvrir_n8n():
    import webbrowser
    webbrowser.open(N8N)
    return {"ok": True}


def tester_n8n():
    """Teste le jeton colle par l'utilisateur sur le serveur MCP de n8n ; s'il est accepte, active le module n8n."""
    cle = Path(reglages.chemin_secret("n8n-cle-mcp.txt"))
    jeton = cle.read_text(encoding="utf-8").strip() if cle.is_file() else ""
    if not jeton:
        return {"ok": False, "message": tr("n8n.cle_absente")}
    if not _n8n_repond():
        return {"ok": False, "message": tr("n8n.ne_repond_pas")}
    corps = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                   "clientInfo": {"name": "agent-local", "version": VERSION}}}).encode()
    demande = urllib.request.Request(N8N + "/mcp-server/http", data=corps, method="POST", headers={
        "Authorization": f"Bearer {jeton}", "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    try:
        urllib.request.urlopen(demande, timeout=15).close()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"ok": False, "message": tr("n8n.cle_refusee")}
        return {"ok": False, "message": tr("n8n.erreur_v1", v1=e.code)}
    except Exception as e:
        return {"ok": False, "message": tr("n8n.erreur_v1", v1=e)}
    _activer_module("n8n")
    return {"ok": True, "message": tr("n8n.connecte")}


def etat_admin():
    """Etat des outils administrateur, et dernier refus du controle d'integrite (affiche en clair dans Reglages)."""
    def tache(nom):
        return subprocess.run(["schtasks", "/query", "/tn", nom], capture_output=True, creationflags=SANS_FENETRE).returncode == 0
    journal = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "AgentLocal" / "Sante" / "controle_integrite.log"
    refus = ""
    if journal.exists():
        lignes = journal.read_text(encoding="utf-8-sig", errors="replace").strip().splitlines()
        refus = lignes[-1] if lignes else ""
    return {"sante": tache(r"\AgentLocal\Autoruns") and tache(r"\AgentLocal\LibreHardwareMonitor"),
            "reparation": tache(r"\AgentLocal\Reparation"),
            "dernier_refus_integrite": refus}


def desinstaller(supprimer_modeles=False, supprimer_secrets=False):
    options = f" -Installation \"{INSTALLATION}\""
    options += " -SupprimerModeles" if supprimer_modeles else ""
    options += " -SupprimerSecrets" if supprimer_secrets else ""
    return lancer_admin("desinstaller.ps1", options=options)


def recapitulatif_desinstallation(supprimer_modeles=False, supprimer_secrets=False):
    """Ce que la desinstallation retirera, affiche AVANT de demander la confirmation."""
    elements = [tr("assistant.taches_planifiees_d_agent_local"), r"C:\Program Files\AgentLocal",
                r"C:\ProgramData\AgentLocal", tr("assistant.raccourci_bureau_agent_local")]
    if supprimer_modeles:
        elements += [str(MODELES), str(MOTEUR), tr("assistant.environnements_de_la_dictee_et")]
    if supprimer_secrets:
        elements.append(str(reglages.SECRETS))
    return elements


# ---------------------------------------------------------------------------------------------------------------
# Mises a jour et test du modele
def verifier_mises_a_jour():
    """Consulte la derniere version publiee sur GitHub ; n'installe rien."""
    depot = reglages.brut().get("mises_a_jour", {}).get("depot", "")
    if not depot:
        return {"ok": False, "message": tr("assistant.aucun_depot_de_mises_a")}
    try:
        sortie = _lire_json(f"https://api.github.com/repos/{depot}/releases/latest")
    except Exception as e:
        return {"ok": False, "message": tr("assistant.impossible_de_joindre_github", e=e)}
    distante = sortie.get("tag_name", "").lstrip("v")
    def cle(v):
        return [int(x) for x in re.findall(r"\d+", v)[:3]]
    return {"ok": True, "actuelle": VERSION, "disponible": distante, "nouvelle": cle(distante) > cle(VERSION),
            "notes": sortie.get("body", ""), "archive": sortie.get("zipball_url", ""), "page": sortie.get("html_url", "")}


def installer_mise_a_jour(archive):
    """Apres accord : remplace le code par la version publiee. Garde config.json, les secrets, les donnees, les
    modeles, le moteur et les environnements installes. Ne supprime aucun fichier existant."""
    depot = reglages.brut().get("mises_a_jour", {}).get("depot", "")
    if not archive.startswith(f"https://api.github.com/repos/{depot}/zipball/"):
        return {"ok": False, "message": tr("assistant.adresse_de_mise_a_jour")}
    gardes = ("noyau/config.json", "noyau/donnees/", "noyau/competences/", "noyau/.venv/", "modeles/", "moteur/",
              "outils/windows-mcp/", "modules/dictee/.venv/", "modules/voix-xtts/.venv/")

    def travail():
        zip_ = _telecharger("mise_a_jour", archive, Path(tempfile.gettempdir()) / "agent-local-maj.zip")
        with zipfile.ZipFile(zip_) as z:
            for info in z.infolist():
                relatif = info.filename.split("/", 1)[1] if "/" in info.filename else ""
                if not relatif or info.is_dir() or relatif.startswith(gardes) or ".." in relatif:
                    continue
                cible = INSTALLATION / relatif
                cible.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as source, open(cible, "wb") as destination:
                    shutil.copyfileobj(source, destination)
        zip_.unlink()
        return tr("assistant.mise_a_jour_installee_fermez")
    return _en_fond("mise_a_jour", travail)


def tester_modele():
    """Envoie une courte question au modele et mesure la vitesse (jetons par seconde)."""
    conf = reglages.charger()["llm"]
    corps = json.dumps({"messages": [{"role": "user", "content": tr("assistant.question_test_modele")}],
                        "max_tokens": 200, "temperature": 0.2}).encode()
    debut = time.time()
    try:
        requete = urllib.request.Request(conf["url"], data=corps, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(requete, timeout=180) as r:
            reponse = json.load(r)
    except Exception as e:
        return {"ok": False, "message": tr("assistant.le_modele_ne_repond_pas", e=e)}
    duree = time.time() - debut
    texte = reponse["choices"][0]["message"].get("content") or ""
    texte = re.sub(r"(?s)<think>.*?</think>", "", texte).strip()
    vitesse = (reponse.get("timings") or {}).get("predicted_per_second")
    if not vitesse:
        jetons = (reponse.get("usage") or {}).get("completion_tokens") or 0
        vitesse = jetons / duree if duree else 0
    return {"ok": True, "reponse": texte, "vitesse": round(vitesse, 1), "duree": round(duree, 1)}


# ---------------------------------------------------------------------------------------------------------------
# Mes donnees (chaque effacement est confirme dans la fenetre avant l'appel)
def donnees_souvenirs():
    import memoire
    return [dict(s) for s in memoire.lister()]


def donnees_oublier(id_souvenir):
    import memoire
    return memoire.oublier(int(id_souvenir)) is not None


def donnees_oublier_tout():
    import memoire
    return memoire.oublier_tout()


def donnees_vider_conversations():
    import memoire
    return memoire.vider_conversations()


def donnees_vider_journal():
    import memoire
    journal = memoire.BASE.parent / "journal.jsonl"
    if journal.exists():
        journal.unlink()
    return True


# ---------------------------------------------------------------------------------------------------------------
# Reglages : ce que la fenetre peut lire et ecrire dans config.json (jamais de secret)
CHAMPS_MODIFIABLES = {
    "utilisateur": {"prenom", "dossier_sortie", "langue"},
    "lanceur": {"modele", "mmproj", "contexte", "cartes", "carte_principale", "llama_server", "port", "options_supplementaires"},
    "autorisations": {"mode"},
    "modules": {"vision", "voix", "dictee", "recherche", "navigateur", "windows", "wikipedia", "sante", "reparation",
                "cloud", "telegram", "messagerie", "hermes", "n8n"},
    "voix": {"nom"},
    "dictee": {"modele", "carte", "langue"},
}
DEMANDENT_REDEMARRAGE = {"utilisateur.langue", "lanceur", "modules", "autorisations.mode", "dictee"}


def reglages_lire():
    import langue
    conf = reglages.brut()
    return {"config": {r: conf.get(r, {}) for r in CHAMPS_MODIFIABLES} | {"premier_lancement_fait": conf.get("premier_lancement_fait") is True},
            "langues": langue.disponibles(), "langue": langue.code(), "niveaux": list(reglages.NIVEAUX),
            "composants": COMPOSANTS, "version": VERSION, "installation": str(INSTALLATION),
            "reprise": conf.get("reprise_assistant")}


def reglages_enregistrer(modifs):
    """Ecrit les champs autorises ; renvoie s'il faut redemarrer Agent Local pour les appliquer."""
    conf = reglages.brut()
    redemarrer = False
    for rubrique, valeurs in (modifs or {}).items():
        permis = CHAMPS_MODIFIABLES.get(rubrique, set())
        if not permis or not isinstance(valeurs, dict):
            continue   # rubrique inconnue : ignoree (jamais d'erreur qui bloquerait l'assistant)
        for cle, valeur in valeurs.items():
            if cle not in permis or conf.get(rubrique, {}).get(cle) == valeur:
                continue
            conf.setdefault(rubrique, {})[cle] = valeur
            redemarrer = redemarrer or rubrique in DEMANDENT_REDEMARRAGE or f"{rubrique}.{cle}" in DEMANDENT_REDEMARRAGE
    if "langue" in (modifs or {}).get("utilisateur", {}):
        conf.setdefault("dictee", {})["langue"] = modifs["utilisateur"]["langue"]
    reglages.enregistrer(conf)
    return {"ok": True, "redemarrer": redemarrer}


def terminer_assistant():
    conf = reglages.brut()
    conf["premier_lancement_fait"] = True
    reglages.enregistrer(conf)
    return relancer()


def relancer():
    """Relance Agent Local par son lanceur (seule facon de demarrer le modele) ; la fenetre se ferme ensuite."""
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                      str(INSTALLATION / "lancer_agent_local.ps1"), "-AttendreFermeture"],
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return {"ok": True, "fermer": True}


FONCTIONS_FENETRE = {
    "detecter", "choisir_dictee", "voix_disponibles", "tester_voix", "tester_dictee", "progression", "verifier_pilote",
    "telecharger_modele", "telecharger_moteur", "installer_composant", "enregistrer_cle", "cles_enregistrees",
    "lancer_admin", "etat_admin", "desinstaller", "recapitulatif_desinstallation", "verifier_mises_a_jour",
    "installer_mise_a_jour", "tester_modele", "donnees_souvenirs", "donnees_oublier", "donnees_oublier_tout",
    "donnees_vider_conversations", "donnees_vider_journal", "reglages_lire", "reglages_enregistrer",
    "terminer_assistant", "relancer", "etat_docker", "demarrer_docker", "redemarrer_windows", "annuler_redemarrage",
    "effacer_reprise", "etat_n8n", "ouvrir_n8n", "tester_n8n",
}
