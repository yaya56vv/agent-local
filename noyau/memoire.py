"""Le carnet d'Agent Local : souvenirs durables + fil des conversations (SQLite).

Recherche plein texte en francais (FTS5, insensible aux accents et majuscules),
sans aucun modele a charger. Utilise a la fois par le noyau et par le MCP memoire.
"""
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from langue import t as tr

BASE = Path(__file__).parent / "donnees" / "memoire.db"
MOTS_VIDES = set("""le la les un une des de du au aux et ou mais donc or ni car que qui quoi dont ce cet
cette ces mon ma mes ton ta tes son sa ses notre nos votre vos leur leurs je tu il elle on nous vous ils
elles me te se lui y en ne pas plus est sont suis es etre avoir ai as a avons avez ont fait faire dans
sur sous pour par avec sans chez vers comme tout tous toute toutes bien tres peux peut veux veut""".split())

SCHEMA = """
CREATE TABLE IF NOT EXISTS souvenirs (
  id INTEGER PRIMARY KEY, texte TEXT NOT NULL, categorie TEXT NOT NULL DEFAULT 'divers',
  essentiel INTEGER NOT NULL DEFAULT 0, cree TEXT NOT NULL, maj TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS souvenirs_fts USING fts5(
  texte, categorie, content='souvenirs', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS s_ai AFTER INSERT ON souvenirs BEGIN
  INSERT INTO souvenirs_fts(rowid, texte, categorie) VALUES (new.id, new.texte, new.categorie); END;
CREATE TRIGGER IF NOT EXISTS s_ad AFTER DELETE ON souvenirs BEGIN
  INSERT INTO souvenirs_fts(souvenirs_fts, rowid, texte, categorie) VALUES ('delete', old.id, old.texte, old.categorie); END;
CREATE TRIGGER IF NOT EXISTS s_au AFTER UPDATE ON souvenirs BEGIN
  INSERT INTO souvenirs_fts(souvenirs_fts, rowid, texte, categorie) VALUES ('delete', old.id, old.texte, old.categorie);
  INSERT INTO souvenirs_fts(rowid, texte, categorie) VALUES (new.id, new.texte, new.categorie); END;
CREATE TABLE IF NOT EXISTS conversations (id INTEGER PRIMARY KEY, debut TEXT NOT NULL, titre TEXT);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY, conversation_id INTEGER NOT NULL REFERENCES conversations(id),
  role TEXT NOT NULL, contenu TEXT, extra TEXT, ts TEXT NOT NULL);
"""


def _maintenant():
    return datetime.now().isoformat(timespec="seconds")


def connexion():
    BASE.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(BASE)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    return c


# ---------- souvenirs ----------
def retenir(texte, categorie="divers", essentiel=False):
    with connexion() as c:
        cur = c.execute("INSERT INTO souvenirs(texte, categorie, essentiel, cree, maj) VALUES (?,?,?,?,?)",
                        (texte.strip(), categorie.strip().lower() or "divers", int(essentiel), _maintenant(), _maintenant()))
        return cur.lastrowid


def oublier(id_souvenir):
    with connexion() as c:
        ligne = c.execute("SELECT texte FROM souvenirs WHERE id=?", (id_souvenir,)).fetchone()
        if not ligne:
            return None
        c.execute("DELETE FROM souvenirs WHERE id=?", (id_souvenir,))
        return ligne["texte"]


def oublier_tout():
    """Rubrique « Mes donnees » des Reglages : vide tout le carnet (apres confirmation dans la fenetre)."""
    with connexion() as c:
        n = c.execute("SELECT COUNT(*) FROM souvenirs").fetchone()[0]
        c.execute("DELETE FROM souvenirs")
    return n


def vider_conversations():
    """Rubrique « Mes donnees » des Reglages : efface l'historique des conversations (apres confirmation)."""
    with connexion() as c:
        n = c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        c.execute("DELETE FROM messages")
        c.execute("DELETE FROM conversations")
    return n


def _requete_fts(texte):
    mots = {m for m in re.findall(r"\w+", texte.lower()) if len(m) > 2 and m not in MOTS_VIDES}
    return " OR ".join(f'"{m}"*' for m in sorted(mots)) if mots else None


def rechercher(texte, limite=8):
    requete = _requete_fts(texte)
    if not requete:
        return []
    with connexion() as c:
        lignes = c.execute("""SELECT s.* FROM souvenirs_fts f JOIN souvenirs s ON s.id = f.rowid
                              WHERE souvenirs_fts MATCH ? ORDER BY bm25(souvenirs_fts) LIMIT ?""",
                           (requete, limite)).fetchall()
    return [dict(l) for l in lignes]


