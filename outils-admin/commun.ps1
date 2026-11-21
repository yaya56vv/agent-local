# Fonctions communes aux scripts administrateur d'Agent Local (charge par installer_sante.ps1, installer_reparation.ps1
# et desinstaller.ps1). Les droits sont toujours lus et ecrits par identifiant (SID), jamais par nom : les noms des
# groupes changent avec la langue de Windows (ex. BUILTIN\Utilisateurs) et certains ne se traduisent pas.

$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path $PSScriptRoot) 'outils\langue.ps1')
$LANGUE_CHOISIE = Charger-Langue (Join-Path (Split-Path $PSScriptRoot) 'langues') $Langue
$SID_SYSTEME = 'S-1-5-18'; $SID_ADMINS = 'S-1-5-32-544'; $SID_UTILISATEURS = 'S-1-5-32-545'
$SID_TRUSTEDINSTALLER = 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464'; $SID_CREATEUR = 'S-1-3-0'
$BOM = New-Object System.Text.UTF8Encoding $true
$OUTILS = Join-Path $env:ProgramFiles 'AgentLocalOutils'
$SANTE = Join-Path $env:ProgramData 'AgentLocalSante'
$DISQUES = Join-Path $env:ProgramData 'AgentLocalDisques'
$REPARATION = Join-Path $env:ProgramData 'AgentLocalReparation'
$script:lhmArrete = $false

function Etape($t) { Write-Host ''; Write-Host "=== $t" -ForegroundColor Cyan }
function Ok($t) { Write-Host "  [OK] $t" -ForegroundColor Green }
function Info($t) { Write-Host "  $t" }
function Arret($t) {
    Write-Host "  $(T 'admin.commun.arret') $t" -ForegroundColor Red
    if ($script:lhmArrete -and -not (Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue)) {
        Start-ScheduledTask -TaskName LibreHardwareMonitor -ErrorAction SilentlyContinue }
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

function Ecrire-Script($chemin, $texte) {
    $e = $null; [System.Management.Automation.Language.Parser]::ParseInput($texte, [ref]$null, [ref]$e) | Out-Null
    if ($e) { Arret (T 'admin.commun.le_script_prepare_pour_v1' @{ v1 = $chemin; v2 = ($e[0].Message) }) }
    [System.IO.File]::WriteAllText($chemin, $texte, $BOM)
}

function Proteger($dossier) {
    # Systeme et Administrateurs : controle total ; Utilisateurs : lecture seule. Les fichiers presents heritent.
    New-Item -ItemType Directory -Force $dossier | Out-Null
    icacls $dossier /inheritance:r /grant:r "*${SID_SYSTEME}:(OI)(CI)F" "*${SID_ADMINS}:(OI)(CI)F" "*${SID_UTILISATEURS}:(OI)(CI)RX" | Out-Null
    if ($LASTEXITCODE -ne 0) { Arret (T 'admin.commun.icacls_a_echoue_sur_v1' @{ v1 = $dossier }) }
    if (Get-ChildItem $dossier -Force) { icacls "$dossier\*" /reset /T /C | Out-Null }
}

function Verifier-Protege($dossier) {
    # Masque : ecriture (0x116), suppression (0x40, 0x10000), droits et propriete (0x40000, 0x80000), GENERIC_ALL et
    # GENERIC_WRITE (forme des droits herites). CREATEUR PROPRIETAIRE ne vise que l'auteur d'un nouveau fichier, donc
    # un compte qui pouvait deja ecrire ici.
    $admis = $SID_SYSTEME, $SID_ADMINS, $SID_TRUSTEDINSTALLER, $SID_CREATEUR
    $faibles = (Get-Acl $dossier).GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]) | Where-Object {
        $_.AccessControlType -eq 'Allow' -and $_.IdentityReference.Value -notin $admis -and ([int]$_.FileSystemRights -band 0x500D0156) }
    if ($faibles) { Arret (T 'admin.commun.v1_n_est_pas_protege' @{ v1 = $dossier; v2 = $faibles })$($_.IdentityReference.Value) $($_.FileSystemRights)" }) -join ' ; ')" }
    Ok (T 'admin.commun.v1_ecriture_reservee_aux_administrateurs' @{ v1 = $dossier })
}

function Enregistrer-Tache($nom, $action, $compte, $limite, [switch]$AuDemarrageDeSession) {
    $principal = New-ScheduledTaskPrincipal -UserId $compte.Sid -LogonType Interactive -RunLevel Highest
    $reglages = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit $limite
    $options = @{ Action = $action; Principal = $principal; Settings = $reglages
                  Description = 'Agent Local (outils administrateur facultatifs)' }
    if ($AuDemarrageDeSession) { $d = New-ScheduledTaskTrigger -AtLogOn -User $compte.Nom; $d.Delay = 'PT30S'; $options.Trigger = $d }
    $tache = New-ScheduledTask @options
    Register-ScheduledTask -TaskName $nom -InputObject $tache -Force | Out-Null
    Ok (T 'admin.commun.tache_planifiee_v1_compte_v2' @{ v1 = $nom; v2 = ($compte.Nom) })
}

function Action-PowerShell($script, $dossierTravail) {
    $a = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
    if ($dossierTravail) { New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $a -WorkingDirectory $dossierTravail }
    else { New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $a }
}
