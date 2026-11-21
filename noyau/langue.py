"""Langues d'Agent Local : tous les textes affiches a l'utilisateur ou envoyes au modele viennent de langues/<code>.json.

Ajouter une langue = ajouter un fichier langues/<code>.json (memes cles que fr.json, et "_nom" = nom de la langue).
La langue choisie est dans config.json (utilisateur.langue) ; a defaut, celle de Windows si un fichier existe, sinon l'anglais.
Une cle absente de la langue choisie retombe sur l'anglais, puis sur le francais (langue d'origine du projet).
Usage : t("cle", nom=valeur) ; les variables s'ecrivent {nom} dans les fichiers de langue.
"""
import ctypes
import json
import locale

import reglages

DOSSIER = reglages.INSTALLATION / "langues"
_cache = {}


def _fichier(code):
    if code not in _cache:
        chemin = DOSSIER / f"{code}.json"
        _cache[code] = json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else {}
    return _cache[code]


def disponibles():
    """{code: nom affiche} pour chaque fichier de langue present."""
    return {f.stem: _fichier(f.stem).get("_nom", f.stem) for f in sorted(DOSSIER.glob("*.json"))}


def langue_windows():
    try:
        code = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), "")[:2]
    except (AttributeError, OSError):
        code = ""
    return code if code in disponibles() else "en"


def code():
    choisie = (reglages.brut().get("utilisateur", {}).get("langue") or "").strip()
    return choisie if choisie in disponibles() else langue_windows()


def tout(code_langue=None):
    """Tous les textes de la langue (pour la fenetre), completes par l'anglais puis le francais."""
    code_langue = code_langue or code()
    return {**_fichier("fr"), **_fichier("en"), **_fichier(code_langue)}


def t(cle, **valeurs):
    texte = _fichier(code()).get(cle) or _fichier("en").get(cle) or _fichier("fr").get(cle) or cle
    return texte.format(**valeurs) if valeurs else texte
