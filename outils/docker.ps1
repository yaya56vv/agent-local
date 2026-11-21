# Docker Desktop pour Agent Local (utilise par installer.ps1, lancer_agent_local.ps1 et l'assistant, noyau/assistant.py).
# - Docker Desktop refuse de demarrer pour un compte qui n'est pas dans le groupe Windows « docker-users », et l'ajout ne
#   compte qu'apres une nouvelle ouverture de session. On le verifie AVANT de lancer Docker : on n'ouvre jamais Docker dans
#   un etat ou il planterait (et proposerait « Reset to factory defaults », qui efface ses donnees).
# - Rien ici ne modifie les reglages de Docker. Seuls les conteneurs d'Agent Local (noms agent-local-*) sont crees.
# Necessite outils\langue.ps1 (fonction T) deja charge.

$DOCKER_DESKTOP = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
# chemin complet : juste apres l'installation, le PATH de cette session ne connait pas encore docker.exe
$DOCKER_CLI = Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'
if (-not (Test-Path $DOCKER_CLI)) { $DOCKER_CLI = 'docker' }

# Conteneurs par module : image officielle epinglee par empreinte (version figee, publiee depuis plus de deux semaines),
# port ouvert sur 127.0.0.1 seulement (jamais sur le reseau). {DONNEES} = dossier donnees d'Agent Local.
# La messagerie n'a pas de conteneur dans cette version.
$CONTENEURS = [ordered]@{
    recherche = @{ nom = 'agent-local-searxng'
                   options = @('-p', '127.0.0.1:8080:8080', '-v', '{DONNEES}\searxng:/etc/searxng')
                   image = 'searxng/searxng@sha256:c750ee1d859b26d3aeae51c07f6a48c3a0bfbaa9195d71a18b258862d88c4c3c' }
    # n8n 2.46.6 (04/11/2026). Donnees (compte, workflows, cles) dans le volume Docker persistant agent-local-n8n.
    n8n = @{ nom = 'agent-local-n8n'
             options = @('-p', '127.0.0.1:5678:5678', '-v', 'agent-local-n8n:/home/node/.n8n',
                         '-e', 'N8N_DIAGNOSTICS_ENABLED=false', '-e', 'N8N_PERSONALIZATION_ENABLED=false',
                         '-e', 'N8N_VERSION_NOTIFICATIONS_ENABLED=false')
             image = 'n8nio/n8n@sha256:8602f5dfacbe2c931eeafd010de0e68182310e9f309921e780ab69182e92b3ae' }
}
$MODULES_DOCKER = @('recherche', 'messagerie', 'n8n')   # modules qui ont besoin de Docker

function Docker-Installe { Test-Path $DOCKER_DESKTOP }

function Docker-Repond {
    # docker.exe absent : $LASTEXITCODE garderait la valeur d'une commande precedente, d'ou ce controle d'abord
    if (-not (Get-Command $DOCKER_CLI -ErrorAction SilentlyContinue)) { return $false }
    & $DOCKER_CLI info *> $null; return ($LASTEXITCODE -eq 0)
}

function Etat-GroupeDocker {
    # 'actif' : membre, et la session actuelle le sait ; 'a_reconnecter' : membre, mais il faut rouvrir la session Windows ;
    # 'non_membre' : pas dans le groupe ; 'sans_groupe' : le groupe n'existe pas (Docker Desktop pas encore installe).
    try { $groupe = Get-LocalGroup -Name 'docker-users' -ErrorAction Stop } catch { return 'sans_groupe' }
    $moi = [Security.Principal.WindowsIdentity]::GetCurrent()
    if (@($moi.Groups | ForEach-Object { $_.Value }) -contains $groupe.SID.Value) { return 'actif' }
    $membres = @()
    try { $membres = @(Get-LocalGroupMember -Group 'docker-users' -ErrorAction Stop | ForEach-Object { $_.SID.Value }) }
    catch {   # Get-LocalGroupMember echoue si le groupe contient un compte supprime : on lit la liste par « net localgroup »
        $noms = net localgroup docker-users 2>$null
        if ($noms -match "^\s*($([regex]::Escape($moi.Name))|$([regex]::Escape($env:USERNAME)))\s*$") { return 'a_reconnecter' } }
    if ($membres -contains $moi.User.Value) { return 'a_reconnecter' }
    return 'non_membre'
}

