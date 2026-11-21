// Assistant de premier lancement (5 ecrans) et page Reglages. Tout passe par api().assistant(fonction, arguments)
// (liste fermee cote noyau, noyau/assistant.py). Aucun texte ici : tout vient des fichiers de langue (T).
const A = (fonction, ...args) => window.pywebview.api.assistant(fonction, args);
const echappe = (s) => { const d = document.createElement('div'); d.textContent = String(s ?? ''); return d.innerHTML; };
const ETAPES = ['vous', 'modele', 'autonomie', 'modules', 'admin'];
const RUBRIQUES = ['vous', 'modele', 'autonomie', 'modules', 'admin', 'cles', 'donnees', 'avance'];
let REG = null, DETECT = null, mode = 'assistant', courant = 'vous', suivi = null, modifs = {}, sourceChoisie = null;

function noter(rubrique, cle, valeur) { (modifs[rubrique] ||= {})[cle] = valeur; }
function valeurConf(rubrique, cle, defaut = '') {
  return modifs[rubrique]?.[cle] ?? REG.config[rubrique]?.[cle] ?? defaut;
}
function go(octets) { return (octets / 1073741824).toFixed(1).replace('.', T('as.separateur_decimal')); }

// ---------- squelette commun ----------
function voile() {
  let v = document.getElementById('as-voile');
  if (!v) {
    v = document.createElement('div');
    v.id = 'as-voile';
    v.className = 'as-voile';
    document.body.appendChild(v);
  }
  return v;
}

async function ouvrirAssistant() {
  mode = 'assistant';
  REG = await A('reglages_lire');
  courant = 'vous';
  dessiner();
}

async function ouvrirReglages(rubrique = 'vous') {
  mode = 'reglages';
  REG = await A('reglages_lire');
  courant = rubrique;
  dessiner();
}

function fermer() { voile().hidden = true; clearInterval(suivi); suivi = null; }

function dessiner() {
  const v = voile();
  v.hidden = false;
  modifs = {};
  const contenu = SECTIONS[courant]();
  if (mode === 'assistant') {
    const i = ETAPES.indexOf(courant);
    v.innerHTML = `<div class="as-fenetre" role="dialog" aria-modal="true">
      <div class="as-barre"><span class="as-nom">${T('as.titre_' + courant)}</span>
        <div class="as-etapes">${ETAPES.map((e, k) => `<span class="${k < i ? 'fait' : k === i ? 'ici' : ''}">${k + 1} ${T('as.onglet_' + e)}${k < i ? ' ✓' : ''}</span>`).join('')}</div></div>
      <div class="as-corps">${contenu}</div>
      <div class="as-pied">
        <button class="as-btn discret" id="as-retour" ${i === 0 ? 'hidden' : ''}>${T('as.retour')}</button>
        ${courant === 'admin' ? `<button class="as-btn" id="as-passer">${T('as.passer')}</button>` : '<span></span>'}
        <button class="as-btn principal" id="as-suivant">${i === ETAPES.length - 1 ? T('as.terminer') : T('as.suivant_' + ETAPES[i + 1])}</button>
      </div></div>`;
    v.querySelector('#as-retour').onclick = async () => { await enregistrer(); courant = ETAPES[i - 1]; dessiner(); };
    v.querySelector('#as-suivant').onclick = async (e) => {
      try {
        if (!(await enregistrer())) return;
        if (i === ETAPES.length - 1) { await A('terminer_assistant'); return; }
        courant = ETAPES[i + 1]; dessiner();
      } catch (erreur) {   // ne jamais laisser l'utilisateur bloque sans explication
        e.target.insertAdjacentText('beforebegin', `${T('as.erreur_enregistrement')} ${erreur?.message || erreur} `);
      }
    };
    const passer = v.querySelector('#as-passer');
    if (passer) passer.onclick = async () => { await enregistrer(); await A('terminer_assistant'); };
  } else {
    v.innerHTML = `<div class="as-fenetre" role="dialog" aria-modal="true" style="height:min(760px,100%)">
      <div class="as-barre"><span class="as-nom">${T('as.reglages')}</span>
        <button class="as-btn petit discret" id="as-fermer">✕ ${T('as.fermer')}</button></div>
      <div class="as-reglages">
        <aside>${RUBRIQUES.map((r) => `<button data-rubrique="${r}" class="${r === courant ? 'ici' : ''}">${T('as.rubrique_' + r)}</button>`).join('')}</aside>
        <div class="as-corps">${contenu}
          <div id="as-redemarrer"></div>
          ${['cles', 'donnees', 'avance'].includes(courant) ? '' : `<div class="as-ligne" style="justify-content:flex-end">
            <button class="as-btn principal" id="as-enregistrer">${T('as.enregistrer')}</button></div>`}
        </div></div></div>`;
    v.querySelector('#as-fermer').onclick = fermer;
    v.querySelectorAll('[data-rubrique]').forEach((b) => b.onclick = () => { courant = b.dataset.rubrique; dessiner(); });
    const bouton = v.querySelector('#as-enregistrer');
    if (bouton) bouton.onclick = async () => {
      const r = await enregistrer();
      if (r && r.redemarrer) {
        v.querySelector('#as-redemarrer').innerHTML = `<div class="as-alerte info as-ligne">${T('as.redemarrage_necessaire')}
          <button class="as-btn petit principal" id="as-relancer">${T('as.redemarrer_maintenant')}</button></div>`;
        v.querySelector('#as-relancer').onclick = () => A('relancer');
      } else if (r) {
        v.querySelector('#as-redemarrer').innerHTML = `<div class="as-alerte vert">${T('as.enregistre')}</div>`;
      }
    };
  }
  (LIENS[courant] || (() => {}))(v);
  suivreProgression();
}

