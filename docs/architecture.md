# Architecture

**🇫🇷 Version française : [architecture.fr.md](architecture.fr.md)**

## Principle

One agent (the **chef**) runs in a loop: remember → reflect → act → observe. It acts only through **tools**, almost all provided by standard **MCP servers** (Model Context Protocol). Adding a capability means plugging an MCP server, not writing a separate path. The safety nets are in the loop code (`noyau/agent.py`), between the model and the tools.

```
Window (frontend/, pywebview)
  → noyau/app.py (bridge between window and kernel; setup wizard and Settings via noyau/assistant.py)
    → noyau/agent.py: the mission (notebook, skills, plan, safety nets)
      → noyau/llm.py: local model (llama-server, 127.0.0.1)
      → noyau/pupitre_mcp.py: MCP servers (stdio) and ranking of their tools (auto / ask / forbidden)
    → events → window (stream, Mission panel, artifacts, voice)
```

## Main Files

| File | Role |
|---|---|
| `noyau/reglages.py` | only entry point for configuration: path markers, enabled modules, autonomy levels, secrets folder |
| `noyau/langue.py`, `langues/*.json` | all texts; adding a language = adding a file |
| `noyau/agent.py` | mission loop, internal tools (plan, artifacts, vision, notepad), safety nets 1 to 11 |
| `noyau/llm.py` | model client: continuous stream, bounded reflection, tool calls |
| `noyau/pupitre_mcp.py` | connects MCP servers and ranks their tools |
| `noyau/mcp_*.py` | Agent Local MCP servers (memory, terminal, PDF, office, health, repair…) |
| `noyau/filet.py` | safety net (backup before modification, forbidden zone detection) |
| `noyau/garde_navigateur.py` | browser safety net |
| `noyau/assistant.py` | setup wizard and Settings: detection, verified downloads, components, admin tools, updates |
| `lancer_agent_local.ps1` | startup: model (doesn't stop the server it started), dictation, Docker and SearXNG, window |
| `installer.ps1` | minimal installation |
| `outils-admin/` | optional admin scripts (health, repair, uninstall) |
| `modules/dictee`, `modules/voix-xtts` | optional modules, each in its own Python environment |

## Configuration

`noyau/config.json` is written by the assistant and the Settings page (model: `noyau/config.example.json`, ignored by git). Markers: `{INSTALLATION}`, `{NOYAU}`, `{DONNEES}`, `{PYTHON}`, `{SECRETS}`, `{SORTIE}` and Windows variables (`%USERPROFILE%`). An MCP server with `"module": "x"` is only connected if `modules.x` is `true`.

## Data

Everything is stored in `noyau/donnees/` (ignored by git, forbidden to the agent): `memoire.db` (notebook, conversations, tasks, artifacts), `journal.jsonl`, `copies/` (safety net), browser profile, SearXNG settings. User skills are in `noyau/competences/`, created at first launch from `noyau/competences-exemples/<langue>/`.

## Technical Choices

- **Local model served by official llama.cpp** (b12193, CUDA 12.4): no option specific to a fork. Qwen conversation template is applied by the server; cache delimiters (`message_delimiters`) are only sent if `llm.reperes_messages` is enabled (TurboQuant fork).
- **Conversation memory ≥ 65 536 tokens**: tool descriptions alone occupy 15 000 to 27 000 tokens.
- **Bounded reflection**: 2 500 tokens at start of a request, 400 between tools, to keep the agent fast.
- **Review before rendering**: a mission with a plan of 3 steps or more is reviewed once, numbers compared to raw tool results.