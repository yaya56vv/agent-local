# Modules

**🇫🇷 Version française : [modules.fr.md](modules.fr.md)**

Always included: memory (notebook), files, PDF, Word and Excel, PowerShell terminal, programs, software (winget), hardware, scheduler, artifacts. Other modules activate in the assistant or in **Settings → Modules**. An external component installs only after its license is displayed and your checkbox « I agree » is checked.

| Module | What it does | What it installs | Data sent outside the PC |
|---|---|---|---|
| Vision | The agent views an image or screen | mmproj model file (Hugging Face) | none |
| Voice | Reads responses aloud; French or English voices depending on language | nothing (edge-tts is in the kernel) | **the text being read, sent to Microsoft** |
| Backup voice | Offline voice when Internet is cut off | coqui-tts, PyTorch, XTTS-v2 model (non-commercial) | none |
| Dictation | Ctrl+Alt to dictate in any window; Telegram voice transcription | faster-whisper, NVIDIA libraries, Whisper model (Hugging Face) | none |
| Web search | Searches without account or key, reads pages | Docker Desktop (winget), SearXNG (pinned by fingerprint) | your searches, sent to SearXNG search engines |
| Browser | Browsing, reading, forms in a separate profile | Playwright MCP (npm) | pages visited |
| Windows control | Open software, click, type | Windows-MCP 0.8.5 (PyPI) | none |
| Offline Wikipedia | Full French Wikipedia, no Internet | libzim (GPL-3.0), Kiwix ZIM file (≈ 13 GB) | none |
| PC Health | Temperatures, disks, boot, logs | Autoruns, LibreHardwareMonitor, CrystalDiskInfo (winget), admin tasks | none |
| Repair Kit | 10 admin troubleshooting actions, each confirmed in a window | one scheduled task (standard account: Windows confirmation for each action) | none |

## Advanced modules (disabled by default)

| Module | What it does | Warning |
|---|---|---|
| Cloud advisor | Requests a second opinion from an online model (OpenRouter) | paid; each send is requested; passwords, card numbers and IBANs are refused outright |
| Telegram | Missions and approvals from your phone | you create your own bot (@BotFather); only the first account that sends the displayed code is obeyed |
| Mail | Read and sort your emails (Gmail, Yahoo) | app password; only moving to « Local Agent Folder » is allowed, upon approval |
| Hermes | Assigns a long mission to Hermes Agent, installed separately | Hermes acts according to its own rules, outside Agent Local safeguards (except the forbidden zone, which is refused before launch) |
| n8n | Launches your n8n automations | non-free license (internal use only); each launch is requested |

Keys and tokens are entered in **Settings → Keys and Accounts**. They are stored in `%APPDATA%\AgentLocal\secrets`, never in `config.json`.