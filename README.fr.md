# Agent Local

**🇬🇧 English version: [README.md](README.md)**

Un agent d'intelligence artificielle **qui tourne entièrement sur votre PC Windows**. Il lit et range vos fichiers, crée des PDF, des documents Word et Excel, pilote un navigateur, cherche sur le web, surveille la santé du PC, et vous parle à voix haute. Vous pouvez aussi lui dicter vos demandes. Le modèle d'IA tourne sur votre carte graphique : vos fichiers et vos conversations ne partent pas sur Internet.

Il **demande votre accord** avant toute action qui modifie quelque chose ou envoie des données, selon le niveau d'autonomie que vous choisissez. L'interface, l'agent, la voix et la dictée fonctionnent **en français et en anglais**.

---

## Votre PC peut-il faire tourner Agent Local ?

Agent Local a besoin d'une **carte graphique NVIDIA**. Plus elle a de mémoire, plus le modèle peut être capable. L'assistant d'installation détecte votre carte, vous indique votre palier et vous propose le bon modèle **avant tout téléchargement**.

| Votre carte (mémoire vidéo) | Modèle conseillé (+ vision) | Fichiers | Mémoire de conversation | Ce qu'il fait bien | Ce qu'il fait mal | Verdict |
|---|---|---|---|---|---|---|
| **24 Go et plus** | Qwen3.8-27B · UD-Q4_K_M | 16,6 + 0,9 Go *(mesuré)* | 65 536 jetons *(mesuré : 19,3 Go occupés ; 131 072 tient en 21,8 Go)* | missions longues en plusieurs étapes, outils nombreux, vision, français et anglais soignés | réponses plus lentes qu'un petit modèle | **complet** |
| **16 Go** | Qwen3.5-9B · Q6_K | 7,5 + 0,9 Go *(mesuré)* | 65 536 jetons *(estimé)* | tâches courantes, fichiers, recherche, vision, rapide | se trompe plus souvent sur les longues missions et les formulaires compliqués | **utilisable** |
| **12 Go** | Qwen3.5-9B · Q4_K_M | 5,7 + 0,9 Go *(mesuré)* | 65 536 jetons *(estimé)* | questions, fichiers, recherches simples | missions en plusieurs étapes peu fiables | **limité** |
| **8 Go** | Qwen3.5-4B · Q4_K_M | 2,7 + 0,7 Go *(mesuré)* | 65 536 jetons *(estimé)* | petites questions, lecture de fichiers | choisit souvent mal ses outils | **déconseillé** |
| **Sans carte NVIDIA** | — | — | — | — | — | **non pris en charge pour l'instant** (prévu plus tard) |

*« Mesuré » : taille des fichiers sur Hugging Face, et palier 24 Go sur une vraie RTX 3090 (ci-dessous). « Estimé » : pas encore mesuré ; l'assistant ajuste la mémoire de conversation.*

**Mesuré le 21/11/2026** — RTX 3090 (24 Go) seule, llama.cpp officiel b12193 (CUDA 12.4), Qwen3.8-27B UD-Q4_K_M + vision, 65 536 jetons, cache q8_0 : chargé en 15 s ; 19,3 Go de mémoire vidéo occupés ; **41,5 jetons/s** pour une réponse courte, 38,9 jetons/s avec 9 000 jetons de contexte ; lecture du contexte à 1 400 jetons/s. Dictée Whisper large-v3 sur la **même** carte : +2,2 Go (21,5 Go au total), une phrase transcrite en 1,8 s. Avec 131 072 jetons : 21,8 Go, même vitesse.
Pourquoi au moins 65 536 jetons de mémoire ? À chaque étape, l'agent relit la description de tous ses outils (environ 15 000 à 27 000 jetons selon les modules activés).

### Configuration

| | Minimum | Recommandé |
|---|---|---|
| Système | Windows 10 22H2 ou Windows 11, 64 bits | Windows 11 |
| Carte graphique | NVIDIA 8 Go (12 Go pour un usage réel) | NVIDIA 24 Go |
| Pilote NVIDIA | 551.61 ou plus récent (CUDA 12.4) | dernier pilote |
| Mémoire vive | 16 Go *(estimé)* | 32 Go |
| Disque | ≈ 6 Go libres pour le palier 8 Go *(estimé)* | ≈ 19 Go pour le palier 24 Go *(mesuré : modèle 17,5 + moteur 1,2 + Python 0,1)*, plus avec les modules, sur un SSD |
| Internet | pour l'installation seulement | — |

### Modules facultatifs

