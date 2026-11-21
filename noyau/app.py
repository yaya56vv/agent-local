"""Agent Local v2 - application de bureau.

Ouvre l'interface (frontend/index.html) dans sa propre fenetre (pywebview)
et la relie au noyau. Le noyau tourne dans une boucle asyncio a part ;
la fenetre l'appelle par window.pywebview.api.*, le noyau lui repond
par window.agentEvenement(...).
"""
import asyncio
import base64
import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import webview

import artefacts
import competences
import filet
import memoire
import planificateur
import reglages
import telegram_pont
from agent import Agent
from pupitre_mcp import PupitreMCP
from voix import Voix
from langue import t as tr

ICI = Path(__file__).parent
INTERFACE = ICI.parent / "frontend" / "index.html"
DOSSIER_PIECES_JOINTES = Path.home() / "Documents" / tr("app.pieces_jointes")
PIECE_JOINTE_MAX = 50 * 2**20   # octets
REPRISE = (tr("app.reprise_apres_interruption_ta_mission"))


class Pont:
    def __init__(self):
        self._fenetre = None
        self._config = reglages.charger()
        self._boucle = asyncio.new_event_loop()
        self._pupitre = PupitreMCP(self._config["mcp_servers"], self._config["autorisations"])
        self._agent = None
        self._attentes = {}          # id d'appel -> Future de l'autorisation
        self._tampon = []            # morceaux de flux en attente d'envoi
        self._dernier_envoi = 0.0
        self._voix = None
        self._occupe, self._planifiee, self._en_cours = False, None, None
        self._telegram, self._telephone, self._artefacts_tel = None, False, []   # pilotage par Telegram (12/11/2026)
        threading.Thread(target=self._tourner, daemon=True).start()

    # --- boucle du noyau ---------------------------------------------------
    def _tourner(self):
        asyncio.set_event_loop(self._boucle)
        self._voix = Voix({**self._config.get("voix", {}), "active": self._config["modules"].get("voix") is True},
                          self._pousser)
        self._boucle.create_task(self._voix.ouvrier())
        self._fin, pret = asyncio.Event(), asyncio.Event()
        self._vie = self._boucle.create_task(self._vie_du_pupitre(pret))
        self._boucle.run_until_complete(pret.wait())
        self._agent = Agent(self._config, self._pupitre, self._signaler, self._demander)
        import langue
        competences.installer_exemples(langue.code())   # premier lancement : fiches d'exemple
        planificateur.recaler_manquees()
        filet.nettoyer()   # copies de securite : 7 jours au plus, 5 Go au plus
        self._boucle.create_task(self._surveiller_taches())
        self._telegram = telegram_pont.Telegram(self)
        self._boucle.create_task(self._telegram.tourner())
        self._boucle.run_forever()

    async def _vie_du_pupitre(self, pret):
        """Une seule tache ouvre les MCP, attend la fermeture de la fenetre, puis les referme :
        la bibliotheque MCP exige que l'ouverture et la fermeture se fassent dans la meme tache."""
        await self._pupitre.brancher()
        pret.set()
        await self._fin.wait()
        await self._pupitre.debrancher()

    def _fermer(self):
        """Appele a la fermeture de la fenetre : referme proprement les MCP (et donc le navigateur de l'agent)."""
        async def attendre():
            self._fin.set()
            await self._vie
        try:
            asyncio.run_coroutine_threadsafe(attendre(), self._boucle).result(timeout=15)
        except Exception:
            pass
        self._boucle.call_soon_threadsafe(self._boucle.stop)

    def _pousser(self, evenements):
        if self._fenetre and evenements:
            self._fenetre.evaluate_js(f"window.agentEvenement && window.agentEvenement({json.dumps(evenements)})")

    async def _signaler(self, ev):
        # La voix suit la reponse ecrite du chef, phrase par phrase.
        if ev["type"] == "texte" and not ev.get("agent"):
            self._voix.ajouter(ev["texte"])
        elif ev["type"] in ("appel_outil", "reponse", "erreur") and not ev.get("agent"):
            self._voix.terminer()
        elif ev["type"] == "debut_mission":
            self._voix.vider()
        # Les morceaux de pensee/texte sont regroupes (~10 envois/s) pour garder la fenetre fluide.
        if ev["type"] in ("reflexion", "texte"):
            self._tampon.append(ev)
            if time.monotonic() - self._dernier_envoi < 0.1:
                return
        else:
            self._tampon.append(ev)
        if self._telephone and ev["type"] == "artefact":   # renvoye au telephone en fin de mission
            self._artefacts_tel.append(ev["id"])
        lot, self._tampon = self._tampon, []
        self._dernier_envoi = time.monotonic()
        self._pousser(lot)

    async def _demander(self, appel):
        if self._planifiee:   # tache planifiee : l'utilisateur n'est peut-etre pas la, toute demande est refusee d'office
            await self._signaler({"type": "refus_auto", "outil": appel["outil"],
                                  "texte": tr("app.tache_planifiee_action_necessitant_ton")})
            return False
        futur = self._boucle.create_future()
        self._attentes[appel["id"]] = futur
        await self._signaler({"type": "demande_autorisation", **appel})
        telephone = self._telephone and self._telegram   # mission venue du telephone : les boutons y vont aussi
        if telephone:
            await self._telegram.demander_accord(appel)
        try:
            accorde = await futur
            if telephone:
                await self._telegram.accord_donne(appel["id"], accorde)
            return accorde
        finally:
            self._attentes.pop(appel["id"], None)

    async def _mission(self, texte, tache=None, telephone=False):
        self._occupe, self._planifiee = True, tache
        self._agent.tache_planifiee = bool(tache)
        self._en_cours = asyncio.current_task()   # ce que le bouton Stop interrompt
        await self._signaler({"type": "debut_mission", "texte": texte,
                              "planifiee": tache["titre"] if tache else None, "telephone": telephone})
        reponse = None
        try:
            demande = tr("app.tache_planifiee", v1=tache['titre'], texte=texte) if tache else texte
            reponse = await self._agent.mission(demande)
        except asyncio.CancelledError:
            self._agent._ajouter({"role": "assistant", "content": tr("app.mission_arretee_a_la_demande")})
            await self._signaler({"type": "erreur", "texte": tr("app.mission_arretee_a_ta_demande")})
        finally:
            self._occupe, self._planifiee = False, None
            self._agent.tache_planifiee = False
            await self._signaler({"type": "fin_mission"})
        return reponse

    async def mission_telephone(self, texte):
        """Une mission envoyee depuis Telegram : meme chemin qu'une mission tapee au PC, puis la reponse et les
        artefacts repartent vers le telephone."""
        if self._occupe:
            await self._telegram.envoyer_texte(tr("app.une_mission_est_deja_en_2"))
            return
        self._occupe, self._telephone, self._artefacts_tel = True, True, []
        try:
            reponse = await self._mission(texte, telephone=True)
            await self._telegram.envoyer_texte(reponse or tr("app.la_mission_s_est_arretee"))
            extensions = {"code": ".txt", "html": ".html"}
            for id_a in dict.fromkeys(self._artefacts_tel):
                a = artefacts.lire(id_a)
                nom = re.sub(r'[<>:"/\\|?*]', "_", a["titre"] or "artefact") + extensions.get(a["type"], ".md")
                await self._telegram.envoyer_fichier(nom, a["contenu"])
        finally:
            self._telephone = False

    async def _surveiller_taches(self):
        """Toutes les 30 secondes : lance la premiere tache planifiee arrivee a echeance, si l'agent est libre."""
        while True:
            await asyncio.sleep(30)
            if self._occupe or not self._agent:
                continue
            try:
                echues = planificateur.echues()
                if echues:
                    t = echues[0]
                    reponse = await self._mission(t["consigne"], tache=t)
                    planificateur.marquer_executee(t, reponse)
                    await self._signaler({"type": "taches_maj"})
            except Exception as e:
                await self._signaler({"type": "erreur", "texte": f"Planificateur : {e}"})

    # --- fonctions appelees par la fenetre ---------------------------------
    def etat(self):
        for _ in range(300):                      # attend le branchement des MCP (30 s max)
            if self._agent:
                break
            time.sleep(0.1)
        serveurs = [{"nom": n, "etat": e,
                     "outils": [{"nom": o["outil"], "niveau": o["niveau"]}
                                for o in self._pupitre.outils.values() if o["serveur"] == n]}
                    for n, e in self._pupitre.etats.items()]
        return {"pret": self._agent is not None, "modele": self._config["llm"]["url"], "serveurs": serveurs}

    def envoyer(self, texte):
        if self._occupe:
            raison = (tr("app.une_tache_planifiee_est_en", v1=self._planifiee['titre']) if self._planifiee
                      else tr("app.une_mission_est_deja_en"))
            return {"ok": False, "raison": raison}
        self._occupe = True   # pris tout de suite, pour que le planificateur ne lance rien en meme temps
        asyncio.run_coroutine_threadsafe(self._mission(texte), self._boucle)
        return {"ok": True}

    def joindre_fichier(self, nom, contenu_base64):
        """Le trombone : enregistre la piece jointe dans Documents\\Pieces jointes (dossier que l'outil
        fichiers du chef sait lire) et renvoie son chemin, que la fenetre ajoute au message."""
        donnees = base64.b64decode(contenu_base64.split(",", 1)[-1])
        if len(donnees) > PIECE_JOINTE_MAX:
            return {"ok": False, "raison": tr("app.fichier_trop_gros_plus_de", v1=PIECE_JOINTE_MAX // 2**20)}
        propre = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(nom).name).strip(" .") or "piece-jointe"
        DOSSIER_PIECES_JOINTES.mkdir(parents=True, exist_ok=True)
        chemin = DOSSIER_PIECES_JOINTES / f"{datetime.now():%Y-%m-%d_%H%M%S}_{propre}"
        chemin.write_bytes(donnees)
        return {"ok": True, "chemin": str(chemin)}

    def repondre_autorisation(self, id_appel, accorde):
        futur = self._attentes.get(id_appel)
        if futur and not futur.done():
            self._boucle.call_soon_threadsafe(futur.set_result, bool(accorde))
        return True

    def arreter(self):
        if self._occupe and self._en_cours and not self._en_cours.done():
            self._boucle.call_soon_threadsafe(self._en_cours.cancel)
        self._boucle.call_soon_threadsafe(self._voix.vider)
        return True

    # --- artefacts -----------------------------------------------------------
    def artefacts_lister(self):
        return artefacts.lister()

    def artefact_lire(self, id_artefact):
        return artefacts.lire(int(id_artefact))

    def artefact_enregistrer(self, id_artefact):
        return artefacts.enregistrer_fichier(int(id_artefact))

    # --- taches planifiees ---------------------------------------------------
    def taches_lister(self):
        return planificateur.lister()

    def tache_supprimer(self, id_tache):
        return planificateur.supprimer(int(id_tache)) is not None

    # --- voix ----------------------------------------------------------------
    def voix_reglages(self):
        return {"nom": self._voix.nom, "choix": self._voix.choix}

    def regler_voix(self, nom):
        self._boucle.call_soon_threadsafe(self._voix.regler, nom)
        return True

    # --- memoire -------------------------------------------------------------
    def competences_lister(self):
        return [{k: f[k] for k in ("nom", "description", "maj")} for f in competences.lister()]

    def competence_lire(self, nom):
        return competences.lire(nom)

    def memoire_lister(self):
        return memoire.lister()

    def memoire_rechercher(self, texte):
        return memoire.rechercher(texte, 20)

    def presse_papiers(self):
        """Texte du presse-papiers de Windows, pour le « Coller » du clic droit (la page web n'a pas toujours le droit
        de le lire elle-meme). Demande de l'utilisateur du 11/11/2026."""
        import subprocess
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw"],
                           capture_output=True, encoding="utf-8", errors="replace", timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return (r.stdout or "").rstrip("\r\n")

    def nouvelle_conversation(self):
        if self._occupe:
            return {"ok": False, "raison": tr("app.une_mission_est_en_cours")}
        self._boucle.call_soon_threadsafe(self._agent.nouvelle_conversation)
        return {"ok": True}

    # --- filet de securite : annuler la derniere modification (12/11/2026) ---
    def derniere_modification(self):
        return filet.derniere_action()

    def annuler_modification(self):
        if self._occupe:
            return {"ok": False, "texte": tr("app.une_mission_est_en_cours_2")}
        return filet.annuler_derniere()

    def telegram_etat(self):
        return self._telegram.etat() if self._telegram else {"actif": False}

    # --- historique des conversations (12/11/2026) --------
    def conversations_lister(self):
        actuelle = self._agent.conversation if self._agent else None
        return [{**c, "actuelle": c["id"] == actuelle} for c in memoire.lister_conversations()]

    def conversation_reprendre(self, id_conversation):
        """Rend la conversation choisie active et renvoie ce que la fenetre doit reafficher : les demandes de l'utilisateur,
        les reponses du chef et le nom des outils utilises (pas les resultats bruts, ni les messages internes)."""
        if self._occupe:
            return {"ok": False, "raison": tr("app.une_mission_est_en_cours")}
        id_conversation = int(id_conversation)

        async def reprendre():   # dans la boucle du noyau, comme tout ce qui touche a l'agent
            self._agent.reprendre_conversation(id_conversation)
        asyncio.run_coroutine_threadsafe(reprendre(), self._boucle).result(timeout=15)
        return {"ok": True, "messages": self._affichage()}

    def _affichage(self):
        """La conversation active, pour la fenetre : demandes de l'utilisateur, reponses du chef, noms des outils utilises."""
        affichage = []
        for m in self._agent.historique:
            if m.get("interne") or m.get("image"):
                continue
            if m["role"] == "user" and m.get("content"):
                affichage.append({"genre": "demande", "texte": m["content"]})
            elif m["role"] == "assistant":
                if m.get("tool_calls"):
                    affichage.append({"genre": "outils", "texte": ", ".join(
                        a["function"]["name"].replace("__", " › ") for a in m["tool_calls"])})
                if (m.get("content") or "").strip():
                    affichage.append({"genre": "reponse", "texte": m["content"].strip()})
        return affichage

    # --- assistant de premier lancement et page Reglages (noyau/assistant.py) ---
    def assistant(self, fonction, parametres=None):   # pas « arguments » : nom reserve en JavaScript
        """Seule porte entre la fenetre et assistant.py : liste fermee de fonctions."""
        import assistant as module
        if fonction not in module.FONCTIONS_FENETRE:
            return {"ok": False, "message": "fonction inconnue"}
        resultat = getattr(module, fonction)(*(parametres or []))
        if isinstance(resultat, dict) and resultat.get("fermer") and self._fenetre:
            threading.Timer(1.0, self._fenetre.destroy).start()
        return resultat

    def textes(self, code_langue):
        """Textes d'une autre langue, pour changer de langue dans l'assistant sans redemarrer."""
        import langue
        return langue.tout(code_langue)

    def choisir_dossier(self):
        choix = self._fenetre.create_file_dialog(webview.FOLDER_DIALOG)
        return choix[0] if choix else ""

    def choisir_fichier_gguf(self):
        choix = self._fenetre.create_file_dialog(webview.OPEN_DIALOG, file_types=("GGUF (*.gguf)",))
        return choix[0] if choix else ""

    # --- reprise apres plantage (12/11/2026) -------------
    def mission_interrompue(self):
        return memoire.mission_interrompue(self._agent.conversation if self._agent else None)

    def _demande_active(self):
        return next((m["content"] for m in reversed(self._agent.historique) if m["role"] == "user"
                     and not m.get("interne") and not m.get("image")), "")

    def reprendre_mission(self, id_conversation):
        """Depuis la fenetre : la conversation interrompue redevient active et la mission repart la ou elle s'est arretee."""
        r = self.conversation_reprendre(id_conversation)
        if not r["ok"]:
            return r
        self._occupe = True
        asyncio.run_coroutine_threadsafe(self._mission(REPRISE.format(self._demande_active())), self._boucle)
        return r

    async def reprendre_mission_telephone(self, id_conversation):
        if self._occupe:
            await self._telegram.envoyer_texte(tr("app.une_mission_est_deja_en_3"))
            return
        self._agent.reprendre_conversation(int(id_conversation))
        await self._signaler({"type": "conversation_reprise", "messages": self._affichage()})
        await self.mission_telephone(REPRISE.format(self._demande_active()))

    def abandonner_mission(self, id_conversation):
        memoire.enregistrer_message(int(id_conversation),
                                    {"role": "assistant", "content": tr("app.mission_interrompue_abandonnee_par_l")})
        return True


def ecrire_textes_interface():
    """Langue de la fenetre : js/textes.js (genere, hors git) contient les textes de la langue choisie, lus au chargement."""
    import langue
    contenu = (f"window.LANGUE = {json.dumps(langue.code())};\n"
               f"window.TEXTES = {json.dumps(langue.tout(), ensure_ascii=False)};\n")
    (INTERFACE.parent / "js" / "textes.js").write_text(contenu, encoding="utf-8")


def principal():
    ecrire_textes_interface()
    pont = Pont()
    pont._fenetre = webview.create_window(tr("app.agent_local_cockpit"), str(INTERFACE), js_api=pont,
                                         width=1600, height=950, min_size=(1100, 700),
                                         text_select=True)   # l'utilisateur veut surligner et copier les reponses (11/11/2026)
    webview.start(http_server=True)
    # Fenetre fermee : les MCP sont refermes proprement, ce qui referme aussi le navigateur de l'agent
    # (sinon Edge resterait ouvert en arriere-plan et bloquerait son profil au prochain demarrage).
    pont._fermer()


if __name__ == "__main__":
    principal()
