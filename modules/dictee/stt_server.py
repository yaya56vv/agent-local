"""Dictee d'Agent Local : maintenir Ctrl+Alt pour dicter, relacher pour transcrire (faster-whisper, sur le PC).
Le texte est colle dans la fenetre qui etait active au moment de l'appui. Rien n'est envoye sur Internet.

Reglages (fournis par le lanceur depuis config.json, rubrique "dictee") :
  DICTEE_MODELE  modele Whisper (large-v3 par defaut ; l'assistant choisit plus petit si la carte manque de memoire)
  DICTEE_CARTE   UUID ou numero de la carte NVIDIA ; "cpu" = sur le processeur ; vide = choix de CUDA
  DICTEE_LANGUE  langue (fr par defaut)
On cible une carte par son UUID plutot que par son numero : nvidia-smi les numerote par ordre de bus PCI, CUDA par
defaut de la plus rapide a la plus lente ; "0" ne designe donc pas toujours la meme carte.
"""

import sys
import os
import threading

# Sous pythonw (lance par Agent Local), il n'y a pas de console : les messages partent dans un journal, pour pouvoir
# diagnostiquer une panne. Le journal repart a zero a chaque lancement.
if sys.stdout is None or sys.stderr is None:
    _journal = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dictee.log"),
                    "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _journal

CARTE = os.environ.get("DICTEE_CARTE", "").strip()
if CARTE and CARTE.lower() != "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = CARTE   # AVANT tout chargement de CUDA

import pathlib

def _bibliotheques_nvidia():
    """Sous Windows, ctranslate2 ne trouve pas seul les DLL CUDA installees par pip (nvidia-cublas-cu12,
    nvidia-cudnn-cu12) : on ajoute leurs dossiers au chemin de chargement."""
    import site
    for racine in site.getsitepackages():
        for bin_ in pathlib.Path(racine, "nvidia").glob("*/bin"):
            os.add_dll_directory(str(bin_))
            os.environ["PATH"] = str(bin_) + os.pathsep + os.environ.get("PATH", "")


_bibliotheques_nvidia()

import time
import numpy as np
import sounddevice as sd
from pynput import keyboard
from faster_whisper import WhisperModel
import pyperclip
import ctypes
import ctypes.wintypes

# -- API Windows pour gestion du focus --
user32 = ctypes.windll.user32

def get_foreground_window():
    """Recupere le handle de la fenetre active"""
    return user32.GetForegroundWindow()

def set_foreground_window(hwnd):
    """Remet le focus sur une fenetre"""
    if hwnd and user32.IsWindow(hwnd):
        user32.SetForegroundWindow(hwnd)
        return True
    return False

def send_paste(hwnd):
    """Envoie Ctrl+V a la fenetre cible via keybd_event"""
    # Remettre le focus sur la fenetre cible
    if hwnd:
        set_foreground_window(hwnd)
        time.sleep(0.15)
    
    # Simuler Ctrl+V via keybd_event (plus fiable que pyautogui)
    VK_CONTROL = 0x11
    VK_V = 0x56
    KEYEVENTF_KEYUP = 0x0002
    
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(VK_V, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.02)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


# -- Configuration --
MODEL_SIZE = os.environ.get("DICTEE_MODELE") or "large-v3"
DEVICE = "cpu" if CARTE.lower() == "cpu" else "cuda"
COMPUTE_TYPE = "int8" if DEVICE == "cpu" else "int8_float16"  # poids en int8, calcul en float16 : ~2 Go de memoire
                                                              # video economises sur large-v3, qualite quasi identique.
LANGUAGE = os.environ.get("DICTEE_LANGUE") or "fr"
SAMPLE_RATE = 16000
CHANNELS = 1

HOTKEY_COMBO = {keyboard.Key.ctrl_l, keyboard.Key.alt_l}

# -- Etat global --
recording = False
transcribing = False
audio_buffer = []
current_keys = set()
model = None
stream = None
lock = threading.Lock()
target_window = None  # fenetre ou coller le texte


def load_model():
    global model
    print(f"[LOAD] Chargement du modele {MODEL_SIZE} sur {DEVICE} ({COMPUTE_TYPE})...", flush=True)
    start = time.time()
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    elapsed = time.time() - start
    print(f"[OK] Modele charge en {elapsed:.1f}s", flush=True)
    return model


def audio_callback(indata, frames, time_info, status):
    if recording:
        audio_buffer.append(indata.copy())


def start_recording():
    global recording, audio_buffer, stream, target_window
    with lock:
        if recording or transcribing:
            return
        recording = True
        audio_buffer = []
        # Memoriser la fenetre active MAINTENANT (avant que le focus change)
        target_window = get_foreground_window()

    print("[MIC] Enregistrement...", flush=True)
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype='float32',
        callback=audio_callback
    )
    stream.start()


def stop_recording_and_transcribe():
    global recording, transcribing, stream, target_window
    with lock:
        if not recording or transcribing:
            return
        recording = False
        transcribing = True

    if stream:
        stream.stop()
        stream.close()
        stream = None

    if not audio_buffer:
        print("[!] Aucun audio capture", flush=True)
        with lock:
            transcribing = False
        return

    print("[STT] Transcription...", flush=True)
    audio_data = np.concatenate(audio_buffer, axis=0).flatten()

    start = time.time()
    try:
        segments, info = model.transcribe(
            audio_data,
            language=LANGUAGE,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        full_text = " ".join(text_parts)
        elapsed = time.time() - start

        if full_text:
            print(f"[OK] ({elapsed:.1f}s) : {full_text}", flush=True)
            pyperclip.copy(full_text)
            # Attendre que les touches soient bien relachees
            time.sleep(0.4)
            # Coller dans la fenetre cible (pas dans le terminal!)
            send_paste(target_window)
            print(f"[PASTE] Colle dans fenetre cible", flush=True)
        else:
            print("[!] Aucun texte detecte", flush=True)
    except Exception as e:
        print(f"[ERR] {e}", flush=True)
    finally:
        with lock:
            transcribing = False


def on_press(key):
    current_keys.add(key)
    if HOTKEY_COMBO.issubset(current_keys):
        start_recording()


def on_release(key):
    was_combo_active = HOTKEY_COMBO.issubset(current_keys)
    current_keys.discard(key)

    if was_combo_active and key in HOTKEY_COMBO:
        threading.Thread(target=stop_recording_and_transcribe, daemon=True).start()


def main():
    print("=" * 60, flush=True)
    print("  STT Whisper - Speech to Text", flush=True)
    print(f"  Modele: {MODEL_SIZE} | GPU: {DEVICE} ({COMPUTE_TYPE})", flush=True)
    print(f"  Langue: {LANGUAGE}", flush=True)
    print(f"  Raccourci: Maintenir Ctrl+Alt pour dicter", flush=True)
    print("=" * 60, flush=True)

    load_model()

    print("\n[READY] Pret ! Maintenez Ctrl+Alt et parlez...", flush=True)

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            print("\n[STOP] Arret du STT", flush=True)


if __name__ == "__main__":
    main()
