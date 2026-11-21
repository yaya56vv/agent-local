@echo off
rem Installation d'Agent Local au double-clic (Windows n'execute pas un fichier .ps1 directement).
rem Les messages ci-dessous s'affichent avant que les fichiers de langue soient lisibles : ils sont donc en deux langues.
if not exist "%~dp0installer.ps1" (
  echo.
  echo  [FR] Decompressez d'abord le fichier zip : clic droit sur le zip, puis "Extraire tout".
  echo       Ouvrez ensuite le dossier agent-local et double-cliquez sur "Installer Agent Local".
  echo  [EN] Unzip the file first: right-click the zip, then "Extract All".
  echo       Then open the agent-local folder and double-click "Installer Agent Local".
  echo.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer.ps1"
if errorlevel 1 pause
