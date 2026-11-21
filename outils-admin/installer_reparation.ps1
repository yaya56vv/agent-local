# Agent Local - outils administrateur facultatifs : TROUSSE DE REPARATION.
# Lance depuis l'assistant ou Reglages > Outils admin, avec la confirmation de Windows (UAC).
#
# Ce qu'il fait :
#   1. cree C:\ProgramData\AgentLocal\Reparation : scripts\ (ecriture reservee aux administrateurs), demande\ (Agent Local
#      y depose sa demande : modifiable par les Utilisateurs), resultats\ et pilotes\ ;
#   2. y ecrit le repartiteur : une LISTE FERMEE de gestes de depannage. Avant chaque geste (sauf la simple liste des
#      points de restauration), une fenetre « Agent Local - confirmation administrateur » s'ouvre sur l'ecran : Windows
#      interdit a un programme ordinaire d'y cliquer, donc un programme qui deposerait une fausse demande dans demande\
#      ne peut rien faire sans le clic de l'utilisateur. Sans reponse en 10 minutes, le geste est refuse ;
#   3. cree la tache planifiee \AgentLocal\Reparation (droits administrateur, lancee a la demande par Agent Local).
# Ne supprime rien.
param([string]$Utilisateur = '', [string]$Langue = '')
. (Join-Path $PSScriptRoot 'commun.ps1')
Verifier-Admin
Start-Transcript -Path (Join-Path $env:ProgramData 'AgentLocal-reparation-installation.log') -Append | Out-Null
trap { Arret (T 'admin.installer_reparation.erreur_inattendue_v1' @{ v1 = ($_.Exception.Message) }) }
$compte = Compte-Utilisateur $Utilisateur
if (-not $compte.Profil) { Arret (T 'admin.installer_reparation.profil_introuvable_pour_v1' @{ v1 = ($compte.Nom) }) }

Etape (T 'admin.installer_reparation.1_dossiers')
$scripts = Join-Path $REPARATION 'scripts'
Verifier-Avant-Ecrasement @($REPARATION) @('Reparation')
Proteger-Racine $RACINE_DONNEES
Proteger $REPARATION
Proteger $scripts
foreach ($d in 'demande', 'resultats', 'pilotes') { New-Item -ItemType Directory -Force (Join-Path $REPARATION $d) | Out-Null }
# demande\ : Agent Local (droits ordinaires) y depose sa demande ; la fenetre de confirmation fait barriere.
icacls (Join-Path $REPARATION 'demande') /grant "*${SID_UTILISATEURS}:(OI)(CI)M" | Out-Null
Verifier-Protege $scripts
Marquer $REPARATION
Ok (T 'admin.installer_reparation.v1_pret' @{ v1 = $REPARATION })

