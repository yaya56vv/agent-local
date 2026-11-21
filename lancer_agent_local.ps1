# Agent Local - demarrage en un clic.
# Lit noyau\config.json (ecrit par l'assistant de premier lancement et la page Reglages), lance si besoin le modele
# (llama-server), la dictee et Docker selon les modules choisis, puis ouvre la fenetre.
# Regle : ce lanceur n'arrete JAMAIS un programme qu'il n'a pas lance lui-meme (numero note dans donnees\llama-server.pid).

param([switch]$AttendreFermeture)   # relance depuis la fenetre (assistant, Reglages) : attendre qu'elle se ferme
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'outils\langue.ps1')
. (Join-Path $PSScriptRoot 'outils\docker.ps1')
$installation = $PSScriptRoot
$noyau = Join-Path $installation 'noyau'
$donnees = Join-Path $noyau 'donnees'
$python = Join-Path $noyau '.venv\Scripts\python.exe'
$pythonw = Join-Path $noyau '.venv\Scripts\pythonw.exe'
$fichierPid = Join-Path $donnees 'llama-server.pid'
New-Item -ItemType Directory -Force $donnees | Out-Null

function Developper([string]$texte) {
    if (-not $texte) { return '' }
    $texte = $texte.Replace('{INSTALLATION}', $installation).Replace('{NOYAU}', $noyau).Replace('{DONNEES}', $donnees)
    [Environment]::ExpandEnvironmentVariables($texte)
}
function Ok($t) { Write-Host "  $(T 'lanceur.ok') $t" -ForegroundColor Green }
function Attention($t) { Write-Host "  $(T 'lanceur.attention') $t" -ForegroundColor Yellow }

Write-Host ''
Write-Host "  $(T 'lanceur.bandeau')" -ForegroundColor Cyan
Write-Host '  ----------------------------------------'

$null = Charger-Langue (Join-Path $installation 'langues') ''
if (-not (Test-Path $python)) {
    Write-Host "  $(T 'lanceur.erreur') $(T 'lanceur.non_installe')" -ForegroundColor Red
    Read-Host "  $(T 'lanceur.entree_fermer')"; exit 1
}