function Etat-Docker {
    # absent | sans_droits | a_reconnecter | arrete | pret
    if (-not (Docker-Installe)) { return 'absent' }
    switch (Etat-GroupeDocker) { 'non_membre' { return 'sans_droits' } 'a_reconnecter' { return 'a_reconnecter' } }
    if (Docker-Repond) { return 'pret' }
    return 'arrete'
}

function Verifier-GroupeDocker([string]$installation, [string]$langue) {
    # Lanceur et installateur : renvoie $true si Docker peut etre lance maintenant. Sinon explique, propose l'ajout au
    # groupe (fenetre Windows, visible meme si le lanceur est reduit), et renvoie $false.
    switch (Etat-GroupeDocker) {
        'actif' { return $true }
        'sans_groupe' { return $true }
        'a_reconnecter' { Write-Host "  $(T 'docker.reconnecter')" -ForegroundColor Yellow; return $false }
        'non_membre' {
            Write-Host "  $(T 'docker.pas_membre')" -ForegroundColor Yellow
            Add-Type -AssemblyName System.Windows.Forms
            $reponse = [System.Windows.Forms.MessageBox]::Show("$(T 'docker.pas_membre')`n`n$(T 'docker.proposer_ajout')", 'Agent Local - Docker',
                [System.Windows.Forms.MessageBoxButtons]::YesNo, [System.Windows.Forms.MessageBoxIcon]::Warning)
            if ($reponse -eq [System.Windows.Forms.DialogResult]::Yes) {
                $script = Join-Path $installation 'outils-admin\ajouter_docker_users.ps1'
                $compte = [Security.Principal.WindowsIdentity]::GetCurrent().Name
                try {
                    Start-Process powershell -Verb RunAs -Wait -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -Utilisateur `"$compte`" -Langue $langue"
                    if ((Etat-GroupeDocker) -ne 'non_membre') { Write-Host "  $(T 'docker.reconnecter')" -ForegroundColor Yellow }
                } catch { Write-Host "  $(T 'docker.ajout_refuse')" -ForegroundColor Yellow }
            } else { Write-Host "  $(T 'docker.sans_docker')" -ForegroundColor Yellow }
            return $false
        }
    }
}

function Demarrer-Docker {
    # Lance Docker Desktop seulement si le compte en a le droit, et attend jusqu'a 2 minutes qu'il reponde.
    # Renvoie $true si Docker repond. N'affiche rien : l'appelant explique.
    if (Docker-Repond) { return $true }
    if (-not (Docker-Installe) -or (Etat-GroupeDocker) -notin 'actif', 'sans_groupe') { return $false }
    Start-Process -FilePath $DOCKER_DESKTOP
    for ($i = 0; $i -lt 40; $i++) { Start-Sleep 3; if (Docker-Repond) { return $true } }
    return $false
}

function Port-Occupe([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { return $client.ConnectAsync('127.0.0.1', $port).Wait(500) } catch { return $false } finally { $client.Dispose() }
}

function Demarrer-Conteneurs([string]$donnees, [string[]]$modules) {
    # Cree, ou relance s'il est arrete, le conteneur de chaque module choisi. Ecrit une ligne « module=ok|echec|occupe » par module.
    foreach ($m in $modules) {
        $c = $CONTENEURS[$m]; if (-not $c) { continue }
        $existe = & $DOCKER_CLI ps -a --filter "name=^$($c.nom)$" --format '{{.Names}}'
        if ($existe) {
            $enMarche = & $DOCKER_CLI ps --filter "name=^$($c.nom)$" --format '{{.Names}}'
            if (-not $enMarche) { & $DOCKER_CLI start $c.nom *> $null } else { $global:LASTEXITCODE = 0 }
        } elseif (Port-Occupe ($c.options[1] -split ':')[1]) {
            # le port est deja pris (par exemple un n8n que vous avez installe vous-meme) : on l'utilise tel quel
            "$m=occupe"; continue
        } else {
            $options = @($c.options | ForEach-Object { $_.Replace('{DONNEES}', $donnees) })
            & $DOCKER_CLI run -d --name $c.nom --restart unless-stopped @options $c.image *> $null
        }
        "$m=$(if ($LASTEXITCODE -eq 0) { 'ok' } else { 'echec' })"
    }
}
