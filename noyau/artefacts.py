"""Artefacts d'Agent Local : les contenus longs que l'agent ecrit pour l'utilisateur (lettres, documents, programmes, pages).

Ranges dans la base du carnet (donnees/memoire.db), avec un numero de version a chaque modification.
Enregistrement en fichier dans Documents\\Agent Local, sans jamais ecraser un fichier existant.
"""
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import reglages
from memoire import connexion

TYPES = ("texte", "code", "html")
EXTENSIONS = {"python": ".py", "javascript": ".js", "typescript": ".ts", "powershell": ".ps1", "bash": ".sh",
              "html": ".html", "css": ".css", "json": ".json", "sql": ".sql", "java": ".java", "c": ".c",
              "cpp": ".cpp", "csharp": ".cs", "batch": ".bat", "yaml": ".yaml", "markdown": ".md"}
SCHEMA = """CREATE TABLE IF NOT EXISTS artefacts (
  id INTEGER PRIMARY KEY, titre TEXT NOT NULL, type TEXT NOT NULL, langage TEXT,
  contenu TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, cree TEXT NOT NULL, maj TEXT NOT NULL)"""


def _cnx():
    c = connexion()
    c.execute(SCHEMA)
    return c


def _maintenant():
    return datetime.now().isoformat(timespec="seconds")


def creer(titre, type_, contenu, langage=""):
    type_ = type_ if type_ in TYPES else "texte"
    with _cnx() as c:
        return c.execute("INSERT INTO artefacts(titre, type, langage, contenu, cree, maj) VALUES (?,?,?,?,?,?)",
                         (titre.strip() or "Sans titre", type_, (langage or "").strip().lower(), contenu,
                          _maintenant(), _maintenant())).lastrowid


def modifier(id_artefact, contenu, titre=None):
    with _cnx() as c:
        ligne = c.execute("SELECT version, titre FROM artefacts WHERE id=?", (id_artefact,)).fetchone()
        if not ligne:
            return None
        version = ligne["version"] + 1
        c.execute("UPDATE artefacts SET contenu=?, titre=?, version=?, maj=? WHERE id=?",
                  (contenu, (titre or ligne["titre"]).strip(), version, _maintenant(), id_artefact))
        return version


def lire(id_artefact):
    with _cnx() as c:
        ligne = c.execute("SELECT * FROM artefacts WHERE id=?", (id_artefact,)).fetchone()
        return dict(ligne) if ligne else None


def lister(limite=30):
    with _cnx() as c:
        return [dict(l) for l in c.execute(
            "SELECT id, titre, type, langage, version, maj FROM artefacts ORDER BY maj DESC LIMIT ?", (limite,))]


def _extension(a):
    if a["type"] == "html":
        return ".html"
    if a["type"] == "code":
        return EXTENSIONS.get(a["langage"] or "", ".txt")
    return ".md"


def enregistrer_fichier(id_artefact):
    """Ecrit l'artefact dans le dossier de sortie choisi par l'utilisateur. Renvoie le chemin cree (jamais d'ecrasement)."""
    a = lire(id_artefact)
    if not a:
        return None
    sortie = Path(reglages.charger()["utilisateur"]["dossier_sortie"])
    sortie.mkdir(parents=True, exist_ok=True)
    base = unicodedata.normalize("NFKD", a["titre"]).encode("ascii", "ignore").decode()
    base = re.sub(r"[^\w\- ]+", "", base).strip().replace(" ", "_")[:60] or f"artefact_{a['id']}"
    chemin, n = sortie / f"{base}{_extension(a)}", 2
    while chemin.exists():
        chemin, n = sortie / f"{base}_{n}{_extension(a)}", n + 1
    chemin.write_text(a["contenu"], encoding="utf-8")
    return str(chemin)
