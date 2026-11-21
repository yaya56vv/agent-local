"""Le classeur de competences d'Agent Local : des fiches de savoir-faire reutilisables.

Format standard (le meme qu'Hermes / agentskills) : un dossier par competence,
contenant un SKILL.md qui commence par un en-tete name / description.
Une competence supprimee part dans _corbeille (jamais effacee).
"""
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path

from memoire import MOTS_VIDES
from langue import t as tr

CLASSEUR = Path(__file__).parent / "competences"
CORBEILLE = CLASSEUR / "_corbeille"
NOM_VALIDE = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")


def installer_exemples(code_langue):
    """Premier lancement : copie les fiches d'exemple de la langue choisie dans le classeur, s'il est vide."""
    import shutil
    if CLASSEUR.exists() and any(CLASSEUR.glob("*/SKILL.md")):
        return 0
    source = Path(__file__).parent / "competences-exemples" / code_langue
    if not source.exists():
        source = Path(__file__).parent / "competences-exemples" / "en"
    shutil.copytree(source, CLASSEUR, dirs_exist_ok=True)
    return len(list(CLASSEUR.glob("*/SKILL.md")))


def _simple(texte):
    t = unicodedata.normalize("NFKD", texte.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def nom_propre(nom):
    """'Ranger les Téléchargements' -> 'ranger-les-telechargements'"""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", _simple(nom))).strip("-")[:60]


def _lire_fichier(dossier):
    fichier = dossier / "SKILL.md"
    if not fichier.exists():
        return None
    texte = fichier.read_text(encoding="utf-8")
    entete, corps = {}, texte
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", texte, flags=re.S)
    if m:
        for ligne in m.group(1).splitlines():
            if ":" in ligne:
                cle, valeur = ligne.split(":", 1)
                entete[cle.strip()] = valeur.strip().strip('"')
        corps = m.group(2)
    return {"nom": entete.get("name", dossier.name), "description": entete.get("description", ""),
            "maj": datetime.fromtimestamp(fichier.stat().st_mtime).isoformat(timespec="seconds"),
            "contenu": corps.strip()}


def lister():
    CLASSEUR.mkdir(exist_ok=True)
    fiches = [_lire_fichier(d) for d in sorted(CLASSEUR.iterdir()) if d.is_dir() and not d.name.startswith("_")]
    return [f for f in fiches if f]


def lire(nom):
    return _lire_fichier(CLASSEUR / nom_propre(nom))


def ecrire(nom, description, contenu):
    """Cree ou remplace une competence. Renvoie (nom_propre, cree: bool)."""
    n = nom_propre(nom)
    if not NOM_VALIDE.match(n):
        raise ValueError(tr("competences.nom_de_competence_invalide_lettres"))
    dossier = CLASSEUR / n
    cree = not (dossier / "SKILL.md").exists()
    dossier.mkdir(parents=True, exist_ok=True)
    description = " ".join(description.split()).replace('"', "'")
    (dossier / "SKILL.md").write_text(f'---\nname: {n}\ndescription: "{description}"\n---\n\n{contenu.strip()}\n',
                                      encoding="utf-8")
    return n, cree


def supprimer(nom):
    n = nom_propre(nom)
    dossier = CLASSEUR / n
    if not dossier.is_dir():
        return False
    CORBEILLE.mkdir(parents=True, exist_ok=True)
    shutil.move(str(dossier), str(CORBEILLE / f"{n}_{datetime.now():%Y%m%d-%H%M%S}"))
    return True


def rechercher(texte, limite=2, seuil=2):
    """Competences les plus proches d'une demande (mots en commun, le nom et la description comptent double)."""
    mots = {m for m in re.findall(r"\w+", _simple(texte)) if len(m) > 2 and m not in MOTS_VIDES}
    if not mots:
        return []
    notes = []
    for f in lister():
        tete = set(re.findall(r"\w+", _simple(f["nom"].replace("-", " ") + " " + f["description"])))
        corps = set(re.findall(r"\w+", _simple(f["contenu"])))
        note = sum(2 if any(t.startswith(m[:5]) for t in tete) else (1 if any(c.startswith(m[:5]) for c in corps) else 0)
                   for m in mots)
        if note >= seuil:
            notes.append((note, f))
    return [f for _, f in sorted(notes, key=lambda x: -x[0])[:limite]]
