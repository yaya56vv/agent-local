# Safeguards

**🇫🇷 Version française : [garde-fous.fr.md](garde-fous.fr.md)**

Design principle: **protection is in the code, not only in the model instruction.** Whatever the model thinks, a protected action will not be allowed. Numbers refer to comments in `noyau/agent.py`.

## Autonomy levels (`noyau/reglages.py`)

| | Cautious (default) | Balanced | Autonomous |
|---|---|---|---|
| Read files, pages, hardware | free | free | free |
| Write a file | approval | free in output folder, approval elsewhere | free in personal folders, approval elsewhere |
| Click and type in a software (Windows-MCP) | approval | approval | free |
| Browser: navigate, read | free | free | free |
| Browser: click, fill | approval | free, except send, payment, password | free, except send, payment, password |
| Launch a program | approval | approval | free |
| Delete | forbidden by Windows-MCP; Recycle Bin on approval | Recycle Bin, on approval | Recycle Bin, on approval |
| PowerShell that modifies, admin, software installation | approval | approval | approval |
| Send data (cloud, n8n, form, message, email, purchase, payment) | approval | approval | approval |
| Scheduled task (no one is monitoring) | read-only | read-only | approvals are refused by default |
| Learn a new skill | approval | approval | free |

## Always active

1. **Forbidden zone** (safeguard 1 and 6): the installation folder (code, settings, notebook, conversations) cannot be read or modified by any tool. A PowerShell command, a Hermes mission or a path that mentions it is refused, however it is written (`/` or `\`, variables `%USERPROFILE%` and `$env:USERPROFILE`, `~`, 8.3 short names).
2. **Overwriting a file** requires approval (safeguard 2).
3. **Journal** of everything that modifies (safeguard 3), visible and deletable in Settings → My Data.
4. **Browser** (safeguard 4, `garde_navigateur.py`): no password, code or card number typed by the agent; local addresses and private network addresses are refused; only http and https; form submission and engagement buttons are allowed on approval.
5. **Messaging** (safeguard 5): only moving INBOX to "Agent Local Trash" is allowed; deletion, sending and archiving are invisible to the model.
6. **PowerShell sorted** (safeguard 6): PowerShell analyzer lists every called command; only reads pass without approval.
7. **Outside personal folders** (safeguard 7): modification elsewhere requires approval.
8. **Safety net** (safeguard 8, `filet.py`): copy of each file before modification, kept for 7 days; "Undo last change" button.
9. **Word and Excel** (safeguard 9): never written with text tools, which would damage them.
10. **Windows-MCP** (safeguard 10): free reading; writing files and registry on approval; deletion to Recycle Bin (or forbidden in Cautious mode); local addresses refused.
11. **Scheduled tasks** (safeguard 11): in Cautious and Balanced mode, only reads execute.

## Administrator tools (optional, `outils-admin/`)

- **Repair kit**: the agent only chooses an action from a closed list. Before each action, a window "Agent Local - Administrator confirmation" opens on the screen. Since it belongs to an administrator process, Windows prevents a regular program from clicking it: a false request placed by malicious software cannot do anything without your click. Without response in 10 minutes, the action is refused. On a standard account, Windows also asks for an administrator password before each action (no scheduled task is created).
- **PC Health**: tools launched as administrator are copied to `C:\Program Files\AgentLocal\Outils`, where only administrators can write. At each launch, Autoruns must have a valid Microsoft signature, and each LibreHardwareMonitor code file must have the SHA-256 fingerprint recorded at installation. A changed, missing or extra file blocks the launch, which Settings displays clearly, with a "Repair / Update" button. The Autoruns and Disks tasks run under the System account, so they also work for a standard account: your account can run them, but not change them.
- Rights are verified by security identifier (SID), which works regardless of Windows language.
- **Never a silent overwrite**: these scripts only use their own names (`C:\ProgramData\AgentLocal`, `C:\Program Files\AgentLocal`, the `\AgentLocal\` folder of Task Scheduler). If they find an item with that name that they did not create, they show it and ask you to type YES before replacing it.

## Secrets

Keys and tokens are stored in `%APPDATA%\AgentLocal\secrets`, reserved for your Windows account. They are never written in `config.json`, never displayed after input, and never sent to the cloud advisor.