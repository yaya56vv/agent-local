// Agent Local v2 - branchement de l'interface sur le noyau (via pywebview).
// Remplace l'ancienne tuyauterie JS : memes elements, memes styles.

const $ = (id) => document.getElementById(id);
const api = () => window.pywebview.api;
let celluleEnCours = {}, taches = [], plan = null, tours = 0;
let debutMission = 0, chrono = null, filtre = 'all', autorisationEnCours = null;

// ---------- volets depliants (comme avant) ----------
document.querySelectorAll('.accordion-header').forEach((h) => {
  h.addEventListener('click', () => {
    const cible = $(h.dataset.target);
    if (!cible) return;
    cible.classList.toggle('open');
    h.classList.toggle('open');
  });
});

// ---------- flux reel : une colonne par agent (le chef), des lignes pensee / action / reponse ----------
let colonnes = {}, agentCourant = 'chef';
const TITRES = { chef: `<i class="fas fa-robot"></i> ${T('ui.agent_v2.agent_local_chef')}` };
function creerColonne(qui) {
  const col = document.createElement('div');
  col.className = 'flux-column';
  col.innerHTML = `<div class="flux-header">${TITRES[qui] || qui}</div><div class="flux-content"></div>`;
  $('live-stream-container').appendChild(col);
  colonnes[qui] = col;
  return col;
}
function preparerColonne() {
  $('live-stream-container').innerHTML = '';
  colonnes = {};
  creerColonne('chef');
}
const contenu = () => (colonnes[agentCourant] || creerColonne(agentCourant)).querySelector('.flux-content');

function nouvelleLigne(slot) {
  const row = document.createElement('div');
  row.className = 'flux-row';
  row.dataset.slot = slot;
  let cible = null;
  ['thought', 'action', 'response'].forEach((s) => {
    const c = document.createElement('div');
    c.classList.add('flux-cell', s === slot ? s : 'empty');
    if (s === slot) cible = c;
    row.appendChild(c);
  });
  appliquerFiltre(row);
  contenu().appendChild(row);
  return cible;
}

function ajouterTexte(slot, texte) {
  const cle = `${agentCourant}:${slot}`;
  if (!celluleEnCours[cle]) celluleEnCours[cle] = nouvelleLigne(slot);
  celluleEnCours[cle].textContent += texte;
  defiler();
}
function defiler() { const c = contenu(); c.scrollTop = c.scrollHeight; }
function appliquerFiltre(row) { row.style.display = (filtre === 'all' || row.dataset.slot === filtre) ? '' : 'none'; }

document.querySelectorAll('.timeline-filters .filter-btn').forEach((b) => {
  b.addEventListener('click', () => {
    document.querySelectorAll('.timeline-filters .filter-btn').forEach((x) => x.classList.remove('active'));
    b.classList.add('active');
    filtre = b.dataset.filter;
    document.querySelectorAll('#live-stream-container .flux-row').forEach(appliquerFiltre);
  });
});

// ---------- panneau Mission ----------
const ICONES = { fait: '✓', 'en-cours': '●', 'a-faire': '○', bloque: '!', annule: '✕' };
function badgeMission(texte, classe) { const b = $('mission-etat-badge'); b.textContent = texte; b.className = `mission-etat-badge ${classe}`; }
function dessinerTaches() {
  const liste = plan || taches;   // le plan annonce par l'agent, sinon ses actions au fil de l'eau
  const zone = $('mission-taches-liste');
  const fait = liste.filter((t) => t.etat === 'fait').length;
  document.querySelector('.mission-taches-titre span').textContent = plan ? T('ui.agent_v2.plan_de_la_mission') : T('ui.agent_v2.actions_realisees');
  document.querySelector('.mission-taches-progression').textContent = liste.length ? `${fait}/${liste.length}` : '';
  zone.innerHTML = liste.length ? liste.map((t) => `
    <div class="mission-tache-item ${t.etat}"><div class="tache-indicateur ${t.etat}">${ICONES[t.etat]}</div>
    <div class="tache-contenu"><div class="tache-titre">${echapper(t.titre)}</div>
    ${t.detail ? `<div class="tache-description">${echapper(t.detail)}</div>` : ''}</div></div>`).join('')
    : `<div class="taches-vide"><i class="fas fa-list"></i><span>${T('ui.agent_v2.aucune_action_pour_l_instant')}</span></div>`;
  document.querySelector('.mission-timeline').innerHTML = liste.map((t, i) =>
    `<div class="timeline-etape ${t.etat}" title="${echapper(t.titre)}"><span class="etape-numero">${i + 1}</span></div>`).join('');
  $('mission-progression').textContent = liste.length ? `${Math.round(100 * fait / liste.length)}%` : '0%';
  $('mission-etapes').textContent = tours;
}
function etapeSuivanteEnCours() {
  if (!plan || plan.some((e) => e.etat === 'en-cours')) return;
  const suivante = plan.find((e) => e.etat === 'a-faire');
  if (suivante) suivante.etat = 'en-cours';
}
function echapper(s) { const d = document.createElement('div'); d.textContent = String(s ?? ''); return d.innerHTML; }

// ---------- statut de l'agent ----------
function statutAgent(texte, classe, qui = 'chef') {
  const s = document.querySelector(`#agents-list [data-agent="${qui}"] .agent-status`);
  if (s) { s.textContent = texte; s.className = `agent-status ${classe}`; }
}