async function enregistrer() {
  if (!Object.keys(modifs).length) return { ok: true, redemarrer: false };
  const r = await A('reglages_enregistrer', modifs);
  REG = await A('reglages_lire');
  modifs = {};
  return r;
}

// ---------- progression des telechargements et installations ----------
function suivreProgression() {
  clearInterval(suivi);
  suivi = setInterval(async () => {
    const zones = document.querySelectorAll('[data-travail]');
    if (!zones.length) return;
    const travaux = await A('progression');
    zones.forEach((z) => {
      const t = travaux[z.dataset.travail];
      if (!t) return;
      const barre = z.querySelector('.as-progression i'), texte = z.querySelector('.as-etat');
      if (barre && t.total) barre.style.width = `${Math.min(100, (100 * t.fait) / t.total)}%`;
      if (barre && t.etat === 'termine') barre.style.width = '100%';
      if (texte) {
        const chiffres = t.total && t.etat === 'en cours' ? ` · ${go(t.fait)} / ${go(t.total)} ${T('as.unite_go')}` : '';
        texte.textContent = (t.etat === 'erreur' ? '✕ ' : t.etat === 'termine' ? '✓ ' : '') + t.message + chiffres;
        texte.className = `as-etat as-mono ${t.etat === 'erreur' ? 'p-licence' : t.etat === 'termine' ? 'p-local' : 'as-gris'}`;
      }
    });
  }, 1000);
}
const zoneTravail = (id) => `<div data-travail="${id}" style="display:grid;gap:6px"><div class="as-progression"><i></i></div>
  <span class="as-etat as-mono as-gris"></span></div>`;

// ---------- un composant externe : licence en clair, case J'accepte, bouton Installer ----------
function composant(id, options = {}) {
  const c = REG.composants[id];
  return `<div class="as-licence" data-composant="${id}">
    <div class="as-ligne"><b>${echappe(c.nom)}</b><span class="as-pastille p-licence">${echappe(c.licence)}</span>
      <span class="as-mono as-gris">${c.taille_go ? `≈ ${String(c.taille_go).replace('.', T('as.separateur_decimal'))} ${T('as.unite_go')}` : ''}</span></div>
    <span class="as-gris">${echappe(c.texte)}</span>
    ${c.lien ? `<span class="as-mono as-gris">${T('as.licence_complete')} ${echappe(c.lien)}</span>` : ''}
    <label><input type="checkbox" data-accepte="${id}"> ${echappe(c.case || T('as.j_accepte'))}</label>
    <div class="as-ligne"><button class="as-btn ${c.admin ? 'bouclier' : ''}" data-installer="${id}" disabled>
      ${c.admin ? '🛡 ' + T('as.installer_admin') : T('as.installer')}</button></div>
    ${zoneTravail(id)}</div>`;
}
function lierComposants(racine, optionsPar = {}) {
  racine.querySelectorAll('[data-accepte]').forEach((caseAccepte) => {
    const bouton = racine.querySelector(`[data-installer="${caseAccepte.dataset.accepte}"]`);
    caseAccepte.onchange = () => { bouton.disabled = !caseAccepte.checked; };
    bouton.onclick = async () => {
      const id = bouton.dataset.installer;
      bouton.disabled = true;
      const r = await A('installer_composant', id, caseAccepte.checked, (optionsPar[id] || (() => ({})))());
      const etat = racine.querySelector(`[data-travail="${id}"] .as-etat`);
      if (r && r.message && etat) etat.textContent = r.message;
      if (r && r.ok === false) bouton.disabled = false;
    };
  });
}

// ---------- confirmation integree a la page (pas de confirm()) ----------
function confirmer(bouton, texte, action) {
  const zone = document.createElement('span');
  zone.className = 'as-confirmer';
  zone.innerHTML = `<span class="as-alerte rouge">${texte}</span>
    <button class="as-btn petit danger">${T('as.oui_confirmer')}</button><button class="as-btn petit discret">${T('as.annuler')}</button>`;
  bouton.replaceWith(zone);
  const [oui, non] = zone.querySelectorAll('button');
  non.onclick = () => zone.replaceWith(bouton);
  oui.onclick = async () => { oui.disabled = true; await action(); dessiner(); };
}

