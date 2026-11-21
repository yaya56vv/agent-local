"""Pupitre MCP : branche les serveurs MCP standard (stdio) et classe leurs outils.

Classement de chaque outil :
  "auto"      -> lecture seule, l'agent l'utilise librement
  "demander"  -> modifie quelque chose, l'utilisateur doit autoriser
  "interdit"  -> jamais execute
Une regle explicite dans config.json ("serveur__outil": "auto"|"demander"|"interdit")
l'emporte toujours sur le classement automatique.
"""
import re
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from langue import t as tr


def _env(env):
    """Une valeur "fichier:<chemin>" est lue dans ce fichier, hors du depot (16/11/2026, decision de l'utilisateur : le jeton
    du navigateur Chrome ne doit pas aller dans git). Fichier absent = ce seul MCP en erreur."""
    if not env:
        return env
    return {k: (open(v[len("fichier:"):], encoding="utf-8").read().strip()
                if isinstance(v, str) and v.startswith("fichier:") else v) for k, v in env.items()}


def _nom_sur(serveur, outil):
    return re.sub(r"[^A-Za-z0-9_-]", "_", f"{serveur}__{outil}")[:64]


class PupitreMCP:
    def __init__(self, serveurs, autorisations):
        self.serveurs = serveurs
        self.motifs = [m.lower() for m in autorisations.get("motifs_lecture", [])]
        self.regles = autorisations.get("regles", {})
        self.libres = set(autorisations.get("serveurs_libres", []))  # serveurs libres par defaut (leur garde-fou affine)
        self.pile = AsyncExitStack()
        self.outils = {}      # nom_sur -> {serveur, outil, session, niveau, description}
        self.etats = {}       # serveur -> "branche" | "erreur : ..."

    async def brancher(self):
        for nom, conf in self.serveurs.items():
            try:
                params = StdioServerParameters(command=conf["command"], args=conf.get("args", []),
                                               env=_env(conf.get("env")))
                lecture, ecriture = await self.pile.enter_async_context(stdio_client(params))
                session = await self.pile.enter_async_context(ClientSession(lecture, ecriture))
                await session.initialize()
                for o in (await session.list_tools()).tools:
                    cle = _nom_sur(nom, o.name)
                    lit = self._est_lecture(o)
                    defaut = "auto" if lit or nom in self.libres else "demander"
                    self.outils[cle] = {"serveur": nom, "outil": o.name, "session": session,
                                        "lecture": lit,
                                        "niveau": self.regles.get(cle, defaut),
                                        "description": o.description or "",
                                        "schema": o.inputSchema or {"type": "object", "properties": {}}}
                self.etats[nom] = "branche"
            except Exception as e:
                self.etats[nom] = tr("commun.etat_erreur", v1=e)

    def _est_lecture(self, outil):
        ann = getattr(outil, "annotations", None)
        if ann is not None and getattr(ann, "readOnlyHint", None) is True:
            return True
        nom = outil.name.lower()
        return any(nom.startswith(m) or f"_{m}" in nom for m in self.motifs)

    def pour_le_modele(self):
        return [{"type": "function", "function": {"name": cle, "description": o["description"],
                 "parameters": o["schema"]}}
                for cle, o in self.outils.items() if o["niveau"] != "interdit"]

    async def appeler(self, cle, arguments):
        o = self.outils[cle]
        res = await o["session"].call_tool(o["outil"], arguments)
        morceaux = [getattr(c, "text", None) or f"[{c.type}]" for c in res.content]
        return (tr("commun.erreur_deux_points") if res.isError else "") + "\n".join(morceaux)

    async def debrancher(self):
        await self.pile.aclose()