// ---------- autorisations : la fenetre de confirmation existante ----------
function ouvrirAutorisation(ev) {
  autorisationEnCours = ev.id;
  $('confirm-agent-name').textContent = T('ui.agent_v2.agent_local');
  $('confirm-action-type').textContent = `${ev.serveur} › ${ev.outil}`;
  $('confirm-action-params').textContent = JSON.stringify(ev.arguments, null, 2);
  document.querySelector('.modal-warning-footer').innerHTML =
    `<strong>${echapper(ev.motif || T('ui.agent_v2.action_modifie'))}</strong> ${T('ui.agent_v2.tu_autorises')}`;
  $('confirmation-modal').classList.remove('hidden');
  statutAgent(T('ui.agent_v2.attend_ton_accord'), 'status-active');
  badgeMission(T('ui.agent_v2.en_attente'), 'attente');
}
function repondre(accord) {
  if (!autorisationEnCours) return;
  api().repondre_autorisation(autorisationEnCours, accord);
  autorisationEnCours = null;
  $('confirmation-modal').classList.add('hidden');
  statutAgent(T('ui.agent_v2.travaille'), 'status-working');
  badgeMission(T('ui.agent_v2.en_cours'), 'en-cours');
}
$('confirm-approve-btn').addEventListener('click', () => repondre(true));
$('confirm-deny-btn').addEventListener('click', () => repondre(false));
window.closeConfirmationModal = () => repondre(false);

// ---------- voix : les phrases arrivent en mp3 et sont jouees dans l'ordre ----------
const fileAudio = [];
let audioEnCours = null;
function voyantAudio(parle) {
  const p = $('global-audio-led');
  if (p) p.style.boxShadow = parle ? '0 0 10px 2px rgba(0, 255, 170, 0.7)' : '';
}
function jouerSuivant() {
  if (audioEnCours || !fileAudio.length) { if (!audioEnCours) voyantAudio(false); return; }
  const morceau = fileAudio.shift();   // { audio, format } : mp3 d'Henri ou wav de Ludvig (voix de secours)
  audioEnCours = new Audio(`data:audio/${morceau.format === 'wav' ? 'wav' : 'mpeg'};base64,${morceau.audio}`);
  voyantAudio(true);
  const suite = () => { audioEnCours = null; jouerSuivant(); };
  audioEnCours.onended = suite;
  audioEnCours.onerror = suite;
  audioEnCours.play().catch(suite);
}
function couperVoix() {
  fileAudio.length = 0;
  if (audioEnCours) { audioEnCours.pause(); audioEnCours = null; }
  voyantAudio(false);
}
async function preparerSelecteurVoix() {
  const sel = $('audio-output-mode');
  const r = await api().voix_reglages();
  sel.innerHTML = Object.entries(r.choix).map(([id, nom]) => `<option value="${id}">${echapper(nom)}</option>`).join('')
    + `<option value="">${T('ui.agent_v2.muet')}</option>`;
  sel.value = r.nom;
  sel.onchange = () => { if (!sel.value) couperVoix(); api().regler_voix(sel.value); };
}

// ---------- jauge de la memoire du modele (remplie a chaque reflexion, videe par une nouvelle conversation) ----------
function preparerJaugeMemoire() {
  const jauge = document.createElement('div');
  jauge.id = 'jauge-memoire';
  jauge.className = 'service-status-pill';
  jauge.style.cssText = 'gap:8px;min-width:190px';
  jauge.innerHTML = `<i class="fas fa-memory"></i><span class="pill-label">${T('ui.agent_v2.memoire')}</span>
    <span style="flex:1;height:6px;min-width:60px;border-radius:3px;background:rgba(255,255,255,0.12);overflow:hidden">
      <span id="jauge-memoire-barre" style="display:block;height:100%;width:0%;border-radius:3px;transition:width .4s,background .4s"></span></span>
    <span id="jauge-memoire-texte" class="pill-label">0 %</span>`;
  document.querySelector('.audio-controls').prepend(jauge);
  majJaugeMemoire(0, 0);
}
function majJaugeMemoire(jetons, limite) {
  const pct = limite ? Math.min(100, Math.round(100 * jetons / limite)) : 0;
  const couleur = pct < 60 ? '#00ffaa' : pct < 85 ? '#ffaa00' : '#ff4466';
  const barre = $('jauge-memoire-barre');
  barre.style.width = `${Math.max(pct, jetons ? 1 : 0)}%`;
  barre.style.background = couleur;
  barre.style.boxShadow = `0 0 6px ${couleur}`;
  $('jauge-memoire-texte').textContent = `${pct} %`;
  $('jauge-memoire-texte').style.color = couleur;
  $('jauge-memoire').title = limite
    ? `${T('ui.agent_v2.memoire_du_modele_v1_jetons', {v1: jetons.toLocaleString(LANGUE), v2: limite.toLocaleString(LANGUE)})}`
      + (pct >= 85 ? T('ui.agent_v2.presque_pleine_pense_au_bouton') : '')
    : T('ui.agent_v2.memoire_du_modele_vide_conversation');
}

// ---------- evenements venus du noyau ----------
window.agentEvenement = (lot) => lot.forEach(traiter);