// ---------- les rubriques ----------
const SECTIONS = {
  vous: () => `<h2>${T('as.vous_titre')}</h2><p class="as-sous">${T('as.vous_sous')}</p>
    <label class="as-champ" for="as-langue">${T('as.langue')}
      <select id="as-langue">${Object.entries(REG.langues).map(([c, n]) => `<option value="${c}" ${c === REG.langue ? 'selected' : ''}>${echappe(n)}</option>`).join('')}</select>
      <small>${T('as.langue_aide')}</small></label>
    <label class="as-champ" for="as-prenom">${T('as.prenom')}
      <input type="text" id="as-prenom" value="${echappe(valeurConf('utilisateur', 'prenom'))}">
      <small>${T('as.prenom_aide')}</small></label>
    <label class="as-champ" for="as-sortie">${T('as.sortie')}
      <span class="as-saisie"><input type="text" id="as-sortie" value="${echappe(valeurConf('utilisateur', 'dossier_sortie'))}">
      <button class="as-btn" id="as-parcourir">${T('as.parcourir')}</button></span>
      <small>${T('as.sortie_aide')}</small></label>
    <div class="as-alerte info">${T('as.zone_installation')}</div>`,

  modele: () => {
    if (!DETECT) return `<p class="as-gris">${T('as.detection_en_cours')}</p>`;
    const p = DETECT.palier, pr = DETECT.principale;
    const source = valeurConf('lanceur', 'modele') && !p ? 'gguf' : (sourceChoisie || 'conseille');
    const cartes = DETECT.cartes.map((c) => `<option value="${c.index}" ${String(valeurConf('lanceur', 'carte_principale', '') === '' ? (pr?.index ?? 0) : valeurConf('lanceur', 'carte_principale')) === String(c.index) ? 'selected' : ''}>
      ${echappe(c.nom)} — ${String(c.memoire_go).replace('.', T('as.separateur_decimal'))} ${T('as.unite_go')}</option>`).join('');
    return `<h2>${T('as.modele_titre')}</h2><p class="as-sous">${T('as.modele_sous')}</p>
      ${pr ? `<div class="as-detection"><div class="chiffre">${String(pr.memoire_go).replace('.', T('as.separateur_decimal'))} ${T('as.unite_go')}</div>
        <div>${DETECT.cartes.map((c) => `<b>${echappe(c.nom)}</b> · ${String(c.memoire_go).replace('.', T('as.separateur_decimal'))} ${T('as.unite_go')}
          <span class="as-mono as-gris">(${T('as.libres', { v1: String(c.libre_go).replace('.', T('as.separateur_decimal')) })} · ${T('as.pilote')} ${echappe(c.pilote)})</span>`).join('<br>')}
          <br><span class="as-mono as-gris">${T('as.ram_disque', { v1: DETECT.ram_go, v2: DETECT.disque_libre_go })}</span></div></div>` : ''}
      ${DETECT.refus ? `<div class="as-alerte rouge">${echappe(DETECT.refus)}</div>` : ''}
      <div class="as-table-zone"><table class="as-paliers">
        <tr><th>${T('as.col_carte')}</th><th>${T('as.col_modele')}</th><th>${T('as.col_fichiers')}</th><th>${T('as.col_contexte')}</th><th>${T('as.col_verdict')}</th></tr>
        ${DETECT.paliers.map((x) => `<tr class="${p && x.id === p.id ? 'ici' : ''}"><td>${T('as.palier_' + x.id)}</td><td>${echappe(x.nom)}</td>
          <td class="as-mono">${String(x.taille_go).replace('.', T('as.separateur_decimal'))} + ${String(x.mmproj_go).replace('.', T('as.separateur_decimal'))} ${T('as.unite_go')}</td>
          <td class="as-mono">${x.contexte.toLocaleString(LANGUE)}</td><td><span class="as-pastille ${{ complet: 'p-local', utilisable: 'p-reco', limite: 'p-envoi' }[x.verdict] || 'p-licence'}">${T('as.verdict_' + x.verdict)}</span></td></tr>`).join('')}
        <tr><td>${T('as.palier_sans')}</td><td colspan="3">${T('as.sans_nvidia')}</td><td><span class="as-pastille p-licence">${T('as.verdict_non_pris_en_charge')}</span></td></tr>
      </table></div>
      <p class="as-mono as-gris" style="margin:0">${T('as.mesure_estime')}</p>
      <label class="as-champ" for="as-source">${T('as.source')}
        <select id="as-source"><option value="conseille" ${source === 'conseille' ? 'selected' : ''} ${p ? '' : 'disabled'}>${T('as.source_conseille')}</option>
          <option value="gguf" ${source === 'gguf' ? 'selected' : ''}>${T('as.source_gguf')}</option></select></label>
      <div id="as-zone-source"></div>
      <div class="as-grille">
        <label class="as-champ" for="as-carte">${T('as.carte_modele')}<select id="as-carte" ${cartes ? '' : 'disabled'}>${cartes}</select></label>
        <label class="as-champ" for="as-contexte">${T('as.contexte')}<select id="as-contexte">${DETECT.contextes.map((c) =>
          `<option value="${c}" ${Number(valeurConf('lanceur', 'contexte', 65536)) === c ? 'selected' : ''}>${T('as.contexte_option', { v1: c.toLocaleString(LANGUE) })}${c === 65536 ? ' — ' + T('as.conseille') : ''}${c === 262144 ? ' — ' + T('as.plusieurs_cartes') : ''}</option>`).join('')}</select></label>
      </div>
      <div class="as-carte"><h3>${T('as.moteur')} <span class="as-pastille p-local">${T('as.local')}</span></h3>
        <p>${T('as.moteur_aide')}</p>
        <div class="as-ligne">${DETECT.moteur_present ? `<span class="as-mono p-local">✓ ${T('as.moteur_deja_installe')}</span>` : ''}<button class="as-btn ${DETECT.moteur_present ? 'discret petit' : ''}" id="as-moteur">${DETECT.moteur_present ? T('as.reinstaller') : T('as.installer_moteur')}</button><span class="as-mono as-gris" id="as-pilote"></span></div>
        ${zoneTravail('moteur')}</div>
      ${mode === 'reglages' ? `<div class="as-carte"><h3>${T('as.tester_modele')}</h3><p>${T('as.tester_modele_aide')}</p>
        <div class="as-ligne"><button class="as-btn" id="as-tester-modele">${T('as.tester')}</button></div><div id="as-test-modele" class="as-mono"></div></div>
        <details class="as-avances"><summary>${T('as.options_expertes')}</summary><div style="display:grid;gap:10px;padding-top:10px">
          <label class="as-champ" for="as-exe">${T('as.programme_llama')}<input type="text" id="as-exe" value="${echappe(valeurConf('lanceur', 'llama_server'))}"></label>
          <label class="as-champ" for="as-port">${T('as.port')}<input type="text" id="as-port" value="${echappe(valeurConf('lanceur', 'port', 8090))}"></label>
          <label class="as-champ" for="as-repartition">${T('as.repartition')}<input type="text" id="as-repartition" value="${echappe(valeurConf('lanceur', 'cartes'))}"><small>${T('as.repartition_aide')}</small></label>
          <label class="as-champ" for="as-options">${T('as.options_supplementaires')}<input type="text" id="as-options" value="${echappe((valeurConf('lanceur', 'options_supplementaires', []) || []).join(' '))}"><small>${T('as.options_aide')}</small></label>
        </div></details>` : ''}`;
  },

  autonomie: () => `<h2>${T('as.autonomie_titre')}</h2><p class="as-sous">${T('as.autonomie_sous')}</p>
    <div style="display:grid;gap:12px">${REG.niveaux.map((n) => `<label class="as-carte as-choix ${valeurConf('autorisations', 'mode', 'prudent') === n ? 'choisie' : ''}">
      <input type="radio" name="as-niveau" value="${n}" ${valeurConf('autorisations', 'mode', 'prudent') === n ? 'checked' : ''}>
      <div><h3>${T('as.niveau_' + n)} ${n === 'prudent' ? `<span class="as-pastille p-reco">${T('as.par_defaut')}</span>` : ''}${n === 'autonome' ? `<span class="as-pastille p-envoi">${T('as.experimente')}</span>` : ''}</h3>
      <p>${T('as.niveau_' + n + '_texte')}</p></div></label>`).join('')}</div>
    <div class="as-alerte info">${T('as.toujours_actifs')}</div>`,

  modules: () => {
    const m = (id) => valeurConf('modules', id, false);
    const ligne = (id, pastille, classe, detail = '', actions = '') => `<div class="as-module">
      <input type="checkbox" data-module="${id}" ${m(id) ? 'checked' : ''} aria-label="${T('as.module_' + id)}">
      <div><h4>${T('as.module_' + id)} ${pastille ? `<span class="as-pastille ${classe}">${pastille}</span>` : ''}</h4><p>${T('as.module_' + id + '_texte')}</p></div>
      <div class="actions">${actions}</div>${detail ? `<div class="detail">${detail}</div>` : ''}</div>`;
    return `<h2>${T('as.modules_titre')}</h2><p class="as-sous">${T('as.modules_sous')}</p><div>
      ${ligne('vision', T('as.local'), 'p-local')}
      ${ligne('voix', T('as.envoie_microsoft'), 'p-envoi', `<label class="as-champ" for="as-voix">${T('as.voix_choix')}<select id="as-voix"><option>${T('as.chargement')}</option></select></label>
        <div class="as-alerte">${T('as.voix_avertissement')}</div>
        <details class="as-avances"><summary>${T('as.voix_secours')}</summary>${composant('xtts')}</details>`,
        `<button class="as-btn petit" id="as-tester-voix">▶ ${T('as.tester')}</button>`)}
      ${ligne('dictee', T('as.local'), 'p-local', `<label class="as-champ" for="as-carte-dictee">${T('as.carte_dictee')}<select id="as-carte-dictee"></select></label>
        <div class="as-alerte info" id="as-dictee-choix"></div>${composant('dictee')}<div id="as-test-dictee" class="as-mono"></div>`,
        `<button class="as-btn petit" id="as-tester-dictee">🎙 ${T('as.tester')}</button>`)}
      ${ligne('recherche', T('as.moteur_local'), 'p-local', composant('docker'))}
      ${ligne('navigateur', T('as.profil_isole'), 'p-local')}
      ${ligne('windows', '', '', composant('windows_mcp'))}
      ${ligne('wikipedia', T('as.local'), 'p-local', composant('wikipedia'))}
      </div>
      <details class="as-avances"><summary>${T('as.modules_avances')}</summary><div style="padding-top:8px">
        ${ligne('cloud', T('as.envoie_donnees'), 'p-envoi', cle('openrouter.env', 'OPENROUTER_API_KEY'))}
        ${ligne('telegram', T('as.a_distance'), 'p-envoi', cle('telegram.env', 'TELEGRAM_BOT_TOKEN'))}
        ${ligne('messagerie', T('as.compte_mail'), 'p-envoi', T('as.messagerie_aide'))}
        ${ligne('hermes', '', '')}
        ${ligne('n8n', T('as.licence_non_libre'), 'p-licence', cle('n8n-cle-mcp.txt', ''))}
      </div></details>`;
  },

  admin: () => `<h2>${T('as.admin_titre')}</h2><p class="as-sous">${T('as.admin_sous')}</p>
    <div id="as-etat-admin"></div>
    <div class="as-grille">${composant('sante')}${composant('reparation')}</div>
    ${mode === 'reglages' ? `<div class="as-carte"><h3>${T('as.reparer_titre')}</h3><p>${T('as.reparer_aide')}</p>
      <div class="as-ligne"><button class="as-btn bouclier" id="as-reparer">🛡 ${T('as.reparer_bouton')}</button></div></div>` : ''}`,

  cles: () => `<h2>${T('as.rubrique_cles')}</h2><p class="as-sous">${T('as.cles_sous')}</p><div id="as-liste-cles" class="as-mono"></div>
    ${cle('openrouter.env', 'OPENROUTER_API_KEY')}${cle('telegram.env', 'TELEGRAM_BOT_TOKEN')}${cle('n8n-cle-mcp.txt', '')}`,

  donnees: () => `<h2>${T('as.rubrique_donnees')}</h2><p class="as-sous">${T('as.donnees_sous')}</p>
    <div class="as-carte"><h3>${T('as.carnet')}</h3><div id="as-souvenirs" class="as-gris">${T('as.chargement')}</div>
      <div class="as-ligne"><button class="as-btn danger" id="as-oublier-tout">${T('as.oublier_tout')}</button></div></div>
    <div class="as-carte"><h3>${T('as.historique')}</h3><p>${T('as.historique_aide')}</p>
      <div class="as-ligne"><button class="as-btn danger" id="as-vider-historique">${T('as.vider_historique')}</button></div></div>
    <div class="as-carte"><h3>${T('as.journal')}</h3><p>${T('as.journal_aide')}</p>
      <div class="as-ligne"><button class="as-btn danger" id="as-vider-journal">${T('as.vider_journal')}</button></div></div>`,

  avance: () => `<h2>${T('as.rubrique_avance')}</h2>
    <div class="as-carte"><h3>${T('as.mises_a_jour')}</h3><p>${T('as.mises_a_jour_aide', { v1: echappe(REG.version) })}</p>
      <div class="as-ligne"><button class="as-btn" id="as-verifier-maj">${T('as.verifier_maj')}</button></div><div id="as-maj"></div>${zoneTravail('mise_a_jour')}</div>
    <div class="as-carte"><h3>${T('as.desinstaller_titre')}</h3><p>${T('as.desinstaller_aide')}</p>
      <label class="as-choix"><input type="checkbox" id="as-suppr-modeles"> ${T('as.suppr_modeles')}</label>
      <label class="as-choix"><input type="checkbox" id="as-suppr-secrets"> ${T('as.suppr_secrets')}</label>
      <div class="as-ligne"><button class="as-btn danger" id="as-recap">${T('as.voir_recap')}</button></div><div id="as-zone-recap"></div></div>`,
};

