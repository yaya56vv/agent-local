# Agent Local - outils administrateur facultatifs : SANTE DU PC.
# Lance depuis l'assistant ou Reglages > Outils admin (bouton « Installer » ou « Reparer / mettre a jour »), avec la
# confirmation de Windows (UAC). Relancer ce script apres une mise a jour winget d'Autoruns ou de LibreHardwareMonitor :
# il recopie les outils et releve de nouvelles empreintes.
#
# Ce qu'il fait :
#   1. installe avec winget, depuis la source officielle, Autoruns (Microsoft Sysinternals), LibreHardwareMonitor et
#      CrystalDiskInfo, si absents. Leurs licences ont ete affichees et acceptees dans l'assistant (-LicencesAcceptees) ;
#   2. copie Autoruns et LibreHardwareMonitor dans C:\Program Files\AgentLocalOutils (ecriture reservee aux
#      administrateurs), car un programme lance en administrateur ne doit jamais venir d'un dossier modifiable ;
#   3. lanceurs avec controle d'integrite : signature Microsoft pour Autoruns, empreintes SHA-256 pour LHM (un fichier de
#      code change, manquant ou en trop = pas de lancement, note dans C:\ProgramData\AgentLocalSante\controle_integrite.log) ;
#   4. taches planifiees AutorunsAgent, LibreHardwareMonitor (ouverture de session) et DisquesAgent, pour ce compte ;
#   5. pare-feu : le serveur web de LibreHardwareMonitor (port 8085) n'est joignable que depuis ce PC.
# Ne supprime rien. N'envoie rien sur Internet en dehors des telechargements winget.
param([string]$Utilisateur = '', [switch]$LicencesAcceptees, [string]$Langue = '')
. (Join-Path $PSScriptRoot 'commun.ps1')
Verifier-Admin
Start-Transcript -Path (Join-Path $env:ProgramData 'AgentLocalSante-installation.log') -Append | Out-Null
trap { Arret (T 'admin.installer_sante.erreur_inattendue_v1' @{ v1 = ($_.Exception.Message) }) }
if (-not $LicencesAcceptees) { Arret (T 'admin.installer_sante.les_licences_n_ont_pas') }
$compte = Compte-Utilisateur $Utilisateur

function Source-WinGet($motif) {
    $c = @(foreach ($racine in "$env:LOCALAPPDATA\Microsoft\WinGet\Packages", "$env:ProgramFiles\WinGet\Packages",
                               "$($compte.Profil)\AppData\Local\Microsoft\WinGet\Packages") {
        Get-ChildItem (Join-Path $racine $motif) -ErrorAction SilentlyContinue }) | Sort-Object FullName -Unique
    if ($c.Count -gt 1) { Arret (T 'admin.installer_sante.plusieurs_sources_possibles_pour_v1' @{ v1 = $motif; v2 = (($c.FullName) -join ' ; ') }) }
    if ($c.Count -eq 1) { $c[0].FullName }
}
function Installer-WinGet($id) {
    Info (T 'admin.installer_sante.winget_v1' @{ v1 = $id })
    winget install --id $id --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Null
    # 0 = installe ; -1978335189 = deja installe, rien a mettre a jour
    if ($LASTEXITCODE -notin 0, -1978335189) { Arret (T 'admin.installer_sante.winget_n_a_pas_pu' @{ v1 = $id; v2 = $LASTEXITCODE }) }
}