function traiter(ev) {
  agentCourant = ev.agent || 'chef';   // chaque evenement va dans la colonne de son agent
  switch (ev.type) {
    case 'memoire': majJaugeMemoire(ev.jetons, ev.limite); break;
    case 'voix': fileAudio.push({ audio: ev.audio, format: ev.format || 'mpeg' }); jouerSuivant(); break;
    case 'voix_stop': couperVoix(); break;
    case 'voix_erreur': nouvelleLigne('response').textContent = `🔇 ${ev.texte}`; defiler(); break;
    case 'taches_maj': chargerTaches(); break;
    case 'artefact_partiel': window.Artefacts.partiel(ev); break;
    case 'artefact': {
      window.Artefacts.afficher({ ...ev, type: ev.genre });
      const c = nouvelleLigne('response');
      c.textContent = `${T('ui.agent_v2.artefact_v1_v_v2_clique', {v1: ev.titre, v2: ev.version})}`;
      c.style.cursor = 'pointer';
      c.addEventListener('click', () => window.Artefacts.ouvrir(ev.id));
      defiler(); break;
    }
    case 'telegram': nouvelleLigne('action').textContent = ev.texte; defiler(); break;
    case 'conversation_reprise':
      afficherConversation(ev.messages);
      nouvelleLigne('response').textContent = T('ui.agent_v2.reprise_de_la_mission_interrompue');
      chargerHistorique(); break;
    case 'nouvelle_conversation':
      preparerColonne(); celluleEnCours = {}; majJaugeMemoire(0, 0);
      nouvelleLigne('response').textContent = T('ui.agent_v2.nouvelle_conversation_demandee_depuis_le');
      setTimeout(chargerHistorique, 300); break;
    case 'refus_auto': nouvelleLigne('action').textContent = `⛔ ${ev.texte} (${ev.outil})`; defiler(); break;
    case 'debut_mission':
      taches = []; plan = null; tours = 0; debutMission = Date.now();
      $('mission-objectif-texte').textContent = ev.planifiee ? `⏰ ${ev.planifiee} — ${ev.texte}` : ev.texte;
      if (ev.planifiee) { nouvelleLigne('response').textContent = `${T('ui.agent_v2.tache_planifiee_v1', {v1: ev.planifiee})}`; defiler(); }
      if (ev.telephone) { const c = nouvelleLigne('response'); c.textContent = `📱 ${ev.texte}`; c.style.opacity = '0.75'; defiler(); }
      badgeMission(T('ui.agent_v2.en_cours'), 'en-cours'); statutAgent(T('ui.agent_v2.travaille'), 'status-working');
      clearInterval(chrono);
      chrono = setInterval(() => { $('mission-duree').textContent = `${Math.round((Date.now() - debutMission) / 1000)} s`; }, 500);
      dessinerTaches(); break;
    case 'tour':
      Object.keys(celluleEnCours).filter((k) => k.startsWith(`${agentCourant}:`)).forEach((k) => delete celluleEnCours[k]);
      if (agentCourant === 'chef') { tours = ev.numero; $('mission-etapes').textContent = tours; }
      break;
    case 'plan':
      plan = ev.etapes.map((t) => ({ titre: t, etat: 'a-faire' }));
      etapeSuivanteEnCours();
      nouvelleLigne('action').textContent = T('ui.agent_v2.plan_annonce') + ev.etapes.map((t, i) => `${i + 1}. ${t}`).join('\n');
      dessinerTaches(); defiler(); break;
    case 'etape': {
      const e = plan && plan[ev.numero - 1];
      if (e) {
        e.etat = ev.echec ? 'bloque' : 'fait';
        e.detail = ev.note || '';
        etapeSuivanteEnCours();
      }
      nouvelleLigne('action').textContent = `${ev.echec ? '!' : '✓'} ${T('ui.agent_v2.etape_v1', {v1: ev.numero})}${e ? ` : ${e.titre}` : ''}${ev.note ? `\n${ev.note}` : ''}`;
      dessinerTaches(); defiler(); break;
    }
    case 'rappel': {
      const c = nouvelleLigne('action');
      c.textContent = ev.souvenirs.length
        ? `${T('ui.agent_v2.rappel_du_carnet_v1_souvenir', {v1: ev.souvenirs.length})}` + ev.souvenirs.map((s) => `• ${s.texte}`).join('\n')
        : T('ui.agent_v2.rappel_du_carnet_rien_de');
      if (ev.competences && ev.competences.length) {
        c.textContent += T('ui.agent_v2.competence_s_a_suivre') + ev.competences.map((f) => f.nom).join(', ');
      }
      defiler(); break;
    }
    case 'apprentissage':
      celluleEnCours = {};
      statutAgent(T('ui.agent_v2.apprend'), 'status-working');
      nouvelleLigne('action').textContent = T('ui.agent_v2.moment_d_apprentissage_y_a');
      defiler(); break;
    case 'reflexion': ajouterTexte('thought', ev.texte); break;
    case 'texte': ajouterTexte('response', ev.texte); break;
    case 'appel_outil': {
      const c = nouvelleLigne('action');
      c.textContent = `${ev.serveur === 'competences' ? '📘' : '🔧'} ${ev.serveur} › ${ev.outil}${ev.niveau === 'demander' ? `  (${T('ui.agent_v2.autorisation_requise')})` : ''}\n${JSON.stringify(ev.arguments)}`;
      c.id = `appel-${ev.id}`;
      taches.push({ id: ev.id, titre: `${ev.agent ? '🤝 ' : ''}${ev.serveur} › ${ev.outil}`, etat: 'en-cours' });
      dessinerTaches(); defiler(); break;
    }
    case 'demande_autorisation': ouvrirAutorisation(ev); break;
    case 'autorisation': {
      if (autorisationEnCours === ev.id) { autorisationEnCours = null; $('confirmation-modal').classList.add('hidden'); }
      const t = taches.find((x) => x.id === ev.id);
      const c = $(`appel-${ev.id}`);
      if (c) c.textContent += ev.accordee ? T('ui.agent_v2.autorise_par_toi') : T('ui.agent_v2.refuse_par_toi');
      if (t && !ev.accordee) { t.etat = 'annule'; t.detail = T('ui.agent_v2.refuse'); }
      dessinerTaches(); break;
    }
    case 'resultat_outil': {
      const t = taches.find((x) => x.id === ev.id);
      const echec = new RegExp(`^(${T('commun.prefixe_erreur')}|${T('commun.prefixe_refus')})`).test(ev.resultat);
      if (t) { t.etat = echec ? 'bloque' : 'fait'; t.detail = `${ev.duree} s`; }
      const c = $(`appel-${ev.id}`);
      if (c) c.textContent += `\n→ ${ev.resultat.slice(0, 600)}`;
      if (ev.serveur === 'memoire') chargerCarnet();
      if (ev.serveur === 'competences') chargerCompetences();
      if (ev.serveur === 'planificateur') chargerTaches();
      dessinerTaches(); defiler(); break;
    }
    case 'erreur': nouvelleLigne('response').textContent = `⚠ ${ev.texte}`; statutAgent(T('ui.agent_v2.erreur'), 'status-error'); badgeMission(T('ui.agent_v2.erreur'), 'erreur'); break;
    case 'fin_mission':
      clearInterval(chrono);
      if (autorisationEnCours) { autorisationEnCours = null; $('confirmation-modal').classList.add('hidden'); }
      if (!$('mission-etat-badge').classList.contains('erreur')) badgeMission(T('ui.agent_v2.terminee'), 'terminee');
      statutAgent(T('ui.agent_v2.au_repos'), 'status-idle');
      $('chat-send').disabled = false;
      chargerHistorique();
      $('chat-input').focus(); break;
  }
}

