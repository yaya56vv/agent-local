# Garde-fous

**English: [garde-fous.md](garde-fous.md)**

Règle de conception : **une protection est dans le code, jamais seulement dans la consigne du modèle.** Quoi que pense le modèle, une action protégée ne passe pas. Les numéros renvoient aux commentaires de `noyau/agent.py`.

## Niveaux d'autonomie (`noyau/reglages.py`)

| | Prudent (défaut) | Équilibré | Autonome |
|---|---|---|---|
| Lire fichiers, pages, matériel | libre | libre | libre |
| Écrire un fichier | accord | libre dans le dossier de sortie, accord ailleurs | libre dans les dossiers personnels, accord ailleurs |
| Cliquer et taper dans un logiciel (Windows-MCP) | accord | accord | libre |
| Navigateur : se déplacer, lire | libre | libre | libre |
| Navigateur : cliquer, remplir | accord | libre, sauf envoi, paiement, mot de passe | libre, sauf envoi, paiement, mot de passe |
| Lancer un programme | accord | accord | libre |
| Supprimer | interdit par Windows-MCP ; Corbeille sur accord | Corbeille, sur accord | Corbeille, sur accord |
| PowerShell qui modifie, administrateur, installation de logiciels | accord | accord | accord |
| Envoyer des données (cloud, n8n, formulaire, message, e-mail, achat, paiement) | accord | accord | accord |
| Tâche planifiée (personne ne surveille) | lecture seule | lecture seule | les accords sont refusés d'office |
| Apprendre une nouvelle fiche de compétence | accord | accord | libre |

## Toujours actifs

1. **Zone interdite** (garde-fous 1 et 6) : le dossier d'installation (code, réglages, carnet, conversations) ne peut être ni lu ni modifié, par aucun outil. Une commande PowerShell, une mission Hermès ou un chemin qui le cite sont refusés, quelle que soit leur écriture (`/` ou `\`, variables `%USERPROFILE%` et `$env:USERPROFILE`, `~`, nom court `8.3`).
2. **Écraser un fichier** redemande l'accord (garde-fou 2).
3. **Journal** de tout ce qui modifie (garde-fou 3), visible et effaçable dans Réglages → Mes données.
4. **Navigateur** (garde-fou 4, `garde_navigateur.py`) : jamais de mot de passe, de code ou de numéro de carte tapé par l'agent ; adresses locales et du réseau privé refusées ; seulement http et https ; envoi de formulaire et boutons d'engagement sur accord.
5. **Messagerie** (garde-fou 5) : seul le déplacement de INBOX vers « Tri Agent Local » est permis ; suppression, envoi et archivage sont invisibles pour le modèle.
6. **PowerShell trié** (garde-fou 6) : l'analyseur de PowerShell liste chaque commande appelée ; seules les lectures passent sans accord.
7. **Hors des dossiers personnels** (garde-fou 7) : une modification ailleurs demande l'accord.
8. **Filet de sécurité** (garde-fou 8, `filet.py`) : copie de chaque fichier avant modification, gardée 7 jours ; bouton « Annuler la dernière modification ».
9. **Word et Excel** (garde-fou 9) : jamais écrits avec les outils texte, qui les abîmeraient.
10. **Windows-MCP** (garde-fou 10) : lecture libre ; écriture de fichiers et du registre sur accord ; suppression vers la Corbeille (ou interdite en Prudent) ; adresses locales refusées.
11. **Tâches planifiées** (garde-fou 11) : en Prudent et Équilibré, seules les lectures s'exécutent.

## Outils administrateur (facultatifs, `outils-admin/`)

- **Trousse de réparation** : l'agent ne fait que choisir un geste dans une liste fermée. Avant chaque geste, une fenêtre « Agent Local - confirmation administrateur » s'ouvre sur l'écran. Comme elle appartient à un processus administrateur, Windows interdit à un programme ordinaire d'y cliquer : une fausse demande déposée par un logiciel malveillant ne peut rien faire sans votre clic. Sans réponse en 10 minutes, le geste est refusé.
- **Santé du PC** : les outils lancés en administrateur sont copiés dans `C:\Program Files\AgentLocal\Outils`, où seuls les administrateurs peuvent écrire. À chaque lancement, Autoruns doit avoir une signature Microsoft valide, et chaque fichier de code de LibreHardwareMonitor doit avoir l'empreinte SHA-256 relevée à l'installation. Un fichier changé, manquant ou en trop bloque le lancement, ce que Réglages affiche en clair, avec un bouton « Réparer / mettre à jour ». Les tâches Autoruns et Disques tournent sous le compte Système, pour fonctionner aussi avec un compte standard : votre compte peut les lancer, mais pas les modifier.
- Les droits sont vérifiés par identifiant de sécurité (SID), ce qui fonctionne quelle que soit la langue de Windows.
- **Jamais d'écrasement silencieux** : ces scripts n'utilisent que leurs propres noms (`C:\ProgramData\AgentLocal`, `C:\Program Files\AgentLocal`, dossier `\AgentLocal\` du Planificateur de tâches). S'ils trouvent un élément de ce nom qu'ils n'ont pas créé, ils le montrent et demandent de taper OUI avant de le remplacer.

## Secrets

Les clés et jetons sont enregistrés dans `%APPDATA%\AgentLocal\secrets`, réservé à votre compte Windows. Ils ne sont jamais écrits dans `config.json`, jamais affichés après leur saisie, et jamais envoyés au conseiller cloud.
