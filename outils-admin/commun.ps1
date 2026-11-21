# Fonctions communes aux scripts administrateur d'Agent Local (charge par installer_sante.ps1, installer_reparation.ps1
# et desinstaller.ps1). Les droits sont toujours lus et ecrits par identifiant (SID), jamais par nom : les noms des
# groupes changent avec la langue de Windows (ex. BUILTIN\Utilisateurs) et certains ne se traduisent pas.
# Tout ce que ces scripts creent porte des noms propres a cette version : dossiers C:\ProgramData\AgentLocal et
# C:\Program Files\AgentLocal, taches dans le dossier \AgentLocal\ du Planificateur. Une autre installation (par exemple
# une version personnelle d'Agent Local) n'est donc jamais touchee.

$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path $PSScriptRoot) 'outils\langue.ps1')
$LANGUE_CHOISIE = Charger-Langue (Join-Path (Split-Path $PSScriptRoot) 'langues') $Langue
$SID_SYSTEME = 'S-1-5-18'; $SID_ADMINS = 'S-1-5-32-544'; $SID_UTILISATEURS = 'S-1-5-32-545'
$SID_TRUSTEDINSTALLER = 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464'; $SID_CREATEUR = 'S-1-3-0'
$BOM = New-Object System.Text.UTF8Encoding $true
$RACINE_DONNEES = Join-Path $env:ProgramData 'AgentLocal'
$RACINE_OUTILS = Join-Path $env:ProgramFiles 'AgentLocal'
$OUTILS = Join-Path $RACINE_OUTILS 'Outils'
$SANTE = Join-Path $RACINE_DONNEES 'Sante'
$DISQUES = Join-Path $RACINE_DONNEES 'Disques'
$REPARATION = Join-Path $RACINE_DONNEES 'Reparation'
$DOSSIER_TACHES = '\AgentLocal\'          # dossier propre du Planificateur de taches
$MARQUE = '.installe-par-agent-local'     # fichier temoin : ce dossier a ete cree par ces scripts
$script:lhmArrete = $false

