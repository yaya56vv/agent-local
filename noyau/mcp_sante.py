"""MCP sante d'Agent Local : la sante du PC (14/11/2026). LECTURE SEULE.
- Temperatures et ventilateurs : lus sur le serveur web de LibreHardwareMonitor (http://127.0.0.1:8085/data.json),
  lance au demarrage de Windows par la tache planifiee « LibreHardwareMonitor » (droits administrateur, sans invite).
- Observateur d'evenements : journaux Systeme et Application (erreurs, avertissements, incidents graves).
- Sysinternals : Autoruns (demarrage_windows) et l'equivalent de Process Explorer (processus_gourmands).
Outils : temperatures, evenements_recents, details_evenement, incidents_graves, demarrage_windows,
processus_gourmands (tous libres).
"""
import json
import re
import subprocess
import time
import urllib.request

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from langue import t as tr

serveur = FastMCP("sante")
LECTURE = ToolAnnotations(readOnlyHint=True)
URL_LHM = "http://127.0.0.1:8085/data.json"
TACHE_LHM = r"\AgentLocal\LibreHardwareMonitor"


def _nombre(texte):
    """'72,0 °C' -> 72.0 ; None si illisible."""
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(texte or ""))
    return float(m.group(0).replace(",", ".")) if m else None


def _lire_lhm():
    """Lit le serveur web de LibreHardwareMonitor ; s'il ne repond pas, relance sa tache planifiee une fois."""
    for essai in range(2):
        try:
            with urllib.request.urlopen(URL_LHM, timeout=5) as r:
                return json.loads(r.read().decode("utf-8", errors="replace"))
        except Exception:
            if essai == 0:
                subprocess.run(["schtasks", "/run", "/tn", TACHE_LHM], capture_output=True, timeout=20)
                time.sleep(20)
    return None


def _capteurs(noeud, appareil, sortie):
    """Parcourt l'arbre de LHM et collecte (appareil, nom, type, valeur, min, max)."""
    image = str(noeud.get("ImageURL", ""))
    if any(k in image for k in ("cpu", "nvidia", "ati", "intel", "ram", "hdd", "nvme", "mainboard", "chip", "battery")):
        appareil = noeud.get("Text", appareil)
    if noeud.get("Type") in ("Temperature", "Fan"):
        sortie.append((appareil, noeud.get("Text", ""), noeud.get("Type"), _nombre(noeud.get("Value")),
                       _nombre(noeud.get("Min")), _nombre(noeud.get("Max"))))
    for enfant in noeud.get("Children", []):
        _capteurs(enfant, appareil, sortie)


def _verdict(appareil, nom, valeur, seuils_disque):
    """Seuils simples par famille de composant. Renvoie '' si normal, sinon 'A SURVEILLER' / 'ALERTE'."""
    a, n = appareil.lower(), nom.lower()
    if valeur is None:
        return ""
    if "core" in a and ("intel" in a or "ryzen" in a or "cpu" in a) or "package" in n:
        surveiller, alerte = 90, 95                      # processeur : limite (TjMax) a 100 °C
    elif "hot spot" in n:
        surveiller, alerte = 100, 105                    # point chaud carte graphique
    elif "memory junction" in n:
        surveiller, alerte = 95, 105                     # memoire de la carte graphique
    elif "gpu" in n:
        surveiller, alerte = 85, 90                      # coeur de la carte graphique
    elif "dimm" in n:
        surveiller, alerte = 70, 80                      # barrettes de memoire vive (critique 85)
    elif appareil in seuils_disque:
        alerte = seuils_disque[appareil]
        surveiller = alerte - 10                         # SSD : seuil d'alerte donne par le disque lui-meme
    else:
        return ""
    if valeur >= alerte:
        return " -> ALERTE"
    if valeur >= surveiller:
        return " -> A SURVEILLER"
    return ""


