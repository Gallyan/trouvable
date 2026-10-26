# Reviews: Google's rules and French law

Read on 2026-10-25 on official pages. Re-open them before quoting; date the reading.

## Google

| Rule | Quote | Source |
|---|---|---|
| Asking is allowed | "you can ask customers to visit a Google link or scan a QR code"; incentives are "strictly prohibited" | support.google.com/business/answer/3474122 |
| No review gating | Merchants must not "Discourage or prohibit negative reviews, or selectively solicit positive reviews from customers" | support.google.com/contributionpolicy/answer/7400114 |
| No conflict of interest | "A conflict of interest may include current or former employment"; no review quotas for staff | same |
| No incentive | Not allowed: "reviews and ratings influenced by a payment, discount, free goods or services, or any other benefit" | support.google.com/contributionpolicy/answer/16597558 (read in part) |
| No stars from own reviews | "If the entity that's being reviewed controls the reviews about itself, their pages that use LocalBusiness or any other type of Organization structured data are ineligible for star review feature." | developers.google.com/search/docs/appearance/structured-data/review-snippet (updated 2026-09-08) |

So: ask every customer the same way, with the same link, after the service, with nothing in
return; never filter who is asked by how satisfied they seem; owner, staff and family do not
review.

## French law (Code de la consommation, Légifrance)

| Article | What it requires | Who it binds |
|---|---|---|
| L111-7-2 (in force since 17 Feb 2024) | Anyone who collects, moderates or publishes consumer reviews gives fair information on how: « Elle précise si ces avis font ou non l'objet d'un contrôle »; « Elle affiche la date de l'avis et ses éventuelles mises à jour. »; a free, reasoned reporting feature for professionals | A site that publishes reviews on its own pages, or a review widget it runs |
| D111-9 to D111-12 (renumbered from D111-16 to D111-19 by décret n° 2024-753, in force since 9 July 2024) | D111-10: say whether reviews are checked, show « La date de publication de chaque avis, ainsi que celle de l'expérience de consommation », the ranking criteria (chronological among them), whether reviews were rewarded, how long they stay; D111-11 and D111-12: when reviews are checked, the checks and « Les motifs justifiant un refus de publication de l'avis », and the author is told why | same |
| L121-4, 21° | Misleading practice: « se présenter faussement comme un consommateur » | Anyone |
| L121-4, 27° and 28° | Claiming reviews come from real buyers without the steps to verify it; « De diffuser ou faire diffuser par une autre personne morale ou physique des faux avis », or editing reviews to promote products | Anyone, including the business and any agency it pays |

Quote the article numbers above, not the old D111-16 to D111-19 (the DGCCRF page below still
cites the old numbers).

DGCCRF, « Avis en ligne : attention aux faux commentaires ! » (economie.gouv.fr, written
27/03/2024, read from a PDF given by the user on 2026-10-25):

- Practices found in its investigations: « modération biaisée des avis, en supprimant tout ou
  partie des avis négatifs ou en différant la publication des avis négatifs », fake reviews by
  the business, its circle or specialised providers, consumers recruited to post for a reward.
- Penalty for these misleading practices: « deux ans d'emprisonnement et 300 000 euros
  d'amende », which can rise to 10 % of average annual turnover or 50 % of the spending on the
  practice; « Le fait d'apporter sciemment aide ou assistance est puni des mêmes peines »: an
  agency or freelancer who helps is exposed too.
- Voluntary standard NF ISO 20488 (collecting, moderating and publishing online reviews): no
  bought reviews, all positive and negative reviews published, most recent first.

## Where this lands in a deliverable

- A review request (email, SMS, card at the counter) asks everyone, says nothing about the
  expected rating, offers nothing, gives the direct link.
- Reviews shown on the site: date of the review and of the experience, whether they were
  checked, link to the source; no `AggregateRating` markup expecting stars for the business's
  own reviews.
- Replying to reviews, negative ones included, is the owner's job; Claude drafts, the owner
  posts.

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

Asking a past customer for a review: no official CNIL statement found on 2026-10-25. The CNIL
page separates prospecting from transactional and relationship messages, and gives anonymous
surveys that « découlent directement du service demandé et ne visent pas à promouvoir d'autres
offres » as possibly not prospecting (SAN-2024-002). This is a reading, not a rule: keep the
request free of any offer or promotion, send it only to real customers, include an opt-out, and
never write again to someone who objected.
