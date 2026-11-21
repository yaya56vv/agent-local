# Installation

**🇫🇷 Version française : [installation.fr.md](installation.fr.md)**

## 1. Before You Begin

- Windows 10 22H2 or Windows 11, 64-bit, with **winget** (the « App Installer » from the Microsoft Store, present by default on Windows 11).
- A **NVIDIA graphics card** with at least 8 GB (24 GB for full use) and a **NVIDIA driver 551.61 or more recent**. The assistant checks the driver before downloading the engine, and if it is too old, it provides the link to the NVIDIA website.
- An Internet connection during installation. Afterward, Local Agent works offline, except for modules that require it (Microsoft voice, web search, browser).

## 2. Install

1. Download the repository (**Code → Download ZIP**) and extract it into a simple folder, for example `C:\AgentLocal`. Avoid synced folders (OneDrive): models weigh several gigabytes.
2. In the unzipped folder, **double-click `Installer Agent Local`** (it runs `installer.ps1`).
   - If Windows blocks the script: open PowerShell in the folder and type `powershell -NoProfile -ExecutionPolicy Bypass -File installer.ps1`.
3. The installer:
   - installs **Python 3.13** and **Node.js LTS** with winget if missing (official sources);
   - creates the Python environment `noyau\.venv` and installs the dependencies at fixed versions (`requirements.txt`);
   - creates `noyau\config.json` from the example, never overwriting an existing configuration;
   - creates the **Local Agent** shortcut on the Desktop, then opens Local Agent.
   It does not ask for administrator rights.

## 3. First-Time Setup Wizard

| Screen | What You Choose |
|---|---|
| 1. You | language (detected from Windows), first name, output folder |
| 2. Model | all your NVIDIA cards are detected; recommended level and model are shown; download from Hugging Face (verified by SHA-256) or your own GGUF file; installs the official llama.cpp engine (b12193, CUDA 12.4, verified by SHA-256) |
| 3. Autonomy | Cautious, Balanced or Autonomous |
| 4. Modules | voice, dictation, web search, browser, Windows control, Wikipedia, advanced modules; for each external component: clear license, checkbox « I accept », « Install » button |
| 5. Admin Tools | PC health and repair kit, with Windows confirmation |

At the end, Local Agent restarts with your model. Everything remains editable in **⚙ Settings**.

## 4. Dictation on a single card

Measured on an RTX 3090 alone: Qwen3.8-27B (65,536 tokens) uses 19.3 GB and Whisper large-v3 adds 2.2 GB, i.e. 21.5 GB out of 24: the most accurate dictation fits on the same card. On a smaller card, the wizard automatically picks a smaller Whisper (small, +0.6 GB) or the CPU, and explains it in one sentence. With two cards, dictation goes on the second one.

## 5. Update, Reinstall

- **Settings → Advanced → Check for Updates**: displays the latest news published on GitHub; nothing is installed without your consent. Your settings, keys, conversations, models, and modules are preserved.
- **Settings → Advanced → Uninstall**: displays a summary, then removes scheduled tasks, folders created in `C:\ProgramData` and `C:\Program Files`, and the shortcut. Models and the secrets folder are only deleted if you check the box.

## 6. In Case of Problem

- **Model fails to start**: the startup window shows the last lines of its log (`noyau\donnees\llama-server.log`). Most often, the card memory is insufficient: lower the conversation memory in Settings → Model.
- **Another program uses port 8090**: Local Agent never stops it. Change the port in Settings → Model → Expert Options.
- **Logs**: `noyau\donnees\app_erreurs.log` (window), `noyau\donnees\llama-server.log` (model), `modules\dictee\dictee.log` (dictation).