@serveur.tool(annotations=LECTURE, description=tr("outil.sante.temperatures"))
def temperatures() -> str:
    donnees = _lire_lhm()
    if donnees is None:
        return (tr("mcp_sante.impossible_de_lire_les_temperatures") + URL_LHM +
                tr("mcp_sante.meme_apres_relance_de_sa"))
    capteurs = []
    _capteurs(donnees, "", capteurs)
    ignorer = ("distance to tjmax", "resolution", "limit", "warning temperature", "critical temperature",
               "core max", "core average")
    seuils_disque = {a: v for a, n, t, v, _, _ in capteurs if n.lower() == "warning temperature" and v}
    lignes, alertes = [], []
    for appareil, nom, type_, valeur, mini, maxi in capteurs:
        if any(i in nom.lower() for i in ignorer):
            continue
        unite = "tr/min" if type_ == "Fan" else "°C"
        v = _verdict(appareil, nom, valeur, seuils_disque) if type_ == "Temperature" else ""
        lignes.append(f"- {appareil} | {nom} : {valeur:g} {unite} (min {mini:g}, max {maxi:g}){v}"
                      if None not in (valeur, mini, maxi) else f"- {appareil} | {nom} : illisible")
        if v:
            alertes.append(f"{appareil} {nom} ({valeur:g} {unite}){v}")
    entete = (tr("mcp_sante.verdict_tout_est_dans_les") if not alertes else
              "VERDICT : " + str(len(alertes)) + " point(s) a signaler : " + " ; ".join(alertes))
    return entete + "\n" + "\n".join(lignes) + (tr("mcp_sante.note_des_ventilateurs_a_0"))


def _powershell(script):
    """Execute une commande PowerShell de LECTURE et renvoie son resultat JSON decode (liste)."""
    commande = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ErrorActionPreference='SilentlyContinue'; " + script
    sortie = subprocess.run(["powershell", "-NoProfile", "-Command", commande], capture_output=True,
                            timeout=120, encoding="utf-8", errors="replace").stdout.strip()
    if not sortie:
        return []
    donnees = json.loads(sortie)
    return donnees if isinstance(donnees, list) else [donnees]


def _etat_frequence(nombre, premiere_ts, derniere_ts):
    """Dit si un evenement repetitif semble avoir CESSE : silence depuis la derniere occurrence bien plus long
    que l'intervalle moyen entre deux occurrences (ajout du 14/11/2026, apres un rapport qui disait « plante en
    boucle » pour un probleme repare le matin meme)."""
    try:
        maintenant = time.time()
        silence = maintenant - float(derniere_ts)
        h = silence / 3600
        depuis = tr("mcp_sante.aucune_occurrence_depuis_h", h=h) if h < 48 else tr("mcp_sante.aucune_occurrence_depuis_jours", v1=h / 24)
        if nombre >= 3:
            intervalle = (float(derniere_ts) - float(premiere_ts)) / (nombre - 1)
            if intervalle < 120:
                return tr("mcp_sante.survenu_en_une_seule_rafale", depuis=depuis)
            if silence > max(3600, 3 * intervalle):
                return tr("mcp_sante.semble_avoir_cesse_alors_qu", depuis=depuis, v1=intervalle / 60)
            return tr("mcp_sante.toujours_actif_revient_recemment_toutes", v1=intervalle / 60, depuis=depuis)
        return f" ({depuis})"
    except Exception:
        return ""


NIVEAUX = {1: "CRITIQUE", 2: "Erreur", 3: "Avertissement"}


