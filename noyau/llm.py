"""Client du modele local (llama-server) en flux continu, avec reflexion amorcee en francais.

Le noyau prepare lui-meme le texte de la conversation (gabarit du modele via /apply-template),
ouvre la reflexion avec quelques mots en francais (sinon ce modele pense en anglais),
puis relit en direct la sortie brute de /completion :
  <reflexion> </think> <reponse> <tool_call><function=nom><parameter=cle>valeur</parameter>...</function></tool_call>

Evenements emis (interface inchangee pour le reste du noyau) :
  ("memoire", {jetons, limite})       -> remplissage de la memoire du modele (jauge de la fenetre)
  ("reflexion", texte)                -> morceau de la pensee du modele
  ("texte", texte)                    -> morceau de la reponse
  ("appel_partiel", {nom, arguments}) -> appel d'outil en cours de redaction (pour l'affichage en direct)
  ("fin", message)                    -> message complet {content, reasoning, tool_calls}
"""
import json
import re
import time
import uuid

import httpx

import vision
import reglages
from langue import t as tr

# L'amorce s'arrete au milieu d'une phrase francaise : le modele doit la continuer en francais.
# (mesure du 08/11/2026 : amorce terminee par un point ~ melange anglais/chinois ; phrase ouverte = 98 % de francais)
AMORCE_DEMANDE = tr("llm.amorce_demande")
# Entre deux outils, une reflexion COURTE suffit (decision du 12/11/2026, pour la vitesse) : la reflexion
# complete reste au debut de la demande (comprendre, planifier) et sur une image.
AMORCE_APRES_OUTIL = tr("llm.amorce_apres_outil")
AMORCE_IMAGE = tr("llm.amorce_image")
# Pendant la reflexion seulement, les mots anglais les plus courants sont penalises : le modele derivait vers
# l'anglais au fil des longues reflexions. La reponse et les appels d'outils (code compris) ne sont pas penalises.
_MOTS_ANGLAIS = ["the", "The", "we", "We", "need", "user", "User", "let", "Let", "so", "So", "is", "to", "and", "should",
                 "I", "will", "this", "This", "that", "with", "First", "Now", "Okay", "Wait", "then", "Then", "But", "but",
                 "it", "It", "of", "for", "can", "have", "file", "files", "Next", "Actually", "maybe", "Maybe", "also"]
PENALITE_ANGLAIS = [[" " + m, -6] for m in _MOTS_ANGLAIS] + [[m, -6] for m in _MOTS_ANGLAIS if m[0].isupper()]
FIN_PENSEE, DEBUT_OUTIL = "</think>", "<tool_call>"
BUDGET_APRES_OUTIL = 400   # jetons de reflexion entre deux outils (~12 s)
BUDGET_REFLEXION = 2500    # jetons de reflexion au debut d'une demande ou devant une image
CLOTURE_REFLEXION = tr("llm.cloture_reflexion")
MARGE_REPONSE = 3072   # jetons a garder libres pour reflechir et repondre ; en dessous : "memoire pleine"
# Reperes des messages dans le gabarit de Qwen (16/11/2026, decision de l'utilisateur) : avec eux, llama-server pose un point de
# sauvegarde juste avant chaque message (dont le message de contexte de la fin) et, a l'etape suivante, ne relit que
# la nouveaute. Sans eux, il ne gardait que le debut fixe : toute la mission etait relue a chaque etape.
REPERES_MESSAGES = [{"role": "assistant", "delimiter": "<|im_start|>assistant"},
                    {"role": "tool", "delimiter": "<|im_start|>user\n<tool_response>"},
                    {"role": "user", "delimiter": "<|im_start|>user"},
                    {"role": "system", "delimiter": "<|im_start|>system"}]
# Champ propre a llama.cpp TurboQuant : le llama.cpp officiel calcule lui-meme ces reperes d'apres le gabarit du modele.
# Envoye seulement si config.json le demande (llm.reperes_messages = true, pour un serveur TurboQuant).
EXTRA_TURBOQUANT = ({"message_delimiters": REPERES_MESSAGES}
                    if reglages.brut().get("llm", {}).get("reperes_messages") is True else {})
RE_APPEL = re.compile(r"<tool_call>(.*?)(?:</tool_call>|$)", re.S)
RE_FONCTION = re.compile(r"<function=([^>\s]+)>")
RE_PARAMETRE = re.compile(r"<parameter=([^>\s]+)>\n?(.*?)(?:\n?</parameter>|$)", re.S)


