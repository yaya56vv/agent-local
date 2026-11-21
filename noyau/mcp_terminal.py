"""MCP terminal d'Agent Local : lancer une commande PowerShell (decision du 11/11/2026 : il veut que l'agent
ait, hors ligne de Claude, des capacites proches). Chaque commande passe par l'autorisation de l'utilisateur (regle "demander"
dans config.json) et le garde-fou 6 d'agent.py refuse toute commande qui cite une zone interdite.
Droits de l'utilisateur, pas d'administrateur : une commande qui en a besoin fait apparaitre la fenetre de Windows.
Outil : executer_powershell.
"""
import os
import re
import subprocess
import winreg
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from langue import t as tr

serveur = FastMCP("terminal")
PROFIL = str(Path.home())
LIMITE = 12000   # caracteres de sortie renvoyes au modele


def _environnement():
    """Environnement Windows complet (systeme puis utilisateur, comme une vraie session), complete par celui du
    processus. Le client MCP lance ce serveur avec un environnement reduit (sans windir, ProgramFiles, ProgramData...) :
    le module Storage (Get-Volume, Get-Disk) ne se chargeait pas. Corrige le 11/11/2026."""
    brut = {}
    for racine, cle in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                        (winreg.HKEY_CURRENT_USER, "Environment")):
        try:
            with winreg.OpenKey(racine, cle) as k:
                for i in range(winreg.QueryInfoKey(k)[1]):
                    nom, valeur, _ = winreg.EnumValue(k, i)
                    if nom.upper() == "PATH" and "PATH" in {n.upper() for n in brut}:
                        cle_path = next(n for n in brut if n.upper() == "PATH")
                        brut[cle_path] = brut[cle_path].rstrip(";") + ";" + str(valeur)
                    else:
                        brut[nom] = str(valeur)
        except OSError:
            pass
    env = {**{k: v for k, v in os.environ.items()}}
    systemroot = os.environ.get("SystemRoot", r"C:\WINDOWS")
    defauts = {"windir": systemroot, "ProgramFiles": r"C:\Program Files", "ProgramFiles(x86)": r"C:\Program Files (x86)",
               "ProgramW6432": r"C:\Program Files", "ProgramData": r"C:\ProgramData",
               "CommonProgramFiles": r"C:\Program Files\Common Files", "ALLUSERSPROFILE": r"C:\ProgramData",
               "PUBLIC": r"C:\Users\Public", "ComSpec": systemroot + r"\system32\cmd.exe"}
    for nom, valeur in defauts.items():
        env.setdefault(nom, valeur)
    for nom, valeur in brut.items():   # variables du registre, une fois %...% remplaces (sans tenir compte des majuscules)
        connues = {k.upper(): v for k, v in env.items()}
        valeur = re.sub(r"%([^%;]+)%", lambda m: connues.get(m.group(1).upper(), m.group(0)), valeur)
        if nom.upper() == "PATH":
            env["Path"] = valeur
        elif nom not in env or nom.upper() == "PSMODULEPATH":
            env[nom] = valeur
    for k in [k for k in env if k.upper() == "PATH" and k != "Path"]:
        env.pop(k)
    return env


ENV = _environnement()


@serveur.tool(description=tr("outil.terminal.executer_powershell"))
def executer_powershell(commande: str, dossier: str = "", delai_secondes: int = 120) -> str:
    dossier = dossier.strip().strip('"') or PROFIL
    if not os.path.isdir(dossier):
        return tr("mcp_terminal.erreur_le_dossier_n_existe", dossier=dossier)
    delai = max(5, min(int(delai_secondes or 120), 600))
    script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference='SilentlyContinue'; " + commande
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], cwd=dossier, env=ENV,
                           capture_output=True, timeout=delai, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return tr("mcp_terminal.erreur_la_commande_a_depasse", delai=delai)
    sortie = (r.stdout or "").strip()
    erreurs = (r.stderr or "").strip()
    texte = tr("mcp_terminal.code_de_sortie", v1=r.returncode)
    texte += f"--- Sortie ---\n{sortie}\n" if sortie else "--- Sortie : (vide)\n"
    if erreurs:
        texte += f"--- Erreurs ---\n{erreurs}\n"
    if len(texte) > LIMITE:
        texte = texte[:LIMITE] + tr("mcp_terminal.sortie_coupee_a_caracteres_filtre", LIMITE=LIMITE)
    return texte


