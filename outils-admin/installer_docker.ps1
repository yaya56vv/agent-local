# Agent Local - installe Docker Desktop pour les modules qui en ont besoin (recherche web SearXNG, messagerie, n8n).
# Lance par l'assistant ou la page Reglages, APRES que l'utilisateur a coche « J'accepte » sous la licence de Docker,
# dans un PowerShell administrateur (confirmation Windows). Etapes :
#   1. WSL 2 : active les fonctions Windows « Sous-systeme Windows pour Linux » et « Plateforme de machine virtuelle »
#      si elles ne le sont pas (un redemarrage est alors necessaire) ;
#   2. Docker Desktop depuis la source officielle (winget, paquet Docker.DockerDesktop), s'il n'est pas deja installe ;
#   3. ajoute le compte qui utilise Agent Local au groupe « docker-users » (l'installateur de Docker n'y met que le compte
#      administrateur qui l'a lance) ;
#   4. ecrit le resultat dans le fichier -Resultat (lu par l'assistant) : faut-il redemarrer ?
# Ne touche a aucun reglage de Docker, ne lance aucun conteneur.
param([string]$Utilisateur = '', [string]$Langue = '', [switch]$LicencesAcceptees, [string]$Resultat = '')
. (Join-Path $PSScriptRoot 'commun.ps1')
Verifier-Admin
Start-Transcript -Path (Join-Path $env:ProgramData 'AgentLocal-docker-installation.log') -Append | Out-Null
$redemarrer = $false
function Ecrire-Resultat($ok, $message) {
    if ($Resultat) { [System.IO.File]::WriteAllText($Resultat, (@{ ok = $ok; redemarrage = $redemarrer; message = $message
                        date = (Get-Date).ToString('o') } | ConvertTo-Json), (New-Object System.Text.UTF8Encoding $false)) }
}
trap { Ecrire-Resultat $false $_.Exception.Message; Arret (T 'admin.commun.erreur_inattendue' @{ v1 = $_.Exception.Message }) }
if (-not $LicencesAcceptees) { Ecrire-Resultat $false (T 'docker.licence_non_acceptee'); Arret (T 'docker.licence_non_acceptee') }
$compte = Compte-Utilisateur $Utilisateur

Etape (T 'docker.etape_wsl')
foreach ($f in 'Microsoft-Windows-Subsystem-Linux', 'VirtualMachinePlatform') {
    $etat = (Get-WindowsOptionalFeature -Online -FeatureName $f).State
    if ($etat -eq 'Enabled') { Ok (T 'docker.fonction_active' @{ v1 = $f }) }
    else {
        $r = Enable-WindowsOptionalFeature -Online -FeatureName $f -All -NoRestart
        if ($r.RestartNeeded) { $redemarrer = $true }
        Ok (T 'docker.fonction_activee' @{ v1 = $f })
    }
}
if (-not $redemarrer) {   # WSL deja en place : mise a jour de son noyau (sans effet s'il est a jour)
    wsl.exe --update --web-download 2>&1 | Out-Null
    wsl.exe --set-default-version 2 2>&1 | Out-Null
}

Etape (T 'docker.etape_installation')
$exe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
if (Test-Path $exe) { Ok (T 'docker.deja_installe') }
else {
    # winget : commande de l'administrateur, sinon le winget installe pour tous (dossier WindowsApps)
    $winget = (Get-Command winget.exe -ErrorAction SilentlyContinue).Source
    if (-not $winget) {
        $paquet = Get-AppxPackage -AllUsers Microsoft.DesktopAppInstaller -ErrorAction SilentlyContinue | Sort-Object Version | Select-Object -Last 1
        if ($paquet) { $winget = Join-Path $paquet.InstallLocation 'winget.exe' } }
    if (-not $winget -or -not (Test-Path $winget)) { Ecrire-Resultat $false (T 'docker.winget_absent'); Arret (T 'docker.winget_absent') }
    Info (T 'docker.telechargement')
    & $winget install --id Docker.DockerDesktop --exact --source winget --scope machine --silent `
        --accept-package-agreements --accept-source-agreements --disable-interactivity
    if (-not (Test-Path $exe)) { Ecrire-Resultat $false (T 'docker.installation_echec' @{ v1 = $LASTEXITCODE }); Arret (T 'docker.installation_echec' @{ v1 = $LASTEXITCODE }) }
    if ($LASTEXITCODE -eq 3010) { $redemarrer = $true }
    Ok (T 'docker.installe')
}

Etape (T 'docker.etape_groupe')
$groupe = Get-LocalGroup -Name 'docker-users' -ErrorAction SilentlyContinue
if (-not $groupe) { $groupe = New-LocalGroup -Name 'docker-users' -Description 'Docker Desktop' }
$deja = $false
try { $deja = @(Get-LocalGroupMember -Group 'docker-users' -ErrorAction Stop | ForEach-Object { $_.SID.Value }) -contains $compte.Sid } catch { }
if ($deja) { Ok (T 'docker.deja_membre' @{ v1 = $compte.Nom }) }
else { Add-LocalGroupMember -SID $groupe.SID -Member $compte.Sid; Ok (T 'docker.ajoute' @{ v1 = $compte.Nom }); $redemarrer = $true }

Ecrire-Resultat $true ''
Write-Host ''
if ($redemarrer) { Write-Host "  $(T 'docker.fin_redemarrage')" -ForegroundColor Yellow } else { Write-Host "  $(T 'docker.fin_ok')" -ForegroundColor Green }
Stop-Transcript | Out-Null
Start-Sleep 4   # la fenetre se ferme seule : la suite se passe dans l'assistant