@serveur.tool(annotations=LECTURE, description=tr("outil.sante.evenements_recents"))
def evenements_recents(heures: int = 24, avec_avertissements: bool = False) -> str:
    heures = max(1, min(int(heures), 24 * 30))
    niveaux = "1,2,3" if avec_avertissements else "1,2"
    liste = _powershell(
        f"Get-WinEvent -FilterHashtable @{{LogName='System','Application'; Level={niveaux}; "
        f"StartTime=(Get-Date).AddHours(-{heures})}} -MaxEvents 2000 | Group-Object ProviderName, Id | "
        "Sort-Object Count -Descending | Select-Object -First 30 | ForEach-Object { $e = $_.Group[0]; "
        "[pscustomobject]@{ Source=$e.ProviderName; Id=$e.Id; Niveau=$e.Level; Journal=$e.LogName; Nombre=$_.Count; "
        "Derniere=$e.TimeCreated.ToString('dd/MM HH:mm'); DTs=[DateTimeOffset]::new($e.TimeCreated).ToUnixTimeSeconds(); PTs=[DateTimeOffset]::new($_.Group[[Math]::Min(9, $_.Count - 1)].TimeCreated).ToUnixTimeSeconds(); N10=[Math]::Min(10, $_.Count); "
        "Message=(($e.Message -split \"`n\")[0]).Trim() } } | ConvertTo-Json -Compress")
    if not liste:
        return tr("mcp_sante.aucune_erreur_dans_les_journaux", heures=heures)
    lignes = [tr("mcp_sante.type_s_d_evenements_sur", v1=len(liste), heures=heures)]
    for e in liste:
        msg = (e.get("Message") or tr("mcp_sante.pas_de_texte"))[:220]
        lignes.append(tr("mcp_sante.n_fois_derniere_le", v1=NIVEAUX.get(e.get('Niveau'), e.get('Niveau')), v2=e.get('Source'), v3=e.get('Id'), v4=e.get('Journal'), v5=e.get('Nombre'), v6=e.get('Derniere'), v7=_etat_frequence(e.get('N10') or 0, e.get('PTs'), e.get('DTs')), msg=msg))
    lignes.append(tr("mcp_sante.rappel_la_plupart_des_pc"))
    return "\n".join(lignes)


@serveur.tool(annotations=LECTURE, description=tr("outil.sante.details_evenement"))
def details_evenement(source: str, numero: int, combien: int = 3) -> str:
    source_ps = source.replace("'", "''")
    liste = _powershell(
        f"Get-WinEvent -FilterHashtable @{{LogName='System','Application'; ProviderName='{source_ps}'; Id={int(numero)}}} "
        f"-MaxEvents {max(1, min(int(combien), 10))} | ForEach-Object {{ [pscustomobject]@{{ "
        "Date=$_.TimeCreated.ToString('dd/MM/yyyy HH:mm:ss'); Niveau=$_.LevelDisplayName; Message=$_.Message } } "
        "| ConvertTo-Json -Compress")
    if not liste:
        return tr("mcp_sante.aucun_evenement_trouve_pour_la", source=source, numero=numero)
    return "\n\n".join(f"{e.get('Date')} ({e.get('Niveau')}) :\n{(e.get('Message') or '')[:1500]}" for e in liste)


# Evenements qui signalent un vrai probleme de sante (source, numero, explication en francais simple)
GRAVES = [
    ("Microsoft-Windows-Kernel-Power", 41, tr("mcp_sante.arret_brutal_le_pc_s")),
    ("EventLog", 6008, tr("mcp_sante.l_arret_precedent_etait_inattendu")),
    ("Microsoft-Windows-WER-SystemErrorReporting", 1001, tr("mcp_sante.ecran_bleu_bugcheck_plantage_du")),
    ("Microsoft-Windows-WHEA-Logger", None, tr("mcp_sante.erreur_materielle_signalee_par_le")),
    ("Microsoft-Windows-Kernel-Processor-Power", 37, tr("mcp_sante.le_processeur_a_ete_bride")),
    ("disk", None, tr("mcp_sante.erreur_du_disque")),
    ("Ntfs", None, tr("mcp_sante.probleme_du_systeme_de_fichiers")),
    ("nvlddmkm", None, tr("mcp_sante.plantage_ou_reinitialisation_du_pilote")),
    ("Display", 4101, tr("mcp_sante.le_pilote_graphique_a_cesse")),
    ("Application Error", 1000, tr("mcp_sante.un_programme_s_est_ferme")),
]


