# Agent Local

**🇫🇷 Version française : [README.fr.md](README.fr.md)**

An AI agent that **runs entirely on your Windows PC**. It reads and organizes your files, creates PDFs, Word and Excel documents, drives a browser, searches the web, checks your PC's health and talks to you out loud. You can also dictate your requests. The AI model runs on your graphics card: your files and conversations stay on your computer.

It **asks for your approval** before anything that changes something or sends data, according to the autonomy level you choose. The interface, the agent, the voice and the dictation work in **English and French**.

---

## Can your PC run Agent Local?

Agent Local needs an **NVIDIA graphics card**. The more video memory it has, the more capable the model can be. The setup wizard detects your card, shows your tier and offers the right model **before anything is downloaded**.

| Your card (video memory) | Recommended model (+ vision) | Files | Conversation memory | Good at | Weak at | Verdict |
|---|---|---|---|---|---|---|
| **24 GB or more** | Qwen3.8-27B · UD-Q4_K_M | 16.6 + 0.9 GB *(measured)* | 65,536 tokens *(measured: 19.3 GB used; 131,072 fits in 21.8 GB)* | long multi-step missions, many tools, vision, fluent English and French | slower answers than a small model | **complete** |
| **16 GB** | Qwen3.5-9B · Q6_K | 7.5 + 0.9 GB *(measured)* | 65,536 tokens *(estimated)* | everyday tasks, files, search, vision, fast | more mistakes on long missions and complex forms | **usable** |
| **12 GB** | Qwen3.5-9B · Q4_K_M | 5.7 + 0.9 GB *(measured)* | 65,536 tokens *(estimated)* | questions, files, simple searches | multi-step missions are unreliable | **limited** |
| **8 GB** | Qwen3.5-4B · Q4_K_M | 2.7 + 0.7 GB *(measured)* | 65,536 tokens *(estimated)* | short questions, reading files | often picks the wrong tool | **not recommended** |
| **No NVIDIA card** | — | — | — | — | — | **not supported yet** (planned) |

*"Measured": file sizes on Hugging Face, and the 24 GB tier on a real RTX 3090 (below). "Estimated": not measured yet; the wizard adjusts the conversation memory.*

**Measured on 21/11/2026** — RTX 3090 (24 GB) alone, official llama.cpp b12193 (CUDA 12.4), Qwen3.8-27B UD-Q4_K_M + vision, 65,536 tokens, q8_0 cache: loaded in 15 s; 19.3 GB of video memory used; **41.5 tokens/s** for a short answer, 38.9 tokens/s with 9,000 tokens of context; context read at 1,400 tokens/s. Whisper large-v3 dictation on the **same** card: +2.2 GB (21.5 GB in total), a sentence transcribed in 1.8 s. With 131,072 tokens: 21.8 GB, same speed.
Why at least 65,536 tokens? At every step, the agent re-reads the description of all its tools (about 15,000 to 27,000 tokens depending on the enabled modules).

### Requirements

| | Minimum | Recommended |
|---|---|---|
| System | Windows 10 22H2 or Windows 11, 64-bit | Windows 11 |
| Graphics card | NVIDIA 8 GB (12 GB for real use) | NVIDIA 24 GB |
| NVIDIA driver | 551.61 or newer (CUDA 12.4) | latest driver |
| RAM | 16 GB *(estimated)* | 32 GB |
| Disk | ≈ 6 GB free for the 8 GB tier *(estimated)* | ≈ 19 GB for the 24 GB tier *(measured: model 17.5 + engine 1.2 + Python 0.1)*, more with modules, on an SSD |
| Internet | for the installation only | — |

### Optional modules

| Module | Extra disk space | Graphics card | Internet |
|---|---|---|---|
| Dictation (Whisper large-v3) | ≈ 4.5 GB *(estimated)* | NVIDIA: +2.2 GB of video memory, fits next to the 27B on one 24 GB card *(measured)*; otherwise CPU, slower | installation only |
| Voice (Microsoft edge-tts) | — | no | **yes, for every sentence read aloud** |
| Offline backup voice (XTTS-v2, non-commercial) | ≈ 6 GB *(estimated)* | NVIDIA recommended | installation only |
| Offline Wikipedia (Kiwix, in your language) | ≈ 12 GB in French, ≈ 49 GB in English *(measured)* | no | installation only |
| Web search (SearXNG in Docker Desktop) | ≈ 4 GB *(estimated)* | no | yes |
| Browser (isolated profile) | ≈ 0.5 GB *(estimated)* | no | yes |
| PC health (Autoruns, LibreHardwareMonitor, CrystalDiskInfo) | ≈ 0.1 GB | no | installation only |

---

## Installation

1. Download this repository (**Code → Download ZIP**) and unzip it, for example to `C:\AgentLocal`.
2. Right-click **`installer.ps1`** → **Run with PowerShell**.
   It installs only the bare minimum: Python 3.13 and Node.js (with winget, if they are missing), then Agent Local's dependencies. It creates a desktop shortcut and opens Agent Local.
3. The **setup wizard** guides you through 5 screens:
   1. **language**, first name and the folder where the agent saves what it creates;
   2. **model**: detection of your card, recommended model downloaded from Hugging Face (checked by SHA-256), or your own GGUF file; official llama.cpp engine;
   3. **autonomy level**: Cautious (default), Balanced or Autonomous;
   4. **modules** to tick, with a "Test" button for the voice and the dictation, each component's licence and an "I accept" box;
   5. optional **administrator tools** (PC health, repair kit), installed with Windows' confirmation.

You never edit a file by hand: everything can be changed later in **⚙ Settings**.
Details: [docs/installation.md](docs/installation.md).

---

## What the agent may do, and what it asks first

| Level | In one sentence |
|---|---|
| **Cautious** (default) | It reads freely; it asks you before changing a file, clicking for you or sending anything. |
| **Balanced** | It writes on its own in its output folder and drives the browser; it asks for everything else. |
| **Autonomous** | It acts on its own in your personal folders and programs; it always asks for your approval before deleting, acting as administrator, submitting a form, sending a message or an e-mail, and before any purchase or payment. |

Always on, whatever the level: the installation folder is off-limits to the agent; deletion only goes to the Recycle Bin, with your approval; administrator actions are confirmed by Windows; every action is logged; a safety copy is made before every change.
Details: [docs/garde-fous.md](docs/garde-fous.md).

## Warnings

- **Henri voice (edge-tts)**: every answer read aloud is sent to Microsoft's online service. edge-tts is not an official service; it may change or stop working. Turn the voice off if your conversations are confidential.
- **XTTS-v2 backup voice**: model under the Coqui Public Model License, **personal and non-commercial use only**.
- **Autonomy**: an AI model can make mistakes. Keep Cautious mode until you know the agent well, and read what it asks you to approve.
- **Hermes, n8n, cloud advisor, Telegram, mail**: advanced modules, off by default. They send data to third-party services or act outside Agent Local's safeguards: read [docs/modules.md](docs/modules.md) before enabling them.

## Licences

Agent Local's code is under the **MIT licence** ([LICENSE](LICENSE)). External components (models, llama.cpp, Docker Desktop, Sysinternals, XTTS, Wikipedia…) are **not** included in this repository. The wizard downloads them from their official source after showing you their licence: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Documentation

- [Installation](docs/installation.md) · [Modules](docs/modules.md) · [Safeguards](docs/garde-fous.md) · [Architecture](docs/architecture.md)
- [Report a security issue](SECURITY.md)