@serveur.tool(description=tr("outil.terminal.mettre_a_la_corbeille"))
def mettre_a_la_corbeille(chemin: str) -> str:
    cible = os.path.abspath(str(chemin or "").strip().strip('"'))
    if not os.path.exists(cible):
        return tr("mcp_terminal.erreur_n_existe_pas", cible=cible)
    if os.path.splitdrive(cible)[1] in ("\\", "/", ""):
        return tr("mcp_terminal.erreur_on_ne_met_pas")
    methode = "DeleteDirectory" if os.path.isdir(cible) else "DeleteFile"
    script = (tr("mcp_terminal.add_type_assemblyname_microsoft_visualbasic", methode=methode))
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       env={**ENV, "CIBLE_CORBEILLE": cible}, capture_output=True, timeout=120,
                       encoding="utf-8", errors="replace")
    if os.path.exists(cible):
        return tr("mcp_terminal.erreur_n_a_pas_pu", cible=cible, v1=(r.stderr or '').strip()[:500])
    return tr("mcp_terminal.mis_a_la_corbeille_recuperable", cible=cible)


@serveur.tool(description=tr("outil.terminal.executer_en_administrateur"))
def executer_en_administrateur(commande: str, raison: str, delai_secondes: int = 300) -> str:
    import tempfile
    import time
    delai = max(30, min(int(delai_secondes or 300), 1800))
    # dossier ordinaire (pas mkdtemp, dont les droits restreints rendaient la sortie illisible une fois ecrite par
    # l'administrateur) : les fichiers y heritent des droits normaux du dossier personnel
    dossier = os.path.join(tempfile.gettempdir(), "agent_admin", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(dossier, exist_ok=True)
    script, sortie = os.path.join(dossier, "commande.ps1"), os.path.join(dossier, "sortie.txt")
    corps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference='SilentlyContinue'\n"
             f"try {{ & {{ {commande} }} *>&1 | Out-String -Width 200 | Out-File -FilePath '{sortie}' -Encoding utf8 }}\n"
             f"catch {{ \"{tr('commun.erreur_deux_points')}$($_.Exception.Message)\" | Out-File -FilePath '{sortie}' -Encoding utf8 }}\n")
    with open(script, "w", encoding="utf-8-sig") as f:
        f.write(corps)
    lanceur = (f"try {{ Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "
               f"'-NoProfile','-ExecutionPolicy','Bypass','-File','{script}' -ErrorAction Stop; 'LANCE' }} "
               f"catch {{ 'REFUSE' }}")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", lanceur], env=ENV, capture_output=True,
                           timeout=delai, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return tr("mcp_terminal.erreur_pas_de_reponse_apres", delai=delai)
    if "REFUSE" in (r.stdout or ""):
        return tr("mcp_terminal.refus_l_utilisateur_n_a")
    # Start-Process -Verb RunAs ne patiente pas toujours vraiment : on attend que la sortie soit ecrite
    debut = time.time()
    while time.time() - debut < delai:
        if os.path.exists(sortie) and os.path.getsize(sortie) > 0:
            time.sleep(1)
            break
        time.sleep(1)
    try:
        texte = open(sortie, encoding="utf-8-sig", errors="replace").read().strip()
    except OSError:
        texte = tr("mcp_terminal.aucune_sortie")
    texte = tr("mcp_terminal.execute_en_administrateur_sortie") + (texte or "(vide)")
    return texte[:LIMITE] + (tr("mcp_terminal.sortie_coupee") if len(texte) > LIMITE else "")


if __name__ == "__main__":
    serveur.run()
