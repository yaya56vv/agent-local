# Agent Local - installation minimale. Clic droit > « Executer avec PowerShell », ou :
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer.ps1
# Installe seulement le strict minimum : Python 3.13 et Node.js LTS (avec winget, s'ils manquent), l'environnement Python
# du noyau et ses dependances figees (requirements.txt). Cree un raccourci sur le Bureau puis ouvre Agent Local, dont
# l'assistant propose ensuite tout le reste (modele, moteur, modules), avec leurs licences.
# Ne demande pas les droits administrateur. Ne supprime rien.
param([switch]$SansRaccourci, [switch]$SansLancement)
$ErrorActionPreference = 'Stop'
$installation = $PSScriptRoot
. (Join-Path $installation 'outils\langue.ps1')
. (Join-Path $installation 'outils\docker.ps1')
$langue = Charger-Langue (Join-Path $installation 'langues') ''
function Ok($t) { Write-Host "  [OK] $t" -ForegroundColor Green }
function Etape($t) { Write-Host ''; Write-Host "== $t" -ForegroundColor Cyan }
function Echec($t) { Write-Host "  [!] $t" -ForegroundColor Red; Read-Host (T 'installeur.entree_fermer'); exit 1 }
$Host.UI.RawUI.WindowTitle = T 'installeur.titre'
Write-Host ''
Write-Host ('  ' + (T 'installeur.titre')) -ForegroundColor Cyan

Etape (T 'installeur.etape_prerequis')
if ([Environment]::OSVersion.Version.Build -lt 19045) { Echec (T 'installeur.windows_trop_ancien') }
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Echec (T 'installeur.winget_absent') }
function Python313 {
    foreach ($c in @((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'), (Join-Path $env:ProgramFiles 'Python313\python.exe'))) {
        if (Test-Path $c) { return $c } }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { $chemin = & py -3.13 -c "import sys; print(sys.executable)" 2>$null; if ($LASTEXITCODE -eq 0 -and $chemin) { return $chemin.Trim() } }
    return $null
}
$python = Python313
if (-not $python) {
    Write-Host ('  ' + (T 'installeur.installation_python'))
    winget install --id Python.Python.3.13 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Null
    $python = Python313
    if (-not $python) { Echec (T 'installeur.python_echec') }
}
Ok (T 'installeur.python_ok' @{ chemin = $python })
if (-not (Get-Command node -ErrorAction SilentlyContinue) -and -not (Test-Path (Join-Path $env:ProgramFiles 'nodejs\node.exe'))) {
    Write-Host ('  ' + (T 'installeur.installation_node'))
    winget install --id OpenJS.NodeJS.LTS --exact --source winget --silent --accept-package-agreements --accept-source-agreements | Out-Null
    if (-not (Test-Path (Join-Path $env:ProgramFiles 'nodejs\node.exe'))) { Echec (T 'installeur.node_echec') }
}
Ok (T 'installeur.node_ok')

Etape (T 'installeur.etape_environnement')
$venv = Join-Path $installation 'noyau\.venv'
if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) { & $python -m venv $venv; if ($LASTEXITCODE) { Echec (T 'installeur.venv_echec') } }
& (Join-Path $venv 'Scripts\python.exe') -m pip install --disable-pip-version-check --quiet -r (Join-Path $installation 'requirements.txt')
if ($LASTEXITCODE) { Echec (T 'installeur.pip_echec') }
Ok (T 'installeur.dependances_ok')
$config = Join-Path $installation 'noyau\config.json'
if (-not (Test-Path $config)) {
    Copy-Item (Join-Path $installation 'noyau\config.example.json') $config
    Ok (T 'installeur.config_creee')
} else { Ok (T 'installeur.config_gardee') }

if (Docker-Installe) {
    Etape (T 'docker.etape')
    if (Verifier-GroupeDocker $installation $langue) { Ok (T 'docker.ok') }
}

if (-not $SansRaccourci) {
    Etape (T 'installeur.etape_raccourci')
    $raccourci = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Agent Local.lnk'
    $coquille = New-Object -ComObject WScript.Shell
    $lien = $coquille.CreateShortcut($raccourci)
    $lien.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $lien.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File `"$(Join-Path $installation 'lancer_agent_local.ps1')`""
    $lien.WorkingDirectory = $installation
    $lien.IconLocation = Join-Path $installation 'noyau\icone.ico'
    $lien.Save()
    Ok (T 'installeur.raccourci_ok')
}

Write-Host ''
Write-Host ('  ' + (T 'installeur.termine')) -ForegroundColor Green
if (-not $SansLancement) { Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File `"$(Join-Path $installation 'lancer_agent_local.ps1')`"" }
