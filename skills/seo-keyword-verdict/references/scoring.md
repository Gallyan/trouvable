# Score out of 100 and override gates

**Heuristic, design choice of this skill, to calibrate** on the user's own outcomes. The score
is a way to make the judgement explicit and comparable between queries, not a measurement.
Every component is `estimated` from the page-one table; say which rows drove it.

## Components

| Component | Max | 0 when | Max when |
|---|---|---|---|
| Beatable page one | 30 | All top results are large brands, official docs or publishers that answer fully | Several of the top 5 are forums, thin or off-intent pages, or small sites like the user's |
| Freshness gap | 15 | Top results are recent and cover the current version | Most cover an old version or are undated on a topic that moves |
| Answer gap | 20 | Every top result answers fully | Most answer partly or not at all |
| Demand signals | 15 | No signal found | Autocomplete, several recent threads, and/or Search Console impressions |
| Site fit | 10 | Off the site's topic, or needs expertise the site cannot show | Squarely in the site's topic, with first-hand experience to add |
| Format fit | 10 | Page one wants a format the user cannot produce (tool, product page, video) | The user can produce the dominant format |

Score bands: 70–100 → `WRITE`; 50–69 → `WRITE A NARROWER PAGE`; 0–49 → `DROP`.

For a site under about 6 months old (heuristic), subtract 10 from "Beatable page one" when the
top 5 are all established sites, and say so.

## Override gates

Run every gate after scoring. The first gate that triggers sets the verdict; list the others
that also triggered.

| # | Gate | Triggers when | Verdict |
|---|---|---|---|
| G1 | Policy | The only way to compete would be doorway pages, mass variants, fake reviews or bought links | `DROP` |
| G2 | Overlap | A page in the user's URL list already targets the same intent | `EXTEND AN EXISTING PAGE` (name it) |
| G3 | Too early | The subject is days old, page one is unsettled, and key facts are unconfirmed at their primary source | `WAIT` with a date, or write only confirmed facts if the user can be first and accepts to update |
| G4 | Format wall | Page one is entirely a format the user cannot produce | `DROP`, or `WRITE A NARROWER PAGE` if a neighbouring intent is open |
| G5 | No demand | No demand signal of any kind and no impressions | `WAIT` or `DROP`, never `WRITE` |
| G6 | Expertise | The topic affects health, money or safety and the site cannot show the needed expertise | `DROP` or a narrower angle the site can back |

A missing URL list is not a gate: the verdict stays, marked `PROVISIONAL`, because G2 could not
be checked.

## Judgement calls

Name the two or three calls with the largest effect, for example: "result 3 counted as
answering partly (+/- 5 on Answer gap)". If another reading of a second sample would change the
verdict, say so; giving two samples (A and B) with both scores is better than averaging.
