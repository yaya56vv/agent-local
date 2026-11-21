"""Les yeux d'Agent Local (11/11/2026) : Qwen3.8-27B voit grace a son mmproj.

L'outil interne `regarder` (agent.py) designe une image ; elle entre dans la conversation comme un message
portant la cle "image" (un chemin), et llm.py la transmet au modele au moment de l'envoi, via encoder().
"""
import base64
import io
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageGrab

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
COTE_MAX = 1600            # au-dela, l'image est reduite : une capture 4K couterait des milliers de jetons
JETONS_PAR_IMAGE = 2000    # estimation prudente de ce qu'une image occupe dans la memoire du modele
DOSSIER_CAPTURES = Path(__file__).parent / "donnees" / "captures-ecran"


def capturer_ecran():
    """Photographie tous les ecrans de l'utilisateur et renvoie le chemin du fichier."""
    DOSSIER_CAPTURES.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER_CAPTURES / f"ecran_{datetime.now():%Y-%m-%d_%H%M%S}.png"
    ImageGrab.grab(all_screens=True).save(chemin)
    return str(chemin)


def encoder(chemin):
    """L'image, reduite si besoin, en base64 (format attendu par llama-server)."""
    with Image.open(chemin) as im:
        im = im.convert("RGB")
        im.thumbnail((COTE_MAX, COTE_MAX))
        tampon = io.BytesIO()
        im.save(tampon, format="JPEG", quality=92)
    return base64.b64encode(tampon.getvalue()).decode()
