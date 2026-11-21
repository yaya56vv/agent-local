# Agent Local - desinstallation propre (Reglages > Avance > Desinstaller, ou a la main en administrateur).
# Retire : les taches planifiees d'Agent Local, les dossiers C:\ProgramData\AgentLocal* et C:\Program Files\AgentLocalOutils,
# la regle de pare-feu, le raccourci Bureau ; au choix, les modeles telecharges (-SupprimerModeles) et le dossier de
# secrets (-SupprimerSecrets). Affiche un recapitulatif et demande de taper OUI avant de supprimer quoi que ce soit.
# Le dossier d'installation lui-meme (code, conversations, carnet) reste : supprimez-le a la main ensuite si vous le voulez.
# Les logiciels installes avec winget (Autoruns, LibreHardwareMonitor, CrystalDiskInfo, Docker Desktop) restent installes :
# retirez-les depuis les Parametres de Windows si vous le voulez.
param([string]$Utilisateur = '', [string]$Installation = '', [switch]$SupprimerModeles, [switch]$SupprimerSecrets, [string]$Langue = '')
. (Join-Path $PSScriptRoot 'commun.ps1')
Verifier-Admin
trap { Arret (T 'admin.desinstaller.erreur_inattendue_v1' @{ v1 = ($_.Exception.Message) }) }
$compte = Compte-Utilisateur $Utilisateur
if (-not $Installation) { $Installation = Split-Path $PSScriptRoot }

$taches = @('ReparationAgent', 'AutorunsAgent', 'DisquesAgent', 'LibreHardwareMonitor' | ForEach-Object {
    Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue | Where-Object { $_.Description -like 'Agent Local*' } })
$dossiers = @($OUTILS, $SANTE, $DISQUES, $REPARATION | Where-Object { Test-Path $_ })
$raccourci = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Agent Local.lnk'
$raccourciUtilisateur = Join-Path $compte.Profil 'Desktop\Agent Local.lnk'
$raccourcis = @($raccourci, $raccourciUtilisateur | Sort-Object -Unique | Where-Object { Test-Path $_ })
$modeles = @(foreach ($d in (Join-Path $Installation 'modeles'), (Join-Path $Installation 'moteur'), (Join-Path $Installation 'modules\dictee\.venv'),
                            (Join-Path $Installation 'modules\voix-xtts\.venv')) { if ($SupprimerModeles -and (Test-Path $d)) { $d } })
$secrets = Join-Path $compte.Profil 'AppData\Roaming\AgentLocal\secrets'
$secrets = @(if ($SupprimerSecrets -and (Test-Path $secrets)) { $secrets })

Etape (T 'admin.desinstaller.recapitulatif_voici_ce_qui_va')
foreach ($t in $taches) { Info (T 'admin.desinstaller.tache_planifiee_v1' @{ v1 = ($t.TaskName) }) }
foreach ($d in $dossiers + $modeles + $secrets) { Info (T 'admin.desinstaller.dossier_v1' @{ v1 = $d }) }
foreach ($r in $raccourcis) { Info (T 'admin.desinstaller.raccourci_v1' @{ v1 = $r }) }
Info (T 'admin.desinstaller.regle_de_pare_feu_agent')
if (-not ($taches + $dossiers + $raccourcis + $modeles + $secrets)) { Info (T 'admin.desinstaller.rien_a_supprimer') }
Write-Host ''
if ((Read-Host (T 'admin.desinstaller.taper_oui' @{ mot = (T 'admin.desinstaller.mot_oui') })) -cne (T 'admin.desinstaller.mot_oui')) {
    Write-Host (T 'admin.desinstaller.annule'); Read-Host (T 'admin.commun.entree_fermer'); exit }

Etape (T 'admin.desinstaller.suppression')
foreach ($t in $taches) { Unregister-ScheduledTask -TaskName $t.TaskName -Confirm:$false; Ok (T 'admin.desinstaller.tache_v1_retiree' @{ v1 = ($t.TaskName) }) }
Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$OUTILS*" } | Stop-Process -Force
Get-NetFirewallRule -DisplayName 'Agent Local - LibreHardwareMonitor' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
foreach ($d in $dossiers + $modeles + $secrets) { Remove-Item $d -Recurse -Force; Ok (T 'admin.desinstaller.dossier_v1_supprime' @{ v1 = $d }) }
foreach ($r in $raccourcis) { Remove-Item $r -Force; Ok (T 'admin.desinstaller.raccourci_v1_supprime' @{ v1 = $r }) }
Write-Host ''
Write-Host (T 'admin.commun.termine') -ForegroundColor Green
Read-Host (T 'admin.commun.entree_fermer')
