// Agent Local - panneau d'artefacts : lettres, documents, programmes et pages web, affiches pendant leur ecriture.
(() => {
  const api = () => window.pywebview.api;
  const esc = (s) => { const d = document.createElement('div'); d.textContent = String(s ?? ''); return d.innerHTML; };
  let courant = null;        // artefact affiche {id, titre, type, langage, contenu, version}
  let vue = 'apercu';        // 'apercu' ou 'source'

  // ---------- le panneau ----------
  const panneau = document.createElement('div');
  panneau.id = 'panneau-artefact';
  panneau.style.cssText = `display:none; position:fixed; top:70px; right:12px; bottom:12px; width:46%; z-index:60;
    flex-direction:column; background:rgba(8,14,26,0.97); border:1px solid rgba(0,255,200,0.35);
    border-radius:12px; box-shadow:0 0 30px rgba(0,255,200,0.15); overflow:hidden;`;
  panneau.innerHTML = `
    <div style="display:flex; align-items:center; gap:8px; padding:10px 12px; border-bottom:1px solid rgba(0,255,200,0.2);">
      <span id="art-titre" style="font-weight:600; color:#00ffc8; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"></span>
      <span id="art-version" style="font-size:12px; opacity:0.7;"></span>
      <select id="art-liste" title="${T('ui.artefacts.autres_artefacts')}" style="max-width:150px;"></select>
      <button id="art-vue" class="filter-btn" title="${T('ui.artefacts.basculer_apercu_texte_brut')}">${T('ui.artefacts.source')}</button>
      <button id="art-copier" class="filter-btn" title="${T('ui.artefacts.copier_le_contenu')}">${T('ui.artefacts.copier')}</button>
      <button id="art-enregistrer" class="filter-btn" title="${T('ui.artefacts.enregistrer_dans_documents_agent_local')}">${T('ui.artefacts.enregistrer')}</button>
      <button id="art-fermer" class="filter-btn" title="${T('ui.artefacts.fermer_le_panneau')}">✕</button>
    </div>
    <div id="art-etat" style="display:none; padding:4px 12px; font-size:12px; color:#00ffc8;"></div>
    <div id="art-corps" style="flex:1; overflow:auto; padding:16px 20px; line-height:1.55;"></div>`;
  document.body.appendChild(panneau);
  const $a = (id) => document.getElementById(id);

  // ---------- mise en forme Markdown simple (lettres, documents) ----------
  function markdown(texte) {
    const blocs = [];
    let t = esc(texte).replace(/```(\w*)\n([\s\S]*?)```/g, (_, l, c) => { blocs.push(c); return `\u0000${blocs.length - 1}\u0000`; });
    t = t.replace(/^###### (.*)$/gm, '<h6>$1</h6>').replace(/^##### (.*)$/gm, '<h5>$1</h5>')
      .replace(/^#### (.*)$/gm, '<h4>$1</h4>').replace(/^### (.*)$/gm, '<h3>$1</h3>')
      .replace(/^## (.*)$/gm, '<h2>$1</h2>').replace(/^# (.*)$/gm, '<h1>$1</h1>')
      .replace(/^---+$/gm, '<hr>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/(^|\W)\*(?!\s)(.+?)\*(?=\W|$)/g, '$1<em>$2</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
    const lignes = t.split('\n'); const html = []; let liste = null, para = [];
    const fermerPara = () => { if (para.length) { html.push(`<p>${para.join('<br>')}</p>`); para = []; } };
    const fermerListe = () => { if (liste) { html.push(`</${liste}>`); liste = null; } };
    for (const l of lignes) {
      const puce = l.match(/^\s*[-*•] (.*)$/), num = l.match(/^\s*\d+[.)] (.*)$/);
      if (puce || num) {
        fermerPara();
        const type = puce ? 'ul' : 'ol';
        if (liste !== type) { fermerListe(); html.push(`<${type}>`); liste = type; }
        html.push(`<li>${(puce || num)[1]}</li>`);
      } else if (/^<(h\d|hr)/.test(l) || l.startsWith('\u0000')) { fermerPara(); fermerListe(); html.push(l); }
      else if (!l.trim()) { fermerPara(); fermerListe(); }
      else { fermerListe(); para.push(l); }
    }
    fermerPara(); fermerListe();
    return html.join('\n').replace(/\u0000(\d+)\u0000/g, (_, i) => `<pre style="background:rgba(0,0,0,0.35); padding:10px; border-radius:6px; overflow:auto;"><code>${blocs[i]}</code></pre>`);
  }

  // ---------- affichage ----------
  function dessiner() {
    const corps = $a('art-corps');
    if (!courant) return;
    $a('art-titre').textContent = `📄 ${courant.titre || 'Artefact'}`;
    $a('art-version').textContent = courant.version ? `v${courant.version}` : T('ui.artefacts.en_ecriture');
    $a('art-vue').textContent = vue === 'apercu' ? T('ui.artefacts.source') : T('ui.artefacts.apercu');
    if (vue === 'source' || courant.enCours || courant.type === 'code') {
      corps.innerHTML = `<pre style="margin:0; white-space:pre-wrap; font-family:'JetBrains Mono',Consolas,monospace; font-size:13px;">${esc(courant.contenu)}</pre>`;
      if (courant.enCours) corps.scrollTop = corps.scrollHeight;
    } else if (courant.type === 'html') {
      corps.innerHTML = '';
      const cadre = document.createElement('iframe');
      cadre.setAttribute('sandbox', 'allow-scripts allow-forms allow-modals');   // isolee : aucun acces a la fenetre d'Agent Local
      cadre.style.cssText = 'width:100%; height:100%; border:0; background:#fff; border-radius:6px;';
      cadre.srcdoc = courant.contenu;
      corps.appendChild(cadre);
    } else {
      corps.innerHTML = `<div style="max-width:760px; margin:0 auto; font-size:15px;">${markdown(courant.contenu)}</div>`;
    }
  }
  function ouvrirPanneau() { panneau.style.display = 'flex'; }
  async function rafraichirListe() {
    const liste = await api().artefacts_lister();
    $a('art-liste').innerHTML = `<option value="">${T('ui.artefacts.artefacts')}</option>` + liste.map((a) =>
      `<option value="${a.id}" ${courant && courant.id === a.id ? 'selected' : ''}>${esc(a.titre)} (v${a.version})</option>`).join('');
  }

  // Extrait le texte d'un argument JSON encore incomplet ("contenu": "Madame, ...)
  function champPartiel(json, nom) {
    const m = json.match(new RegExp(`"${nom}"\\s*:\\s*"`));
    if (!m) return null;
    let i = m.index + m[0].length, brut = '';
    for (; i < json.length; i++) {
      const c = json[i];
      if (c === '\\') { brut += json.slice(i, i + 2); i++; continue; }
      if (c === '"') break;
      brut += c;
    }
    for (let coupe = 0; coupe <= 6; coupe++) {   // retire une sequence d'echappement coupee en fin de flux
      try { return JSON.parse(`"${brut.slice(0, brut.length - coupe)}"`); } catch (e) { /* on raccourcit */ }
    }
    return null;
  }

  // ---------- appele par agent_v2.js ----------
  window.Artefacts = {
    partiel(ev) {
      const contenu = champPartiel(ev.arguments, 'contenu');
      if (contenu === null) return;
      if (!courant || !courant.enCours) {
        courant = { id: null, titre: '', type: 'texte', contenu: '', version: null, enCours: true };
        vue = 'source';
      }
      courant.titre = champPartiel(ev.arguments, 'titre') || courant.titre || T('ui.artefacts.artefact');
      courant.type = champPartiel(ev.arguments, 'type') || courant.type;
      courant.contenu = contenu;
      $a('art-etat').style.display = 'block';
      $a('art-etat').textContent = `${T('ui.artefacts.l_agent_ecrit_v1_caracteres', {v1: contenu.length})}`;
      ouvrirPanneau(); dessiner();
    },
    afficher(a) {
      courant = { ...a, enCours: false };
      vue = 'apercu';
      $a('art-etat').style.display = 'none';
      ouvrirPanneau(); dessiner(); rafraichirListe();
    },
    async ouvrir(id) {
      const a = await api().artefact_lire(id);
      if (a) this.afficher(a);
    },
  };

  // ---------- boutons ----------
  $a('art-fermer').addEventListener('click', () => { panneau.style.display = 'none'; });
  $a('art-vue').addEventListener('click', () => { vue = vue === 'apercu' ? 'source' : 'apercu'; dessiner(); });
  $a('art-copier').addEventListener('click', async () => {
    if (!courant) return;
    try { await navigator.clipboard.writeText(courant.contenu); $a('art-copier').textContent = T('ui.artefacts.copie'); }
    catch (e) { $a('art-copier').textContent = T('ui.artefacts.echec'); }
    setTimeout(() => { $a('art-copier').textContent = T('ui.artefacts.copier'); }, 1500);
  });
  $a('art-enregistrer').addEventListener('click', async () => {
    if (!courant || !courant.id) return;
    const chemin = await api().artefact_enregistrer(courant.id);
    $a('art-etat').style.display = 'block';
    $a('art-etat').textContent = chemin ? `${T('ui.artefacts.enregistre_v1', {v1: chemin})}` : T('ui.artefacts.echec_de_l_enregistrement');
  });
  $a('art-liste').addEventListener('change', (e) => { if (e.target.value) window.Artefacts.ouvrir(e.target.value); });
})();
