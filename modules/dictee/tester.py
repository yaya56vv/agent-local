"""Essai de la dictee (bouton « Tester » de l'assistant) : enregistre quelques secondes au micro puis transcrit.
Avec --charger : telecharge seulement le modele Whisper (installation), sans micro."""
import os
import sys

sys.argv += [] if len(sys.argv) > 1 else ["4"]
CARTE = os.environ.get("DICTEE_CARTE", "").strip()
if CARTE and CARTE.lower() != "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = CARTE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stt_server  # noqa: E402  (charge les bibliotheques NVIDIA et lit les memes reglages)

modele = stt_server.load_model()
if sys.argv[1] == "--charger":
    print("modele pret")
    sys.exit(0)
import sounddevice as sd  # noqa: E402

secondes = float(sys.argv[1])
audio = sd.rec(int(secondes * stt_server.SAMPLE_RATE), samplerate=stt_server.SAMPLE_RATE, channels=1, dtype="float32")
sd.wait()
segments, _ = modele.transcribe(audio.flatten(), language=stt_server.LANGUAGE, vad_filter=True)
sys.stdout.reconfigure(encoding="utf-8")
print(" ".join(s.text.strip() for s in segments).strip() or "(rien entendu)")
