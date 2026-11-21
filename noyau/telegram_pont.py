"""Telegram : piloter Agent Local depuis le telephone (12/11/2026).

Le robot (cree par l'utilisateur avec @BotFather) n'obeit qu'a son proprietaire. Tant qu'aucun proprietaire n'est enregistre, la fenetre
d'Agent Local affiche un code a 6 chiffres ; le premier compte qui l'envoie au robot devient le proprietaire
(enregistre dans donnees/telegram.json). Tout autre compte est ignore, sans reponse.
La cle du robot reste dans telegram.env, dans le dossier de secrets (saisie dans l'assistant), jamais dans le code.
Module desactive par defaut (config.json : modules.telegram).
Messages texte = missions ; messages vocaux = transcrits par Whisper (module dictee) puis traites comme du texte.
Commandes : /nouvelle (conversation neuve), /stop (arreter la mission).
"""
import asyncio
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

import reglages
from langue import t as tr

ICI = Path(__file__).parent
FICHIER_CLE = reglages.chemin_secret("telegram.env")
FICHIER_PROPRIETAIRE = ICI / "donnees" / "telegram.json"
LONGUEUR_MAX = 4000   # Telegram refuse les messages de plus de 4 096 caracteres


def _lire_cle():
    if not FICHIER_CLE.is_file():
        return None
    for ligne in FICHIER_CLE.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("TELEGRAM_BOT_TOKEN="):
            return ligne.split("=", 1)[1].strip() or None
    return None


