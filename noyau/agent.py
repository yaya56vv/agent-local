"""Boucle de l'agent : se souvenir -> penser -> agir (outils MCP) -> observer -> recommencer.

Chaque etape est signalee par un evenement (dict), destine a l'interface :
  rappel, tour, reflexion, texte, appel_outil, autorisation, resultat_outil, reponse, erreur
L'autorisation passe par la fonction `demander(appel)` fournie par l'interface,
qui renvoie True (accepte) ou False (refuse).
Le fil de la conversation est enregistre dans le carnet (memoire.py) a chaque message.
"""
import json
import os
import re
import subprocess
import time
from datetime import datetime

import artefacts
import competences
import filet
import garde_navigateur
import memoire
import reseau
import vision
from llm import discuter
from langue import t as tr

JOURNAL = memoire.BASE.parent / "journal.jsonl"


def _dans_zone(chemin, zones):
    chemin = os.path.normcase(chemin)
    for z in zones:
        z = os.path.normcase(os.path.abspath(z))
        if chemin == z or chemin.startswith(z.rstrip("\\") + "\\"):
            return z
    return None


# PowerShell en lecture seule (decision du 11/11/2026 : les commandes qui ne font que lire passent sans
# son accord). Trieur volontairement prudent : au moindre doute, la commande reste soumise a son accord.
_PS_LECTURE = {
    "select-object", "select-string", "where-object", "sort-object", "measure-object", "group-object",
    "format-table", "format-list", "format-wide", "out-string", "convertto-json", "convertto-csv", "convertto-html",
    "test-path", "test-connection", "test-netconnection", "resolve-path", "split-path", "join-path", "compare-object",
    "foreach-object", "%", "?", "where", "select", "sort", "measure", "ft", "fl", "dir", "ls", "gci", "cat", "type",
    "gc", "gps", "gsv", "ipconfig", "whoami", "hostname", "systeminfo", "nvidia-smi", "driverquery", "tasklist",
    "netstat", "ping", "tracert", "nslookup", "where.exe", "echo", "write-output", "out-null", "out-host",
    "convertfrom-json", "convertfrom-csv",
}
_PS_DANGER = re.compile(
    r"(\b(set|remove|new|add|clear|stop|start|restart|invoke|install|uninstall|enable|disable|rename|move|copy|"
    r"out(?!-(?:string|null|host)\b)|export|import|update|write(?!-output\b)|register|unregister|suspend|resume|mount|dismount|initialize|"
    r"format-volume|save|send|grant|revoke|lock|unlock|push|pop|reset|repair|protect|unprotect|block|unblock|"
    r"expand|compress|confirm|wait|debug|receive|connect|disconnect|publish|approve|deny|use|edit|undo|redo)-\w+)"
    r"|>|\biex\b|\.invoke|\[(io|system\.io|diagnostics|reflection|wmiclass|activator)|::|\.delete|\.kill|\.terminate"
    r"|\.(remove|create|setvalue|deletevalue|start|stop|write)\w*\(|\b(rm|del|erase|rd|rmdir|ri|mv|move|cp|copy|ren|"
    r"md|mkdir|ni|sc|reg|netsh|pnputil|bcdedit|wmic|diskpart|format|shutdown|taskkill|cmd|powershell|pwsh|start|"
    r"saps|kill|spps|curl|wget|iwr|irm|bitsadmin|certutil|schtasks|icacls|takeown|attrib|cipher|net)(\.exe)?\b(?!-)"
    r"|&|`|-encodedcommand|-enc\b"
    # ipconfig n'est une lecture que pour l'affichage (ipconfig, ipconfig /all) : /release, /renew, /flushdns...
    # modifient la connexion et restent soumis a l'accord de l'utilisateur (11/11/2026)
    r"|\bipconfig(\.exe)?\s+/(release|renew|flushdns|registerdns|setclassid|allcompartments\s+/release)", re.IGNORECASE)
# Appels statiques inoffensifs (calculs, textes, dates) : retires avant la recherche de '::' dangereux (11/11/2026)
_PS_STATIQUES_SURS = re.compile(r"\[(system\.)?(math|string|datetime|timespan|char|int|int32|int64|long|double|decimal|"
                                r"convert|regex|guid|version|bool|uint64|globalization\.cultureinfo)\]::", re.IGNORECASE)


# L'analyseur de PowerShell lui-meme liste chaque commande appelee, y compris dans les if, foreach, $(...) et
# affectations $x = ... (decision du 12/11/2026 : les lectures demandaient encore son accord, parce que
# l'ancien decoupage refusait toute ligne commencant par une variable, un texte entre guillemets ou un if).
_ANALYSE_PS = (
    "$e=$null; $a=[System.Management.Automation.Language.Parser]::ParseInput($env:AGENT_COMMANDE_PS,[ref]$null,[ref]$e);"
    "if($e){'#ERREUR'};"
    "$a.FindAll({param($n) $n -is [System.Management.Automation.Language.CommandAst]},$true) |"
    " ForEach-Object { $c=$_.GetCommandName(); if($c){$c}else{'#DYNAMIQUE'} };"
    "if($a.FindAll({param($n) $n -is [System.Management.Automation.Language.RedirectionAst]},$true)){'#REDIRECTION'}")