@serveur.tool(annotations=LECTURE, description=tr("outil.sante.incidents_graves"))
def incidents_graves(jours: int = 30) -> str:
    jours = max(1, min(int(jours), 365))
    sources = ",".join("'" + s + "'" for s in {g[0] for g in GRAVES})
    liste = _powershell(
        f"Get-WinEvent -FilterHashtable @{{LogName='System','Application'; ProviderName={sources}; "
        f"StartTime=(Get-Date).AddDays(-{jours})}} -MaxEvents 5000 | Where-Object {{ $_.Level -le 3 -or $_.Id -in 41,6008,37 }} | "
        "Group-Object ProviderName, Id, { if ($_.ProviderName -eq 'Application Error') { ($_.Message -split [char]10)[0] } else { '-' } } | ForEach-Object { $e = $_.Group[0]; [pscustomobject]@{ Source=$e.ProviderName; DTs=[DateTimeOffset]::new($e.TimeCreated).ToUnixTimeSeconds(); PTs=[DateTimeOffset]::new($_.Group[[Math]::Min(9, $_.Count - 1)].TimeCreated).ToUnixTimeSeconds(); N10=[Math]::Min(10, $_.Count); "
        "Id=$e.Id; Nombre=$_.Count; Derniere=$e.TimeCreated.ToString('dd/MM/yyyy HH:mm'); "
        "Detail=(($e.Message -split \"`n\")[0]).Trim() } } | ConvertTo-Json -Compress")
    trouves = []
    for e in liste:
        for source, numero, explication in GRAVES:
            if e.get("Source") == source and (numero is None or e.get("Id") == numero):
                detail = f" ({(e.get('Detail') or '')[:150]})" if source == "Application Error" else ""
                trouves.append(tr("mcp_sante.fois_la_derniere_le_n", explication=explication, v1=e.get('Nombre'), v2=e.get('Derniere'), source=source, v3=e.get('Id'), detail=detail, v4=_etat_frequence(e.get('N10') or 0, e.get('PTs'), e.get('DTs'))))
                break
    if not trouves:
        return tr("mcp_sante.aucun_incident_grave_sur_les", jours=jours)
    return (tr("mcp_sante.incidents_des_derniers_jours", jours=jours) + "\n".join(trouves) +
            tr("mcp_sante.pour_le_texte_complet_d"))


# --- Sysinternals (14/11/2026) ---------------------------------------------------------
# Copie protegee (ecriture reservee aux administrateurs) depuis le 20/11/2026 (renforcement des garde-fous) :
# outils-admin\installer_sante.ps1 ; la tache \AgentLocal\Autoruns controle sa signature Microsoft avant de la lancer.
AUTORUNSC = r"C:\Program Files\AgentLocal\Outils\Autoruns\autorunsc64.exe"
CATEGORIES_BRUIT = {"Known DLLs", "Codecs", "Winsock Providers", "Print Monitors", "LSA Providers", "Network Providers"}