def _base(url):
    return url.split("/v1/")[0].rstrip("/")


def _types(outils):
    """nom d'outil -> {parametre: type JSON attendu}"""
    return {o["function"]["name"]: {k: (v or {}).get("type", "string")
                                    for k, v in (o["function"].get("parameters") or {}).get("properties", {}).items()}
            for o in outils or []}


def _valeur(brut, type_attendu):
    if type_attendu in (None, "string"):
        return brut
    try:
        return json.loads(brut)
    except (json.JSONDecodeError, TypeError):
        return brut


def lire_appels(texte, types):
    """Relit les appels d'outils (complets ou encore en cours d'ecriture) : [(nom, {arguments})]"""
    appels = []
    for bloc in RE_APPEL.findall(texte):
        f = RE_FONCTION.search(bloc)
        if not f:
            continue
        nom = f.group(1)
        args = {k: _valeur(v, types.get(nom, {}).get(k)) for k, v in RE_PARAMETRE.findall(bloc[f.end():])}
        appels.append((nom, args))
    return appels


def _sur(texte, marqueur):
    """Partie du texte qu'on peut afficher sans risquer de couper un marqueur en train d'arriver."""
    for n in range(min(len(marqueur) - 1, len(texte)), 0, -1):
        if marqueur.startswith(texte[-n:]):
            return texte[:-n]
    return texte


def _avec_images(messages):
    """Les messages portant une cle "image" (outil regarder) deviennent texte + image pour le gabarit du modele ;
    les images, dans l'ordre, accompagnent ensuite le texte du prompt (multimodal_data)."""
    prets, images = [], []
    for m in messages:
        chemin = m.get("image")
        m = {k: v for k, v in m.items() if k not in ("image", "interne", "contexte")}   # marques internes d'agent.py
        if chemin:
            images.append(vision.encoder(chemin))
            m["content"] = [{"type": "text", "text": m.get("content") or ""},
                            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + images[-1]}}]
        prets.append(m)
    return prets, images


