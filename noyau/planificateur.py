"""Planificateur d'Agent Local : des taches qui se lancent toutes seules a l'heure dite.

Rythmes : quotidien (heure), hebdomadaire (jour + heure), intervalle (toutes les N minutes), une_fois (date + heure).
Les taches sont rangees dans la base du carnet (donnees/memoire.db). Elles ne tournent que fenetre ouverte :
une tache manquee pendant que la fenetre etait fermee n'est pas rattrapee, elle reprend a sa prochaine heure.
"""
from datetime import datetime, timedelta

from memoire import connexion
from langue import t as tr

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
SCHEMA = """CREATE TABLE IF NOT EXISTS taches (
  id INTEGER PRIMARY KEY, titre TEXT NOT NULL, consigne TEXT NOT NULL, rythme TEXT NOT NULL,
  heure TEXT, jour TEXT, minutes INTEGER, date TEXT,
  prochaine TEXT, derniere TEXT, dernier_resultat TEXT, active INTEGER NOT NULL DEFAULT 1, creee TEXT NOT NULL)"""


def _cnx():
    c = connexion()
    c.execute(SCHEMA)
    return c


def _hm(heure):
    """'8:00', '08:30', '8h', '8h15' -> (heures, minutes)"""
    parties = str(heure).strip().lower().replace("h", ":").split(":")
    try:
        h = int(parties[0])
        m = int(parties[1]) if len(parties) > 1 and parties[1] else 0
    except ValueError:
        raise ValueError(tr("planificateur.heure_invalide_attendu_hh_mm"))
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(tr("planificateur.heure_invalide_attendu_hh_mm"))
    return h, m


def prochaine_execution(t, apres=None):
    """Prochaine date d'execution d'une tache (dict), strictement apres `apres`."""
    apres = apres or datetime.now()
    if t["rythme"] == "intervalle":
        return apres + timedelta(minutes=max(5, int(t["minutes"])))
    if t["rythme"] == "une_fois":
        d = datetime.fromisoformat(str(t["date"]).replace(" ", "T"))
        return d if d > apres else None
    h, m = _hm(t["heure"])
    candidat = apres.replace(hour=h, minute=m, second=0, microsecond=0)
    if t["rythme"] == "quotidien":
        return candidat if candidat > apres else candidat + timedelta(days=1)
    if t["rythme"] == "hebdomadaire":
        cible = JOURS.index(str(t["jour"]).lower().strip())
        candidat += timedelta(days=(cible - candidat.weekday()) % 7)
        return candidat if candidat > apres else candidat + timedelta(days=7)
    raise ValueError(tr("planificateur.rythme_inconnu_quotidien_hebdomadaire_intervalle"))


def decrire(t):
    r = t["rythme"]
    if r == "quotidien":
        return tr("planificateur.chaque_jour_a", v1=t['heure'])
    if r == "hebdomadaire":
        return f"chaque {t['jour']} a {t['heure']}"
    if r == "intervalle":
        return tr("planificateur.toutes_les_minutes", v1=t['minutes'])
    return tr("planificateur.une_fois_le", v1=t['date'])


def ajouter(titre, consigne, rythme, heure=None, jour=None, minutes=None, date=None):
    t = {"rythme": rythme, "heure": heure, "jour": jour, "minutes": minutes, "date": date}
    if rythme == "hebdomadaire" and str(jour).lower().strip() not in JOURS:
        raise ValueError(tr("planificateur.jour_invalide_lundi_dimanche"))
    prochaine = prochaine_execution(t)
    if prochaine is None:
        raise ValueError(tr("planificateur.cette_date_est_deja_passee"))
    with _cnx() as c:
        cur = c.execute("""INSERT INTO taches(titre, consigne, rythme, heure, jour, minutes, date, prochaine, creee)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (titre.strip(), consigne.strip(), rythme, heure, jour, minutes, date,
                         prochaine.isoformat(timespec="minutes"), datetime.now().isoformat(timespec="seconds")))
        return cur.lastrowid, prochaine


def lister():
    with _cnx() as c:
        taches = [dict(l) for l in c.execute("SELECT * FROM taches WHERE active=1 ORDER BY prochaine")]
    for t in taches:
        t["rythme_lisible"] = decrire(t)
    return taches


def supprimer(id_tache):
    with _cnx() as c:
        ligne = c.execute("SELECT titre FROM taches WHERE id=? AND active=1", (id_tache,)).fetchone()
        if not ligne:
            return None
        c.execute("UPDATE taches SET active=0 WHERE id=?", (id_tache,))
        return ligne["titre"]


def echues(maintenant=None):
    maintenant = (maintenant or datetime.now()).isoformat(timespec="minutes")
    with _cnx() as c:
        return [dict(l) for l in c.execute("SELECT * FROM taches WHERE active=1 AND prochaine <= ? ORDER BY prochaine",
                                           (maintenant,))]


def marquer_executee(t, resultat):
    suivante = prochaine_execution(t)
    with _cnx() as c:
        c.execute("UPDATE taches SET derniere=?, dernier_resultat=?, prochaine=?, active=? WHERE id=?",
                  (datetime.now().isoformat(timespec="minutes"), (resultat or "")[:500],
                   suivante.isoformat(timespec="minutes") if suivante else None, 1 if suivante else 0, t["id"]))


def recaler_manquees():
    """Au demarrage : une tache dont l'heure est passee depuis plus de 10 minutes n'est pas rattrapee."""
    limite = datetime.now() - timedelta(minutes=10)
    with _cnx() as c:
        for l in c.execute("SELECT * FROM taches WHERE active=1 AND prochaine < ?",
                           (limite.isoformat(timespec="minutes"),)).fetchall():
            t = dict(l)
            suivante = prochaine_execution(t)
            c.execute("UPDATE taches SET prochaine=?, active=? WHERE id=?",
                      (suivante.isoformat(timespec="minutes") if suivante else None, 1 if suivante else 0, t["id"]))