@serveur.tool(annotations=LECTURE, description=tr("outil.sante.demarrage_windows"))
def demarrage_windows() -> str:
    import csv, io, os, tempfile
    # 1) Version complete : tache planifiee \AgentLocal\Autoruns (administrateur, sans invite), qui ecrit ce fichier
    sortie = r"C:\ProgramData\AgentLocal\Sante\autoruns.csv"   # dossier protege (20/11/2026), lecture seule pour l'utilisateur
    debut, admin = time.time(), False
    subprocess.run(["schtasks", "/run", "/tn", r"\AgentLocal\Autoruns"], capture_output=True, timeout=20)
    while time.time() - debut < 150:
        time.sleep(5)
        etat = subprocess.run(["schtasks", "/query", "/tn", r"\AgentLocal\Autoruns", "/fo", "csv", "/nh"],
                              capture_output=True, timeout=20, encoding="utf-8", errors="replace").stdout
        if os.path.exists(sortie) and os.path.getmtime(sortie) > debut and "Running" not in etat and "cours" not in etat:
            admin = True
            break
    # 2) Secours : version sans droits administrateur (services et pilotes incomplets)
    if not admin:
        sortie = os.path.join(tempfile.gettempdir(), "agent_autoruns.csv")
        try:
            subprocess.run([AUTORUNSC, "-accepteula", "-nobanner", "-a", "bdehlmstw", "-c", "-s", "-o", sortie],
                           capture_output=True, timeout=180)
        except Exception as e:
            return tr("mcp_sante.autoruns_n_a_pas_pu", e=e)
    try:
        brut = open(sortie, "rb").read()
    except Exception as e:
        return tr("mcp_sante.autoruns_n_a_pas_produit", e=e)
    texte = brut.decode("utf-16") if brut[:2] in (b"\xff\xfe", b"\xfe\xff") else brut.decode("utf-8", "replace")
    lignes = [l for l in csv.DictReader(io.StringIO(texte))
              if l.get("Enabled") == "enabled" and l.get("Category") not in CATEGORIES_BRUIT
              and not re.match(r"\(Verified\) Microsoft", (l.get("Signer") or "").strip())]
    # (l'option -m d'Autoruns masque TOUT ce qui est signe, pas seulement Microsoft : on trie donc ici, 14/11/2026)
    if not lignes:
        return tr("mcp_sante.aucun_element_de_demarrage_hors")
    par_cat, a_signaler = {}, []
    for l in lignes:
        nom = l.get("Entry") or tr("mcp_sante.sans_nom")
        signe = (l.get("Signer") or "").strip()
        chemin = (l.get("Image Path") or "").strip()
        note = ""
        if not chemin or "file not found" in chemin.lower():
            note = tr("mcp_sante.fichier_introuvable_entree_orpheline")
        elif not signe or "not verified" in signe.lower():
            note = tr("mcp_sante.non_signe_signature_non_verifiee")
        if note:
            a_signaler.append(f"{nom} ({l.get('Category')}){note}")
        editeur = (l.get("Company") or "").replace("(Verified)", "").replace("(Not Verified)", "").strip()
        par_cat.setdefault(l.get("Category"), []).append(f"{nom}" + (f" - {editeur}" if editeur else "") + note)
    rapport = [tr("mcp_sante.elements_actifs_au_demarrage_hors", v1=len(lignes))]
    for cat, items in par_cat.items():
        uniques = list(dict.fromkeys(items))
        rapport.append(f"* {cat} ({len(uniques)}) : " + " ; ".join(uniques[:60]) +
                       (f" ; (+{len(uniques) - 60} autres)" if len(uniques) > 60 else ""))
    rapport.append(tr("mcp_sante.a_signaler_element_s_un", v1=len(a_signaler)) +
                   (tr("mcp_sante.lecture_complete_avec_les_droits") if admin else
                    tr("mcp_sante.lecture_sans_les_droits_administrateur")))
    return "\n".join(rapport)


DISKINFO = r"C:\ProgramData\AgentLocal\Disques\DiskInfo.txt"


@serveur.tool(annotations=LECTURE, description=tr("outil.sante.sante_disques"))
def sante_disques() -> str:
    import os
    avant = os.path.getmtime(DISKINFO) if os.path.exists(DISKINFO) else 0
    subprocess.run(["schtasks", "/run", "/tn", r"\AgentLocal\Disques"], capture_output=True, timeout=20)
    for _ in range(60):
        time.sleep(1)
        if os.path.exists(DISKINFO) and os.path.getmtime(DISKINFO) > avant:
            time.sleep(1)
            break
    if not os.path.exists(DISKINFO):
        return tr("mcp_sante.erreur_le_rapport_de_crystaldiskinfo")
    frais = os.path.getmtime(DISKINFO) > avant
    texte = open(DISKINFO, encoding="utf-8", errors="replace").read()
    if texte.count("\x00") > 10:
        texte = open(DISKINFO, encoding="utf-16", errors="replace").read()
    garder = ("Model", "Disk Size", "Drive Letter", "Health Status", "Temperature", "Power On Hours",
              "Power On Count", "Host Writes", "Percentage Used", "Available Spare", tr("mcp_sante.media_and_data_integrity"),
              "Error Information Log")
    lignes = [l.strip() for l in texte.splitlines() if l.strip().startswith(garder)]
    entete = "" if frais else tr("mcp_sante.attention_rapport_ancien_la_tache")
    return entete + "\n".join(lignes) if lignes else entete + texte[:3000]