Etape (T 'admin.installer_sante.1_telechargement_depuis_la_source')
$exeAutoruns = Source-WinGet 'Microsoft.Sysinternals.Autoruns_*\autorunsc64.exe'
if (-not $exeAutoruns) { Installer-WinGet 'Microsoft.Sysinternals.Autoruns'; $exeAutoruns = Source-WinGet 'Microsoft.Sysinternals.Autoruns_*\autorunsc64.exe' }
$exeLhm = Source-WinGet 'LibreHardwareMonitor.LibreHardwareMonitor_*\LibreHardwareMonitor.exe'
if (-not $exeLhm) { Installer-WinGet 'LibreHardwareMonitor.LibreHardwareMonitor'; $exeLhm = Source-WinGet 'LibreHardwareMonitor.LibreHardwareMonitor_*\LibreHardwareMonitor.exe' }
$exeDiskInfo = Join-Path $env:ProgramFiles 'CrystalDiskInfo\DiskInfo64.exe'
if (-not (Test-Path $exeDiskInfo)) { Installer-WinGet 'CrystalDewWorld.CrystalDiskInfo' }
foreach ($f in $exeAutoruns, $exeLhm, $exeDiskInfo) { if (-not $f -or -not (Test-Path $f)) { Arret (T 'admin.installer_sante.introuvable_apres_installation_v1' @{ v1 = $f }) } }
$sig = Get-AuthenticodeSignature $exeAutoruns
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { Arret (T 'admin.installer_sante.signature_d_autoruns_invalide_v1' @{ v1 = ($sig.Status) }) }
Ok (T 'admin.installer_sante.autoruns_v1_signature_microsoft_valide' @{ v1 = $exeAutoruns })
Ok (T 'admin.installer_sante.librehardwaremonitor_v1_non_signe_par' @{ v1 = $exeLhm })
Ok (T 'admin.installer_sante.crystaldiskinfo_v1' @{ v1 = $exeDiskInfo })

Etape (T 'admin.installer_sante.2_dossiers_proteges')
Proteger $SANTE; Verifier-Protege $SANTE
Proteger $DISQUES; Verifier-Protege $DISQUES
New-Item -ItemType Directory -Force "$OUTILS\Autoruns", "$OUTILS\LibreHardwareMonitor" | Out-Null
Verifier-Protege $OUTILS

