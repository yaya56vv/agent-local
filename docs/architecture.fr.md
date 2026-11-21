# Architecture

**English: [architecture.md](architecture.md)**

## Principe

Un seul agent (le **chef**) tourne en boucle : se souvenir → réfléchir → agir → observer. Il agit uniquement par des **outils**, presque tous fournis par des **serveurs MCP** standard (Model Context Protocol). Ajouter une capacité, c'est brancher un serveur MCP, pas écrire une voie à part. Les garde-fous sont dans le code de la boucle (`noyau/agent.py`), entre le modèle et les outils.

```
Fenêtre (frontend/, pywebview)
  → noyau/app.py (pont entre la fenêtre et le noyau ; assistant et Réglages via noyau/assistant.py)
    → noyau/agent.py : la mission (carnet, compétences, plan, garde-fous)
      → noyau/llm.py : modèle local (llama-server, 127.0.0.1)
      → noyau/pupitre_mcp.py : serveurs MCP (stdio) et classement de leurs outils (auto / demander / interdit)
    → événements → fenêtre (flux, panneau Mission, artefacts, voix)
```

## Fichiers principaux

| Fichier | Rôle |
|---|---|
| `noyau/reglages.py` | seule porte d'entrée de la configuration : marqueurs de chemins, modules activés, niveaux d'autonomie, dossier de secrets |
| `noyau/langue.py`, `langues/*.json` | tous les textes ; ajouter une langue = ajouter un fichier |
| `noyau/agent.py` | boucle de mission, outils internes (plan, artefacts, vision, bloc-notes), garde-fous 1 à 11 |
| `noyau/llm.py` | client du modèle : flux continu, réflexion bornée, appels d'outils |
| `noyau/pupitre_mcp.py` | branche les serveurs MCP et classe leurs outils |
| `noyau/mcp_*.py` | serveurs MCP d'Agent Local (mémoire, terminal, PDF, bureautique, santé, réparation…) |
| `noyau/filet.py` | filet de sécurité (copie avant modification, annulation) et repérage de la zone interdite |
| `noyau/garde_navigateur.py` | garde-fou du navigateur |
| `noyau/assistant.py` | assistant de premier lancement et Réglages : détection, téléchargements vérifiés, composants, outils admin, mises à jour |
| `lancer_agent_local.ps1` | démarrage : modèle (n'arrête que le serveur qu'il a lancé), dictée, Docker et SearXNG, fenêtre |
| `installer.ps1` | installation minimale |
| `outils-admin/` | scripts administrateur facultatifs (santé, réparation, désinstallation) |
| `modules/dictee`, `modules/voix-xtts` | modules facultatifs, chacun dans son propre environnement Python |

## Configuration

`noyau/config.json` est écrit par l'assistant et la page Réglages (modèle : `noyau/config.example.json`, ignoré par git). Marqueurs : `{INSTALLATION}`, `{NOYAU}`, `{DONNEES}`, `{PYTHON}`, `{SECRETS}`, `{SORTIE}` et les variables Windows (`%USERPROFILE%`). Un serveur MCP qui porte `"module": "x"` n'est branché que si `modules.x` vaut `true`.

## Données

Tout est enregistré dans `noyau/donnees/` (ignoré par git, interdit à l'agent) : `memoire.db` (carnet, conversations, tâches, artefacts), `journal.jsonl`, `copies/` (filet de sécurité), profil du navigateur, réglages de SearXNG. Les compétences de l'utilisateur sont dans `noyau/competences/`, créées au premier lancement à partir de `noyau/competences-exemples/<langue>/`.

## Choix techniques

- **Modèle local servi par llama.cpp officiel** (b12193, CUDA 12.4) : aucune option propre à un fork. Le gabarit de conversation de Qwen est appliqué par le serveur ; les repères de cache (`message_delimiters`) ne sont envoyés que si `llm.reperes_messages` est activé (fork TurboQuant).
- **Mémoire de conversation ≥ 65 536 jetons** : la description des outils occupe à elle seule 15 000 à 27 000 jetons.
- **Réflexion bornée** : 2 500 jetons au début d'une demande, 400 entre deux outils, pour garder l'agent rapide.
- **Relecture avant de rendre** : une mission avec un plan de 3 étapes ou plus est relue une fois, chiffres comparés aux résultats bruts des outils.
