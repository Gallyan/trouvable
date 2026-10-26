# Pillar and cluster relation table

The relation table is the single source for every link brief and related-posts block. It is
drafted by Claude, then confirmed or edited by the user. No brief is written before that.

## Columns

| Column | Content |
|---|---|
| `pillar` | Short topic name |
| `pillar_url` | The page that covers the topic broadly |
| `cluster_url` | A page covering one sub-question of the pillar |
| `relation` | `pillar→cluster`, `cluster→pillar`, `cluster↔cluster` (siblings worth linking), `cross-pillar` |
| `language` | Page language; links stay within one language unless the user says otherwise |
| `current_editorial_links` | From the graph (`measured`) |
| `wanted` | `yes` / `no` / `already` |
| `confirmed` | Filled by the user: `yes`, `no`, or an edit |

## How to draft it

1. Candidate pillars: pages with the most editorial inlinks, section landing pages, and the
   topics the user named. Keep five at most for the first pass (heuristic).
2. Clusters: pages whose URL path, title and H1 belong to the pillar's topic. Read the title
   and first paragraph of each; do not rely on URL folders alone.
3. Pages that fit no pillar are listed apart: candidates for a new pillar, merging, or no
   action.
4. Pages that fit two pillars: pick one as primary, mark the other `cross-pillar`.

## Default link pattern (heuristic, to adapt)

- Every cluster links to its pillar once, in the content, early.
- The pillar links to each of its clusters, in the content or in a section listing them.
- Siblings link to each other only when one answers a question the other raises.
- Cross-pillar links only where the text calls for them.

## Page map

For each confirmed pillar, a small map: the pillar, its clusters, existing editorial links
(solid) and proposed ones (dashed), in a list or a Mermaid diagram if the user's tool shows
it.

```
pillar: {topic} — {pillar_url}
  ├── {cluster_url}   existing: pillar→cluster, cluster→pillar
  ├── {cluster_url}   proposed: cluster→pillar
  └── {cluster_url}   proposed: pillar→cluster, sibling→{cluster_url}
```
