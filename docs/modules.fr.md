# Modules

**English: [modules.md](modules.md)**

Toujours inclus : mémoire (carnet), fichiers, PDF, Word et Excel, terminal PowerShell, programmes, logiciels (winget), matériel, planificateur, artefacts. Les autres modules s'activent dans l'assistant ou dans **Réglages → Modules**. Un composant externe s'installe seulement après l'affichage de sa licence et votre case « J'accepte ».

| Module | Ce qu'il fait | Ce qu'il installe | Données envoyées hors du PC |
|---|---|---|---|
| Vision | l'agent regarde une image ou l'écran | fichier mmproj du modèle (Hugging Face) | aucune |
| Voix | lit les réponses à voix haute ; voix françaises ou anglaises selon la langue | rien (edge-tts est dans le noyau) | **le texte lu, envoyé à Microsoft** |
| Voix de secours | voix hors ligne quand Internet est coupé | coqui-tts, PyTorch, modèle XTTS-v2 (non commercial) | aucune |
| Dictée | Ctrl+Alt pour dicter dans n'importe quelle fenêtre ; transcription des vocaux Telegram | faster-whisper, bibliothèques NVIDIA, modèle Whisper (Hugging Face) | aucune |
| Recherche web | recherche sans compte ni clé, lecture de pages | Docker Desktop (winget), SearXNG (épinglé par empreinte) | vos recherches, aux moteurs interrogés par SearXNG |
| Navigateur | navigation, lecture, formulaires dans un profil séparé | Playwright MCP (npm) | les pages visitées |
| Pilotage de Windows | ouvrir des logiciels, cliquer, taper | Windows-MCP 0.8.5 (PyPI) | aucune |
| Wikipédia hors ligne | toute Wikipédia en français, sans Internet | libzim (GPL-3.0), fichier ZIM Kiwix (≈ 13 Go) | aucune |
| Santé du PC | températures, disques, démarrage, journaux | Autoruns, LibreHardwareMonitor, CrystalDiskInfo (winget), tâches administrateur | aucune |
| Trousse de réparation | 10 gestes de dépannage en administrateur, chacun confirmé dans une fenêtre | une tâche planifiée administrateur (compte standard : confirmation Windows à chaque geste) | aucune |

## Modules avancés (désactivés par défaut)

| Module | Ce qu'il fait | Attention |
|---|---|---|
| Conseiller cloud | demande un second avis à un modèle en ligne (OpenRouter) | payant ; chaque envoi vous est demandé ; mots de passe, numéros de carte et IBAN sont refusés d'office |
| Telegram | missions et accords depuis votre téléphone | vous créez votre propre robot (@BotFather) ; seul le premier compte qui envoie le code affiché est obéi |
| Messagerie | lire et trier vos mails (Gmail, Yahoo) | mot de passe d'application ; seul le déplacement vers « Tri Agent Local » est permis, sur accord |
| Hermès | confie une longue mission à Hermes Agent, installé à part | Hermès agit selon ses propres règles, hors des garde-fous d'Agent Local (sauf la zone interdite, refusée avant le lancement) |
| n8n | lance vos automatisations n8n | licence non libre (usage interne) ; chaque lancement vous est demandé |

Les clés et jetons se saisissent dans **Réglages → Clés et comptes**. Ils sont enregistrés dans `%APPDATA%\AgentLocal\secrets`, jamais dans `config.json`.
