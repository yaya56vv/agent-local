"""Transcrit un message vocal Telegram (fichier .ogg) en texte, avec le meme modele que la dictee.

Lance par telegram_pont.py avec le Python du module dictee (modules\\dictee\\.venv), qui contient faster-whisper :
Agent Local n'a pas a charger Whisper lui-meme. Usage : python transcrire_vocal.py fichier.ogg
Reglages lus dans l'environnement (fournis par telegram_pont.py depuis config.json, rubrique "dictee") :
DICTEE_MODELE (large-v3 par defaut), DICTEE_CARTE (UUID ou numero de la carte NVIDIA ; vide = choix de CUDA),
DICTEE_LANGUE (fr par defaut). Le texte transcrit est ecrit sur la sortie standard, en UTF-8.
"""
import os
import pathlib
import sys

if os.environ.get("DICTEE_CARTE"):
    os.environ["CUDA_VISIBLE_DEVICES"] = os.environ["DICTEE_CARTE"]   # avant tout chargement de CUDA

def _bibliotheques_nvidia():
    """Sous Windows, ctranslate2 ne trouve pas seul les DLL CUDA installees par pip (nvidia-cublas-cu12,
    nvidia-cudnn-cu12) : on ajoute leurs dossiers au chemin de chargement."""
    import site
    for racine in site.getsitepackages():
        for bin_ in pathlib.Path(racine, "nvidia").glob("*/bin"):
            os.add_dll_directory(str(bin_))
            os.environ["PATH"] = str(bin_) + os.pathsep + os.environ.get("PATH", "")


_bibliotheques_nvidia()

from faster_whisper import WhisperModel  # noqa: E402  (apres le choix de la carte)

modele = WhisperModel(os.environ.get("DICTEE_MODELE") or "large-v3", device="cuda", compute_type="int8_float16")
segments, _ = modele.transcribe(sys.argv[1], language=os.environ.get("DICTEE_LANGUE") or "fr", vad_filter=True)
sys.stdout.reconfigure(encoding="utf-8")
print(" ".join(s.text.strip() for s in segments).strip())