// ---------- envoi d'un message ----------
async function envoyer() {
  agentCourant = 'chef';
  const zone = $('chat-input');
  let texte = zone.value.trim();
  if (!texte && !pieceJointe) return;
  if (pieceJointe) {
    // le trombone : la fenetre depose le fichier dans Documents\Pieces jointes et donne son chemin au chef
    const j = await api().joindre_fichier(pieceJointe.nom, pieceJointe.contenu);
    if (!j.ok) { nouvelleLigne('response').textContent = `⚠ ${j.raison}`; defiler(); return; }
    texte = `${T('ui.agent_v2.v1_n_n_piece_jointe', {v1: texte || T('ui.agent_v2.voici_piece_jointe'), v2: j.chemin})}`;
  }
  const r = await api().envoyer(texte);
  agentCourant = 'chef';   // des evenements ont pu arriver pendant l'attente
  if (!r.ok) { nouvelleLigne('response').textContent = `⚠ ${r.raison}`; return; }
  zone.value = '';
  retirerPieceJointe();
  $('chat-send').disabled = true;
  const c = nouvelleLigne('response');
  c.textContent = `🧑 ${texte}`;
  c.style.opacity = '0.75';
  defiler();
}
$('chat-send').addEventListener('click', envoyer);
$('chat-input').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); envoyer(); } });

// ---------- le trombone : choisir une piece jointe, la previsualiser, la retirer ----------
let pieceJointe = null;   // { nom, contenu (data URL) }
function retirerPieceJointe() {
  pieceJointe = null;
  $('file-input').value = '';
  $('file-preview-container').classList.add('hidden');
  $('file-preview-image').classList.add('hidden');
}
$('file-input').addEventListener('change', () => {
  const fichier = $('file-input').files[0];
  if (!fichier) return;
  const lecteur = new FileReader();
  lecteur.onload = () => {
    pieceJointe = { nom: fichier.name, contenu: lecteur.result };
    $('file-preview-name').textContent = fichier.name;
    $('file-preview-size').textContent = `${(fichier.size / 1024).toFixed(0)} Ko`;
    const image = fichier.type.startsWith('image/');
    $('file-preview-image').classList.toggle('hidden', !image);
    if (image) $('file-preview-image').src = lecteur.result;
    $('file-preview-container').classList.remove('hidden');
    $('chat-input').focus();
  };
  lecteur.readAsDataURL(fichier);
});
$('file-preview-remove').addEventListener('click', retirerPieceJointe);

