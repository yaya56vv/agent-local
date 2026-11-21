"""Voix de secours hors ligne d'Agent Local : petit serveur XTTS-v2 (Coqui TTS) sur 127.0.0.1.

FACULTATIF, installe par l'assistant seulement si l'utilisateur a coche « Usage personnel et non commercial uniquement » :
le modele XTTS-v2 est sous Coqui Public Model License (CPML), qui interdit tout usage commercial. Agent Local transmet
cette acceptation par la variable XTTS_LICENCE_ACCEPTEE=1 ; sans elle, ce serveur refuse de demarrer.

Routes : GET / -> « pret » ; POST /wav (texte UTF-8 dans le corps) -> son WAV, sans le jouer (la fenetre d'Agent Local le joue).
Reglages : XTTS_PORT (8771), XTTS_VOIX (une voix integree au modele, par defaut « Ludvig Milivoj »), XTTS_LANGUE (fr).
"""
import io
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if os.environ.get("XTTS_LICENCE_ACCEPTEE") != "1":
    sys.exit("Licence CPML (usage non commercial) non acceptee dans Agent Local : serveur XTTS non demarre.")
os.environ["COQUI_TOS_AGREED"] = "1"   # acceptation donnee par l'utilisateur dans l'assistant, pas d'office

import torch  # noqa: E402
from TTS.api import TTS  # noqa: E402

PORT = int(os.environ.get("XTTS_PORT", "8771"))
VOIX = os.environ.get("XTTS_VOIX", "Ludvig Milivoj")
LANGUE = os.environ.get("XTTS_LANGUE", "fr")
MOTEUR = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda" if torch.cuda.is_available() else "cpu")


class Requete(BaseHTTPRequestHandler):
    def _repondre(self, code, contenu, type_):
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(contenu)))
        self.end_headers()
        self.wfile.write(contenu)

    def do_GET(self):
        self._repondre(200, "pret".encode("utf-8"), "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path.rstrip("/") != "/wav":
            return self._repondre(404, b"route inconnue", "text/plain")
        texte = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8", "replace").strip()
        if not texte:
            return self._repondre(400, b"texte vide", "text/plain")
        tampon = io.BytesIO()
        import soundfile
        audio = MOTEUR.tts(text=texte, speaker=VOIX, language=LANGUE)
        soundfile.write(tampon, audio, MOTEUR.synthesizer.output_sample_rate, format="WAV")
        self._repondre(200, tampon.getvalue(), "audio/wav")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Requete).serve_forever()
