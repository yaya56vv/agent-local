---
name: uninstall-a-program
description: "Uninstall a software cleanly via winget, check the real state after an error, then identify and clean the residuals (data folders, orphan update components, processes) with user approval."
---

## When to use it
The user requests to uninstall a software.

## Steps
1. Search for the software with logiciels__chercher_logiciel to find its exact winget identifier.
2. Read the skill (logiciels__fiche_logiciel) to verify it is the official software from the expected publisher.
3. Uninstall with logiciels__desinstaller_logiciel.
4. If the uninstallation returns an error, do not conclude failure: check the real state with logiciels__logiciels_installes (filter on name) and a registry read (HKLM, HKLM WOW6432Node, HKCU).
5. Search for residuals: remaining processes (Get-Process -Name 'name*'), program folder in Program Files and Program Files (x86), data folder in AppData Local and AppData Roaming.
6. Provide an account and request user approval before cleaning: software uninstalled or not, list of residuals (size, location).
7. Clean the AppData folder first (to the Recycle Bin with terminal__mettre_a_la_corbeille), then the program folder. If a folder does not clear, a residual process often locks it: recheck after cleaning data rather than forcing process stop.
8. Final verification: Test-Path on each folder, Get-Process on processes, registry read on Uninstall.

## Pitfalls to avoid
- winget may return a failure code even if the uninstallation succeeded: always verify the real state.
- The software may disappear from the registry, leaving data in AppData: this is where residual cleaning is needed.
- Chromium browsers often leave a separate update component in Program Files, absent from winget and the registry: this is an orphaned residual.
- Residual processes may refuse Stop-Process (access denied): do not insist, clean data then recheck.
- Measuring a very large folder may exceed the terminal timeout: give an order of magnitude.
- Never remove with Remove-Item: always use terminal__mettre_a_la_corbeille, with user approval (recoverable).