Etape (T 'admin.installer_reparation.2_repartiteur_liste_fermee_de')
$tempUtilisateur = Join-Path $compte.Profil 'AppData\Local\Temp'
$repartiteur = @'
# Repartiteur de la trousse de reparation d'Agent Local. Lance en ADMINISTRATEUR par la tache planifiee
# \AgentLocal\Reparation. N'execute QUE les gestes de la liste fermee ci-dessous ; la demande ne fait que choisir.
$base = Join-Path $env:ProgramData 'AgentLocal\Reparation'
$dem = Join-Path $base 'demande\demande.json'
if (-not (Test-Path $dem)) { exit }
$brut = Get-Content $dem -Raw -Encoding UTF8; Remove-Item $dem -Force
try { $d = $brut | ConvertFrom-Json } catch { exit }
$id = "$($d.id)"; if ($id -notmatch '^\d{8}-\d{6}-[a-z0-9]{4}$') { exit }
$geste = "$($d.geste)"; $cible = "$($d.cible)"
$res = Join-Path $base "resultats\$id.txt"
function Ecrire($t) { Add-Content -Path $res -Value $t -Encoding UTF8 }
# Textes : copie protegee du fichier de langue, posee a l'installation (un programme ordinaire ne peut pas la modifier)
$Ltextes = Get-Content (Join-Path $PSScriptRoot 'langue.json') -Raw -Encoding UTF8 | ConvertFrom-Json
function L($cle, $a = '', $b = '', $c = '') { $t = [string]$Ltextes."admin.repartiteur.$cle"; if (-not $t) { $t = $cle }; $t.Replace('{v1}', [string]$a).Replace('{v2}', [string]$b).Replace('{v3}', [string]$c) }
function Lancer($cmd) { $f = [IO.Path]::GetTempFileName(); cmd /c "chcp 65001 >nul & $cmd > `"$f`" 2>&1"; $o = Get-Content $f -Encoding UTF8 -Raw; Remove-Item $f; ($o -replace "`0", '') }
function PointRestauration($quoi) {
  try { Checkpoint-Computer -Description (L 'point_avant_description' $quoi) -RestorePointType MODIFY_SETTINGS -ErrorAction Stop
        Ecrire (L 'point_avant') }
  catch { Ecrire (L 'point_impossible' $_.Exception.Message); Ecrire "=== TERMINE ==="; exit } }
$services = 'Audiosrv','AudioEndpointBuilder','Spooler','wuauserv','BITS','WlanSvc','bthserv','WSLService','com.docker.service'
$disques = @(Get-Volume | Where-Object { $_.DriveType -eq 'Fixed' -and $_.DriveLetter } | ForEach-Object { [string]$_.DriveLetter })
$pilotes = Join-Path $base 'pilotes'
Ecrire (L 'geste_debut' $geste $cible (Get-Date -Format 'dd/MM/yyyy HH:mm:ss'))
if ($geste -ne 'lister_points') {
  Add-Type -AssemblyName System.Windows.Forms, System.Drawing
  $gestes = 'point_restauration', 'reparer_windows', 'verifier_disque', 'reparer_reseau_leger', 'reparer_reseau_complet',
    'redemarrer_service', 'nettoyer_temp', 'sauvegarder_pilotes', 'reinstaller_pilote', 'restaurer_point'
  $quoi = if ($geste -in $gestes) { L "lib_$geste" } else { L 'geste_inconnu' $geste }
  if ($cible) { $quoi = "$quoi : $cible" }
  $fen = New-Object System.Windows.Forms.Form
  $fen.Text = (L 'fenetre_titre'); $fen.TopMost = $true; $fen.StartPosition = 'CenterScreen'
  $fen.FormBorderStyle = 'FixedDialog'; $fen.MaximizeBox = $false; $fen.MinimizeBox = $false
  $fen.ClientSize = New-Object System.Drawing.Size(520, 200)
  $txt = New-Object System.Windows.Forms.Label
  $txt.Location = New-Object System.Drawing.Point(15, 15); $txt.Size = New-Object System.Drawing.Size(490, 130)
  $txt.Font = New-Object System.Drawing.Font('Segoe UI', 10)
  $txt.Text = (L 'fenetre_texte' $quoi)
  $oui = New-Object System.Windows.Forms.Button; $oui.Text = (L 'autoriser'); $oui.Size = New-Object System.Drawing.Size(110, 32)
  $oui.Location = New-Object System.Drawing.Point(270, 155); $oui.DialogResult = [System.Windows.Forms.DialogResult]::OK
  $non = New-Object System.Windows.Forms.Button; $non.Text = (L 'refuser'); $non.Size = New-Object System.Drawing.Size(110, 32)
  $non.Location = New-Object System.Drawing.Point(395, 155); $non.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
  $fen.Controls.AddRange(@($txt, $oui, $non)); $fen.AcceptButton = $non; $fen.CancelButton = $non; $fen.ActiveControl = $non
  $minuterie = New-Object System.Windows.Forms.Timer; $minuterie.Interval = 600000
  $minuterie.Add_Tick({ $fen.DialogResult = [System.Windows.Forms.DialogResult]::Cancel; $fen.Close() }); $minuterie.Start()
  $fen.Add_Shown({ $fen.Activate() })
  $reponse = $fen.ShowDialog(); $minuterie.Stop()
  if ($reponse -ne [System.Windows.Forms.DialogResult]::OK) {
    Ecrire (L 'refuse')
    Ecrire "=== TERMINE === le $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')"; exit }
  Ecrire (L 'confirme')
}
switch ($geste) {
  'point_restauration' { try { Checkpoint-Computer -Description (L 'point_manuel') -RestorePointType MODIFY_SETTINGS -ErrorAction Stop; Ecrire (L 'point_cree') } catch { Ecrire (L 'echec' $_.Exception.Message) } }
  'lister_points' { Get-ComputerRestorePoint | ForEach-Object { Ecrire ("n°{0} - {1} - {2}" -f $_.SequenceNumber, $_.ConvertToDateTime($_.CreationTime).ToString('dd/MM/yyyy HH:mm'), $_.Description) } }
  'reparer_windows' { PointRestauration (L 'reparation_windows')
    Ecrire (L 'dism')
    Ecrire ((Lancer 'DISM /Online /Cleanup-Image /RestoreHealth') -split "`r?`n" | Where-Object { $_ -match '\S' -and $_ -notmatch '^\s*\[' } | Select-Object -Last 6)
    Ecrire (L 'sfc')
    Ecrire ((Lancer 'sfc /scannow') -split "`r?`n" | Where-Object { $_ -match '\S' -and $_ -notmatch '%' } | Select-Object -Last 6) }
  'verifier_disque' { if ($cible -notin $disques) { Ecrire (L 'disque_refus' ($disques -join ', ')) } else {
    Ecrire ((Lancer "chkdsk ${cible}: /scan") -split "`r?`n" | Where-Object { $_ -match '\S' -and $_ -notmatch '%' } | Select-Object -Last 12) } }
  'reparer_reseau_leger' { Ecrire (Lancer 'ipconfig /flushdns')
    Get-NetAdapter -Physical | Where-Object Status -ne 'Disabled' | ForEach-Object { Restart-NetAdapter -Name $_.Name -Confirm:$false; Ecrire (L 'carte_redemarree' $_.Name) }
    Start-Sleep 10; Ecrire ((Lancer 'ipconfig /renew') -split "`r?`n" | Select-String 'IPv4|Passerelle|Gateway' | ForEach-Object { $_.Line.Trim() }) }
  'reparer_reseau_complet' { PointRestauration (L 'reinitialisation_reseau')
    Ecrire (Lancer 'netsh winsock reset'); Ecrire (Lancer 'netsh int ip reset'); Ecrire (Lancer 'ipconfig /flushdns')
    Ecrire (L 'redemarrage_necessaire') }
  'redemarrer_service' { if ($cible -notin $services) { Ecrire (L 'service_refus' ($services -join ', ')) } else {
    try { Restart-Service -Name $cible -Force -ErrorAction Stop; Ecrire (L 'service_redemarre' $cible (Get-Service $cible).Status) } catch { Ecrire (L 'echec' $_.Exception.Message) } } }
  'nettoyer_temp' { $avant = (Get-PSDrive C).Free
    foreach ($dos in "$env:windir\Temp", '__TEMP_UTILISATEUR__') {
      Get-ChildItem $dos -Recurse -Force -File -ErrorAction SilentlyContinue | Where-Object LastWriteTime -lt (Get-Date).AddDays(-2) | Remove-Item -Force -ErrorAction SilentlyContinue }
    Ecrire (L 'espace_libere' ('{0:N2}' -f (((Get-PSDrive C).Free - $avant) / 1GB))) }
  'sauvegarder_pilotes' { $dest = Join-Path $pilotes (Get-Date -Format 'yyyy-MM-dd')
    Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DeviceClass -in 'DISPLAY', 'MEDIA' -and $_.InfName -like 'oem*' } | ForEach-Object {
      $fam = if ($_.DeviceClass -eq 'DISPLAY') { 'graphique' } else { 'audio' }
      $dossier = Join-Path $dest "$fam\$($_.InfName)"; New-Item -ItemType Directory $dossier -Force | Out-Null
      pnputil /export-driver $_.InfName $dossier | Out-Null
      Ecrire (L 'sauvegarde_pilote' $_.DeviceName $_.DriverVersion $_.InfName) }
    Ecrire (L 'taille_totale' ('{0:N2}' -f ((Get-ChildItem $dest -Recurse -File | Measure-Object Length -Sum).Sum / 1GB)) $dest) }
  'reinstaller_pilote' { if ($cible -notin 'graphique','audio') { Ecrire (L 'pilote_refus') } else {
    $der = Get-ChildItem $pilotes -Directory | Sort-Object Name -Descending | Select-Object -First 1
    if (-not $der -or -not (Test-Path (Join-Path $der.FullName $cible))) { Ecrire (L 'pas_de_sauvegarde') } else {
      PointRestauration (L 'reinstallation_pilote' $cible)
      Ecrire (L 'sauvegarde_utilisee' $der.Name)
      Ecrire ((Lancer "pnputil /add-driver `"$(Join-Path $der.FullName $cible)\*.inf`" /subdirs /install") -split "`r?`n" | Where-Object { $_ -match '\S' } | Select-Object -Last 8) } } }
  'restaurer_point' { if ($cible -notmatch '^\d{1,5}$') { Ecrire (L 'point_refus') } else {
    Ecrire (L 'restauration' $cible); Ecrire '=== TERMINE ==='
    Restore-Computer -RestorePoint ([int]$cible) -Confirm:$false; exit } }
  default { Ecrire (L 'geste_refus' $geste) }
}
Ecrire "=== TERMINE === le $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')"
'@
Copy-Item (Join-Path (Split-Path $PSScriptRoot) "langues\$LANGUE_CHOISIE.json") (Join-Path $scripts 'langue.json') -Force
Ecrire-Script (Join-Path $scripts 'repartiteur.ps1') $repartiteur.Replace('__TEMP_UTILISATEUR__', $tempUtilisateur.Replace("'", "''"))
Verifier-Protege $scripts
Ok (T 'admin.installer_reparation.repartiteur_ecrit_fenetre_de_confirmation')

Etape (T 'admin.installer_reparation.3_tache_planifiee')
Enregistrer-Tache 'Reparation' (Action-PowerShell (Join-Path $scripts 'repartiteur.ps1')) $compte (New-TimeSpan -Hours 3)

Write-Host ''
Write-Host (T 'admin.installer_reparation.termine') -ForegroundColor Green
Stop-Transcript | Out-Null
Read-Host (T 'admin.commun.entree_fermer')