function Etape($t) { Write-Host ''; Write-Host "=== $t" -ForegroundColor Cyan }
function Ok($t) { Write-Host "  [OK] $t" -ForegroundColor Green }
function Info($t) { Write-Host "  $t" }
function Arret($t) {
    Write-Host "  $(T 'admin.commun.arret') $t" -ForegroundColor Red
    if ($script:lhmArrete -and -not (Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$OUTILS\*" })) {
        Start-ScheduledTask -TaskPath $DOSSIER_TACHES -TaskName LibreHardwareMonitor -ErrorAction SilentlyContinue }
    Write-Host "  $(T 'admin.commun.rien_de_plus')" -ForegroundColor Red
    try { Stop-Transcript | Out-Null } catch { }
    Read-Host (T 'admin.commun.entree_fermer'); exit 1
}

function Verifier-Admin {
    $p = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { Arret (T 'admin.commun.ce_script_doit_etre_lance') }
}

function Compte-Utilisateur([string]$utilisateur) {
    # Compte pour lequel les taches sont creees : celui qui utilise Agent Local (transmis par l'interface), sinon
    # le compte qui lance ce script.
    if (-not $utilisateur) { $utilisateur = [Security.Principal.WindowsIdentity]::GetCurrent().Name }
    try { $sid = (New-Object Security.Principal.NTAccount($utilisateur)).Translate([Security.Principal.SecurityIdentifier]).Value }
    catch { Arret (T 'admin.commun.compte_windows_inconnu_v1' @{ v1 = $utilisateur }) }
    [pscustomobject]@{ Nom = $utilisateur; Sid = $sid
                       Profil = (Get-CimInstance Win32_UserProfile -Filter "SID='$sid'").LocalPath }
}

function Verifier-Avant-Ecrasement($dossiers, $taches) {
    # Jamais d'ecrasement silencieux : un dossier cible qui existe sans le fichier temoin, ou une tache du meme nom
    # qui n'a pas ete creee par ces scripts, est montre a l'utilisateur, qui doit taper OUI pour continuer.
    # (Une reinstallation ou « Reparer / mettre a jour » trouve le temoin : aucune question.)
    $etrangers = @()
    foreach ($d in $dossiers) { if ((Test-Path $d) -and -not (Test-Path (Join-Path $d $MARQUE))) { $etrangers += $d } }
    foreach ($t in $taches) {
        $x = Get-ScheduledTask -TaskPath $DOSSIER_TACHES -TaskName $t -ErrorAction SilentlyContinue
        # description posee par Enregistrer-Tache (en francais ou en anglais selon la langue de l'installation)
        if ($x -and $x.Description -notlike 'Agent Local (*') { $etrangers += "$DOSSIER_TACHES$t" } }
    if (-not $etrangers) { return }
    Write-Host ''
    Write-Host "  $(T 'admin.commun.installation_existante')" -ForegroundColor Yellow
    foreach ($e in $etrangers) { Info "- $e" }
    $mot = T 'admin.desinstaller.mot_oui'
    if ((Read-Host (T 'admin.commun.taper_pour_ecraser' @{ mot = $mot })) -cne $mot) { Arret (T 'admin.commun.ecrasement_refuse') }
}

function Marquer($dossier) { Set-Content -Path (Join-Path $dossier $MARQUE) -Value (Get-Date -Format 'yyyy-MM-dd HH:mm') -Encoding ASCII }

function Ecrire-Script($chemin, $texte) {
    $e = $null; [System.Management.Automation.Language.Parser]::ParseInput($texte, [ref]$null, [ref]$e) | Out-Null
    if ($e) { Arret (T 'admin.commun.le_script_prepare_pour_v1' @{ v1 = $chemin; v2 = ($e[0].Message) }) }
    [System.IO.File]::WriteAllText($chemin, $texte, $BOM)
}

function Proteger-Racine($dossier) {
    # Dossier parent (C:\ProgramData\AgentLocal, C:\Program Files\AgentLocal) : proprietaire = Administrateurs, et les
    # Utilisateurs n'y creent rien. Les droits propres des sous-dossiers (ex. demande\) ne sont pas reinitialises.
    New-Item -ItemType Directory -Force $dossier | Out-Null
    icacls $dossier /setowner "*$SID_ADMINS" /C | Out-Null
    icacls $dossier /inheritance:r /grant:r "*${SID_SYSTEME}:(OI)(CI)F" "*${SID_ADMINS}:(OI)(CI)F" "*${SID_UTILISATEURS}:(OI)(CI)RX" | Out-Null
    if ($LASTEXITCODE -ne 0) { Arret (T 'admin.commun.icacls_a_echoue_sur_v1' @{ v1 = $dossier }) }
}

function Proteger($dossier) {
    # Systeme et Administrateurs : controle total ; Utilisateurs : lecture seule. Le proprietaire devient Administrateurs
    # (un dossier cree a l'avance par un programme ordinaire lui laisserait sinon le droit de changer les droits).
    New-Item -ItemType Directory -Force $dossier | Out-Null
    icacls $dossier /setowner "*$SID_ADMINS" /T /C | Out-Null
    icacls $dossier /inheritance:r /grant:r "*${SID_SYSTEME}:(OI)(CI)F" "*${SID_ADMINS}:(OI)(CI)F" "*${SID_UTILISATEURS}:(OI)(CI)RX" | Out-Null
    if ($LASTEXITCODE -ne 0) { Arret (T 'admin.commun.icacls_a_echoue_sur_v1' @{ v1 = $dossier }) }
    if (Get-ChildItem $dossier -Force) { icacls "$dossier\*" /reset /T /C | Out-Null }
}

function Verifier-Protege($dossier) {
    # Masque : ecriture (0x116), suppression (0x40, 0x10000), droits et propriete (0x40000, 0x80000), GENERIC_ALL et
    # GENERIC_WRITE (forme des droits herites). CREATEUR PROPRIETAIRE ne vise que l'auteur d'un nouveau fichier, donc
    # un compte qui pouvait deja ecrire ici. Le proprietaire doit etre Administrateurs ou Systeme.
    $acl = Get-Acl $dossier
    $admis = $SID_SYSTEME, $SID_ADMINS, $SID_TRUSTEDINSTALLER, $SID_CREATEUR
    $faibles = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]) | Where-Object {
        $_.AccessControlType -eq 'Allow' -and $_.IdentityReference.Value -notin $admis -and ([int]$_.FileSystemRights -band 0x500D0156) })
    $proprietaire = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
    if ($proprietaire -notin $SID_SYSTEME, $SID_ADMINS, $SID_TRUSTEDINSTALLER) { $faibles += "proprietaire $proprietaire" }
    if ($faibles) {
        $detail = ($faibles | ForEach-Object { if ($_ -is [string]) { $_ } else { "$($_.IdentityReference.Value) $($_.FileSystemRights)" } }) -join ' ; '
        Arret (T 'admin.commun.v1_n_est_pas_protege' @{ v1 = $dossier; v2 = $detail }) }
    Ok (T 'admin.commun.v1_ecriture_reservee_aux_administrateurs' @{ v1 = $dossier })
}

function Enregistrer-Tache($nom, $action, $compte, [TimeSpan]$limite, [switch]$AuDemarrageDeSession) {
    # $limite est une vraie duree (New-TimeSpan, [TimeSpan]::Zero = sans limite) : jamais un texte comme 'PT5M'.
    $principal = New-ScheduledTaskPrincipal -UserId $compte.Sid -LogonType Interactive -RunLevel Highest
    $reglages = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit $limite
    $options = @{ Action = $action; Principal = $principal; Settings = $reglages; Description = (T 'admin.commun.description_tache') }
    if ($AuDemarrageDeSession) {
        $declencheur = New-ScheduledTaskTrigger -AtLogOn -User $compte.Nom
        $declencheur.Delay = 'PT30S'   # cette propriete-ci est un texte au format ISO 8601 (30 secondes apres l'ouverture de session)
        $options.Trigger = $declencheur
    }
    Register-ScheduledTask -TaskPath $DOSSIER_TACHES -TaskName $nom -InputObject (New-ScheduledTask @options) -Force | Out-Null
    Ok (T 'admin.commun.tache_planifiee_v1_compte_v2' @{ v1 = "$DOSSIER_TACHES$nom"; v2 = ($compte.Nom) })
}

function Action-PowerShell($script, $dossierTravail) {
    $a = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
    if ($dossierTravail) { New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $a -WorkingDirectory $dossierTravail }
    else { New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $a }
}
