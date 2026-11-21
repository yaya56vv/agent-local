---
name: verifier-espace-disque
description: "Mesurer l'espace libre d'un disque et repérer les fichiers les plus lourds d'un dossier avec le terminal PowerShell, quand l'utilisateur demande combien de place il reste ou ce qui prend le plus de place."
---

## Quand l'utiliser
Quand l'utilisateur demande l'espace libre d'un disque, les fichiers les plus lourds d'un dossier, ou s'il y a assez de place pour une installation ou un téléchargement.

## Etapes
1. Mesurer l'espace libre : Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'", puis afficher FreeSpace et Size convertis en Go.
2. Lister les fichiers les plus lourds du dossier demandé : Get-ChildItem -Path <dossier> -File -Recurse -ErrorAction SilentlyContinue | Sort-Object Length -Descending | Select-Object -First 5, avec la taille en Mo ou en Go.
3. Présenter les résultats en phrases claires (tailles arrondies, noms lisibles).
4. Si l'utilisateur veut libérer de la place, proposer ce qui pourrait être retiré et attendre son accord : on ne supprime jamais sans accord, et on préfère déplacer.

## Pieges a eviter
- Get-Volume peut échouer (« le module Storage n'a pas pu être chargé ») : utiliser alors Get-CimInstance Win32_LogicalDisk.
- Ne jamais donner de tailles brutes en octets : convertir en Mo ou en Go arrondis.
- Ne jamais supprimer ni déplacer de fichier sans l'accord de l'utilisateur ; la lecture seule est sans danger.
- Le dossier d'installation d'Agent Local est interdit, même pour un simple listing.
