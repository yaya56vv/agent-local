@echo off
rem Lanceur d'Agent Local au double-clic : Windows n'execute pas les fichiers .ps1 directement.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0lancer_agent_local.ps1"
