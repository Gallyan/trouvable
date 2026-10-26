# Pipeline rules

How `prospects.csv` is kept. The user owns the file and edits it; scripts only read it.

## Stages

| Stage | Means | Moves on when |
|---|---|---|
| `lead` | A business that might need the work; no conversation yet, or one first exchange | A real need is confirmed in a conversation |
| `qualified` | Need, decision-maker and rough budget known | A proposal is sent |
| `proposal-sent` | The proposal is with the prospect | They say yes (`won`) or no (`lost`) |
| `won` | Signed or confirmed in writing | Work starts; it leaves the pipeline |
| `lost` | Declined, no budget, chose someone else, or stopped replying | Never reopened silently: add a new row if they come back |

`lost` always carries a `lost_reason` in a few words ("budget", "chose an agency", "no
reply after two follow-ups"). Reasons are what the user learns from; the script tallies them.

## Every open row

- One `next_action` the user can do in under an hour ("send the proposal", "call to go
  through findings"), with a `next_action_date`.
- `last_contact` updated after each real exchange.
- No contact for more than 30 days (default of `pipeline_status.py`, heuristic of this skill,
  to calibrate) makes a row stale: decide to follow up once or move it to `lost`.
- One follow-up after a proposal is normal; repeated chasing is not. After the second
  unanswered message, set `lost` with the reason "no reply".

## Values

- `value` is the amount of the proposal sent or expected, as the user prices it, with its
  `value_unit` (`one-off`, `per-month`, `per-day`). It is `reported` data, not a forecast.
- Never multiply values by a win probability or present the sum as expected revenue.

## Privacy

- Business contacts only. Record a role ("owner", "marketing lead") rather than a person's
  name when the role is enough; never private phone numbers, home addresses or personal
  social accounts.
- No scraping of contact details from the prospect's site or from directories, and no buying
  of contact lists. The user records the contacts they have.
- The file is the user's: they keep it where they choose, and delete a row when the prospect
  asks or when it is no longer needed. Under GDPR a prospect may ask what is held about them;
  a small file with roles and dates makes that easy to answer.
- The skill sends no email and automates no follow-up.

## Email and SMS rules in France (CNIL)

Read on 2026-10-25: cnil.fr/fr/communication-electronique-quelles-regles (page dated 10 June
2026) and article L34-5 of the Code des postes et des communications électroniques (Légifrance).

- L34-5 defines prospecting as any message « destiné à promouvoir, directement ou
  indirectement, des biens, des services ou l'image d'une personne ».
- To consumers (B2C), prospecting « repose, en principe, sur le recueil préalable du
  consentement », except existing customers for « produits ou services analogues fournis par la
  même personne ».
- To professionals (B2B), « Le consentement préalable n'est pas systématiquement requis » when
  the message is « en lien avec l'activité professionnelle de la personne contactée »; the
  recipient is told and can object simply, in every message.
- A message with « une part de contenu commercial » can be « requalifié en prospection
  commerciale ».

For prospects: a first email to a business about its own site is B2B prospecting: professional
address, a reason tied to their activity, the sender identified, an opt-out in every message,
and the row deleted or set to stop when they object. Never to a private address or phone.