def lister(categorie=None):
    with connexion() as c:
        if categorie:
            lignes = c.execute("SELECT * FROM souvenirs WHERE categorie=? ORDER BY maj DESC", (categorie.lower(),))
        else:
            lignes = c.execute("SELECT * FROM souvenirs ORDER BY categorie, maj DESC")
        return [dict(l) for l in lignes.fetchall()]


def essentiels():
    with connexion() as c:
        return [dict(l) for l in c.execute("SELECT * FROM souvenirs WHERE essentiel=1 ORDER BY categorie, id")]


# ---------- fil des conversations ----------
def nouvelle_conversation():
    with connexion() as c:
        return c.execute("INSERT INTO conversations(debut) VALUES (?)", (_maintenant(),)).lastrowid


def enregistrer_message(conversation_id, message):
    # interne (relecture) et image (outil regarder) sont gardes pour qu'une conversation reprise soit relue a l'identique
    extra = {k: v for k, v in message.items() if k in ("tool_calls", "tool_call_id", "interne", "image")}
    with connexion() as c:
        c.execute("INSERT INTO messages(conversation_id, role, contenu, extra, ts) VALUES (?,?,?,?,?)",
                  (conversation_id, message["role"], message.get("content"),
                   json.dumps(extra) if extra else None, _maintenant()))
        if message["role"] == "user" and not extra and message.get("content"):   # titre = premiere demande de l'utilisateur
            c.execute("UPDATE conversations SET titre=? WHERE id=? AND titre IS NULL",
                      (_titre(message["content"]), conversation_id))


def _titre(texte):
    texte = re.sub(r"^\[Tache planifiee : [^\]]*\]\s*", "", " ".join(str(texte).split()))
    return texte[:80] + ("…" if len(texte) > 80 else "")


# ---------- historique des conversations (12/11/2026) ----------
def lister_conversations(limite=200):
    """Les conversations qui contiennent au moins un message, la plus recemment utilisee d'abord. Les anciennes,
    sans titre enregistre, prennent leur premiere demande comme titre."""
    with connexion() as c:
        lignes = c.execute("""
            SELECT co.id, co.debut, co.titre, COUNT(m.id) AS nombre, MAX(m.ts) AS derniere,
                   (SELECT contenu FROM messages WHERE conversation_id = co.id AND role = 'user' AND extra IS NULL
                    ORDER BY id LIMIT 1) AS premiere
            FROM conversations co JOIN messages m ON m.conversation_id = co.id
            GROUP BY co.id ORDER BY derniere DESC LIMIT ?""", (limite,)).fetchall()
    return [{"id": l["id"], "debut": l["debut"], "derniere": l["derniere"], "nombre": l["nombre"],
             "titre": l["titre"] or (_titre(l["premiere"]) if l["premiere"] else tr("memoire.sans_demande"))} for l in lignes]


def lire_conversation(conversation_id):
    """Les messages d'une conversation, sous la forme exacte que l'agent garde dans son historique."""
    with connexion() as c:
        lignes = c.execute("SELECT role, contenu, extra FROM messages WHERE conversation_id=? ORDER BY id",
                           (conversation_id,)).fetchall()
    return [{"role": l["role"], "content": l["contenu"], **(json.loads(l["extra"]) if l["extra"] else {})}
            for l in lignes]


def mission_interrompue(exclure=None, heures=48):
    """Reprise apres plantage (12/11/2026) : la derniere conversation utilisee, si sa mission
    ne s'est pas terminee (le dernier message n'est pas une reponse finale du chef) et date de moins de 48 h."""
    with connexion() as c:
        co = c.execute("""SELECT conversation_id, MAX(ts) AS derniere FROM messages WHERE conversation_id != ?
                          GROUP BY conversation_id ORDER BY derniere DESC LIMIT 1""", (exclure or 0,)).fetchone()
        if not co or datetime.fromisoformat(co["derniere"]) < datetime.now() - timedelta(hours=heures):
            return None
        dernier = c.execute("SELECT role, extra FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 1",
                            (co["conversation_id"],)).fetchone()
        if dernier["role"] == "assistant" and "tool_calls" not in json.loads(dernier["extra"] or "{}"):
            return None   # mission terminee normalement
        demande = c.execute("""SELECT contenu FROM messages WHERE conversation_id=? AND role='user' AND extra IS NULL
                               ORDER BY id DESC LIMIT 1""", (co["conversation_id"],)).fetchone()
    if not demande or not demande["contenu"]:
        return None
    return {"id": co["conversation_id"], "demande": demande["contenu"], "quand": co["derniere"]}
