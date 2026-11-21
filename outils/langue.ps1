# Textes des scripts PowerShell d'Agent Local : lus dans un fichier de langue (langues\<code>.json), jamais ecrits en dur.
# Usage : . .\outils\langue.ps1 ; Charger-Langue $dossierLangues $code ; T 'cle' @{ nom = valeur }
$script:TEXTES = @{}
function Charger-Langue([string]$dossier, [string]$code) {
    if (-not $code) { $code = (Get-UICulture).TwoLetterISOLanguageName }
    if (-not (Test-Path (Join-Path $dossier "$code.json"))) { $code = 'en' }
    $script:TEXTES = @{}
    foreach ($c in 'fr', 'en', $code) {   # francais, puis anglais en secours, puis la langue choisie (la derniere l'emporte)
        $f = Join-Path $dossier "$c.json"
        if (Test-Path $f) { (Get-Content $f -Raw -Encoding UTF8 | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $script:TEXTES[$_.Name] = $_.Value } }
    }
    return $code
}
function T([string]$cle, [hashtable]$valeurs = @{}) {
    $texte = if ($script:TEXTES.ContainsKey($cle)) { [string]$script:TEXTES[$cle] } else { $cle }
    foreach ($k in $valeurs.Keys) { $texte = $texte.Replace("{$k}", [string]$valeurs[$k]) }
    $texte
}