// ---------- ecoute : la dictee Whisper (Ctrl gauche + Alt gauche) colle le texte dans la zone de saisie ----------
let modeConversation = false;
function preparerConversation() {
  const rangee = document.querySelector('#chat-buttons .chat-buttons-row');
  const bouton = document.createElement('button');
  bouton.id = 'mode-conversation';
  bouton.className = 'file-button';
  bouton.title = T('ui.agent_v2.mode_conversation_ce_que_tu');
  bouton.innerHTML = '<i class="fas fa-microphone"></i>';
  bouton.addEventListener('click', () => {
    modeConversation = !modeConversation;
    bouton.style.color = modeConversation ? '#00ffaa' : '';
    bouton.style.textShadow = modeConversation ? '0 0 8px #00ffaa' : '';
    $('chat-input').placeholder = modeConversation
      ? T('ui.agent_v2.mode_conversation_maintiens_ctrl_alt')
      : T('ui.agent_v2.ecrire_un_message_a_l');
    $('chat-input').focus();
  });
  rangee.prepend(bouton);
}
// ---------- nouvelle conversation : repartir sur un fil neuf (le carnet et les competences restent) ----------
function preparerNouvelleConversation() {
  const bouton = document.createElement('button');
  bouton.id = 'nouvelle-conversation';
  bouton.className = 'file-button';
  bouton.title = T('ui.agent_v2.nouvelle_conversation_repartir_de_zero');
  bouton.innerHTML = '<i class="fas fa-plus"></i>';
  bouton.addEventListener('click', async () => {
    const r = await api().nouvelle_conversation();
    if (!r.ok) { nouvelleLigne('response').textContent = `⚠ ${r.raison}`; defiler(); return; }
    agentCourant = 'chef';
    preparerColonne();
    Object.keys(celluleEnCours).forEach((k) => delete celluleEnCours[k]);
    majJaugeMemoire(0, 0);
    nouvelleLigne('response').textContent = T('ui.agent_v2.nouvelle_conversation_le_carnet_et');
    setTimeout(chargerHistorique, 300);   // le noyau bascule de fil juste apres la reponse
    $('chat-input').focus();
  });
  document.querySelector('#chat-buttons .chat-buttons-row').prepend(bouton);
}
// La dictee colle son texte : en mode conversation, on l'envoie aussitot.
$('chat-input').addEventListener('paste', () => {
  if (modeConversation) setTimeout(() => { if (!$('chat-send').disabled) envoyer(); }, 80);
});
// Appuyer sur Ctrl + Alt pour parler coupe la parole a l'agent.
document.addEventListener('keydown', (e) => {
  if ((e.key === 'Control' && e.altKey) || (e.key === 'Alt' && e.ctrlKey)) couperVoix();
});
// La zone de saisie reste prete a recevoir la dictee.
window.addEventListener('focus', () => $('chat-input').focus());
document.addEventListener('click', (e) => {
  // Pas de retour dans la zone de saisie si l'utilisateur vient de surligner du texte (sinon la selection s'efface) - 11/11/2026
  if (String(window.getSelection())) return;
  if (!e.target.closest('input, textarea, select, button, a, label, .modal-content, #panneau-artefact')) $('chat-input').focus();
});
$('emergency-stop-btn').addEventListener('click', () => { couperVoix(); api().arreter(); });
$('btn-mission-annuler').addEventListener('click', () => { couperVoix(); api().arreter(); });

// ---------- filet de securite : annuler la derniere modification de fichier (12/11/2026) ----------
function preparerBoutonAnnuler() {
  const bouton = document.createElement('button');
  bouton.id = 'btn-annuler-modification';
  bouton.className = 'mission-btn';
  bouton.title = T('ui.agent_v2.annuler_la_derniere_modification_de');
  bouton.innerHTML = `<i class="fas fa-undo"></i> ${T('ui.agent_v2.annuler_la_derniere_modification')}`;
  bouton.addEventListener('click', async () => {
    agentCourant = 'chef';
    const d = await api().derniere_modification();
    if (!d) { nouvelleLigne('action').textContent = T('ui.agent_v2.aucune_modification_a_annuler_rien'); defiler(); return; }
    if (!confirm(`${T('ui.agent_v2.annuler_la_derniere_modification_n', {v1: d.outil, v2: d.quand, v3: d.fichiers.join('\n')})}`)) return;
    const r = await api().annuler_modification();
    nouvelleLigne('action').textContent = `↶ ${r.texte}`;
    defiler();
  });
  document.querySelector('.mission-controles').prepend(bouton);
}

// ---------- au demarrage : agent et MCP reels ----------
window.addEventListener('pywebviewready', async () => {
  preparerColonne();
  const e = await api().etat();
  const etiquette = document.querySelector('label[for="audio-output-mode"]');
  if (etiquette) etiquette.textContent = T('ui.agent_v2.voix');
  preparerSelecteurVoix();
  preparerJaugeMemoire();
  preparerConversation();
  $('agents-list').innerHTML = `<div class="agent-item" data-agent="chef">
    <span class="agent-name">${T('ui.agent_v2.chef_modele_local')}</span><span class="agent-status status-idle">${e.pret ? T('ui.agent_v2.au_repos') : T('ui.page.demarrage')}</span></div>`;
  $('mcp-status-list').innerHTML = e.serveurs.map((s) => {
    const ok = s.etat === 'branche';
    const auto = s.outils.filter((o) => o.niveau === 'auto').length;
    return `<div class="mcp-item ${ok ? 'status-ready' : 'status-error'}" title="${echapper(s.etat)}">
      <span class="mcp-indicator"></span><span class="mcp-name">${echapper(s.nom)} · ${s.outils.length} outils (${auto} libres)</span></div>`;
  }).join('') || `<div class="mcp-item status-error"><span class="mcp-indicator"></span><span class="mcp-name">${T('ui.agent_v2.aucun_mcp')}</span></div>`;
  $('mcp-status-list').classList.add('open');
  nouvelleLigne('response').textContent = `${T('ui.agent_v2.agent_local_pret_v1_mcp', {v1: e.serveurs.length})}`;
  defiler();
  preparerNouvelleConversation();
  chargerCarnet();
  preparerVoletCompetences();
  chargerCompetences();
  preparerVoletHistorique();
  chargerHistorique();
  preparerVoletTaches();
  chargerTaches();
  preparerBoutonAnnuler();
  proposerReprise();
  const tg = await api().telegram_etat();   // Telegram : code d'appairage tant qu'aucun telephone n'est relie
  if (tg.actif && tg.code) {
    nouvelleLigne('action').textContent = `${T('ui.agent_v2.telegram_envoie_ce_code_a', {v1: tg.code})}`;
    defiler();
  }
  setInterval(chargerTaches, 60000);
});

