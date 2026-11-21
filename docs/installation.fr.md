# Installation

**English: [installation.md](installation.md)**

## 1. Avant de commencer

- Windows 10 22H2 ou Windows 11, 64 bits, avec **winget** (« App Installer » du Microsoft Store, présent par défaut sur Windows 11).
- Une carte graphique **NVIDIA** d'au moins 8 Go (24 Go pour profiter de tout) et un **pilote NVIDIA 551.61 ou plus récent**. L'assistant vérifie le pilote avant de télécharger le moteur et, s'il est trop ancien, vous donne le lien vers le site de NVIDIA.
- Une connexion Internet pendant l'installation. Ensuite, Agent Local fonctionne sans Internet, sauf les modules qui en ont besoin (voix Microsoft, recherche web, navigateur).

## 2. Installer

1. Téléchargez le dépôt (**Code → Download ZIP**) et décompressez-le dans un dossier simple, par exemple `C:\AgentLocal`. Évitez les dossiers synchronisés (OneDrive) : les modèles pèsent plusieurs gigaoctets.
2. Clic droit sur **`installer.ps1`** → **Exécuter avec PowerShell**.
   - Si Windows bloque le script : ouvrez PowerShell dans le dossier et tapez `powershell -NoProfile -ExecutionPolicy Bypass -File installer.ps1`.
3. L'installateur :
   - installe **Python 3.13** et **Node.js LTS** avec winget s'ils manquent (sources officielles) ;
   - crée l'environnement Python `noyau\.venv` et y installe les dépendances aux versions figées (`requirements.txt`) ;
   - crée `noyau\config.json` à partir de l'exemple, sans jamais écraser une configuration existante ;
   - crée le raccourci **Agent Local** sur le Bureau, puis ouvre Agent Local.
   Il ne demande pas les droits administrateur.

## 3. L'assistant de premier lancement

| Écran | Ce que vous choisissez |
|---|---|
| 1. Vous | langue (détectée d'après Windows), prénom, dossier de sortie |
| 2. Modèle | toutes vos cartes NVIDIA sont détectées ; le palier et le modèle conseillé s'affichent ; téléchargement depuis Hugging Face (vérifié par SHA-256) ou votre propre fichier GGUF ; installation du moteur llama.cpp officiel (b12193, CUDA 12.4, vérifié par SHA-256) |
| 3. Autonomie | Prudent, Équilibré ou Autonome |
| 4. Modules | voix, dictée, recherche web, navigateur, pilotage de Windows, Wikipédia, modules avancés ; pour chaque composant externe : licence en clair, case « J'accepte », bouton « Installer » |
| 5. Outils admin | santé du PC et trousse de réparation, avec la confirmation de Windows |

À la fin, Agent Local redémarre avec votre modèle. Tout reste modifiable dans **⚙ Réglages**.

## 4. Dictée sur une seule carte

Mesuré sur une RTX 3090 seule : le Qwen3.8-27B (65 536 jetons) occupe 19,3 Go et Whisper large-v3 ajoute 2,2 Go, soit 21,5 Go sur 24 : la dictée la plus précise tient sur la même carte. Sur une carte plus petite, l'assistant choisit automatiquement un Whisper plus petit (small, +0,6 Go) ou le processeur, et l'explique en une phrase. Avec deux cartes, la dictée va sur la deuxième.

## 5. Mettre à jour, désinstaller

- **Réglages → Avancé → Vérifier les mises à jour** : affiche les nouveautés publiées sur GitHub ; rien n'est installé sans votre accord. Vos réglages, clés, conversations, modèles et modules sont gardés.
- **Réglages → Avancé → Désinstaller** : affiche un récapitulatif, puis retire les tâches planifiées, les dossiers créés dans `C:\ProgramData` et `C:\Program Files`, et le raccourci. Les modèles et le dossier de secrets ne sont supprimés que si vous le cochez.

## 6. En cas de problème

- **Le modèle ne démarre pas** : la fenêtre de démarrage affiche les dernières lignes de son journal (`noyau\donnees\llama-server.log`). Le plus souvent, la mémoire de la carte ne suffit pas : baissez la mémoire de conversation dans Réglages → Modèle.
- **Un autre programme utilise le port 8090** : Agent Local ne l'arrête jamais. Changez le port dans Réglages → Modèle → Options expertes.
- **Journaux** : `noyau\donnees\app_erreurs.log` (fenêtre), `noyau\donnees\llama-server.log` (modèle), `modules\dictee\dictee.log` (dictée).