async def discuter(url, messages, outils, temperature=0.6):
    base = _base(url)
    types = _types(outils)
    async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=10)) as client:
        prets, images = _avec_images(messages)
        corps = {"messages": prets}
        if outils:
            corps["tools"] = outils
        r = await client.post(f"{base}/apply-template", json=corps)
        if r.status_code != 200:
            raise RuntimeError(tr("llm.le_modele_a_refuse_la", v1=r.status_code, v2=r.text[:400]))
        prompt = r.json()["prompt"]
        # Memoire pleine : au-dela de sa limite, le serveur ne repond plus du tout (la fenetre attendait 10 minutes
        # en silence). On mesure donc la taille AVANT d'envoyer, et on s'arrete avec un message clair.
        jetons = len((await client.post(f"{base}/tokenize", json={"content": prompt})).json().get("tokens", []))
        jetons += vision.JETONS_PAR_IMAGE * len(images)
        limite = (await client.get(f"{base}/props")).json().get("default_generation_settings", {}).get("n_ctx", 0)
        yield ("memoire", {"jetons": jetons, "limite": limite})   # la jauge de la fenetre
        if limite and jetons > limite - MARGE_REPONSE:
            raise RuntimeError(tr("llm.memoire_pleine_la_conversation_occupe", jetons=jetons, limite=limite))
        place = (limite - jetons - 256) if limite else 8192   # ce que la reflexion et la reponse peuvent occuper
        # le message de contexte (heure, bloc-notes) et le rappel automatique du plan (agent.py) ne comptent pas pour
        # choisir l'amorce : apres un rappel, la reflexion reste celle d'apres un outil (courte)
        dernier_message = next((m for m in reversed(messages)
                                if not m.get("contexte") and m.get("interne") != "rappel"), {})
        amorce = (AMORCE_IMAGE if dernier_message.get("image") else
                  AMORCE_APRES_OUTIL if dernier_message.get("role") == "tool" else AMORCE_DEMANDE)
        prompt += ("" if prompt.rstrip().endswith("<think>") else "<think>\n") + amorce
        # Plafond de reflexion (12/11/2026) : la consigne « deux ou trois phrases » ne suffisait pas,
        # le modele hesitait des minutes entre deux outils. Au-dela du plafond, la reflexion est close d'office.
        budget = BUDGET_APRES_OUTIL if amorce == AMORCE_APRES_OUTIL else BUDGET_REFLEXION
        yield ("reflexion", amorce)

        def avec_images(texte):   # le texte du prompt, accompagne des images qu'il designe
            return {"prompt_string": texte, "multimodal_data": images} if images else texte

        sortie, montre_pensee, montre_texte, dernier_partiel = "", 0, 0, 0.0
        # Temps 1 : la reflexion, avec les mots anglais courants penalises (elle s'arrete a </think>).
        # Temps 2 : la reponse et les appels d'outils, SANS penalite (le code des programmes reste intact).
        demande = {"prompt": avec_images(prompt), "stream": True, "temperature": temperature, "n_predict": min(budget, place),
                   "cache_prompt": True, **EXTRA_TURBOQUANT, "stop": [FIN_PENSEE, "<|im_end|>"],
                   "logit_bias": PENALITE_ANGLAIS}
        for temps in (1, 2):
            dernier = {}
            async with client.stream("POST", f"{base}/completion", json=demande) as rep:
                if rep.status_code != 200:
                    raise RuntimeError(tr("llm.le_modele_a_refuse_la_2", v1=rep.status_code, v2=(await rep.aread()).decode('utf-8', 'replace')[:400]))
                async for ligne in rep.aiter_lines():
                    if not ligne.startswith("data:"):
                        continue
                    donnee = json.loads(ligne[5:].strip())
                    sortie += donnee.get("content", "")
                    pensee, a_fini_de_penser, apres = sortie.partition(FIN_PENSEE)
                    if not a_fini_de_penser:
                        visible = _sur(pensee, FIN_PENSEE)
                        if len(visible) > montre_pensee:
                            yield ("reflexion", visible[montre_pensee:])
                            montre_pensee = len(visible)
                    else:
                        if len(pensee) > montre_pensee:
                            yield ("reflexion", pensee[montre_pensee:])
                            montre_pensee = len(pensee)
                        texte, a_un_outil, outils_txt = apres.partition(DEBUT_OUTIL)
                        visible = texte if a_un_outil else _sur(texte, DEBUT_OUTIL)
                        if len(visible) > montre_texte:
                            yield ("texte", visible[montre_texte:])
                            montre_texte = len(visible)
                        if a_un_outil and time.monotonic() - dernier_partiel > 0.15:
                            dernier_partiel = time.monotonic()
                            en_cours = lire_appels(DEBUT_OUTIL + outils_txt, types)
                            if en_cours:
                                nom, args = en_cours[-1]
                                yield ("appel_partiel", {"nom": nom, "arguments": json.dumps(args, ensure_ascii=False)})
                    if donnee.get("stop"):
                        dernier = donnee
                        break
            if temps == 1:
                coupe = dernier.get("stopping_word") != FIN_PENSEE and dernier.get("tokens_predicted", 0) >= budget - 1
                if coupe:   # plafond atteint : on referme la reflexion et le modele passe a l'action
                    yield ("reflexion", CLOTURE_REFLEXION)
                    sortie += CLOTURE_REFLEXION
                elif dernier.get("stopping_word") != FIN_PENSEE:   # pas de fin de reflexion : rien a relancer
                    break
                sortie += FIN_PENSEE
                demande = {"prompt": avec_images(prompt + sortie), "stream": True, "temperature": temperature,
                           "n_predict": max(256, min(8192, place - dernier.get("tokens_predicted", 0))),
                           "cache_prompt": True, **EXTRA_TURBOQUANT, "stop": ["<|im_end|>"]}

    pensee, a_fini_de_penser, apres = sortie.partition(FIN_PENSEE)
    if not a_fini_de_penser:   # le modele n'a jamais referme sa reflexion : on la considere comme la reponse
        pensee, apres = "", pensee
    texte, _, outils_txt = apres.partition(DEBUT_OUTIL)
    tool_calls = [{"id": f"appel_{uuid.uuid4().hex[:12]}", "type": "function",
                   "function": {"name": nom, "arguments": json.dumps(args, ensure_ascii=False)}}
                  for nom, args in lire_appels(DEBUT_OUTIL + outils_txt, types)] if outils_txt else []
    yield ("fin", {"content": texte.strip(), "reasoning": amorce + pensee, "tool_calls": tool_calls})