def _commandes_appelees(texte):
    """Noms des commandes que la ligne PowerShell appellerait, ou None si l'analyse echoue."""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _ANALYSE_PS],
                           capture_output=True, encoding="utf-8", errors="replace", timeout=15,
                           env={**os.environ, "AGENT_COMMANDE_PS": texte},
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return None
    return [l.strip() for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else None


def _powershell_lecture(commande):
    """True seulement si la commande ne fait que lire : aucun motif dangereux dans le texte, et chaque commande
    appelee (selon l'analyseur de PowerShell) est un Get-... ou une commande connue de lecture, sans redirection
    ni commande au nom calcule. Au moindre doute, l'accord de l'utilisateur reste demande."""
    texte = str(commande or "").strip()
    if not texte or _PS_DANGER.search(_PS_STATIQUES_SURS.sub("", texte)):
        return False
    noms = _commandes_appelees(texte)
    if noms is None or any(n.startswith("#") for n in noms):   # [] = que des textes et calculs : lecture
        return False
    return all(n.lower().startswith("get-") or n.lower() in _PS_LECTURE for n in noms)


# Outils internes : ils ne touchent a rien, ils tiennent l'utilisateur informe dans le panneau Mission.
OUTILS_INTERNES = [
    {"type": "function", "function": {
        "name": "plan_mission",
        "description": tr("agent.a_appeler_en_premier_pour"),
        "parameters": {"type": "object", "required": ["etapes"], "properties": {
            "etapes": {"type": "array", "items": {"type": "string"}, "description": tr("agent.etapes_courtes_ex_lister_les")}}}}},
    {"type": "function", "function": {
        "name": "etape_faite",
        "description": tr("agent.a_appeler_des_qu_une"),
        "parameters": {"type": "object", "required": ["numero"], "properties": {
            "numero": {"type": "integer", "description": tr("agent.numero_de_l_etape_en")},
            "note": {"type": "string", "description": tr("agent.resultat_en_quelques_mots_facultatif")},
            "echec": {"type": "boolean", "description": tr("agent.true_si_l_etape_n")}}}}},
    {"type": "function", "function": {
        "name": "noter",
        "description": tr("agent.ton_bloc_notes_de_mission"),
        "parameters": {"type": "object", "required": ["faits"], "properties": {
            "faits": {"type": "array", "items": {"type": "string"},
                      "description": "Faits courts et exacts, ex. 'Disque E: 953,8 Go libres sur 953,9 Go (Get-Volume)'"}}}}},
    {"type": "function", "function": {
        "name": "creer_artefact",
        "description": tr("agent.cree_un_artefact_un_contenu"),
        "parameters": {"type": "object", "required": ["titre", "type", "contenu"], "properties": {
            "titre": {"type": "string", "description": tr("agent.titre_court_ex_lettre_de")},
            "type": {"type": "string", "enum": ["texte", "code", "html"],
                     "description": tr("agent.texte_lettre_ou_document_markdown")},
            "langage": {"type": "string", "description": tr("agent.pour_type_code_python_javascript")},
            "contenu": {"type": "string", "description": tr("agent.le_contenu_complet")}}}}},
    {"type": "function", "function": {
        "name": "modifier_artefact",
        "description": tr("agent.remplace_le_contenu_d_un"),
        "parameters": {"type": "object", "required": ["numero", "contenu"], "properties": {
            "numero": {"type": "integer"},
            "titre": {"type": "string", "description": tr("agent.nouveau_titre_facultatif")},
            "contenu": {"type": "string", "description": tr("agent.le_contenu_complet_de_la")}}}}},
    {"type": "function", "function": {
        "name": "regarder",
        "description": tr("agent.tes_yeux_te_montre_une"),
        "parameters": {"type": "object", "properties": {
            "chemin": {"type": "string", "description": tr("agent.chemin_image_exemple")},
            "ecran": {"type": "boolean", "description": tr("agent.true_pour_photographier_l_ecran")}}}}},
]
OUTILS_ARTEFACT = ("creer_artefact", "modifier_artefact")

# Relecture avant de rendre (decision du 12/11/2026, apres le test d'Atomic Agent : rapide mais disque E
# annonce plein alors qu'il etait vide, colonnes inversees). Pour cette relecture, le modele recoit les resultats
# d'outils BRUTS (non raccourcis), pour comparer a la source et non a sa memoire.
RELECTURE = (
    tr("agent.relecture_interne_avant_de_rendre"))
# Pendant la relecture, seuls ces outils restent disponibles (12/11/2026 : sinon le modele refaisait toute la mission).
# creer_word ajoute le 16/11/2026 (decision de l'utilisateur) : un rapport Word fautif ne pouvait pas etre corrige (refus,
# un tour perdu, erreur laissee dans le fichier) ; il n'ecrase jamais, la correction part dans un nouveau fichier.
OUTILS_RELECTURE = ("modifier_artefact", "fichiers__write_file", "fichiers__edit_file", "bureautique__creer_word",
                    "bureautique__creer_excel")

# Fichier annonce mais absent (decision du 16/11/2026 : un bilan a dit « le rapport est dans ton dossier
# Bilans » alors qu'il n'etait que dans le panneau). Verifie une fois, dans le code, avant la reponse finale.
VERIFICATION_FICHIER = (
    tr("agent.verification_interne_l_utilisateur_ne"))
_RE_CHEMIN_ANNONCE = re.compile(r"[A-Za-z]:\\[^\n*?\"<>|`]+?\.[A-Za-z0-9]{2,5}\b")
_RE_ANNONCE = re.compile(r"\b(est|sont|ete|été|j'ai|bien)\s+(bien\s+)?(enregistr|sauvegard)|"
                         r"\b(est|sont)\s+(bien\s+)?dans\s+(ton|tes|le)\s+(dossier|bilans|documents)", re.IGNORECASE)


def _fichier_annonce_absent(reponse, ecrits):
    """Ce qui manque si la reponse annonce un fichier qui n'existe pas, sinon None. ecrits = chemins vises par les
    actions d'ecriture de la mission."""
    cites = [c.rstrip(" .,;:)") for c in _RE_CHEMIN_ANNONCE.findall(reponse or "")]
    absents = [c for c in cites if not os.path.exists(c)]
    if absents:
        return tr("agent.le_fichier_n_existe_pas", v1=absents[0])
    if not cites and _RE_ANNONCE.search(reponse or "") and not any(os.path.isfile(c) for c in ecrits):
        return tr("agent.aucun_fichier_n_a_ete")
    return None


class Agent:
    def __init__(self, config, pupitre, signaler, demander):
        self.conf = config["llm"]
        self.conf_mem = config.get("memoire", {})
        # Consigne : celle de config.json si l'utilisateur l'a remplacee, sinon celle de la langue choisie.
        prenom = config["utilisateur"].get("prenom", "").strip() or tr("commun.utilisateur_par_defaut")
        sortie = config["utilisateur"]["dossier_sortie"]
        self.consigne = (config.get("consigne_systeme") or tr("consigne.systeme", prenom="{prenom}", sortie="{sortie}")
                         ).replace("{prenom}", prenom).replace("{PRENOM}", prenom).replace("{sortie}", sortie).replace("{SORTIE}", sortie)
        self.auth = config.get("autorisations", {})
        self.tache_planifiee = False   # mis a jour par app.py pendant une tache planifiee (garde-fou 11)
        # Les yeux ne lisent que les dossiers ouverts a l'outil fichiers (meme perimetre que ses mains)
        self.dossiers_lisibles = [a for a in config["mcp_servers"]["fichiers"]["args"] if a[1:3] == ":\\"]
        self.pupitre = pupitre
        self.signaler = signaler
        self.demander = demander
        # Chaque lancement repart sur un fil de conversation neuf (09/11/2026) : l'ancien fil
        # saturait la memoire de travail du modele. Le carnet (souvenirs) et les competences restent intacts.
        self.nouvelle_conversation()
        self._etapes_du_plan, self._competence_touchee = 0, False
        self._notes, self._artefact_touche = [], False   # bloc-notes et artefact de la mission en cours
        self._instantane = ""   # derniere capture de page du navigateur
        self._images_a_montrer = []   # images demandees avec regarder, montrees au modele au tour suivant

    def nouvelle_conversation(self):
        self.conversation = memoire.nouvelle_conversation()
        self.historique = []

    def reprendre_conversation(self, conversation_id):
        """Historique (12/11/2026) : la conversation choisie redevient le fil actif, avec tout son
        contenu ; les messages suivants s'y ajoutent. Une image qui n'existe plus n'est pas remontree au modele."""
        historique = memoire.lire_conversation(conversation_id)
        for m in historique:
            if m.get("image") and not os.path.isfile(m["image"]):
                m.pop("image")
                m["interne"] = True   # reste un message technique, pas une demande de l'utilisateur
        # Une mission coupee net (plantage) peut laisser un appel d'outil sans resultat : le modele le refuserait.
        repondus = {m.get("tool_call_id") for m in historique if m["role"] == "tool"}
        for m in historique:
            if m.get("tool_calls") and not all(a["id"] in repondus for a in m["tool_calls"]):
                m["tool_calls"] = [a for a in m["tool_calls"] if a["id"] in repondus]
                if not m["tool_calls"]:
                    m.pop("tool_calls")
        self.conversation, self.historique = conversation_id, historique

    def _ajouter(self, message):
        self.historique.append(message)
        memoire.enregistrer_message(self.conversation, message)

    def _rappel(self, demande):
        """Ce que l'agent doit avoir sous les yeux : l'essentiel + ce qui touche a la demande."""
        vus, choisis = set(), []
        for s in memoire.essentiels() + memoire.rechercher(demande, self.conf_mem.get("souvenirs_rappeles", 8)):
            if s["id"] not in vus:
                vus.add(s["id"])
                choisis.append(s)
        return choisis

    def _messages_pour_le_modele(self, souvenirs, fiches=(), bruts=False):
        # Debut FIXE pendant toute une mission (consigne, souvenirs, competence) : le serveur du modele le garde en
        # memoire au lieu de relire ~45 000 jetons a chaque etape. Ce qui change souvent (heure, bloc-notes) part
        # dans le message de contexte place a la FIN (decision du 12/11/2026, methode d'Atomic Agent).
        systeme = self.consigne
        if souvenirs:
            lignes = "\n".join(f"- [{s['id']}] ({s['categorie']}) {s['texte']}" for s in souvenirs)
            systeme += (tr("agent.ce_que_tu_sais_deja") + lignes)
        for f in fiches:
            systeme += (tr("agent.competence_qui_correspond_a_la", v1=f['nom'], v2=f['description'], v3=f['contenu'][:3000]))
        # La mission en cours (depuis la derniere demande de l'utilisateur) est TOUJOURS gardee en entiere ; seules les
        # conversations precedentes sont limitees a messages_gardes. Avant le 11/11/2026, la limite s'appliquait
        # aussi a la mission : apres ~15 actions la demande sortait de la fenetre et l'agent perdait le fil.
        # La vraie limite est la memoire du modele (jauge + "memoire pleine" dans llm.py).
        debut_mission = next((i for i in range(len(self.historique) - 1, -1, -1)
                              if self.historique[i]["role"] == "user" and not self.historique[i].get("image")
                              and not self.historique[i].get("interne")), 0)
        debut = max(0, min(debut_mission, len(self.historique) - self.conf_mem.get("messages_gardes", 30)))
        recents = self.historique[debut:]
        while recents and recents[0]["role"] != "user":   # ne jamais commencer au milieu d'un echange d'outils
            recents = recents[1:]
        maintenant = datetime.now()
        jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
        contexte = (tr("agent.informations_automatiques_ce_n_est", v1=jours[maintenant.weekday()], maintenant=maintenant))
        if self._notes:
            contexte += tr("agent.ton_bloc_notes_de_la") + "\n".join(f"- {n}" for n in self._notes)
        return ([{"role": "system", "content": systeme}] + self._alleger(recents, bruts)
                + [{"role": "user", "content": contexte, "contexte": True}])

    @staticmethod
    def _alleger(messages, bruts=False):
        """Les resultats d'outils longs (captures de pages surtout) remplissent vite la memoire du modele :
        seuls les 4 derniers restent entiers, plafonnes a 15 000 caracteres ; les plus anciens sont raccourcis
        a 2 000, les faits utiles etant recopies dans le bloc-notes (outil noter). Les resultats courts ne comptent
        pas, et les comptes rendus d'Hermes ne sont jamais raccourcis (le MCP les plafonne deja a 12 000 caracteres).
        bruts=True (relecture avant de rendre) : seul le plafond de 15 000 s'applique, pour comparer a la source.
        Reglages du 12/11/2026 (avant : 6 entiers, anciens coupes a 4 000, sans bloc-notes), d'apres la methode
        d'Atomic Agent : garder des notes plutot que tout recopier."""
        noms = {a["id"]: a["function"]["name"] for m in messages if m["role"] == "assistant"
                for a in m.get("tool_calls") or []}
        longs_vus, images_vues, alleges = 0, 0, []
        for m in reversed(messages):
            contenu = m.get("content") or ""
            if m.get("image"):   # seules les 2 dernieres images restent sous les yeux du modele
                images_vues += 1
                if images_vues > 2:
                    m = {k: v for k, v in m.items() if k != "image"}
                    m["content"] = contenu + tr("agent.image_deja_vue_rappelle_regarder")
            if m["role"] == "tool" and len(contenu) > 2000 \
                    and not noms.get(m.get("tool_call_id"), "").startswith("hermes__"):
                longs_vus += 1
                if longs_vus > 4 and not bruts:
                    m = {**m, "content": contenu[:2000] + tr("agent.resultat_ancien_raccourci_les_faits")}
                elif len(contenu) > 15000:
                    m = {**m, "content": contenu[:15000] + tr("agent.capture_coupee_a_15_000")}
            alleges.append(m)
        return alleges[::-1]

    async def mission(self, demande):
        souvenirs = self._rappel(demande)
        fiches = competences.rechercher(demande)
        self._etapes_du_plan, self._competence_touchee = 0, False
        self._notes, self._artefact_touche, relu, verifie = [], False, False, False
        self._fichiers_ecrits = set()
        await self.signaler({"type": "rappel",
                             "souvenirs": [{"id": s["id"], "texte": s["texte"], "categorie": s["categorie"]}
                                           for s in souvenirs],
                             "competences": [{"nom": f["nom"], "description": f["description"]} for f in fiches]})
        self._ajouter({"role": "user", "content": demande})
        outils = self.pupitre.pour_le_modele() + OUTILS_INTERNES
        for tour in range(1, self.conf.get("tours_max", 20) + 1):
            await self.signaler({"type": "tour", "numero": tour})
            message = None
            # Tant que la relecture reste a faire, le texte du modele n'est qu'un brouillon : il s'affiche comme une
            # pensee, sans etre lu a voix haute (sinon l'utilisateur entendrait la reponse deux fois).
            brouillon = not relu and (self._etapes_du_plan >= 3 or self._artefact_touche)
            disponibles = [o for o in outils if o["function"]["name"] in OUTILS_RELECTURE] if relu else outils
            try:
                async for genre, donnee in discuter(self.conf["url"],
                                                    self._messages_pour_le_modele(souvenirs, fiches, bruts=relu),
                                                    disponibles, self.conf.get("temperature", 0.6)):
                    if genre == "fin":
                        message = donnee
                    elif genre == "memoire":
                        await self.signaler({"type": "memoire", **donnee})
                    elif genre == "appel_partiel":
                        if donnee["nom"] in OUTILS_ARTEFACT:   # l'utilisateur voit l'artefact s'ecrire en direct
                            await self.signaler({"type": "artefact_partiel", **donnee})
                    else:
                        await self.signaler({"type": "reflexion" if brouillon and genre == "texte" else genre,
                                             "texte": donnee})
            except Exception as e:
                await self.signaler({"type": "erreur", "texte": tr("agent.modele_injoignable_ou_en_erreur", e=e)})
                return None
            appels = message["tool_calls"]
            entree = {"role": "assistant", "content": message["content"]}
            if appels:
                entree["tool_calls"] = appels
            self._ajouter(entree)
            if not appels:
                # Relecture avant de rendre : une fois par mission, si elle a produit un rapport (plan de 3 etapes
                # ou plus, ou artefact), le modele recompare ses chiffres aux resultats bruts des outils.
                if not relu and (self._etapes_du_plan >= 3 or self._artefact_touche):
                    relu = True
                    await self.signaler({"type": "reflexion", "texte": tr("agent.relecture_des_chiffres_avant_de")})
                    self._ajouter({"role": "user", "content": RELECTURE, "interne": True})
                    continue
                manque = _fichier_annonce_absent(message["content"], self._fichiers_ecrits)
                if manque and not verifie:
                    verifie = True
                    await self.signaler({"type": "reflexion", "texte": tr("agent.verification_du_fichier_annonce")})
                    self._ajouter({"role": "user", "content": VERIFICATION_FICHIER.format(manque), "interne": True})
                    continue
                if manque:   # toujours faux apres la verification : l'utilisateur est prevenu par le code lui-meme
                    message["content"] += tr("agent.verification_d_agent_local_ne", manque=manque)
                await self.signaler({"type": "reponse", "texte": message["content"]})
                if self._etapes_du_plan >= 3 and not self._competence_touchee:
                    try:
                        await self._apprendre(souvenirs, fiches)
                    except Exception as e:  # un rate ici ne doit pas gacher une mission reussie
                        await self.signaler({"type": "reflexion", "texte": tr("agent.apprentissage_interrompu", e=e)})
                return message["content"]
            noms_du_tour = [a["function"]["name"] for a in appels]
            for i, appel in enumerate(appels):
                if relu and appel["function"]["name"] not in OUTILS_RELECTURE:
                    resultat = (tr("agent.refus_pendant_la_relecture_tu"))
                else:
                    resultat = await self._executer(appel)
                # Rappel du plan (14/11/2026 : les etapes n'etaient cochees qu'en fin de mission) : apres un
                # tour d'actions sans aucune coche, le dernier resultat rappelle ou en est le plan.
                if (i == len(appels) - 1 and not relu and self._etapes_du_plan >= 2
                        and "etape_faite" not in noms_du_tour and "plan_mission" not in noms_du_tour
                        and len(getattr(self, "_etapes_cochees", set())) < self._etapes_du_plan):
                    faites = sorted(getattr(self, "_etapes_cochees", set()))
                    resultat = (tr("agent.plan_etapes_deja_cochees_sur", resultat=resultat, v1=faites or 'aucune', v2=self._etapes_du_plan))
                self._ajouter({"role": "tool", "tool_call_id": appel["id"], "content": resultat})
            # Rappel FERME (14/11/2026 : le rappel dans le resultat d'outil etait ignore) : apres 2 tours d'actions
            # sans aucune coche alors que le plan a des etapes ouvertes, une consigne interne est ajoutee.
            if not relu and self._etapes_du_plan >= 2 and "plan_mission" not in noms_du_tour:
                if "etape_faite" in noms_du_tour:
                    self._tours_sans_coche = 0
                elif len(getattr(self, "_etapes_cochees", set())) < self._etapes_du_plan:
                    self._tours_sans_coche = getattr(self, "_tours_sans_coche", 0) + 1
                    if self._tours_sans_coche >= 2:
                        self._tours_sans_coche = 0
                        faites = sorted(getattr(self, "_etapes_cochees", set()))
                        # interne = "rappel" : llm.py garde la reflexion COURTE apres ce rappel (16/11/2026 : sinon le
                        # modele le prenait pour une nouvelle demande et reflechissait 2 500 jetons, ~1 min)
                        self._ajouter({"role": "user", "interne": "rappel", "content": (
                            tr("agent.consigne_automatique_ton_plan_a", v1=self._etapes_du_plan, v2=faites or 'aucune'))})
            for chemin in self._images_a_montrer:   # les yeux : l'image suit les resultats d'outils
                self._ajouter({"role": "user", "content": tr("agent.image_demandee_avec_regarder", chemin=chemin), "image": chemin})
            self._images_a_montrer = []
        await self.signaler({"type": "erreur", "texte": tr("agent.nombre_maximal_de_tours_atteint")})
        return None

    async def _apprendre(self, souvenirs, fiches):
        """Moment d'apprentissage apres une mission reussie : y a-t-il une methode a retenir ?
        Se deroule a part (rien n'entre dans le fil de la conversation, rien n'est lu a voix haute)
        et ne dispose que des outils de competences."""
        await self.signaler({"type": "apprentissage"})
        messages = self._messages_pour_le_modele(souvenirs, fiches) + [{"role": "user", "content": (
            tr("agent.moment_d_apprentissage_interne_l"))}]
        outils = [o for o in self.pupitre.pour_le_modele() if o["function"]["name"].startswith("competences__")]
        for _ in range(4):
            message = None
            async for genre, donnee in discuter(self.conf["url"], messages, outils, self.conf.get("temperature", 0.6)):
                if genre == "fin":
                    message = donnee
                elif genre in ("reflexion", "texte"):
                    await self.signaler({"type": "reflexion", "texte": donnee})
            messages.append({"role": "assistant", "content": message["content"],
                             **({"tool_calls": message["tool_calls"]} if message["tool_calls"] else {})})
            if not message["tool_calls"]:
                return
            for appel in message["tool_calls"]:
                messages.append({"role": "tool", "tool_call_id": appel["id"], "content": await self._executer(appel)})

    @staticmethod
    def _evenement_artefact(id_a):
        """L'artefact pour la fenetre. Son champ 'type' (texte / code / html) devient 'genre',
        pour ne pas ecraser le type de l'evenement."""
        a = artefacts.lire(id_a)
        a["genre"] = a.pop("type")
        return {**a, "type": "artefact"}

    async def _regarder(self, id_appel, arguments):
        """Les yeux : verifie l'image (zone interdite comprise), puis la met en attente ; mission() l'ajoute a la
        conversation juste apres les resultats d'outils, et llm.py la transmet au modele."""
        infos = {"id": id_appel, "outil": "regarder", "serveur": "yeux", "arguments": arguments, "niveau": "auto"}
        await self.signaler({"type": "appel_outil", **infos})
        debut = time.monotonic()
        # Le modele envoie parfois ecran sous forme de texte ("True", "true", "oui"...) : corrige le 11/11/2026
        if str(arguments.get("ecran", "")).strip().lower() in ("true", "1", "oui", "yes", "vrai"):
            chemin, resultat = vision.capturer_ecran(), None
        else:
            chemin = str(arguments.get("chemin") or "").strip().strip('"')
            normal = os.path.normcase(os.path.abspath(chemin)) if chemin else ""
            zone = _dans_zone(normal, self.auth.get("zones_interdites", [])) if chemin else None
            hors = chemin and not zone and not _dans_zone(normal, self.dossiers_lisibles)
            resultat = (tr("agent.erreur_donne_le_chemin_complet") if not chemin else
                        tr("agent.refus_est_dans_une_zone_2", chemin=chemin, zone=zone) if zone else
                        tr("agent.refus_est_hors_de_tes", chemin=chemin) if hors else
                        tr("agent.erreur_le_fichier_n_existe", chemin=chemin) if not os.path.isfile(chemin) else
                        tr("agent.erreur_ce_n_est_pas") if os.path.splitext(chemin)[1].lower() not in vision.EXTENSIONS else None)
        if resultat is None:
            self._images_a_montrer.append(chemin)
            resultat = tr("agent.image_chargee_tu_la_vois")
        await self.signaler({"type": "resultat_outil", "id": id_appel, "serveur": "yeux", "outil": "regarder",
                             "resultat": resultat if resultat.startswith(("ERREUR", "REFUS")) else f"{resultat}\n{chemin}",
                             "duree": round(time.monotonic() - debut, 2)})
        return resultat

    async def _executer(self, appel):
        cle = appel["function"]["name"]
        try:
            arguments = json.loads(appel["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            return tr("agent.erreur_arguments_illisibles_json_invalide")
        if cle == "plan_mission":
            brutes = arguments.get("etapes", [])
            brutes = [brutes] if isinstance(brutes, str) else brutes
            etapes = [str(e).strip() for e in brutes if str(e).strip()]
            if not etapes:
                return tr("agent.erreur_le_plan_est_vide")
            self._etapes_du_plan = len(etapes)
            self._etapes_cochees = set()
            self._tours_sans_coche = 0
            await self.signaler({"type": "plan", "etapes": etapes})
            return tr("agent.plan_affiche_etapes_coche_chaque", v1=len(etapes))
        if cle == "etape_faite":
            try:
                numero = int(arguments.get("numero", 0))
            except (TypeError, ValueError):
                return tr("agent.erreur_numero_d_etape_invalide")
            if not hasattr(self, "_etapes_cochees"):
                self._etapes_cochees = set()
            self._etapes_cochees.add(numero)
            await self.signaler({"type": "etape", "numero": numero, "note": arguments.get("note", ""),
                                 "echec": bool(arguments.get("echec", False))})
            return f"Etape {numero} cochee."
        if cle == "noter":
            brutes = arguments.get("faits", [])
            brutes = [brutes] if isinstance(brutes, str) else brutes
            faits = [str(f).strip() for f in brutes if str(f).strip()]
            if not faits:
                return tr("agent.erreur_aucun_fait_a_noter")
            self._notes.extend(faits)
            return (tr("agent.fait_s_note_s_ton", v1=len(faits), v2=len(self._notes)))
        if cle == "creer_artefact":
            contenu = str(arguments.get("contenu", ""))
            if not contenu.strip():
                return tr("agent.erreur_l_artefact_est_vide")
            id_a = artefacts.creer(str(arguments.get("titre", "")), str(arguments.get("type", "texte")),
                                   contenu, str(arguments.get("langage", "")))
            await self.signaler(self._evenement_artefact(id_a))
            self._artefact_touche = True
            return tr("agent.artefact_cree_et_affiche_a", id_a=id_a)
        if cle == "modifier_artefact":
            try:
                id_a = int(arguments.get("numero", 0))
            except (TypeError, ValueError):
                return tr("agent.erreur_numero_d_artefact_invalide")
            contenu = str(arguments.get("contenu", ""))
            if not contenu.strip():
                return tr("agent.erreur_la_nouvelle_version_est")
            version = artefacts.modifier(id_a, contenu, arguments.get("titre"))
            if version is None:
                return tr("agent.erreur_aucun_artefact_numero", id_a=id_a)
            await self.signaler(self._evenement_artefact(id_a))
            return tr("agent.artefact_mis_a_jour_version", id_a=id_a, version=version)
        if cle == "regarder":
            return await self._regarder(appel["id"], arguments)
        outil = self.pupitre.outils.get(cle)
        if outil is None:
            return tr("agent.erreur_l_outil_n_existe", cle=cle)
        if outil["serveur"] == "competences" and outil["outil"] in ("creer_competence", "ameliorer_competence"):
            self._competence_touchee = True
        infos = {"id": appel["id"], "outil": outil["outil"], "serveur": outil["serveur"],
                 "arguments": arguments, "niveau": outil["niveau"]}
        lecture = outil["lecture"]
        mode = str(arguments.get("mode", "")).lower()
        corbeille = False
        # Garde-fou 10 : Windows-MCP (renforcement du 20/11/2026). Le serveur reste libre pour piloter les
        # logiciels, mais ses outils fichiers, registre et lecture web sont tries mode par mode : la lecture passe,
        # ce qui modifie demande l'accord de l'utilisateur, une suppression part a la Corbeille, une adresse locale est refusee.
        if outil["serveur"] == "windows":
            motif = None
            if outil["outil"] == "FileSystem":
                relatifs = [v for v in (arguments.get("path"), arguments.get("destination"))
                            if isinstance(v, str) and v.strip() and not os.path.isabs(v.strip())]
                if relatifs:   # Windows-MCP les calcule depuis le Bureau : ils echapperaient a la zone interdite
                    motif = tr("agent.chemin_relatif_refuse", v1=relatifs[0])
                elif mode in ("read", "list", "search", "info"):
                    lecture = True
                elif mode == "delete" and self.auth.get("suppression_windows") == "interdit":
                    motif = (tr("agent.suppression_interdite_par_windows_mcp"))
                elif mode == "delete":
                    corbeille = "terminal__mettre_a_la_corbeille" in self.pupitre.outils
                    infos["niveau"] = "demander"
                    infos["motif"] = (tr("agent.suppression_envoyee_a_la_corbeille") if corbeille else
                                      tr("agent.suppression_definitive_la_corbeille_est"))
                else:
                    infos["niveau"] = "demander"
            elif outil["outil"] == "Registry":
                if mode in ("get", "list"):
                    lecture = True
                else:
                    infos["niveau"] = "demander"
            elif outil["outil"] in ("Clipboard", "Process"):   # lire le presse-papiers ou la liste des processus est libre
                if mode in ("get", "list"):
                    lecture = True
                elif "windows" not in self.auth.get("serveurs_libres", []):
                    infos["niveau"] = "demander"   # ecrire le presse-papiers, arreter un processus
            elif outil["outil"] == "Scrape":
                dom = arguments.get("use_dom")
                if not (dom is True or str(dom).lower() == "true") and reseau.adresse_locale(str(arguments.get("url", ""))):
                    motif = (tr("agent.adresse_locale_ou_du_reseau"))
            if motif:
                infos["niveau"] = "interdit"
                await self.signaler({"type": "appel_outil", **infos})
                await self.signaler({"type": "resultat_outil", "id": appel["id"], "serveur": outil["serveur"],
                                     "outil": outil["outil"], "duree": 0, "resultat": tr("commun.refus_deux_points") + motif})
                return tr("commun.refus_deux_points") + motif
        # Garde-fou 1 : zones interdites (barriere dans le code, quoi que pense le modele)
        zones = self.auth.get("zones_interdites", [])
        recursif = outil["outil"] in ("directory_tree", "search_files") or (
            cle == "windows__FileSystem" and (mode == "search" or (mode == "list" and
                                                                   str(arguments.get("recursive")).lower() == "true")))
        for chemin in filet.chemins(arguments):
            zone = _dans_zone(chemin, zones)
            if not zone and recursif:
                # un outil recursif lance au-dessus d'une zone interdite y descendrait
                zone = next((z for z in zones
                             if os.path.normcase(os.path.abspath(z)).startswith(os.path.normcase(chemin).rstrip("\\") + "\\")), None)
                if zone:
                    chemin = tr("agent.exploration_recursive_qui_traverserait_utilise", chemin=chemin, zone=zone)
            if zone:
                infos["niveau"] = "interdit"
                await self.signaler({"type": "appel_outil", **infos})
                await self.signaler({"type": "resultat_outil", "id": appel["id"], "serveur": outil["serveur"],
                                     "outil": outil["outil"], "duree": 0,
                                     "resultat": tr("agent.refus_est_dans_une_zone_3", chemin=chemin)})
                return (tr("agent.refus_est_dans_une_zone", chemin=chemin, zone=zone))
        # Garde-fou 5 : la messagerie (11/11/2026). Un mail ne peut etre deplace que de la
        # boite de reception vers le dossier de tri ; la suppression, l'archivage et l'envoi sont "interdit"
        # dans config.json (invisibles pour le modele).
        courrier = self.auth.get("courrier", {})
        if outil["serveur"] in courrier.get("serveurs", []) and outil["outil"] == "move_emails":
            tri = courrier.get("dossier_tri", "Tri Agent Local")
            source = str(arguments.get("source_mailbox") or "INBOX")
            if arguments.get("destination_mailbox") != tri or source.upper() != "INBOX":
                motif = tr("agent.un_mail_ne_peut_etre", tri=tri)
                infos["niveau"] = "interdit"
                await self.signaler({"type": "appel_outil", **infos})
                await self.signaler({"type": "resultat_outil", "id": appel["id"], "serveur": outil["serveur"],
                                     "outil": outil["outil"], "duree": 0, "resultat": tr("commun.refus_deux_points") + motif})
                return tr("commun.refus_deux_points") + motif
        # Garde-fou 9 (16/11/2026) : un document Word ou Excel ne s'ecrit jamais avec les outils texte
        # de l'outil fichiers (texte brut dans un .docx = fichier abime, vu en relecture le 16/11) : outil bureautique.
        if outil["serveur"] == "fichiers" and outil["outil"] in ("write_file", "edit_file"):
            bureau = [c for c in filet.chemins(arguments) if c.lower().endswith((".docx", ".xlsx", ".doc", ".xls"))]
            if bureau:
                motif = (tr("agent.est_un_document_word_ou", v1=bureau[0], v2=outil['outil']))
                infos["niveau"] = "interdit"
                await self.signaler({"type": "appel_outil", **infos})
                await self.signaler({"type": "resultat_outil", "id": appel["id"], "serveur": outil["serveur"],
                                     "outil": outil["outil"], "duree": 0, "resultat": tr("commun.refus_deux_points") + motif})
                return tr("commun.refus_deux_points") + motif
        # Garde-fou 6 : PowerShell (11/11/2026). Une commande est un texte libre : on refuse toute
        # commande qui cite une zone interdite, sous quelque ecriture que ce soit (filet.zone_citee). Depuis le
        # 20/11/2026 (renforcement des garde-fous), le PowerShell de Windows-MCP passe par le meme tri que le terminal :
        # lecture libre, tout le reste sur accord.
        if outil["serveur"] == "terminal" or cle == "windows__PowerShell":
            commande = arguments.get("command" if cle == "windows__PowerShell" else "commande")
            zone = filet.zone_citee(commande, self.auth.get("zones_interdites", []))
            if zone:
                motif = tr("agent.cette_commande_vise_une_zone", v1=os.path.basename(zone.rstrip(chr(92))))
                infos["niveau"] = "interdit"
                await self.signaler({"type": "appel_outil", **infos})
                await self.signaler({"type": "resultat_outil", "id": appel["id"], "serveur": outil["serveur"],
                                     "outil": outil["outil"], "duree": 0, "resultat": tr("commun.refus_deux_points") + motif})
                return tr("agent.refus_n_y_touche_pas", motif=motif)
            if _powershell_lecture(commande):
                infos["niveau"] = "auto"   # lecture seule : passe sans l'accord de l'utilisateur (decision du 11/11/2026)
            elif cle == "windows__PowerShell":
                infos["niveau"] = "demander"
        # Garde-fou 7 (decision du 11/11/2026 : acces a tout l'ordinateur) : une action qui MODIFIE quelque chose
        # en dehors des dossiers personnels (Windows, Program Files, autre disque...) demande toujours l'accord de l'utilisateur.
        personnels = self.auth.get("dossiers_personnels", [])
        if personnels and not lecture and infos["niveau"] == "auto" \
                and outil["serveur"] not in ("navigateur", "terminal", "windows"):   # windows : pleins pouvoirs (12/11)
            dehors = [c for c in filet.chemins(arguments) if not _dans_zone(c, personnels)]
            if dehors:
                infos["niveau"] = "demander"
                infos["motif"] = tr("agent.modification_en_dehors_de_tes", v1=dehors[0])
        # Garde-fou 2 : ecraser un fichier existant redemande l'accord de l'utilisateur
        if cle in self.auth.get("demander_si_le_fichier_existe", []) and \
                any(os.path.exists(c) for c in filet.chemins(arguments)):
            infos["niveau"] = "demander"
            infos["motif"] = tr("agent.ce_fichier_existe_deja_et")
        # Garde-fou 8 : le filet de securite (12/11/2026). Un fichier de plus de 50 Mo n'est pas
        # copie avant modification : l'action demande donc l'accord de l'utilisateur, puisqu'elle ne pourra pas etre annulee.
        sauvegarder = not lecture and outil["serveur"] != "navigateur"
        if sauvegarder:   # pour verifier un fichier annonce en fin de mission (VERIFICATION_FICHIER)
            self._fichiers_ecrits.update(filet.chemins(arguments))
        if sauvegarder and infos["niveau"] == "auto":
            gros = filet.trop_gros(arguments)
            if gros:
                infos["niveau"] = "demander"
                infos["motif"] = tr("agent.fichier_de_plus_de_50", v1=gros[0])
        # Garde-fou 4 : le navigateur (validation de formulaires, mots de passe, adresses locales...)
        if outil["serveur"] == "navigateur":
            niveau, motif = garde_navigateur.decider(outil["outil"], arguments, self._instantane)
            if niveau != "auto":
                infos["niveau"], infos["motif"] = niveau, motif
            if niveau == "interdit":
                await self.signaler({"type": "appel_outil", **infos})
                await self.signaler({"type": "resultat_outil", "id": appel["id"], "serveur": outil["serveur"],
                                     "outil": outil["outil"], "duree": 0, "resultat": tr("commun.refus_deux_points") + motif})
                return tr("commun.refus_deux_points") + motif
        # Garde-fou 11 (version publique) : pendant une tache planifiee, personne ne surveille ; aux niveaux Prudent et
        # Equilibre, seules les lectures s'executent (les demandes d'accord sont deja refusees d'office par app.py).
        if self.tache_planifiee and not lecture and self.auth.get("taches_planifiees_lecture_seule"):
            infos["niveau"] = "interdit"
            infos["motif"] = tr("agent.tache_planifiee_seules_les_lectures")
        await self.signaler({"type": "appel_outil", **infos})
        if infos["niveau"] == "interdit":
            return tr("commun.refus_deux_points") + infos.get("motif", tr("agent.outil_interdit_configuration"))
        if infos["niveau"] == "demander":
            accorde = await self.demander(infos)
            await self.signaler({"type": "autorisation", "id": appel["id"], "accordee": accorde})
            if not accorde:
                return tr("agent.refus_l_utilisateur_n_a")
        debut = time.monotonic()
        if sauvegarder:
            try:
                filet.copier_avant(appel["id"], cle, arguments)
            except Exception as e:   # une copie ratee ne doit pas passer inapercue
                return tr("agent.refus_la_copie_de_securite", e=e)
        try:
            if corbeille:   # garde-fou 10 : une suppression par Windows-MCP part a la Corbeille (recuperable)
                resultat = await self.pupitre.appeler("terminal__mettre_a_la_corbeille", {"chemin": arguments.get("path")})
            else:
                resultat = await self.pupitre.appeler(cle, arguments)
        except Exception as e:
            resultat = tr("agent.outil_a_echoue", e=e)
        if outil["serveur"] == "navigateur" and "[ref=" in resultat:
            self._instantane = resultat   # derniere capture de la page, lue par le garde-fou du navigateur
        # Garde-fou 3 : journal de tout ce qui modifie, pour pouvoir retracer ou defaire
        if not lecture:
            trace = arguments
            if outil["serveur"] == "navigateur":   # ce qui est tape dans les pages n'est pas recopie dans le journal
                trace = {k: v for k, v in arguments.items() if k not in ("text", "value", "fields", "promptText")}
                if "fields" in arguments:
                    trace["champs"] = [c.get("name", "?") for c in arguments.get("fields") or []]
            with open(JOURNAL, "a", encoding="utf-8") as j:
                j.write(json.dumps({"quand": datetime.now().isoformat(timespec="seconds"),
                                    "outil": cle, "arguments": trace,
                                    "resultat": resultat[:300]}, ensure_ascii=False) + "\n")
        await self.signaler({"type": "resultat_outil", "id": appel["id"], "serveur": outil["serveur"],
                             "outil": outil["outil"], "resultat": resultat[:4000],
                             "duree": round(time.monotonic() - debut, 2)})
        return resultat