| Module | Espace disque en plus | Carte graphique | Internet |
|---|---|---|---|
| Dictée (Whisper large-v3) | ≈ 4,5 Go *(estimé)* | NVIDIA : +2,2 Go de mémoire vidéo, tient à côté du 27B sur une seule carte de 24 Go *(mesuré)* ; sinon processeur, plus lent | installation seulement |
| Voix (Microsoft edge-tts) | — | non | **oui, à chaque phrase lue** |
| Voix de secours hors ligne (XTTS-v2, non commercial) | ≈ 6 Go *(estimé)* | NVIDIA conseillée | installation seulement |
| Wikipédia hors ligne (Kiwix, dans votre langue) | ≈ 12 Go en français, ≈ 49 Go en anglais *(mesuré)* | non | installation seulement |
| Recherche web (SearXNG dans Docker Desktop) | ≈ 4 Go *(estimé)* | non | oui |
| Navigateur (profil isolé) | ≈ 0,5 Go *(estimé)* | non | oui |
| Santé du PC (Autoruns, LibreHardwareMonitor, CrystalDiskInfo) | ≈ 0,1 Go | non | installation seulement |

---

## Installation

1. Téléchargez ce dépôt (bouton **Code → Download ZIP**) et décompressez-le (clic droit → **Extraire tout**), par exemple dans `C:\AgentLocal`. Ne lancez rien depuis l'intérieur du zip.
2. Dans le dossier décompressé, **double-cliquez sur `Installer Agent Local`**.
   Il installe le strict minimum : Python 3.13 et Node.js (s'ils manquent, avec winget), puis les dépendances d'Agent Local. Il crée un raccourci sur le Bureau et ouvre Agent Local.
3. **L'assistant de premier lancement** vous guide en 5 écrans :
   1. **langue**, prénom et dossier où ranger ce que l'agent crée ;
   2. **modèle** : détection de votre carte, modèle conseillé téléchargé depuis Hugging Face (vérifié par empreinte), ou votre propre fichier GGUF ; moteur llama.cpp officiel ;
   3. **niveau d'autonomie** : Prudent (par défaut), Équilibré ou Autonome ;
   4. **modules** à cocher, avec un bouton « Tester » pour la voix et la dictée, la licence de chaque composant et une case « J'accepte » ;
   5. **outils administrateur** facultatifs (santé du PC, trousse de réparation), installés avec la confirmation de Windows.

Vous ne modifiez aucun fichier à la main : tout se règle ensuite dans **⚙ Réglages**.
Détails : [docs/installation.fr.md](docs/installation.fr.md).

---

## Ce que l'agent peut faire, et ce qu'il demande avant

| Niveau | En une phrase |
|---|---|
| **Prudent** (par défaut) | Il lit librement ; il vous demande avant de modifier un fichier, de cliquer pour vous ou d'envoyer quoi que ce soit. |
| **Équilibré** | Il écrit seul dans son dossier de sortie et pilote le navigateur ; il demande pour tout le reste. |
| **Autonome** | Il agit seul dans vos dossiers personnels et vos logiciels ; il demande toujours votre accord pour supprimer, agir en administrateur, envoyer un formulaire, un message ou un e-mail, et pour tout achat ou paiement. |

Toujours actifs, quel que soit le niveau : le dossier d'installation est interdit à l'agent ; une suppression va uniquement à la Corbeille, avec votre accord ; les actions administrateur sont confirmées par Windows ; toutes les actions sont journalisées ; une copie de sécurité est faite avant chaque modification.
Détails : [docs/garde-fous.fr.md](docs/garde-fous.fr.md).

## Avertissements

- **Voix Henri (edge-tts)** : chaque réponse lue est envoyée au service en ligne de Microsoft. edge-tts n'est pas un service officiel ; il peut changer ou s'arrêter. Désactivez la voix si vos conversations sont confidentielles.
- **Voix de secours XTTS-v2** : modèle sous Coqui Public Model License, **usage personnel et non commercial uniquement**.
- **Autonomie** : un modèle d'IA peut se tromper. Gardez le mode Prudent tant que vous ne connaissez pas bien l'agent, et relisez ce qu'il vous demande d'autoriser.
- **Hermès, n8n, conseiller cloud, Telegram, messagerie** : modules avancés, désactivés par défaut. Ils envoient des données à des services tiers ou agissent hors des garde-fous d'Agent Local : lisez [docs/modules.fr.md](docs/modules.fr.md) avant de les activer.

## Licences

Le code d'Agent Local est sous **licence MIT** ([LICENSE](LICENSE)). Les composants externes (modèles, llama.cpp, Docker Desktop, Sysinternals, XTTS, Wikipédia…) ne sont **pas** inclus dans ce dépôt. L'assistant les télécharge depuis leur source officielle, après avoir affiché leur licence : voir [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Documentation

- [Installation](docs/installation.fr.md) · [Modules](docs/modules.fr.md) · [Garde-fous](docs/garde-fous.fr.md) · [Architecture](docs/architecture.fr.md)
- [Signaler une faille de sécurité](SECURITY.md)