// ---------- volet Memoire : le carnet ----------
function dessinerSouvenirs(liste) {
  const parCat = {};
  liste.forEach((s) => (parCat[s.categorie] ||= []).push(s));
  $('memory-stats-bar').innerHTML = `<span class="memory-total">${T('ui.agent_v2.v1_souvenir_s_v2_categorie', {v1: liste.length, v2: Object.keys(parCat).length})}</span>`;
  $('memory-tree').innerHTML = liste.length ? Object.entries(parCat).map(([cat, items]) => `
    <div class="memory-folder expanded">
      <div class="memory-folder-header"><i class="fas fa-folder-open"></i> ${echapper(cat)} (${items.length})</div>
      <div class="memory-folder-content" style="display:block">
        ${items.map((s) => `<div class="memory-doc" title="${T('ui.agent_v2.note_le_v1', {v1: echapper(s.cree)})}">${s.essentiel ? '★ ' : ''}[${s.id}] ${echapper(s.texte)}</div>`).join('')}
      </div></div>`).join('')
    : `<div class="memory-empty">${T('ui.agent_v2.carnet_vide_pour_l_instant')}</div>`;
}
async function chargerCarnet() {
  dessinerSouvenirs(await api().memoire_lister());
  document.querySelector('.memory-header')?.classList.add('connected');
}
async function chercherCarnet() {
  const q = $('memory-search-input').value.trim();
  const zone = $('memory-search-results');
  if (!q) { zone.classList.add('hidden'); return; }
  const res = await api().memoire_rechercher(q);
  zone.innerHTML = `<div class="memory-search-header">${T('ui.agent_v2.v1_resultat_s_pour_v2', {v1: res.length, v2: echapper(q)})}</div>` +
    res.map((s) => `<div class="memory-search-result">[${s.id}] (${echapper(s.categorie)}) ${echapper(s.texte)}</div>`).join('');
  zone.classList.remove('hidden');
}
$('memory-search-btn').addEventListener('click', chercherCarnet);
$('memory-search-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') chercherCarnet(); });

// ---------- volet Competences : les fiches de savoir-faire ----------
function preparerVoletCompetences() {
  const volet = document.createElement('div');
  volet.className = T('ui.agent_v2.right_accordion_memory_explorer_accordion');
  volet.innerHTML = `
    <div class="accordion-header memory-header connected open" data-target="competences-list">
      <span class="memory-label"><i class="fas fa-book"></i> ${T('ui.agent_v2.competences')}</span><span class="triangle">▶</span>
    </div>
    <div id="competences-list" class="accordion-content open">
      <div id="competences-stats" class="memory-stats-bar"></div>
      <div id="competences-arbre" class="memory-tree"></div>
      <div id="competence-apercu" class="memory-preview hidden" style="white-space:pre-wrap"></div>
    </div>`;
  $('right-panel').appendChild(volet);
  const entete = volet.querySelector('.accordion-header');
  entete.addEventListener('click', () => { $('competences-list').classList.toggle('open'); entete.classList.toggle('open'); });
}
async function chargerCompetences() {
  const liste = await api().competences_lister();
  $('competences-stats').innerHTML = `<span class="memory-total">${T('ui.agent_v2.v1_competence_s', {v1: liste.length})}</span>`;
  $('competences-arbre').innerHTML = liste.length ? liste.map((c) => `
    <div class="memory-doc" data-competence="${echapper(c.nom)}" title="${T('ui.agent_v2.mise_a_jour_le_v1', {v1: echapper(c.maj)})}">
      📘 <strong>${echapper(c.nom)}</strong><br><small>${echapper(c.description)}</small></div>`).join('')
    : `<div class="memory-empty">${T('ui.agent_v2.aucune_competence_pour_l_instant')}</div>`;
  $('competences-arbre').querySelectorAll('[data-competence]').forEach((el) => el.addEventListener('click', async () => {
    const f = await api().competence_lire(el.dataset.competence);
    const apercu = $('competence-apercu');
    apercu.textContent = f ? `${f.nom}\n${f.description}\n\n${f.contenu}` : T('ui.agent_v2.fiche_introuvable');
    apercu.classList.remove('hidden');
  }));
}

