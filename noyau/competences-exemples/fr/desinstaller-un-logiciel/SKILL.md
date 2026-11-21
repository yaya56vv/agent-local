---
name: desinstaller-un-logiciel
description: "Désinstaller proprement un logiciel via winget, vérifier l'état réel après une erreur, puis repérer et nettoyer les résidus (dossiers de données, composants de mise à jour orphelins, processus) avec l'accord de l'utilisateur."
---

## Quand l'utiliser
L'utilisateur demande de désinstaller un logiciel.

## Etapes
1. Chercher le logiciel avec logiciels__chercher_logiciel pour trouver son identifiant winget exact.
2. Lire la fiche (logiciels__fiche_logiciel) pour vérifier que c'est bien le logiciel officiel de l'éditeur attendu.
3. Désinstaller avec logiciels__desinstaller_logiciel.
4. Si la désinstallation renvoie une erreur, ne pas conclure à l'échec : vérifier l'état réel avec logiciels__logiciels_installes (filtre sur le nom) et une lecture du registre Uninstall (HKLM, HKLM WOW6432Node, HKCU).
5. Chercher les résidus : processus restants (Get-Process -Name 'nom*'), dossier du programme dans Program Files et Program Files (x86), dossier de données dans AppData Local et AppData Roaming.
6. Rendre compte et demander l'accord de l'utilisateur avant de nettoyer : programme désinstallé ou non, liste des résidus (taille, emplacement).
7. Nettoyer d'abord le dossier de données AppData (à la Corbeille avec terminal__mettre_a_la_corbeille), puis le dossier du programme. Si un dossier ne se vide pas, un processus résiduel le verrouille souvent : revérifier après le nettoyage des données plutôt que de forcer l'arrêt de processus protégés.
8. Vérification finale : Test-Path sur chaque dossier, Get-Process sur les processus, relecture du registre Uninstall.

## Pieges a eviter
- winget peut renvoyer un code d'échec alors que la désinstallation a réussi : toujours vérifier l'état réel.
- Le programme peut disparaître du registre en laissant des données dans AppData : c'est le nettoyage des résidus qui reste à proposer.
- Les navigateurs Chromium laissent souvent un composant de mise à jour séparé dans Program Files, absent de winget et du registre : c'est un résidu orphelin.
- Des processus résiduels peuvent refuser Stop-Process (accès refusé) : ne pas insister, nettoyer les données puis revérifier.
- Mesurer un très gros dossier peut dépasser le délai du terminal : donner un ordre de grandeur.
- Ne jamais supprimer avec Remove-Item : toujours terminal__mettre_a_la_corbeille, avec l'accord de l'utilisateur (récupérable).
