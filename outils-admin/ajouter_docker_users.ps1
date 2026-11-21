# Agent Local - ajoute un compte Windows au groupe « docker-users » (necessaire pour utiliser Docker Desktop).
# Lance par le lanceur, l'installateur ou l'assistant, apres accord de l'utilisateur, avec la confirmation de Windows (UAC).
# Ne fait rien d'autre : ni Docker, ni ses reglages ne sont touches. L'ajout compte apres une nouvelle ouverture de session.
param([string]$Utilisateur = '', [string]$Langue = '')
. (Join-Path $PSScriptRoot 'commun.ps1')
Verifier-Admin
trap { Arret (T 'admin.commun.erreur_inattendue' @{ v1 = $_.Exception.Message }) }
$compte = Compte-Utilisateur $Utilisateur
try { $groupe = Get-LocalGroup -Name 'docker-users' -ErrorAction Stop } catch { Arret (T 'docker.groupe_absent') }
$deja = $false
try { $deja = @(Get-LocalGroupMember -Group 'docker-users' -ErrorAction Stop | ForEach-Object { $_.SID.Value }) -contains $compte.Sid } catch { }
if ($deja) { Ok (T 'docker.deja_membre' @{ v1 = $compte.Nom }) }
else { Add-LocalGroupMember -SID $groupe.SID -Member $compte.Sid; Ok (T 'docker.ajoute' @{ v1 = $compte.Nom }) }
Write-Host ''
Write-Host "  $(T 'docker.reconnecter')" -ForegroundColor Yellow
Read-Host (T 'admin.commun.entree_fermer')
