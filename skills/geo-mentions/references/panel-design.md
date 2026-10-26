# Panel design

A panel is a fixed list of questions asked, unchanged, at baseline and at every re-test.
Change the wording and the comparison is lost: write a new panel and a new baseline instead.

## Size

- 15–30 **non-brand** questions per market, plus 3–5 **brand** questions scored apart.
- One panel per market. A market = language + country when answers depend on the country
  (pricing, availability, local services).

## Question families

| Family | Intent | Share of non-brand questions (heuristic, design choice of this skill, to calibrate) | Example shape (adapt, do not copy as-is) |
|---|---|---|---|
| Discovery | "what exists" | ~30 % | "What are good tools to {job} for {audience}?" |
| Comparison | "which is better" among named competitors or types | ~25 % | "{Competitor A} or {Competitor B} for {job}?" / "Alternatives to {Competitor A}?" |
| Problem | a pain, with no product in mind | ~25 % | "How do I {solve problem} without {constraint}?" |
| Decision | ready to choose or buy | ~20 % | "Which {category} should a {audience} pick in {year}?" |
| Brand (apart) | what the engine knows about the brand | 3–5 questions | "What is {Brand}?" / "Is {Brand} reliable?" / "{Brand} pricing" |

Brand questions check accuracy and collisions (wrong founder, merged with a same-name product,
outdated price). They never count towards presence.

## Neutral wording

- Never include the brand, its domain, its slogan or a feature only it has.
- No leading adjectives ("the best new privacy-first…") that describe only the user's product.
- Use the words buyers use: take them from forum threads, support emails, Search Console
  queries (`reported`) — not from the user's marketing copy.
- Comparison questions may name competitors, never the brand.
- Write each market's panel in its own language, by someone who speaks it; do not machine-translate
  a panel and present it as native.

## Repetitions and modes

| Mode | Runs per question per engine | Use |
|---|---|---|
| `quick` | 1 | First look; presence counts only, score marked indicative or not computed |
| `full` | 3, each in a fresh chat (no history, logged out or memory off when the engine allows it) | Baseline and re-tests |

Note for every run: engine, model or mode shown by the interface (`reported`), logged in or not,
country, date. Answers vary between runs; repetitions are what make the score a sample.

## Paste format for raw answers

One block per run, separated by a header line, so `parse_answers.py` (or a human) can split them:

```
### Q07 | perplexity | run 2 | 2026-10-16 | FR
<raw answer, copied in full>
Sources:
<every source link shown, one per line>
```

Ask the user to copy the whole answer including the sources list. A summary is not usable.

## Freezing

Before the first run, save the panel as `panel.csv` (see `templates/panel.csv`) with a version
and date. The re-test uses that file unchanged.
