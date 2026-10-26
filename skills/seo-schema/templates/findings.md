## Constats

Gravité : `error` (le balisage contredit la page ou ne s'analyse pas), `warning` (risqué ou
incohérent), `info` (amélioration). Cette échelle de gravité est un choix de conception de ce skill.

| # | Gravité | Code | Page | Preuve littérale | Correctif (à la source) | Effort |
|---|---|---|---|---|---|---|
| 1 | error | M05 | {url} | balisage `"price": "19"` / visible « 29 € » (HTML statique, lu le {date}) | {gabarit/extension/composant et modification} | {S/M/L ou heures} |

## Faits en désaccord

| Fait | Page (visible) | Balisage | llms.txt | Lequel est juste ? |
|---|---|---|---|---|
| {p. ex. prix de l'offre X} | « {chaîne} » | « {valeur} » | « {chaîne} » | {à vous demander si inconnu} |
