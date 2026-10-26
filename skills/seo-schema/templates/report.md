# Données structurées — {site} — {date}

## Non audité

- Pages hors échantillon : {n} sur {total du sitemap} (`measured`). Échantillon : {mode de sélection}.
- Contenu inséré par JavaScript : non vu (HTML statique uniquement).
- Non lu : {url — raison (statut, page de vérification anti-robot, délai dépassé)}.
- Script ou parcours manuel : {lequel}.

## Verdict

1. {état du balisage en une ligne}
2. {désaccord le plus grave entre la page et le balisage}
3. {deuxième constat le plus grave, ou ce qui est en bon état}
4. {ce qu'un balisage valide implique et n'implique pas, d'après le tableau des règles daté}
5. **Première action :** {un changement, à quel endroit}

## Tableau des règles (lu le {date})

| Type | Fonctionnalité dans Google (telle que documentée) | Propriétés requises | Règles de contenu | URL de la source | Lu le |
|---|---|---|---|---|---|

## Constats

{tableaux issus de templates/findings.md}

## Plan de correction (par risque)

| Ordre | Correctif | Où il est généré | Pages touchées | Effort | Fait quand |
|---|---|---|---|---|---|
| 1 | | | | | une nouvelle exécution du vérificateur montre que {code} a disparu sur {pages} |

## À lancer dans un navigateur (hors de portée de ce skill)

- Outil de test des résultats enrichis de Google et un validateur schema.org sur : {urls} (noms des outils tels que relevés le {date})
- Rapports Search Console à suivre : {tels que nommés dans l'interface le {date}}

## Balisage généré (si demandé)

```json
{JSON-LD avec "{À COMPLÉTER : ...}" pour chaque fait non visible sur la page}
```

## Non mesuré

- {quoi, pourquoi}
