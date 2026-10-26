# Audit du site — {site} — {date}

Exploration (crawl) : {n pages} pages lues sur {n découvertes} découvertes, {mode : complet | échantillon | léger | manuel},
{débit} requêtes/s, robots.txt respecté, lancée le {date} (`measured`).

## Synthèse

1. **État :** {une phrase}
2. **Risque principal :** {une phrase, avec l'identifiant du contrôle}
3. **Premier correctif :** {une phrase}
4. **Score :** {score}/100 — {couverture} % de la grille mesurés (`estimated`, méthode : `references/audit-rubric.md`)
5. **Hors de portée de cet audit :** indexation, requêtes et positions (Search Console), contenu rendu par JavaScript.

## Scores par domaine

| Domaine | Score | Couverture | Contrôles en échec | Contrôles non mesurés |
|---|---|---|---|---|
| A. Hôtes et redirections | | | | |
| B. Accès à l'exploration | | | | |
| C. Codes de statut | | | | |
| D. Directives d'indexabilité | | | | |
| E. Bases on-page | | | | |
| F. Métadonnées de partage | | | | |
| G. Images | | | | |
| H. Liens et architecture | | | | |
| **Global** | | | | |

## À corriger en premier (top 10)

| # | Contrôle | Gravité | Pages touchées | Preuve | Correctif exact | Effort | Fait quand |
|---|---|---|---|---|---|---|---|
| 1 | | | {n} sur {contrôlées} (`measured`) | {URL} → `{literal string or header}` | {fichier / réglage / gabarit} | {h} | {requête ou résultat de la nouvelle exploration qui le prouve} |

## Déjà en place

- {identifiant du contrôle — ce qui est conforme, sur combien de pages}

## Non mesuré

- {identifiant du contrôle — pourquoi (pas de sitemap, exploration arrêtée sur un 403, rendu JavaScript, parcours manuel…)}

## Faux positifs écartés

- {identifiant du contrôle — URL d'exemple — pourquoi ce n'est pas un problème}

## Plan sur 30 jours

| Semaine | Correctifs | Responsable | Vérification |
|---|---|---|---|
| 1 | {correctifs de gravité haute} | | redemander les URL concernées |
| 2 | | | |
| 3 | | | |
| 4 | | | nouvelle exploration complète, comparer scores et couverture |

Effets de ces correctifs sur le trafic : non prévus ; la fourchette inclut zéro.

Fichiers : `issues.csv`, `fix-tracker.csv`.
