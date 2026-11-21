"""Adaptateur n8n -> Agent Local (12/11/2026).

n8n 2.32 expose les workflows que l'utilisateur rend « disponibles par MCP » sur http://localhost:5678/mcp-server/http.
Agent Local ne branche que des serveurs MCP locaux (stdio) : ce script lance l'adaptateur mcp-remote (version figee,
publiee depuis plus de deux semaines) qui fait le pont. Le jeton d'acces MCP, copie par l'utilisateur depuis les reglages de
n8n, reste dans n8n-cle-mcp.txt, dans le dossier de secrets : il ne figure ni dans config.json ni dans git.
"""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import reglages
from langue import t as tr

CLE = Path(reglages.chemin_secret("n8n-cle-mcp.txt"))
ADRESSE = "http://localhost:5678/mcp-server/http"

if not CLE.is_file() or not CLE.read_text(encoding="utf-8").strip():
    sys.stderr.write(tr("mcp_n8n.jeton_mcp_de_n8n_absent", CLE=CLE))
    sys.exit(1)
jeton = CLE.read_text(encoding="utf-8").strip()
# n8n tourne dans Docker et peut demarrer quelques secondes apres Agent Local : on l'attend jusqu'a 90 s
for _ in range(45):
    try:
        urllib.request.urlopen("http://localhost:5678/healthz", timeout=2)
        break
    except Exception:
        time.sleep(2)
env = {**os.environ, "N8N_MCP_AUTH": f"Bearer {jeton}"}
sys.exit(subprocess.run(["cmd", "/c", "npx", "-y", "mcp-remote@0.15.2", ADRESSE, "--transport", "http-only",
                         "--header", "Authorization:${N8N_MCP_AUTH}"], env=env).returncode)
