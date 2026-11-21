"""Garde-fou du navigateur d'Agent Local (outils Playwright).

Pour chaque action, decide : "auto" (libre), "demander" (clic de l'utilisateur) ou "interdit", avec un motif.
Le texte examine combine la description donnee par l'agent ET la vraie etiquette de l'element dans la page
(derniere capture de la page), pour qu'un bouton "Envoyer" ne passe pas sous le nom de "bouton suivant".
"""
import re
import unicodedata

from reseau import adresse_locale
from langue import t as tr

INTERDITS = {
    "browser_run_code_unsafe": tr("garde_navigateur.execution_de_code_arbitraire_dans"),
    "browser_evaluate": tr("garde_navigateur.execution_de_code_javascript_dans"),
    "browser_drop": tr("garde_navigateur.depot_de_fichiers_de_l"),
}
ENGAGEMENT = ("envoy", "valid", "pay", "paiement", "command", "achet", "achat", "confirm", "inscri", "souscri",
              "reserv", "publi", "poster", "soumet", "transf", "virement", "sign", "accept", "supprim", "effac",
              "abonn", "regler", "terminer", "finaliser", "submit", "send", "buy", "order", "checkout", "register",
              "subscribe", "book", "publish", "delete", "remove", "agree", "purchase", "donat", "don ")
SECRETS = ("mot de passe", "password", "passwd", "mdp", "passphrase", "carte bancaire", "numero de carte",
           "card number", "credit card", "cvv", "cvc", "cryptogramme", "expiration", "iban", "bic", "code secret",
           "code pin", " pin", "securite sociale", "social security", "code de verification", "verification code",
           "code a usage unique", "one-time", "otp", "2fa", "authentification a deux")


def _simple(texte):
    t = unicodedata.normalize("NFKD", str(texte).lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _etiquette(cible, instantane):
    """La ligne de la derniere capture de page qui decrit l'element vise (ex. '- button "Envoyer" [ref=e45]')."""
    if not cible or not instantane:
        return ""
    for ligne in instantane.splitlines():
        if f"[ref={cible}]" in ligne:
            return ligne.strip()
    return ""


def _contient(texte, mots):
    t = " " + _simple(texte) + " "
    return next((m for m in mots if m in t), None)


def _option_annoncee(element):
    """'option « GeForce RTX 30 Series » dans la liste' -> 'GeForce RTX 30 Series' (vide si ce n'est pas une option)."""
    if "option" not in _simple(element):
        return ""
    m = re.search(r"[«\"“]\s*([^»\"”]{2,}?)\s*[»\"”]", element or "")
    return m.group(1) if m else ""


def _mots_cles(texte):
    """Mots qui distinguent une option : ceux qui contiennent un chiffre (RTX 40, 4090, Windows 11...),
    sinon les mots d'au moins 4 lettres."""
    mots = set(re.findall(r"[a-z0-9]+", _simple(re.sub(r"\[ref=[^\]]*\]", "", texte))))
    chiffres = {m for m in mots if any(c.isdigit() for c in m)}
    return chiffres or {m for m in mots if len(m) >= 4}


def _mauvaise_cible(element, etiquette):
    """Garde-fou de coherence : l'agent annonce cliquer sur l'option X, mais la ref visee designe autre chose
    (typiquement la liste fermee, qui affiche sa valeur par defaut). Renvoie le motif du refus, ou ''."""
    annonce = _option_annoncee(element)
    if not annonce or not etiquette:
        return ""
    if _mots_cles(annonce) - set(re.findall(r"[a-z0-9]+", _simple(re.sub(r"\[ref=[^\]]*\]", "", etiquette)))):
        return (tr("garde_navigateur.clic_refuse_tu_annonces_l", annonce=annonce, etiquette=etiquette))
    return ""


def decider(outil, args, instantane=""):
    if outil in INTERDITS:
        return "interdit", f"Interdit : {INTERDITS[outil]}."
    if outil in ("browser_navigate", "browser_tabs") and args.get("url"):
        url = str(args["url"]).strip()
        if not url.lower().startswith(("http://", "https://")):
            return "interdit", tr("garde_navigateur.seulement_http")
        if adresse_locale(url):
            return "interdit", tr("garde_navigateur.adresse_locale")
    if outil == "browser_file_upload":
        return "demander", tr("garde_navigateur.envoi_fichier")
    if outil == "browser_handle_dialog" and args.get("accept"):
        return "demander", tr("garde_navigateur.confirmation_page")
    if outil == "browser_press_key" and _simple(args.get("key", "")) in ("enter", "numpadenter", "return"):
        return "demander", tr("garde_navigateur.touche_entree")
    if outil == "browser_type":
        texte = f"{args.get('element', '')} {_etiquette(args.get('target'), instantane)}"
        if _contient(texte, SECRETS):
            return "interdit", tr("garde_navigateur.champ_secret")
        if args.get("submit"):
            return "demander", tr("garde_navigateur.taper_valider", v1=args.get('element') or tr("garde_navigateur.un_champ"))
    if outil == "browser_fill_form":
        for champ in args.get("fields") or []:
            texte = f"{champ.get('name', '')} {champ.get('element', '')} {_etiquette(champ.get('target'), instantane)}"
            if _contient(texte, SECRETS):
                return "interdit", tr("garde_navigateur.champ_nomme_secret", v1=champ.get('name', '?'))
    if outil == "browser_click":
        etiquette = _etiquette(args.get("target"), instantane)
        motif = _mauvaise_cible(args.get("element", ""), etiquette)
        if motif:
            return "interdit", motif
        mot = _contient(f"{args.get('element', '')} {etiquette}", ENGAGEMENT)
        if mot:
            vu = etiquette or args.get("element") or tr("garde_navigateur.ce_bouton")
            return "demander", tr("garde_navigateur.clic_engage", v1=vu)
    return "auto", ""