@serveur.tool(annotations=LECTURE, description=tr("outil.sante.processus_gourmands"))
def processus_gourmands(nombre: int = 12) -> str:
    nombre = max(3, min(int(nombre), 30))
    liste = _powershell(
        "$a = @{}; Get-Process | ForEach-Object { $a[$_.Id] = $_.TotalProcessorTime.TotalMilliseconds }; Start-Sleep 3; "
        "$n = [Environment]::ProcessorCount; Get-Process | ForEach-Object { $c = 0; if ($a.ContainsKey($_.Id)) { "
        "$c = ($_.TotalProcessorTime.TotalMilliseconds - $a[$_.Id]) / 30 / $n }; [pscustomobject]@{ Nom=$_.ProcessName; "
        "Id=$_.Id; CPU=[math]::Round($c,1); RAMMo=[math]::Round($_.WorkingSet64/1MB); Editeur=$_.Company; Chemin=$_.Path } } "
        "| ConvertTo-Json -Compress")
    if not liste:
        return tr("mcp_sante.impossible_de_lire_les_processus")
    def ligne(p):
        return (f"- {p.get('Nom')} (n°{p.get('Id')}) : {p.get('CPU')} % processeur, {p.get('RAMMo')} Mo"
                + (f", {p.get('Editeur')}" if p.get("Editeur") else ""))
    cpu = sorted(liste, key=lambda p: p.get("CPU") or 0, reverse=True)[:nombre]
    ram = sorted(liste, key=lambda p: p.get("RAMMo") or 0, reverse=True)[:nombre]
    total_ram = sum(p.get("RAMMo") or 0 for p in liste)
    return (tr("mcp_sante.processeur_part_de_la_machine") + "\n".join(ligne(p) for p in cpu) +
            tr("mcp_sante.memoire_vive_total_utilise_par", v1=total_ram // 1024) +
            "\n".join(ligne(p) for p in ram))

@serveur.tool(annotations=LECTURE, description=tr("outil.sante.fiche_materiel"))
def fiche_materiel() -> str:
    d = _powershell(
        "$cs = Get-CimInstance Win32_ComputerSystem; $b = Get-CimInstance Win32_BIOS; $os = Get-CimInstance Win32_OperatingSystem; "
        "$cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name.Trim(); "
        "$gpu = Get-CimInstance Win32_VideoController | ForEach-Object { \"$($_.Name) (pilote $($_.DriverVersion))\" }; "
        "$nv = try { (& nvidia-smi --query-gpu=driver_version --format=csv,noheader | Select-Object -First 1).Trim() } catch { '' }; "
        "$w = Get-NetAdapter -Physical | Where-Object { $_.InterfaceDescription -match 'Wi-Fi|Wireless|WLAN' } | Select-Object -First 1; "
        "$wifi = [pscustomobject]@{ DeviceName=$w.InterfaceDescription; DriverVersion=$w.DriverVersion }; "
        "[pscustomobject]@{ Modele=\"$($cs.Manufacturer) $($cs.Model)\"; BIOS=\"$($b.SMBIOSBIOSVersion) du $($b.ReleaseDate.ToString('dd/MM/yyyy'))\"; "
        "Processeur=$cpu; Graphiques=($gpu -join ' ; '); NVIDIA=$nv; RAMGo=[math]::Round($cs.TotalPhysicalMemory/1GB); "
        "WiFi=\"$($wifi.DeviceName) (pilote $($wifi.DriverVersion))\"; Windows=\"$($os.Caption) build $($os.BuildNumber)\" } | ConvertTo-Json -Compress")
    if not d:
        return tr("mcp_sante.impossible_de_lire_la_fiche")
    f = d[0]
    return (tr("mcp_sante.modele_bios_installe_processeur_cartes", v1=f.get('Modele'), v2=f.get('BIOS'), v3=f.get('Processeur'), v4=f.get('Graphiques'), v5=f.get('NVIDIA'), v6=f.get('RAMGo'), v7=f.get('WiFi'), v8=f.get('Windows')))


if __name__ == "__main__":
    serveur.run()