function cle(fichier, variable) {
  return `<div class="as-champ">${T('as.cle_' + fichier.replace(/[^a-z]/g, '_'))}
    <span class="as-saisie"><input type="password" data-cle="${fichier}" data-variable="${variable}" autocomplete="off">
    <button class="as-btn petit" data-enregistrer-cle="${fichier}">${T('as.enregistrer_cle')}</button></span>
    <small>${T('as.cle_aide')}</small></div>`;
}

// ---------- comportements de chaque rubrique ----------
const LIENS = {
  vous: (v) => {
    v.querySelector('#as-prenom').oninput = (e) => noter('utilisateur', 'prenom', e.target.value);
    v.querySelector('#as-sortie').oninput = (e) => noter('utilisateur', 'dossier_sortie', e.target.value);
    v.querySelector('#as-parcourir').onclick = async () => {
      const d = await window.pywebview.api.choisir_dossier();
      if (d) { v.querySelector('#as-sortie').value = d; noter('utilisateur', 'dossier_sortie', d); }
    };
    v.querySelector('#as-langue').onchange = async (e) => {
      await A('reglages_enregistrer', { utilisateur: { langue: e.target.value } });
      Object.assign(TEXTES, await window.pywebview.api.textes(e.target.value));
      REG = await A('reglages_lire');
      traduirePage();
      dessiner();
    };
  },

  modele: async (v) => {
    if (!DETECT) { DETECT = await A('detecter'); dessiner(); return; }
    const p = DETECT.palier;
    const zone = v.querySelector('#as-zone-source');
    const dessinerSource = () => {
      const source = v.querySelector('#as-source').value;
      sourceChoisie = source;   // choix d'affichage, pas un reglage : jamais envoye au noyau
      zone.innerHTML = source === 'conseille' && p ? `<div class="as-carte choisie"><h3>${echappe(p.nom)} <span class="as-pastille p-reco">${T('as.recommande')}</span></h3>
          <p>${T('as.telecharger_aide', { v1: echappe(p.depot) })}</p>
          <label class="as-choix"><input type="checkbox" id="as-vision" ${valeurConf('modules', 'vision', true) ? 'checked' : ''}> ${T('as.avec_vision')}</label>
          <div class="as-ligne">${DETECT.modele_present && String(valeurConf('lanceur', 'modele')).endsWith(p.fichier)
            ? `<span class="as-mono p-local">✓ ${T('as.deja_telecharge')}</span>`
            : `<button class="as-btn principal" id="as-telecharger">${T('as.telecharger')}</button>`}</div>${zoneTravail('modele')}</div>`
        : `<label class="as-champ" for="as-gguf">${T('as.fichier_gguf')}<span class="as-saisie"><input type="text" id="as-gguf" value="${echappe(valeurConf('lanceur', 'modele'))}">
          <button class="as-btn" id="as-choisir-gguf">${T('as.parcourir')}</button></span></label>
          <label class="as-champ" for="as-mmproj">${T('as.fichier_mmproj')}<input type="text" id="as-mmproj" value="${echappe(valeurConf('lanceur', 'mmproj'))}"></label>`;
      const tel = zone.querySelector('#as-telecharger');
      if (tel) tel.onclick = async () => {
        tel.disabled = true;
        const vision = zone.querySelector('#as-vision').checked;
        noter('modules', 'vision', vision);
        await A('telecharger_modele', p.id, vision);
      };
      const gguf = zone.querySelector('#as-gguf');
      if (gguf) {
        gguf.oninput = (e) => noter('lanceur', 'modele', e.target.value);
        zone.querySelector('#as-mmproj').oninput = (e) => noter('lanceur', 'mmproj', e.target.value);
        zone.querySelector('#as-choisir-gguf').onclick = async () => {
          const f = await window.pywebview.api.choisir_fichier_gguf();
          if (f) { gguf.value = f; noter('lanceur', 'modele', f); }
        };
      }
    };
    v.querySelector('#as-source').onchange = dessinerSource;
    dessinerSource();
    const carte = v.querySelector('#as-carte');
    if (carte.value !== '' && valeurConf('lanceur', 'carte_principale', '') === '') noter('lanceur', 'carte_principale', carte.value);
    carte.onchange = (e) => noter('lanceur', 'carte_principale', e.target.value);
    v.querySelector('#as-contexte').onchange = (e) => noter('lanceur', 'contexte', Number(e.target.value));
    v.querySelector('#as-moteur').onclick = async (e) => {
      const r = await A('verifier_pilote');
      v.querySelector('#as-pilote').innerHTML = echappe(r.message) + (r.lien ? ` <span class="as-mono">${echappe(r.lien)}</span>` : '');
      if (!r.ok) return;
      e.target.disabled = true;
      await A('telecharger_moteur');
    };
    const test = v.querySelector('#as-tester-modele');
    if (test) test.onclick = async () => {
      const zoneTest = v.querySelector('#as-test-modele');
      zoneTest.textContent = T('as.test_en_cours');
      const r = await A('tester_modele');
      zoneTest.textContent = r.ok ? T('as.test_resultat', { v1: r.reponse, v2: String(r.vitesse).replace('.', T('as.separateur_decimal')), v3: r.duree }) : r.message;
    };
    [['#as-exe', 'llama_server'], ['#as-port', 'port'], ['#as-repartition', 'cartes']].forEach(([s, c]) => {
      const e = v.querySelector(s); if (e) e.oninput = () => noter('lanceur', c, c === 'port' ? Number(e.value) : e.value);
    });
    const opts = v.querySelector('#as-options');
    if (opts) opts.oninput = () => noter('lanceur', 'options_supplementaires', opts.value.split(/\s+/).filter(Boolean));
  },

  autonomie: (v) => v.querySelectorAll('[name="as-niveau"]').forEach((r) => r.onchange = () => {
    noter('autorisations', 'mode', r.value);
    v.querySelectorAll('.as-choix').forEach((c) => c.classList.toggle('choisie', c.contains(r)));
  }),

  modules: async (v) => {
    v.querySelectorAll('[data-module]').forEach((c) => c.onchange = () => noter('modules', c.dataset.module, c.checked));
    lierCles(v);
    if (!DETECT) DETECT = await A('detecter');
    // voix de la langue choisie
    const voix = await A('voix_disponibles', REG.langue);
    const choixVoix = v.querySelector('#as-voix');
    const actuelle = valeurConf('voix', 'nom');
    choixVoix.innerHTML = Object.entries(voix).map(([id, nom]) => `<option value="${id}" ${id === actuelle ? 'selected' : ''}>${echappe(nom)}</option>`).join('');
    noter('voix', 'nom', choixVoix.value);
    choixVoix.onchange = () => noter('voix', 'nom', choixVoix.value);
    v.querySelector('#as-tester-voix').onclick = async () => {
      const mp3 = await A('tester_voix', choixVoix.value, T('as.phrase_test_voix'));
      new Audio(`data:audio/mpeg;base64,${mp3}`).play();
    };
    // dictee : toutes les cartes, choix automatique du modele Whisper selon la memoire
    const carteDictee = v.querySelector('#as-carte-dictee');
    const choisie = valeurConf('lanceur', 'carte_principale', '');
    const principale = DETECT.cartes.find((c) => choisie !== '' && String(c.index) === String(choisie)) || DETECT.principale;
    let choix = principale && DETECT.palier ? await A('choisir_dictee', principale, DETECT.palier, DETECT.cartes)
      : { carte: 'cpu', modele: 'small', explication: T('as.dictee_processeur') };
    carteDictee.innerHTML = DETECT.cartes.map((c) => `<option value="${c.uuid}" ${c.uuid === choix.carte ? 'selected' : ''}>${echappe(c.nom)}</option>`).join('')
      + `<option value="cpu" ${choix.carte === 'cpu' ? 'selected' : ''}>${T('as.processeur')}</option>`;
    v.querySelector('#as-dictee-choix').textContent = choix.explication;
    carteDictee.onchange = () => { choix = { ...choix, carte: carteDictee.value, modele: carteDictee.value === 'cpu' ? 'small' : choix.modele }; noter('dictee', 'carte', choix.carte); noter('dictee', 'modele', choix.modele); };
    noter('dictee', 'carte', choix.carte); noter('dictee', 'modele', choix.modele);
    lierComposants(v, { dictee: () => ({ choix }) });
    v.querySelector('#as-tester-dictee').onclick = async () => {
      const z = v.querySelector('#as-test-dictee');
      z.textContent = T('as.parlez_maintenant');
      const r = await A('tester_dictee', 4);
      z.textContent = r.ok ? `✓ « ${r.texte} »` : `✕ ${r.texte}`;
    };
  },

  admin: async (v) => {
    lierComposants(v);
    const e = await A('etat_admin');
    v.querySelector('#as-etat-admin').innerHTML = `<div class="as-ligne as-mono">
      <span class="${e.sante ? 'p-local' : 'as-gris'}">${T('as.composant_sante')} : ${e.sante ? T('as.installe') : T('as.non_installe')}</span>
      <span class="${e.reparation ? 'p-local' : 'as-gris'}">${T('as.composant_reparation')} : ${e.reparation ? T('as.installe') : T('as.non_installe')}</span></div>
      ${e.dernier_refus_integrite ? `<div class="as-alerte rouge">${T('as.integrite_bloque', { v1: echappe(e.dernier_refus_integrite) })}</div>` : ''}`;
    const r = v.querySelector('#as-reparer');
    if (r) r.onclick = async () => { const res = await A('lancer_admin', 'installer_sante.ps1', true); r.insertAdjacentHTML('afterend', ` <span class="as-mono">${echappe(res.message)}</span>`); };
  },

  cles: async (v) => {
    lierCles(v);
    const liste = await A('cles_enregistrees');
    v.querySelector('#as-liste-cles').innerHTML = liste.length ? liste.map((c) => `✓ ${echappe(c.nom)} — ${T('as.enregistree_le', { v1: echappe(c.date) })}`).join('<br>') : T('as.aucune_cle');
  },

  donnees: async (v) => {
    const souvenirs = await A('donnees_souvenirs');
    const zone = v.querySelector('#as-souvenirs');
    zone.innerHTML = souvenirs.length ? souvenirs.map((s) => `<div class="as-souvenir"><span>[${s.id}] ${echappe(s.texte)}</span>
      <button class="as-btn petit danger" data-oublier="${s.id}">${T('as.effacer')}</button></div>`).join('') : T('as.carnet_vide');
    zone.querySelectorAll('[data-oublier]').forEach((b) => b.onclick = () => confirmer(b, T('as.confirmer_oublier'), () => A('donnees_oublier', b.dataset.oublier)));
    const lier = (id, texte, fn) => { const b = v.querySelector(id); b.onclick = () => confirmer(b, texte, () => A(fn)); };
    lier('#as-oublier-tout', T('as.confirmer_oublier_tout'), 'donnees_oublier_tout');
    lier('#as-vider-historique', T('as.confirmer_vider_historique'), 'donnees_vider_conversations');
    lier('#as-vider-journal', T('as.confirmer_vider_journal'), 'donnees_vider_journal');
  },

  avance: (v) => {
    v.querySelector('#as-verifier-maj').onclick = async () => {
      const r = await A('verifier_mises_a_jour'), zone = v.querySelector('#as-maj');
      if (!r.ok) { zone.innerHTML = `<div class="as-alerte">${echappe(r.message)}</div>`; return; }
      if (!r.nouvelle) { zone.innerHTML = `<div class="as-alerte vert">${T('as.a_jour', { v1: echappe(r.actuelle) })}</div>`; return; }
      zone.innerHTML = `<div class="as-alerte info">${T('as.nouvelle_version', { v1: echappe(r.disponible), v2: echappe(r.actuelle) })}</div>
        <div class="as-notes as-mono">${echappe(r.notes)}</div><p class="as-gris">${T('as.maj_garde')}</p>
        <div class="as-ligne"><button class="as-btn principal" id="as-installer-maj">${T('as.installer_maj')}</button></div>`;
      const b = zone.querySelector('#as-installer-maj');
      b.onclick = () => confirmer(b, T('as.confirmer_maj'), () => A('installer_mise_a_jour', r.archive));
    };
    v.querySelector('#as-recap').onclick = async () => {
      const m = v.querySelector('#as-suppr-modeles').checked, s = v.querySelector('#as-suppr-secrets').checked;
      const liste = await A('recapitulatif_desinstallation', m, s);
      const zone = v.querySelector('#as-zone-recap');
      zone.innerHTML = `<div class="as-alerte rouge">${T('as.recap_titre')}<ul>${liste.map((x) => `<li class="as-mono">${echappe(x)}</li>`).join('')}</ul>${T('as.recap_fin')}</div>
        <div class="as-ligne"><button class="as-btn danger" id="as-desinstaller">🛡 ${T('as.desinstaller_bouton')}</button></div>`;
      const b = zone.querySelector('#as-desinstaller');
      b.onclick = () => confirmer(b, T('as.confirmer_desinstaller'), () => A('desinstaller', m, s));
    };
  },
};

function lierCles(racine) {
  racine.querySelectorAll('[data-enregistrer-cle]').forEach((b) => b.onclick = async () => {
    const champ = racine.querySelector(`[data-cle="${b.dataset.enregistrerCle}"]`);
    if (!champ.value.trim()) return;
    const contenu = champ.dataset.variable ? `${champ.dataset.variable}=${champ.value.trim()}\n` : champ.value.trim();
    const r = await A('enregistrer_cle', b.dataset.enregistrerCle, contenu);
    champ.value = '';
    b.textContent = r.ok ? T('as.cle_enregistree') : T('as.erreur');
  });
}

// ---------- entree : bouton Reglages, et assistant au premier lancement ----------
window.addEventListener('pywebviewready', async () => {
  const bouton = document.createElement('button');
  bouton.id = 'bouton-reglages';
  bouton.className = 'as-btn petit';
  bouton.textContent = '⚙ ' + T('as.reglages');
  bouton.onclick = () => ouvrirReglages();
  (document.querySelector('.cyber-header-module') || document.body).appendChild(bouton);
  const r = await A('reglages_lire');
  if (!r.config.premier_lancement_fait) ouvrirAssistant();
});