class Telegram:
    def __init__(self, pont):
        self.pont = pont
        modules = pont._config.get("modules", {})
        self.cle = _lire_cle() if modules.get("telegram") is True else None
        self.dictee = pont._config.get("dictee", {}) if modules.get("dictee") is True else None
        self.proprietaire = None
        if FICHIER_PROPRIETAIRE.is_file():
            self.proprietaire = json.loads(FICHIER_PROPRIETAIRE.read_text(encoding="utf-8")).get("proprietaire")
        self.code, self.code_expire = None, 0.0
        if not self.proprietaire:
            self._nouveau_code()
        self._client = None
        self._demandes = {}   # id d'appel -> id du message Telegram portant les boutons

    def _nouveau_code(self):
        """Code d'appairage a 6 chiffres, valable 10 minutes (version publique : un code qui traine ne sert plus)."""
        self.code, self.code_expire = f"{secrets.randbelow(10**6):06d}", time.time() + 600

    def etat(self):
        if not self.proprietaire and time.time() > self.code_expire:
            self._nouveau_code()
        return {"actif": bool(self.cle), "appaire": bool(self.proprietaire), "code": self.code}

    # --- envoi -------------------------------------------------------------
    async def _api(self, methode, **params):
        r = await self._client.post(f"https://api.telegram.org/bot{self.cle}/{methode}", **params)
        return r.json()

    async def envoyer_texte(self, texte, boutons=None):
        if not (self.cle and self.proprietaire and self._client):
            return None
        texte = texte or tr("telegram_pont.reponse_vide")
        morceaux = [texte[i:i + LONGUEUR_MAX] for i in range(0, len(texte), LONGUEUR_MAX)]
        reponse = None
        for i, morceau in enumerate(morceaux):
            donnees = {"chat_id": self.proprietaire, "text": morceau}
            if boutons and i == len(morceaux) - 1:
                donnees["reply_markup"] = {"inline_keyboard": [boutons]}
            reponse = await self._api("sendMessage", json=donnees)
        return reponse

    async def envoyer_fichier(self, nom, contenu):
        if self.cle and self.proprietaire and self._client:
            await self._api("sendDocument", data={"chat_id": self.proprietaire},
                            files={"document": (nom, contenu.encode("utf-8"))})

    async def demander_accord(self, infos):
        """Boutons Autoriser / Refuser sur le telephone ; la fenetre du PC garde aussi les siens."""
        texte = (tr("telegram_pont.agent_local_demande_ton_accord", v1=infos['serveur'], v2=infos['outil'], v3=json.dumps(infos.get('arguments', {}), ensure_ascii=False)[:1500])
                 + (f"\n\n{infos['motif']}" if infos.get("motif") else ""))
        r = await self.envoyer_texte(texte, boutons=[{"text": "✓ Autoriser", "callback_data": f"oui:{infos['id']}"},
                                                     {"text": "✕ Refuser", "callback_data": f"non:{infos['id']}"}])
        if r and r.get("ok"):
            self._demandes[infos["id"]] = r["result"]["message_id"]

    async def accord_donne(self, id_appel, accorde):
        """L'accord a ete donne (au telephone ou au PC) : les boutons disparaissent du message."""
        message = self._demandes.pop(id_appel, None)
        if message and self._client:
            await self._api("editMessageReplyMarkup", json={"chat_id": self.proprietaire, "message_id": message})
            await self.envoyer_texte("✓ autorise" if accorde else "✕ refuse")

    # --- reception ---------------------------------------------------------
    async def tourner(self):
        if not self.cle:
            return
        decalage = 0
        async with httpx.AsyncClient(timeout=httpx.Timeout(45, connect=15)) as self._client:
            await self._proposer_reprise()
            while True:
                try:
                    r = await self._api("getUpdates", json={"offset": decalage, "timeout": 30,
                                                            "allowed_updates": ["message", "callback_query"]})
                    for maj in r.get("result", []):
                        decalage = maj["update_id"] + 1
                        try:
                            await self._traiter(maj)
                        except Exception as e:
                            await self.pont._signaler({"type": "erreur", "texte": f"Telegram : {e}"})
                except (httpx.HTTPError, ValueError):
                    await asyncio.sleep(10)   # pas d'Internet ou Telegram injoignable : on reessaie

    async def _traiter(self, maj):
        if "callback_query" in maj:
            q = maj["callback_query"]
            await self._api("answerCallbackQuery", json={"callback_query_id": q["id"]})
            if q["from"]["id"] == self.proprietaire and ":" in q.get("data", ""):
                choix, ident = q["data"].split(":", 1)
                if choix in ("oui", "non"):
                    self.pont.repondre_autorisation(ident, choix == "oui")
                else:   # reprendre / abandonner une mission interrompue
                    await self._api("editMessageReplyMarkup", json={"chat_id": self.proprietaire,
                                                                    "message_id": q["message"]["message_id"]})
                    if choix == "reprendre":
                        await self.envoyer_texte(tr("telegram_pont.je_reprends_la_mission"))
                        asyncio.create_task(self.pont.reprendre_mission_telephone(int(ident)))
                    else:
                        self.pont.abandonner_mission(int(ident))
                        await self.envoyer_texte(tr("telegram_pont.je_l_abandonne"))
            return
        message = maj.get("message") or {}
        expediteur = (message.get("from") or {}).get("id")
        texte = (message.get("text") or "").strip()
        if not self.proprietaire:   # appairage : le premier qui envoie le bon code devient le proprietaire
            if self.code and self.code in texte and time.time() <= self.code_expire:
                self.proprietaire, self.code = expediteur, None
                FICHIER_PROPRIETAIRE.parent.mkdir(exist_ok=True)
                FICHIER_PROPRIETAIRE.write_text(json.dumps({"proprietaire": expediteur}), encoding="utf-8")
                await self.envoyer_texte(tr("telegram_pont.c_est_fait_je_n"))
                await self.pont._signaler({"type": "telegram", "texte": tr("telegram_pont.telegram_appaire_le_robot_n")})
            return
        if expediteur != self.proprietaire:
            return   # un inconnu : ignore, sans reponse
        if message.get("voice") or message.get("audio"):
            await self.envoyer_texte(tr("telegram_pont.message_vocal_recu_je_le"))
            texte = await self._transcrire(message.get("voice") or message.get("audio"))
            if not texte:
                await self.envoyer_texte(tr("telegram_pont.je_n_ai_pas_reussi"))
                return
            await self.envoyer_texte(tr("telegram_pont.j_ai_compris", texte=texte))
        if not texte:
            await self.envoyer_texte(tr("telegram_pont.je_ne_sais_traiter_que"))
            return
        if texte in ("/start", "/aide"):
            await self.envoyer_texte(tr("telegram_pont.envoie_moi_une_mission_nouvelle"))
        elif texte == "/stop":
            self.pont.arreter()
            await self.envoyer_texte(tr("telegram_pont.arret_demande"))
        elif texte == "/nouvelle":
            r = self.pont.nouvelle_conversation()
            await self.envoyer_texte(tr("telegram_pont.nouvelle_conversation") if r["ok"] else f"⚠ {r['raison']}")
            await self.pont._signaler({"type": "nouvelle_conversation"})
        else:
            asyncio.create_task(self.pont.mission_telephone(texte))

    async def _proposer_reprise(self):
        """Au demarrage : si la derniere mission s'est arretee avant la fin, proposer de la reprendre."""
        mi = self.pont.mission_interrompue() if self.proprietaire else None
        if mi:
            await self.envoyer_texte(tr("telegram_pont.ta_derniere_mission_s_est", v1=mi['quand'][:16].replace('T', ' a '), v2=mi['demande'][:500]),
                                     boutons=[{"text": "▶ Reprendre", "callback_data": f"reprendre:{mi['id']}"},
                                              {"text": "Abandonner", "callback_data": f"abandonner:{mi['id']}"}])

    async def _transcrire(self, fichier):
        infos = await self._api("getFile", json={"file_id": fichier["file_id"]})
        audio = await self._client.get(f"https://api.telegram.org/file/bot{self.cle}/{infos['result']['file_path']}")
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio.content)
        try:
            if not self.dictee:
                return ""
            env = {**os.environ, "DICTEE_MODELE": self.dictee.get("modele", "large-v3"),
                   "DICTEE_CARTE": str(self.dictee.get("carte", "")), "DICTEE_LANGUE": self.dictee.get("langue", "fr")}
            r = await asyncio.to_thread(subprocess.run, [self.dictee["python"], str(ICI / "transcrire_vocal.py"), f.name],
                                        env=env, capture_output=True, encoding="utf-8", errors="replace", timeout=180,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return r.stdout.strip() if r.returncode == 0 else ""
        finally:
            Path(f.name).unlink(missing_ok=True)