// ---------- volet Historique : reprendre une conversation la ou on s'etait arrete (12/11/2026) ----------
function preparerVoletHistorique() {
  const volet = document.createElement('div');
  volet.className = T('ui.agent_v2.right_accordion_memory_explorer_accordion');
  volet.innerHTML = `
    <div class="accordion-header memory-header connected open" data-target="historique-list">
      <span class="memory-label"><i class="fas fa-history"></i> ${T('ui.agent_v2.historique')}</span><span class="triangle">▶</span>
    </div>
    <div id="historique-list" class="accordion-content open">
      <div id="historique-stats" class="memory-stats-bar"></div>
      <div id="historique-arbre" class="memory-tree" style="max-height:320px;overflow-y:auto"></div>
    </div>`;
  $('right-panel').prepend(volet);
  const entete = volet.querySelector('.accordion-header');
  entete.addEventListener('click', () => { $('historique-list').classList.toggle('open'); entete.classList.toggle('open'); });
}
async function chargerHistorique() {
  const liste = await api().conversations_lister();
  $('historique-stats').innerHTML = `<span class="memory-total">${T('ui.agent_v2.v1_conversation_s_clique_pour', {v1: liste.length})}</span>`;
  $('historique-arbre').innerHTML = liste.length ? liste.map((c) => `
    <div class="memory-doc" data-conversation="${c.id}" title="${T('ui.agent_v2.commencee_v1_v2_message_s', {v1: echapper(dateLisible(c.debut)), v2: c.nombre})}"
      style="cursor:pointer;${c.actuelle ? 'border-left:3px solid #00ffaa;background:rgba(0,255,170,0.08)' : ''}">
      💬 <strong>${echapper(c.titre)}</strong><br><small>${echapper(dateLisible(c.derniere))}${c.actuelle ? ` · ${T('ui.agent_v2.en_cours')}` : ''}</small></div>`).join('')
    : `<div class="memory-empty">${T('ui.agent_v2.aucune_conversation_pour_l_instant')}</div>`;
  $('historique-arbre').querySelectorAll('[data-conversation]').forEach((el) => el.addEventListener('click', () => reprendreConversation(el.dataset.conversation)));
}
function afficherConversation(messages) {
  couperVoix();
  preparerColonne();
  Object.keys(celluleEnCours).forEach((k) => delete celluleEnCours[k]);
  majJaugeMemoire(0, 0);   // la jauge se remet a jour au prochain message
  messages.forEach((m) => {
    const c = nouvelleLigne(m.genre === 'outils' ? 'action' : 'response');
    c.textContent = m.genre === 'demande' ? `🧑 ${m.texte}` : m.genre === 'outils' ? `🔧 ${m.texte}` : m.texte;
    if (m.genre === 'demande') c.style.opacity = '0.75';
  });
}
// ---------- reprise apres plantage : proposer de reprendre la mission interrompue (12/11/2026) ----------
async function proposerReprise() {
  const mi = await api().mission_interrompue();
  if (!mi) return;
  const c = nouvelleLigne('action');
  c.innerHTML = `${T('ui.agent_v2.ta_derniere_mission_s_est', {v1: echapper(dateLisible(mi.quand))})}<br>« ${echapper(mi.demande.slice(0, 400))} »<br>`;
  const bouton = (libelle, action) => {
    const b = document.createElement('button');
    b.className = 'mission-btn';
    b.style.margin = '6px 6px 0 0';
    b.textContent = libelle;
    b.addEventListener('click', action);
    c.appendChild(b);
  };
  bouton(T('ui.agent_v2.reprendre_la_mission'), async () => {
    const r = await api().reprendre_mission(mi.id);
    agentCourant = 'chef';
    if (!r.ok) { nouvelleLigne('response').textContent = `⚠ ${r.raison}`; defiler(); return; }
    afficherConversation(r.messages);
    nouvelleLigne('response').textContent = T('ui.agent_v2.reprise_de_la_mission_interrompue_2');
    $('chat-send').disabled = true;
    chargerHistorique();
  });
  bouton(T('ui.agent_v2.abandonner'), async () => {
    await api().abandonner_mission(mi.id);
    c.textContent = T('ui.agent_v2.mission_interrompue_abandonnee');
  });
  defiler();
}
async function reprendreConversation(id) {
  const r = await api().conversation_reprendre(id);
  agentCourant = 'chef';
  if (!r.ok) { nouvelleLigne('response').textContent = `⚠ ${r.raison}`; defiler(); return; }
  afficherConversation(r.messages);
  nouvelleLigne('response').textContent = T('ui.agent_v2.conversation_reprise_continue_la_ou');
  defiler();
  chargerHistorique();
  $('chat-input').focus();
}