Etape (T 'admin.installer_sante.3_copie_des_outils_et')
$lhmEnCours = Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue
if ($lhmEnCours) { $lhmEnCours | Stop-Process -Force; $script:lhmArrete = $true; Start-Sleep 3; Info (T 'admin.installer_sante.librehardwaremonitor_arrete_le_temps_de') }
Copy-Item $exeAutoruns "$OUTILS\Autoruns\autorunsc64.exe" -Force
$eula = Join-Path (Split-Path $exeAutoruns) 'Eula.txt'; if (Test-Path $eula) { Copy-Item $eula "$OUTILS\Autoruns\Eula.txt" -Force }
if ((Get-AuthenticodeSignature "$OUTILS\Autoruns\autorunsc64.exe").Status -ne 'Valid') { Arret (T 'admin.installer_sante.la_copie_d_autoruns_n') }
Ok (T 'admin.installer_sante.autoruns_copie_signature_microsoft_valide')
robocopy (Split-Path $exeLhm) "$OUTILS\LibreHardwareMonitor" /E /R:2 /W:2 /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { Arret (T 'admin.installer_sante.robocopy_a_echoue_code_v1' @{ v1 = $LASTEXITCODE }) }
$configLhm = "$OUTILS\LibreHardwareMonitor\LibreHardwareMonitor.config"
if (-not (Test-Path $configLhm)) {
    # Serveur web sur le port 8085 (lu par l'outil sante__temperatures), demarrage reduit dans la zone de notification.
    [IO.File]::WriteAllText($configLhm, @'
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <appSettings>
    <add key="runWebServerMenuItem" value="true" />
    <add key="listenerPort" value="8085" />
    <add key="startMinMenuItem" value="true" />
    <add key="minTrayMenuItem" value="true" />
    <add key="minCloseMenuItem" value="true" />
  </appSettings>
</configuration>
'@, $BOM)
}
$code = Get-ChildItem "$OUTILS\LibreHardwareMonitor" -Recurse -File | Where-Object { $_.Name -match '\.(exe|dll)$|\.exe\.config$' }
$empreintes = [ordered]@{}
foreach ($f in $code) { $empreintes[$f.FullName.Substring("$OUTILS\LibreHardwareMonitor".Length + 1)] = (Get-FileHash $f.FullName -Algorithm SHA256).Hash }
($empreintes | ConvertTo-Json) | Set-Content "$OUTILS\empreintes_lhm.json" -Encoding UTF8
Ok (T 'admin.installer_sante.librehardwaremonitor_copie_empreintes_de_v1' @{ v1 = ($empreintes.Count) })

Etape (T 'admin.installer_sante.4_lanceurs_avec_controle_d')
Copy-Item (Join-Path (Split-Path $PSScriptRoot) "langues\$LANGUE_CHOISIE.json") (Join-Path $OUTILS 'langue.json') -Force
Ecrire-Script "$OUTILS\lancer_autoruns.ps1" @'
# Lance Autoruns (tache AutorunsAgent, administrateur) depuis le dossier protege, apres controle de sa signature.
$exe = Join-Path $env:ProgramFiles 'AgentLocalOutils\Autoruns\autorunsc64.exe'
$sortie = Join-Path $env:ProgramData 'AgentLocalSante\autoruns.csv'
$journal = Join-Path $env:ProgramData 'AgentLocalSante\controle_integrite.log'
$L = Get-Content (Join-Path $env:ProgramFiles 'AgentLocalOutils\langue.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$sig = Get-AuthenticodeSignature -FilePath $exe
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
  Add-Content -Path $journal -Value "$(Get-Date -Format 'dd/MM/yyyy HH:mm:ss') $($L.'admin.integrite.autoruns_refus'.Replace('{v1}', [string]$sig.Status))" -Encoding UTF8
  exit 1 }
& $exe -accepteula -nobanner -a bdehlmstw -c -s -o $sortie
'@
Ecrire-Script "$OUTILS\lancer_lhm.ps1" @'
# Lance LibreHardwareMonitor (tache du meme nom, administrateur, a l'ouverture de session) depuis le dossier protege,
# apres comparaison de chaque fichier de code (.exe, .dll, .exe.config) aux empreintes relevees a l'installation.
# Un fichier de code change, manquant ou en trop = pas de lancement. Apres une mise a jour : Reglages > Outils admin >
# Reparer / mettre a jour.
$dossier = Join-Path $env:ProgramFiles 'AgentLocalOutils\LibreHardwareMonitor'
$journal = Join-Path $env:ProgramData 'AgentLocalSante\controle_integrite.log'
$L = Get-Content (Join-Path $env:ProgramFiles 'AgentLocalOutils\langue.json') -Raw -Encoding UTF8 | ConvertFrom-Json
function Refus($cle, $v) { Add-Content -Path $journal -Value "$(Get-Date -Format 'dd/MM/yyyy HH:mm:ss') $($L.'admin.integrite.lhm_refus'.Replace('{v1}', $L."admin.integrite.$cle".Replace('{v1}', $v)))" -Encoding UTF8; exit 1 }
$attendu = @{}
(Get-Content (Join-Path $env:ProgramFiles 'AgentLocalOutils\empreintes_lhm.json') -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $attendu[$_.Name] = $_.Value }
$code = Get-ChildItem $dossier -Recurse -File | Where-Object { $_.Name -match '\.(exe|dll)$|\.exe\.config$' }
foreach ($f in $code) {
  $rel = $f.FullName.Substring($dossier.Length + 1)
  if (-not $attendu.ContainsKey($rel)) { Refus 'inattendu' $rel }
  if ((Get-FileHash $f.FullName -Algorithm SHA256).Hash -ne $attendu[$rel]) { Refus 'modifie' $rel } }
foreach ($rel in $attendu.Keys) { if (-not (Test-Path (Join-Path $dossier $rel))) { Refus 'manquant' $rel } }
Start-Process -FilePath (Join-Path $dossier 'LibreHardwareMonitor.exe') -WorkingDirectory $dossier
'@
Ecrire-Script "$DISQUES\disques.ps1" @'
# Etat des disques par CrystalDiskInfo (tache DisquesAgent, administrateur) : rapport copie dans un dossier protege.
$exe = Join-Path $env:ProgramFiles 'CrystalDiskInfo\DiskInfo64.exe'
$src = Join-Path $env:ProgramFiles 'CrystalDiskInfo\DiskInfo.txt'
$dst = Join-Path $env:ProgramData 'AgentLocalDisques\DiskInfo.txt'
Remove-Item $src -ErrorAction SilentlyContinue
Start-Process $exe -ArgumentList '/CopyExit' -Wait
for ($i = 0; $i -lt 60 -and -not (Test-Path $src); $i++) { Start-Sleep 1 }
if (Test-Path $src) { Copy-Item $src $dst -Force }
'@
Verifier-Protege $OUTILS; Verifier-Protege $DISQUES
Ok (T 'admin.installer_sante.lanceurs_ecrits')

Etape (T 'admin.installer_sante.5_taches_planifiees_et_pare')
Enregistrer-Tache 'AutorunsAgent' (Action-PowerShell "$OUTILS\lancer_autoruns.ps1") $compte 'PT5M'
Enregistrer-Tache 'LibreHardwareMonitor' (Action-PowerShell "$OUTILS\lancer_lhm.ps1" "$OUTILS\LibreHardwareMonitor") $compte 'PT0S' -AuDemarrageDeSession
Enregistrer-Tache 'DisquesAgent' (Action-PowerShell "$DISQUES\disques.ps1") $compte 'PT5M'
Get-NetFirewallRule -DisplayName 'Agent Local - LibreHardwareMonitor' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName 'Agent Local - LibreHardwareMonitor' -Direction Inbound -Action Block `
    -Program "$OUTILS\LibreHardwareMonitor\LibreHardwareMonitor.exe" -Profile Any | Out-Null
Ok (T 'admin.installer_sante.pare_feu_librehardwaremonitor_injoignable_depuis')

Etape (T 'admin.installer_sante.6_essais')
Start-ScheduledTask -TaskName LibreHardwareMonitor
$lhmOk = $false
for ($i = 0; $i -lt 12 -and -not $lhmOk; $i++) {
    Start-Sleep 5
    try { Invoke-RestMethod 'http://127.0.0.1:8085/data.json' -TimeoutSec 3 | Out-Null; $lhmOk = $true } catch { }
}
if ($lhmOk) { Ok (T 'admin.installer_sante.librehardwaremonitor_repond_sur_le_port') }
else { Write-Host "  $(T 'admin.commun.a_verifier') $(T 'admin.installer_sante.lhm_a_verifier' @{ journal = "$SANTE\controle_integrite.log" })" -ForegroundColor Yellow }
$debut = Get-Date
Start-ScheduledTask -TaskName AutorunsAgent
$csv = Join-Path $SANTE 'autoruns.csv'
for ($i = 0; $i -lt 36; $i++) {
    Start-Sleep 5
    if ((Test-Path $csv) -and (Get-Item $csv).LastWriteTime -gt $debut -and (Get-ScheduledTask -TaskName AutorunsAgent).State -ne 'Running') { break }
}
if ((Test-Path $csv) -and (Get-Item $csv).LastWriteTime -gt $debut) { Ok (T 'admin.installer_sante.autoruns_a_produit_v1' @{ v1 = $csv }) }
else { Write-Host "  $(T 'admin.commun.a_verifier') $(T 'admin.installer_sante.autoruns_a_verifier' @{ csv = $csv; journal = "$SANTE\controle_integrite.log" })" -ForegroundColor Yellow }

Write-Host ''
Write-Host (T 'admin.installer_sante.termine') -ForegroundColor Green
Stop-Transcript | Out-Null
Read-Host (T 'admin.commun.entree_fermer')
