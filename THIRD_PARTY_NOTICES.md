# Third-party notices / Avis de licences tiers

Agent Local's own code is MIT-licensed (see [LICENSE](LICENSE)). **None of the components below is included in this repository.**
They are downloaded from their official source by the setup wizard, only after the user has read their licence and ticked
"I accept", or installed by the user. Each keeps its own licence.

*Le code d'Agent Local est sous licence MIT. Aucun des composants ci-dessous n'est inclus dans ce dépôt : l'assistant les
télécharge depuis leur source officielle après acceptation de leur licence par l'utilisateur. Chacun garde sa licence.*

| Component | Used for | Licence | Source | Notes |
|---|---|---|---|---|
| llama.cpp b12193 (ggml-org) | runs the model | MIT | github.com/ggml-org/llama.cpp (release b12193, SHA-256 checked) | official build, CUDA 12.4 |
| NVIDIA CUDA runtime (cudart, cuBLAS, cuDNN) | GPU computing | NVIDIA CUDA EULA | llama.cpp release / PyPI | redistributed by their publishers, never by this repository |
| Qwen3.8-27B, Qwen3.5-9B, Qwen3.5-4B (GGUF, Unsloth) | the AI model | Apache-2.0 | huggingface.co/unsloth | SHA-256 checked |
| faster-whisper + Whisper large-v3 (Systran) | dictation | MIT | PyPI, huggingface.co/Systran | |
| edge-tts | voice | LGPL-3.0 | PyPI | unofficial client of a Microsoft online service: the text read aloud is sent to Microsoft |
| Coqui TTS (coqui-tts) | offline backup voice | MPL-2.0 | PyPI | |
| **XTTS-v2 model** | offline backup voice | **Coqui Public Model License (non-commercial)** | huggingface.co/coqui/XTTS-v2 | personal, non-commercial use only; accepted by the user in the wizard |
| PyTorch | backup voice | BSD-3-Clause | download.pytorch.org | |
| **Sysinternals Autoruns** | PC health | **Microsoft Sysinternals licence (proprietary, not redistributable)** | winget (Microsoft.Sysinternals.Autoruns) | downloaded from Microsoft by winget |
| LibreHardwareMonitor | temperatures | MPL-2.0 | winget | |
| CrystalDiskInfo | disk health | MIT | winget | |
| **Docker Desktop** | runs SearXNG and n8n | **Docker Subscription Service Agreement** | winget (Docker.DockerDesktop) | free for personal use, education, open source and companies under 250 employees AND under USD 10 million revenue |
| SearXNG | web search | AGPL-3.0 | Docker Hub (searxng/searxng, pinned by digest) | separate service queried over HTTP |
| mcp-email-server (ai-zerolab) | mail module | BSD-3-Clause | ghcr.io, pinned by digest | |
| **python-libzim** | offline Wikipedia | **GPL-3.0** | PyPI | optional module, installed only if enabled |
| Wikipedia (Kiwix ZIM, French, no pictures) | offline Wikipedia | CC BY-SA 4.0 + GFDL | download.kiwix.org | SHA-256 checked |
| Windows-MCP 0.8.5 (CursorTouch) | Windows control | MIT | PyPI | |
| Playwright MCP 0.0.83 | browser | Apache-2.0 | npm | |
| @modelcontextprotocol/server-filesystem 2.0.0 | files | MIT | npm | |
| mcp-remote 0.15.2 | n8n bridge | MIT | npm | |
| **n8n** | automations (optional) | **Sustainable Use License (not open source)** | Docker Hub (n8nio/n8n 2.46.6, pinned by digest), installed by the wizard after you accept its licence | personal or internal use only |
| Hermes Agent (Nous Research) | external agent (optional) | MIT | installed by the user | acts outside Agent Local's safeguards |
| OpenRouter | cloud advisor (optional) | OpenRouter terms | online service | paid; data sent to a third party, each sending needs approval |
| Telegram Bot API | remote control (optional) | Telegram terms | online service | |
| Python libraries (mcp, httpx, pywebview, pythonnet, python-docx, openpyxl, pillow, pypdf, reportlab) | core | MIT / BSD / Apache-2.0 / PSF / MIT-CMU | PyPI | see requirements.txt |
| Fonts Rajdhani, JetBrains Mono | interface | SIL Open Font License 1.1 | Google Fonts | loaded online |
| Font Awesome Free 6.4.0 | interface icons | CC BY 4.0 / OFL 1.1 / MIT | cdnjs | loaded online |

The icon (`noyau/icone.ico`) was generated with an AI image tool by the project author, and the background (`frontend/images/fond.jpg`) was drawn by a script for this project. Both are MIT-licensed.