// ---------- taches planifiees : en bas du panneau Mission ----------
function preparerVoletTaches() {
  const zone = document.createElement('div');
  zone.className = 'mission-taches-zone';
  zone.innerHTML = `
    <div class="mission-taches-titre"><span>${T('ui.agent_v2.taches_planifiees')}</span><span id="taches-nombre" class="mission-taches-progression"></span></div>
    <div id="taches-planifiees" class="mission-taches-liste"></div>`;
  document.querySelector('.dashboard-mission').appendChild(zone);
}
function dateLisible(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  const auj = new Date();
  const demain = new Date(auj.getTime() + 86400000);
  const heure = d.toLocaleTimeString(LANGUE, { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === auj.toDateString()) return `${T('ui.agent_v2.aujourd_hui_a_v1', {v1: heure})}`;
  if (d.toDateString() === demain.toDateString()) return `${T('ui.agent_v2.demain_a_v1', {v1: heure})}`;
  return T('ui.agent_v2.date_a_heure', {v1: d.toLocaleDateString(LANGUE, { weekday: 'long', day: 'numeric', month: 'long' }), v2: heure});
}
async function chargerTaches() {
  const liste = await api().taches_lister();
  $('taches-nombre').textContent = liste.length ? `${liste.length}` : '';
  $('taches-planifiees').innerHTML = liste.length ? liste.map((t) => `
    <div class="mission-tache-item a-faire" title="${echapper(t.consigne)}">
      <div class="tache-indicateur a-faire">⏰</div>
      <div class="tache-contenu"><div class="tache-titre">${echapper(t.titre)}</div>
        <div class="tache-description">${echapper(t.rythme_lisible)} · prochaine : ${echapper(dateLisible(t.prochaine))}</div></div>
      <button class="mission-btn danger-outline" data-tache="${t.id}" title="${T('ui.agent_v2.retirer_cette_tache')}" style="margin-left:auto">
        <i class="fas fa-times"></i></button>
    </div>`).join('')
    : `<div class="taches-vide"><i class="fas fa-clock"></i><span>${T('ui.agent_v2.aucune_tache_demande_par_exemple')}</span></div>`;
  $('taches-planifiees').querySelectorAll('[data-tache]').forEach((b) => b.addEventListener('click', async () => {
    await api().tache_supprimer(b.dataset.tache);
    chargerTaches();
  }));
}


// ---------- clic droit : menu « Copier » / « Coller » (demandes de l'utilisateur du 11/11/2026) ----------
// La fenetre pywebview n'affiche pas de menu natif au clic droit : on en dessine un petit.
// « Copier » si du texte est surligne ; « Coller » si le clic droit tombe dans une zone ou l'on peut ecrire.
(function menuClicDroit() {
  const menu = document.createElement('div');
  menu.style.cssText = 'position:fixed;z-index:99999;display:none;min-width:150px;padding:4px;border-radius:8px;'
    + 'background:#1e2330;border:1px solid rgba(255,255,255,0.15);box-shadow:0 6px 20px rgba(0,0,0,0.5);'
    + 'font-size:14px;color:#fff;user-select:none';
  const ligne = (action, icone, libelle) => `<div data-action="${action}" style="padding:8px 12px;border-radius:6px;`
    + `cursor:pointer"><i class="fas ${icone}" style="margin-right:8px;width:14px"></i>${libelle}</div>`;
  menu.innerHTML = ligne('copier', 'fa-copy', T('ui.agent_v2.copier')) + ligne('coller', 'fa-paste', T('ui.agent_v2.coller'));
  document.body.appendChild(menu);
  const [itemCopier, itemColler] = menu.children;
  for (const it of menu.children) {
    it.addEventListener('mouseenter', () => { it.style.background = 'rgba(0,255,170,0.15)'; });
    it.addEventListener('mouseleave', () => { it.style.background = 'transparent'; });
  }
  let texte = '';
  let champ = null;   // zone de saisie visee par « Coller »

  const editable = (el) => el && ((el.tagName === 'TEXTAREA') || (el.tagName === 'INPUT'
    && /^(text|search|url|email|)$/i.test(el.type || ''))) && !el.disabled && !el.readOnly;
  const cacher = () => { menu.style.display = 'none'; };

  async function copier(t) {
    try { await navigator.clipboard.writeText(t); return; } catch (e) { /* repli ci-dessous */ }
    const zone = document.createElement('textarea');
    zone.value = t; zone.style.cssText = 'position:fixed;left:-9999px';
    document.body.appendChild(zone); zone.select(); document.execCommand('copy'); zone.remove();
  }
  async function lirePressePapiers() {
    // Lu par le programme (app.py) : dans la fenetre, la lecture par la page peut ouvrir une demande d'autorisation.
    try { return (await api().presse_papiers()) || ''; } catch (e) { return ''; }
  }

  document.addEventListener('contextmenu', (e) => {
    champ = editable(e.target) ? e.target : null;
    texte = champ ? champ.value.substring(champ.selectionStart, champ.selectionEnd) : String(window.getSelection());
    if (!texte && !champ) { cacher(); return; }   // ni texte surligne ni zone de saisie : pas de menu
    e.preventDefault();
    itemCopier.style.display = texte ? 'block' : 'none';
    itemColler.style.display = champ ? 'block' : 'none';
    menu.style.display = 'block';
    menu.style.left = `${Math.min(e.clientX, window.innerWidth - 170)}px`;
    menu.style.top = `${Math.min(e.clientY, window.innerHeight - 100)}px`;
  });
  // mousedown + preventDefault : la selection et le curseur restent en place pendant le clic sur le menu
  itemCopier.addEventListener('mousedown', async (e) => {
    e.preventDefault(); e.stopPropagation();
    await copier(texte);
    cacher();
  });
  itemColler.addEventListener('mousedown', async (e) => {
    e.preventDefault(); e.stopPropagation();
    cacher();
    const cible = champ;
    const t = await lirePressePapiers();
    if (!cible || !t) return;
    cible.focus();
    cible.setRangeText(t, cible.selectionStart, cible.selectionEnd, 'end');   // remplace la selection eventuelle
    cible.dispatchEvent(new Event('input', { bubbles: true }));
  });
  document.addEventListener('mousedown', (e) => { if (!menu.contains(e.target)) cacher(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') cacher(); });
  window.addEventListener('blur', cacher);
})();
