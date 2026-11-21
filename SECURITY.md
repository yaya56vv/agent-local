# Security / Sécurité

## Reporting a vulnerability / Signaler une faille

Please **do not open a public issue** for a security problem. Use GitHub's private reporting instead:
**Security → Report a vulnerability** on this repository. Describe what an attacker could do, how to reproduce it, and
the version (`VERSION` file). You will get an answer as soon as possible.

*Merci de ne pas ouvrir de ticket public pour une faille. Utilisez le signalement privé de GitHub (Security → Report a
vulnerability), avec ce qu'un attaquant pourrait faire, comment le reproduire et la version (fichier `VERSION`).*

## What Agent Local protects / Ce qu'Agent Local protège

An AI model can be wrong or be manipulated by what it reads (a web page, an e-mail, a file). Agent Local's protections
are **in the code**, never only in the model's instructions:

- **Autonomy levels** (Cautious by default): what changes something or sends data needs your approval.
- **Forbidden zone**: the installation folder (code, settings, memory) cannot be read or modified by the agent, whatever the command.
- **No permanent deletion**: deletion goes to the Recycle Bin, with your approval.
- **Safety net**: a copy of every file is kept before it is modified (7 days), with an "Undo last change" button.
- **Browser**: no password, code or card number is ever typed by the agent; local and private network addresses are refused.
- **Administrator tools** (optional): a confirmation window opens on your screen before each repair action, and a normal program cannot click it; tools run as administrator are copied to a protected folder and checked (signature or SHA-256) at every start.
- **Secrets** live in `%APPDATA%\AgentLocal\secrets`, readable by your Windows account only, never in `config.json` or in git.
- **Downloads** come only from official sources and are checked by SHA-256 when the source publishes it.

Details: [docs/garde-fous.md](docs/garde-fous.md) (English) · [docs/garde-fous.fr.md](docs/garde-fous.fr.md) (français).

## Known limits / Limites connues

- Modules marked "advanced" (Hermes, n8n, cloud advisor, Telegram, mail) send data to third parties or act outside the safeguards. They are off by default.
- In Autonomous mode, the agent acts alone in your personal folders and programs: use it only once you know how it behaves.
- The integrity check of LibreHardwareMonitor freezes the files as they were when you installed them; it cannot prove they were genuine at that moment.