# 1. La fenetre est-elle deja ouverte ?
if ($AttendreFermeture) {
    for ($i = 0; $i -lt 30; $i++) {
        if (-not (Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" | Where-Object { $_.CommandLine -like "*$noyau*app.py*" })) { break }
        Start-Sleep -Milliseconds 500
    }
}
$dejaOuverte = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*$noyau*app.py*" }
if ($dejaOuverte) {
    Attention (T 'lanceur.deja_ouvert')
    Start-Sleep -Seconds 4; exit
}

$fichierConfig = Join-Path $noyau 'config.json'
if (-not (Test-Path $fichierConfig)) { $fichierConfig = Join-Path $noyau 'config.example.json' }
$config = Get-Content $fichierConfig -Raw -Encoding UTF8 | ConvertFrom-Json
$null = Charger-Langue (Join-Path $installation 'langues') $config.utilisateur.langue
$Host.UI.RawUI.WindowTitle = T 'lanceur.titre'
$modules = $config.modules
$lanceur = $config.lanceur

# 2. La dictee (Whisper) : avant le modele, pour qu'elle prenne sa place sur la carte graphique.
if ($config.premier_lancement_fait -and $modules.dictee) {
    $serveurDictee = Join-Path $installation 'modules\dictee\stt_server.py'
    $pythonDictee = Developper $config.dictee.python
    $enCours = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$serveurDictee*" }
    if ($enCours) { Ok (T 'lanceur.dictee_tourne') }
    elseif ((Test-Path $serveurDictee) -and (Test-Path $pythonDictee)) {
        $env:DICTEE_MODELE = $config.dictee.modele; $env:DICTEE_CARTE = $config.dictee.carte; $env:DICTEE_LANGUE = $config.dictee.langue
        Start-Process -FilePath ($pythonDictee -replace 'python\.exe$', 'pythonw.exe') -ArgumentList "`"$serveurDictee`"" `
            -WorkingDirectory (Split-Path $serveurDictee)
        Ok (T 'lanceur.dictee_lancee')
    } else { Attention (T 'lanceur.dictee_absente') }
}

# 3. Le modele (llama-server)
function Modele-Pret($port) {
    try { (Invoke-RestMethod "http://127.0.0.1:$port/v1/models" -TimeoutSec 3).data.Count -gt 0 } catch { $false }
}
if ($config.premier_lancement_fait) {
    $exe = Developper $lanceur.llama_server
    $modele = Developper $lanceur.modele
    $port = [string]$lanceur.port
    $notre = $null
    if (Test-Path $fichierPid) {
        $idNote = [int](Get-Content $fichierPid -Raw)
        $notre = Get-CimInstance Win32_Process -Filter "ProcessId=$idNote" | Where-Object { $_.ExecutablePath -eq $exe }
    }
    if ($notre -and (Modele-Pret $port)) {
        Ok (T 'lanceur.modele_tourne' @{ port = $port })
    } elseif (-not $notre -and (Modele-Pret $port)) {
        Attention (T 'lanceur.port_occupe' @{ port = $port })
        $choix = Read-Host "  $(T 'lanceur.port_choix')"
        if ($choix -notmatch "^[$(T 'lanceur.reponse_oui')]") { exit 1 }
    } elseif (-not (Test-Path $exe) -or -not (Test-Path $modele)) {
        Attention (T 'lanceur.moteur_introuvable')
    } else {
        $arguments = @('-m', "`"$modele`"", '-ngl', '99', '-c', [string]$lanceur.contexte, '--jinja',
                       '--host', $lanceur.hote, '--port', $port,
                       '--cache-type-k', $lanceur.cache_k, '--cache-type-v', $lanceur.cache_v)
        if ($modules.vision -and $lanceur.mmproj) { $arguments += @('--mmproj', "`"$(Developper $lanceur.mmproj)`"") }
        # Numerotation des cartes : celle de nvidia-smi (et de l'assistant), pas l'ordre « la plus rapide d'abord » de CUDA.
        $env:CUDA_DEVICE_ORDER = 'PCI_BUS_ID'
        if ($lanceur.cartes) {
            $arguments += @('--split-mode', 'layer', '--tensor-split', $lanceur.cartes)
            if ([string]$lanceur.carte_principale -ne '') { $arguments += @('--main-gpu', [string]$lanceur.carte_principale) }
        } elseif ([string]$lanceur.carte_principale -ne '') {
            $env:CUDA_VISIBLE_DEVICES = [string]$lanceur.carte_principale   # une seule carte : llama.cpp ne voit qu'elle
        }
        $arguments += @($lanceur.options_supplementaires)
        $journal = Join-Path $donnees 'llama-server.log'
        $p = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory (Split-Path $exe) -WindowStyle Hidden `
            -RedirectStandardError $journal -PassThru
        Set-Content -Path $fichierPid -Value $p.Id
        Write-Host "  $(T 'lanceur.chargement_modele' @{ nom = (Split-Path -Leaf $modele) })"
        $pret = $false
        for ($i = 1; $i -le 100; $i++) {
            Start-Sleep -Seconds 3
            if ($p.HasExited) { break }
            if (Modele-Pret $port) { $pret = $true; break }
            if ($i % 5 -eq 0) { Write-Host "    ... $($i * 3) s" }
        }
        if ($pret) { Ok (T 'lanceur.modele_pret') }
        else {
            Write-Host "  $(T 'lanceur.erreur') $(T 'lanceur.modele_echec')" -ForegroundColor Red
            Get-Content $journal -Tail 15 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "    $_" }
            Write-Host "  $(T 'lanceur.modele_causes')"
            if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }   # le notre seulement
            Remove-Item $fichierPid -ErrorAction SilentlyContinue
            Read-Host "  $(T 'lanceur.ouvrir_quand_meme')"
        }
    }
}

# 4. Docker Desktop et conteneurs : seulement si un module qui en a besoin est active (recherche web, messagerie, n8n).
#    Docker n'est jamais lance pour un compte hors du groupe docker-users (il planterait et proposerait de tout effacer).
$modulesDocker = @($MODULES_DOCKER | Where-Object { $modules.$_ })
if ($config.premier_lancement_fait -and $modulesDocker) {
    if (Docker-Repond) { Ok (T 'lanceur.docker_tourne') }
    elseif (-not (Docker-Installe)) { Attention (T 'lanceur.docker_introuvable') }
    elseif (-not (Verifier-GroupeDocker $installation $config.utilisateur.langue)) { Attention (T 'docker.sans_docker') }
    else {
        Write-Host "  $(T 'lanceur.docker_lancement')"
        if (Demarrer-Docker) { Ok (T 'lanceur.docker_pret') } else { Attention (T 'lanceur.docker_pas_pret') }
    }
    if (Docker-Repond) {
        foreach ($ligne in (Demarrer-Conteneurs $donnees $modulesDocker)) {
            $m, $e = $ligne -split '=', 2
            if ($e -eq 'ok') { Ok (T 'lanceur.conteneur_pret' @{ v1 = (T "as.module_$m") }) }
            elseif ($e -eq 'occupe') { Ok (T 'lanceur.conteneur_occupe' @{ v1 = (T "as.module_$m") }) }
            else { Attention (T 'lanceur.conteneur_echec' @{ v1 = (T "as.module_$m") }) }
        }
    }
}

# 5. La fenetre
Write-Host "  $(T 'lanceur.ouverture')"
Start-Process -FilePath $pythonw -ArgumentList 'app.py' -WorkingDirectory $noyau `
    -RedirectStandardError (Join-Path $donnees 'app_erreurs.log') -RedirectStandardOutput (Join-Path $donnees 'app_sortie.log')
Ok (T 'lanceur.parti')
Start-Sleep -Seconds 3
