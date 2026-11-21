"""MCP cloud d'Agent Local : donne au chef un acces ponctuel a un modele plus puissant via OpenRouter.

Decision de l'utilisateur du 16/11/2026 : Qwen local reste le chef ; le cloud n'est qu'un CONSEILLER
appele pour une question difficile, sur autorisation, en n'envoyant que la question.
Outils : demander_au_cloud (sur autorisation), etat_cloud (lecture libre).
La cle et le modele sont dans openrouter.env, dans le dossier de secrets (reglages.SECRETS, hors du depot).
"""
import os
import re

import httpx
import reglages
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from langue import t as tr

FICHIER_CLE = str(reglages.chemin_secret("openrouter.env"))
URL = "https://openrouter.ai/api/v1"
MODELE_PAR_DEFAUT = "moonshotai/kimi-k3.1-pro"
TAILLE_MAX = 20000  # caracteres envoyes au maximum (question + contexte)

serveur = FastMCP("cloud")
LECTURE = ToolAnnotations(readOnlyHint=True)

# Motifs qui ne doivent jamais partir dans le cloud
MOTIFS_SENSIBLES = [
    r"mot de passe\s*[:=]", r"password\s*[:=]", r"\bpasswd\b", r"api[_ -]?key\s*[:=]",
    r"\btoken\s*[:=]", r"\bjeton\s*[:=]", r"\b(?:\d[ -]?){13,19}\b",  # numero de carte
    r"\bFR\d{2}[ ]?(?:\d{4}[ ]?){5}\d{3}\b",  # IBAN francais
    tr("mcp_cloud.begin_a_z_private_key"),
]


def _lire_reglages():
    """Lit la cle et le modele dans le fichier hors depot. Renvoie (cle, modele)."""
    cle, modele = "", MODELE_PAR_DEFAUT
    if os.path.exists(FICHIER_CLE):
        with open(FICHIER_CLE, encoding="utf-8-sig") as f:
            for ligne in f:
                ligne = ligne.strip()
                if ligne.startswith("#") or "=" not in ligne:
                    continue
                nom, valeur = ligne.split("=", 1)
                nom, valeur = nom.strip(), valeur.strip().strip('"').strip("'")
                if nom == "OPENROUTER_API_KEY":
                    cle = valeur
                elif nom == "OPENROUTER_MODELE" and valeur:
                    modele = valeur
    return cle, modele


def _contient_sensible(texte: str):
    for motif in MOTIFS_SENSIBLES:
        if re.search(motif, texte, flags=re.IGNORECASE):
            return motif
    return None


def _entetes(cle):
    return {"Authorization": f"Bearer {cle}", "X-Title": tr("mcp_cloud.agent_local")}


@serveur.tool(description=tr("outil.cloud.demander_au_cloud"))
def demander_au_cloud(question: str, contexte: str = "") -> str:
    texte = (question or "").strip()
    if not texte:
        return tr("mcp_cloud.refus_la_question_est_vide")
    complet = texte + ("\n\nContexte :\n" + contexte.strip() if contexte and contexte.strip() else "")
    if len(complet) > TAILLE_MAX:
        return (tr("mcp_cloud.refus_la_demande_fait_caracteres", v1=len(complet), TAILLE_MAX=TAILLE_MAX))
    motif = _contient_sensible(complet)
    if motif:
        return (tr("mcp_cloud.refus_la_demande_semble_contenir"))
    cle, modele = _lire_reglages()
    if not cle:
        return (tr("mcp_cloud.le_cloud_n_est_pas") + FICHIER_CLE +
                tr("mcp_cloud.rien_n_a_ete_envoye"))
    corps = {
        "model": modele,
        "messages": [
            {"role": "system", "content": tr("mcp_cloud.tu_es_un_expert_consulte")},
            {"role": "user", "content": complet},
        ],
        "max_tokens": 16000,
        "reasoning": {"effort": "medium"},
        "provider": {"data_collection": "deny"},
    }
    try:
        r = httpx.post(f"{URL}/chat/completions", json=corps, headers=_entetes(cle), timeout=180)
    except httpx.HTTPError as e:
        return tr("mcp_cloud.le_cloud_est_injoignable_internet", v1=type(e).__name__)
    if r.status_code != 200:
        try:
            detail = r.json().get("error", {}).get("message", r.text[:300])
        except ValueError:
            detail = r.text[:300]
        return tr("mcp_cloud.le_cloud_a_refuse_la", v1=r.status_code, detail=detail)
    donnees = r.json()
    try:
        reponse = donnees["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError):
        return tr("mcp_cloud.le_cloud_a_renvoye_une")
    if not reponse.strip():
        fin = donnees["choices"][0].get("finish_reason")
        return (tr("mcp_cloud.le_cloud_n_a_rendu") + str(fin) + tr("mcp_cloud.repose_une_question_plus_courte"))
    usage = donnees.get("usage", {}) or {}
    cout = usage.get("cost")
    pied = tr("mcp_cloud.avis_du_modele", modele=modele)
    if cout is not None:
        pied += tr("mcp_cloud.cout_environ", v1=float(cout))
    pied += tr("mcp_cloud.a_verifier_avant_usage")
    return reponse.strip() + pied


@serveur.tool(annotations=LECTURE, description=tr("outil.cloud.etat_cloud"))
def etat_cloud() -> str:
    cle, modele = _lire_reglages()
    if not cle:
        return tr("mcp_cloud.cloud_non_configure_cle_absente", FICHIER_CLE=FICHIER_CLE, modele=modele)
    try:
        r = httpx.get(f"{URL}/key", headers=_entetes(cle), timeout=20)
    except httpx.HTTPError as e:
        return tr("mcp_cloud.cloud_configure_modele_mais_injoignable", modele=modele, v1=type(e).__name__)
    if r.status_code != 200:
        return tr("mcp_cloud.cloud_configure_modele_mais_la", modele=modele, v1=r.status_code)
    d = r.json().get("data", {})
    limite = d.get("limit")
    utilise = d.get("usage")
    reste = d.get("limit_remaining")
    morceaux = [tr("mcp_cloud.cloud_pret_modele", modele=modele)]
    if utilise is not None:
        morceaux.append(tr("mcp_cloud.depense_sur_cette_cle", v1=float(utilise)))
    if limite is not None:
        morceaux.append(f"limite : {float(limite):.2f} $, reste : {float(reste or 0):.2f} $")
    else:
        morceaux.append(tr("mcp_cloud.aucune_limite_de_depense_sur"))
    return ", ".join(morceaux) + "."


if __name__ == "__main__":
    serveur.run()
