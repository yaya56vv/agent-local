// Langue de l'interface : textes fournis par js/textes.js (ecrit par app.py au demarrage, d'apres langues/<code>.json).
// T('cle', {nom: valeur}) remplace {nom} ; les elements data-i18n (texte) et data-i18n-<attribut> sont traduits au chargement.
const TEXTES = window.TEXTES || {};
let LANGUE = window.LANGUE || 'fr';
function T(cle, valeurs) {
  let texte = TEXTES[cle] ?? cle;
  if (valeurs) for (const [nom, valeur] of Object.entries(valeurs)) texte = texte.split(`{${nom}}`).join(String(valeur));
  return texte;
}
function traduirePage(racine = document) {
  racine.querySelectorAll('[data-i18n]').forEach((e) => { e.textContent = T(e.dataset.i18n); });
  ['title', 'placeholder', 'aria-label'].forEach((attribut) => {
    racine.querySelectorAll(`[data-i18n-${attribut}]`).forEach((e) => e.setAttribute(attribut, T(e.getAttribute(`data-i18n-${attribut}`))));
  });
  document.documentElement.lang = LANGUE;
}
document.addEventListener('DOMContentLoaded', () => traduirePage());
