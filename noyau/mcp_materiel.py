"""MCP materiel d'Agent Local : l'etat des peripheriques, comme le Gestionnaire de peripheriques (decision de l'utilisateur
du 11/11/2026). LECTURE SEULE : aucun outil ne modifie, n'active, ne desactive ni ne reinstalle quoi que ce soit.
L'installation d'un pilote (autorisee par l'utilisateur) passe par la consigne de l'agent et une mission Hermes, pas par ce MCP.
Outils : peripheriques_en_erreur, details_peripherique (libres).
"""
import json
import subprocess
import unicodedata

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from langue import t as tr

serveur = FastMCP("materiel")
LECTURE = ToolAnnotations(readOnlyHint=True)

# Codes d'erreur du Gestionnaire de peripheriques (documentation Microsoft), en francais simple
CODES = {
    1: tr("mcp_materiel.mal_configure_le_pilote_ne"),
    3: tr("mcp_materiel.pilote_corrompu_ou_memoire_du"),
    10: tr("mcp_materiel.le_peripherique_ne_peut_pas"),
    12: tr("mcp_materiel.pas_assez_de_ressources_libres"),
    14: tr("mcp_materiel.il_faut_redemarrer_l_ordinateur"),
    18: tr("mcp_materiel.il_faut_reinstaller_le_pilote"),
    19: tr("mcp_materiel.reglages_de_windows_registre_incomplets"),
    21: tr("mcp_materiel.windows_est_en_train_de"),
    22: tr("mcp_materiel.le_peripherique_est_desactive"),
    24: tr("mcp_materiel.absent_mal_branche_ou_sans"),
    28: tr("mcp_materiel.aucun_pilote_installe"),
    29: tr("mcp_materiel.desactive_par_le_microprogramme_bios"),
    31: tr("mcp_materiel.le_pilote_ne_se_charge"),
    32: tr("mcp_materiel.le_service_du_pilote_est"),
    33: tr("mcp_materiel.windows_ne_sait_pas_determiner"),
    34: tr("mcp_materiel.reglage_manuel_des_ressources_necessaire"),
    35: tr("mcp_materiel.le_microprogramme_bios_ne_fournit"),
    36: tr("mcp_materiel.conflit_d_interruption_irq_a"),
    37: tr("mcp_materiel.le_pilote_a_renvoye_une"),
    38: tr("mcp_materiel.une_ancienne_copie_du_pilote"),
    39: tr("mcp_materiel.pilote_corrompu_ou_manquant"),
    40: tr("mcp_materiel.informations_du_pilote_absentes_ou"),
    41: tr("mcp_materiel.pilote_charge_mais_peripherique_introuvable"),
    42: tr("mcp_materiel.peripherique_en_double_detecte"),
    43: tr("mcp_materiel.windows_l_a_arrete_car"),
    44: tr("mcp_materiel.arrete_par_un_programme_ou"),
    45: tr("mcp_materiel.debranche_actuellement_peripherique_memorise_mais"),
    47: tr("mcp_materiel.prepare_pour_un_retrait_en"),
    48: tr("mcp_materiel.pilote_bloque_car_connu_pour"),
    49: tr("mcp_materiel.registre_du_systeme_trop_volumineux"),
    52: tr("mcp_materiel.signature_numerique_du_pilote_non"),
    54: tr("mcp_materiel.en_echec_en_cours_de"),
}


def _powershell(script):
    """Execute une commande PowerShell de LECTURE et renvoie son resultat JSON decode."""
    commande = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + script
    sortie = subprocess.run(["powershell", "-NoProfile", "-Command", commande], capture_output=True,
                            timeout=90, encoding="utf-8", errors="replace").stdout.strip()
    if not sortie:
        return []
    donnees = json.loads(sortie)
    return donnees if isinstance(donnees, list) else [donnees]


@serveur.tool(annotations=LECTURE, description=tr("outil.materiel.peripheriques_en_erreur"))
def peripheriques_en_erreur() -> str:
    liste = _powershell("Get-CimInstance Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -ne 0 } | "
                        "Select-Object Name, PNPClass, Manufacturer, ConfigManagerErrorCode, PNPDeviceID | "
                        "ConvertTo-Json -Compress")
    total = _powershell("@{n=(Get-CimInstance Win32_PnPEntity).Count} | ConvertTo-Json -Compress")[0]["n"]
    if not liste:
        return tr("mcp_materiel.aucun_peripherique_en_erreur_sur", total=total)
    lignes = [tr("mcp_materiel.peripherique_s_en_erreur_sur", v1=len(liste), total=total)]
    for p in liste:
        code = p.get("ConfigManagerErrorCode")
        lignes.append(f"- {p.get('Name')} (categorie {p.get('PNPClass')}, fabricant {p.get('Manufacturer')}) : "
                      f"code {code}, {CODES.get(code, 'code non repertorie')}. Identifiant : {p.get('PNPDeviceID')}")
    return "\n".join(lignes)


def _simple(texte):
    """Nom comparable : sans accents, sans symboles (® ™), espaces speciales ramenees a une espace, minuscules.
    (Windows ecrit 'ASMedia USB 3.1' avec des espaces insecables : la recherche echouait avant le 11/11/2026.)"""
    t = unicodedata.normalize("NFKD", str(texte or ""))
    t = "".join(c for c in t if not unicodedata.combining(c) and c not in "®™©")
    return " ".join(t.lower().split())


@serveur.tool(annotations=LECTURE, description=tr("outil.materiel.details_peripherique"))
def details_peripherique(recherche: str) -> str:
    tous = _powershell("Get-CimInstance Win32_PnPEntity | Select-Object Name, PNPClass, Manufacturer, Status, "
                       "ConfigManagerErrorCode, PNPDeviceID | ConvertTo-Json -Compress")
    cherche = _simple(recherche)
    trouves = [p for p in tous if cherche in _simple(p.get("Name")) or cherche == _simple(p.get("PNPDeviceID"))][:8]
    if not trouves:
        return tr("mcp_materiel.aucun_peripherique_ne_correspond_a", recherche=recherche)
    pilotes = {p.get("DeviceID"): p for p in _powershell(
        "Get-CimInstance Win32_PnPSignedDriver | Select-Object DeviceID, DriverProviderName, DriverVersion, InfName, "
        "@{n='Date';e={if ($_.DriverDate) { $_.DriverDate.ToString('dd/MM/yyyy') }}} | ConvertTo-Json -Compress")}
    blocs = []
    for p in trouves:
        code = p.get("ConfigManagerErrorCode") or 0
        etat = tr("mcp_materiel.fonctionne_normalement") if code == 0 else f"code {code}, {CODES.get(code, 'code non repertorie')}"
        d = pilotes.get(p.get("PNPDeviceID"), {})
        pilote = (f"pilote {d.get('DriverProviderName')} version {d.get('DriverVersion')} du {d.get('Date')} "
                  f"({d.get('InfName')})" if d.get("DriverVersion") else tr("mcp_materiel.aucun_pilote_installe_ou_trouve"))
        blocs.append(f"- {p.get('Name')} (categorie {p.get('PNPClass')}, fabricant {p.get('Manufacturer')}) : {etat} ; "
                     f"{pilote}. Identifiant : {p.get('PNPDeviceID')}")
    return "\n".join(blocs)


if __name__ == "__main__":
    serveur.run()
