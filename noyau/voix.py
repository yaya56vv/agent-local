"""Voix d'Agent Local : lit les reponses a voix haute avec une voix Microsoft (edge-tts), phrase par phrase.

La reponse est decoupee en phrases pendant qu'elle s'ecrit : chaque phrase terminee part a la synthese
pendant que la suivante s'ecrit. L'audio (mp3) est envoye a la fenetre, qui le joue dans l'ordre.
Note : les voix Microsoft passent par le service en ligne de Microsoft (le texte de la reponse y est envoye).
"""
import asyncio
import base64
import os
import re
import subprocess
import time

import edge_tts
import httpx
from langue import t as tr

# Voix de secours SANS Internet (facultative) : un serveur XTTS local installe a part par l'utilisateur
# (config.json : voix.xtts). Non fourni : le modele XTTS-v2 interdit tout usage commercial (THIRD_PARTY_NOTICES.md).

FIN_DE_PHRASE = re.compile(r"[.!?…:;](?=\s)|\n")


def nettoyer(texte):
    """Retire ce qui ne se prononce pas : mise en forme Markdown, adresses web, emojis."""
    t = re.sub(r"```.*?```", " ", texte, flags=re.S)                 # blocs de code
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)                    # [texte](lien) -> texte
    t = re.sub(r"https?://\S+", tr("voix.un_lien"), t)
    t = re.sub(r"^\s{0,3}(#{1,6}|>|[-*•]|\d+[.)])\s+", "", t, flags=re.M)  # titres, citations, puces
    t = re.sub(r"[*_`~|#]", "", t)
    t = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", "", t)  # emojis
    return re.sub(r"\s+", " ", t).strip()


class Voix:
    def __init__(self, conf, pousser):
        self.nom = conf.get("nom", "fr-FR-HenriNeural") if conf.get("active", True) else ""
        self.vitesse = conf.get("vitesse", "+0%")
        self.choix = conf.get("choix", {"fr-FR-HenriNeural": "Henri"})
        xtts = conf.get("xtts", {})
        self.xtts_url = xtts.get("url") or "http://127.0.0.1:8771/"
        self.xtts_serveur, self.xtts_python = xtts.get("serveur", ""), xtts.get("python", "")
        self.xtts_licence = xtts.get("licence_acceptee") is True   # case cochee dans l'assistant (CPML, non commercial)
        self.pousser = pousser          # envoie une liste d'evenements a la fenetre
        self.tampon = ""
        self.file = asyncio.Queue()
        self.generation = 0             # change a chaque arret : l'audio d'avant est abandonne
        self.erreur_signalee = False
        self.secours_jusqua = 0.0       # tant que l'heure est avant cette valeur : voix de secours locale

    def regler(self, nom):
        self.nom = nom if nom in self.choix else ""
        if not self.nom:
            self.vider()

    def ajouter(self, morceau):
        if not self.nom:
            return
        self.tampon += morceau
        fins = list(FIN_DE_PHRASE.finditer(self.tampon))
        if fins and fins[-1].end() >= 25:
            coupe = fins[-1].end()
            self._envoyer(self.tampon[:coupe])
            self.tampon = self.tampon[coupe:]

    def terminer(self):
        if self.tampon:
            self._envoyer(self.tampon)
        self.tampon = ""

    def vider(self):
        self.tampon = ""
        self.generation += 1
        while not self.file.empty():
            self.file.get_nowait()
        self.pousser([{"type": "voix_stop"}])

    def _envoyer(self, texte):
        propre = nettoyer(texte)
        if len(propre) > 1:
            self.file.put_nowait((self.generation, propre))

    async def ouvrier(self):
        while True:
            generation, phrase = await self.file.get()
            if generation != self.generation or not self.nom:
                continue
            audio, format_audio = bytearray(), "mpeg"
            if time.monotonic() >= self.secours_jusqua:
                try:
                    async for bloc in edge_tts.Communicate(phrase, self.nom, rate=self.vitesse).stream():
                        if bloc["type"] == "audio":
                            audio.extend(bloc["data"])
                    self.erreur_signalee = False
                except Exception as e:
                    audio = bytearray()
                    self.secours_jusqua = time.monotonic() + 300   # Henri reessaye dans 5 minutes
                    if not self.erreur_signalee:
                        self.erreur_signalee = True
                        self.pousser([{"type": "voix_erreur", "texte": tr("voix.voix_henri_injoignable_internet_coupe")}])
            if not audio:   # voix de secours locale XTTS, sans Internet
                try:
                    audio, format_audio = await self._secours(phrase), "wav"
                except Exception as e:
                    self.pousser([{"type": "voix_erreur", "texte": tr("voix.voix_de_secours_indisponible_le", e=e)}])
                    continue
            if generation == self.generation and audio:
                self.pousser([{"type": "voix", "audio": base64.b64encode(audio).decode(), "format": format_audio}])

    async def _secours(self, phrase):
        """Phrase lue par le serveur XTTS local (s'il est installe), qui est demarre s'il est eteint."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=3)) as client:
            try:
                await client.get(self.xtts_url, timeout=3)
            except Exception:
                if not (self.xtts_serveur and self.xtts_python and self.xtts_licence):
                    raise RuntimeError(tr("voix.aucune_voix_de_secours_hors"))
                subprocess.Popen([self.xtts_python, self.xtts_serveur], cwd=os.path.dirname(self.xtts_serveur),
                                 env={**os.environ, "XTTS_LICENCE_ACCEPTEE": "1"},
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                for _ in range(90):   # premier chargement du modele : jusqu'a 3 minutes
                    await asyncio.sleep(2)
                    try:
                        await client.get(self.xtts_url, timeout=3)
                        break
                    except Exception:
                        pass
                else:
                    raise RuntimeError(tr("voix.le_serveur_xtts_ne_demarre"))
            r = await client.post(self.xtts_url.rstrip("/") + "/wav", content=phrase.encode("utf-8"),
                                  headers={"Content-Type": "text/plain; charset=utf-8"})
            r.raise_for_status()
            return r.content
