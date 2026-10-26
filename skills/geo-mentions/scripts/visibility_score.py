#!/usr/bin/env python3
"""Score AI-assistant visibility from a frozen panel and parsed runs, per references/scoring.md.

Usage:
    python3 scripts/visibility_score.py --panel panel.csv --runs runs.csv [--presence-checks checks.csv]
        [--brand-domain example.com] [--brand "Acme,Acme App"] [--seed 20261016] [--resamples 1000]
        [--min-runs 30] [--out score.json]

Components (heuristic weights, design choice of this skill, to calibrate): presence 50,
prominence 20, source coverage 15, accuracy 15. Composite score only with >= 30 non-brand runs
per engine in full mode (3 runs per question); otherwise presence counts only.

Network: none.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
from collections import Counter, OrderedDict
from typing import Dict, List, Optional, Tuple, TypedDict

from seokit.report import emit_json, today, untrusted
from seokit.tables import TableError, read_tables

WEIGHTS = {"presence": 50, "prominence": 20, "coverage": 15, "accuracy": 15}
POSITION_VALUES = {1: 1.0, 2: 0.7, 3: 0.5}
LATER_POSITION_VALUE = 0.3
TOP_DOMAINS = 10
FULL_MODE_RUNS = 3
BANDS = [(0, 14, "Absent"), (15, 34, "Marginal"), (35, 59, "Present"), (60, 79, "Strong"), (80, 100, "Leading")]
NO_SCORE = "indicative only / no score"
YES = {"yes", "y", "true", "1", "oui", "o"}
NO = {"no", "n", "false", "0", "non"}

RUN_COLUMNS = ["question_id", "engine", "run", "named", "position", "named_instead", "cited_domains"]
PANEL_COLUMNS = ["question_id", "family", "brand_question"]


class InputError(ValueError):
    pass


class Components(TypedDict):
    presence: Optional[float]
    prominence: Optional[float]
    coverage: Optional[float]
    accuracy: Optional[float]
    top_domains: List[str]
    top_domains_not_read: List[str]
    brand_runs_reviewed: int
    brand_runs_total: int


class EngineReport(TypedDict):
    engine: str
    runs: int
    non_brand_runs: int
    brand_runs: int
    mode_inferred: str
    presence_counts: Dict[str, object]
    unreviewed_ambiguous_runs: int
    components: Optional[Dict[str, object]]
    score: Optional[int]
    status: str
    reason_if_null: Optional[str]
    band: Optional[str]
    range: Optional[List[int]]
    range_label: str


class CompetitorRow(TypedDict):
    competitor_name: str
    runs_naming: int
    share: Optional[float]
    mean_position_value: Optional[float]
    families_led: List[str]
    engines: List[str]


def read_records(path: str, required: List[str]) -> List[Dict[str, str]]:
    """Rows of the first table of a file, keyed by lowercased header; InputError when a column is missing."""
    if not os.path.isfile(path):
        raise InputError(f"{path} not found")

    try:
        tables = read_tables(path)
    except TableError as error:
        raise InputError(str(error)) from error

    if not tables:
        raise InputError(f"{path}: no table found")

    table = tables[0]
    headers = [h.strip().lower() for h in table.headers]
    missing = [name for name in required if name not in headers]

    if missing:
        raise InputError(f"{path}: missing columns {', '.join(missing)}")

    return [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in table.rows]


def split_list(value: str) -> List[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def flag(value: str) -> Optional[bool]:
    folded = (value or "").strip().lower()

    if folded in YES:
        return True

    if folded in NO:
        return False

    return None


def position_value(named: bool, position: Optional[int]) -> float:
    if not named:
        return 0.0

    if position is None:
        return LATER_POSITION_VALUE

    return POSITION_VALUES.get(position, LATER_POSITION_VALUE)


def band_for(score: float) -> str:
    value = int(round(score))

    for low, high, name in BANDS:
        if low <= value <= high:
            return name

    return BANDS[-1][2] if value > 100 else BANDS[0][2]


def band_label(score: int, low: int, high: int) -> str:
    low_band = band_for(low)
    high_band = band_for(high)

    if low_band == high_band:
        return band_for(score)

    return f"{low_band} to {high_band}"


def wilson(successes: int, total: int, z: float = 1.96) -> Optional[List[float]]:
    if total == 0:
        return None

    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator

    return [round(max(0.0, centre - margin), 3), round(min(1.0, centre + margin), 3)]


def percentile(sorted_values: List[float], fraction: float) -> float:
    index = int(round(fraction * (len(sorted_values) - 1)))

    return sorted_values[index]


def normalise_domain(domain: str) -> str:
    value = domain.strip().lower()

    return value[4:] if value.startswith("www.") else value


class Run:
    def __init__(self, record: Dict[str, str], question: Dict[str, str]) -> None:
        self.question_id = record["question_id"]
        self.engine = record["engine"].strip()
        self.run = record["run"]
        self.family = question["family"].strip().lower()
        self.brand_question = flag(question["brand_question"]) is True
        self.named = flag(record["named"]) is True
        position = record.get("position", "").strip()
        self.position = int(position) if position.isdigit() else None
        self.named_instead = split_list(record["named_instead"])
        self.domains = [normalise_domain(d) for d in split_list(record["cited_domains"])]
        self.ambiguous = flag(record.get("ambiguous", "")) is True
        self.accurate = flag(record.get("accurate", ""))
        self.possible = split_list(record.get("possible_competitors", ""))

    @property
    def prominence(self) -> float:
        return position_value(self.named, self.position)

    def competitor_position(self, name: str) -> Optional[int]:
        if name not in self.named_instead:
            return None

        index = self.named_instead.index(name) + 1

        if self.named and self.position is not None and self.position <= index:
            index += 1

        return index


def components(non_brand: List[Run], brand_runs: List[Run], presence_checks: Dict[str, bool],
               own_domains: List[str]) -> Components:
    """The four score components (None when not measurable) and the domains used for coverage."""
    presence = sum(r.named for r in non_brand) / len(non_brand) if non_brand else None
    prominence = sum(r.prominence for r in non_brand) / len(non_brand) if non_brand else None
    top = top_domains(non_brand, own_domains)
    covered = [d for d in top if presence_checks.get(d) is True]
    not_read = [d for d in top if d not in presence_checks]
    coverage = len(covered) / len(top) if top else None
    reviewed = [r for r in brand_runs if r.accurate is not None]
    accuracy = sum(r.accurate is True for r in reviewed) / len(reviewed) if reviewed else None

    return {
        "presence": presence,
        "prominence": prominence,
        "coverage": coverage,
        "accuracy": accuracy,
        "top_domains": top,
        "top_domains_not_read": not_read,
        "brand_runs_reviewed": len(reviewed),
        "brand_runs_total": len(brand_runs),
    }


def top_domains(runs: List[Run], own_domains: List[str]) -> List[str]:
    counts: Counter = Counter()

    for run in runs:
        for domain in run.domains:
            if is_own(domain, own_domains):
                continue

            counts[domain] += 1

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))

    return [domain for domain, _ in ordered[:TOP_DOMAINS]]


def is_own(domain: str, own_domains: List[str]) -> bool:
    return any(domain == own or domain.endswith("." + own) for own in own_domains)


def measured(parts: Components) -> Dict[str, Optional[float]]:
    """The four weighted components, unweighted values by name, in WEIGHTS order."""
    return {
        "presence": parts["presence"],
        "prominence": parts["prominence"],
        "coverage": parts["coverage"],
        "accuracy": parts["accuracy"],
    }


def composite(parts: Components) -> Optional[float]:
    """Weighted sum of the components out of 100, or None when one is not measurable."""
    values = measured(parts)

    if any(value is None for value in values.values()):
        return None

    return sum(WEIGHTS[name] * value for name, value in values.items() if value is not None)


def by_question(runs: List[Run]) -> "OrderedDict[str, List[Run]]":
    grouped: "OrderedDict[str, List[Run]]" = OrderedDict()

    for run in runs:
        grouped.setdefault(run.question_id, []).append(run)

    return grouped


def bootstrap(non_brand: List[Run], brand_runs: List[Run], checks: Dict[str, bool], own: List[str],
              seed: int, resamples: int) -> Optional[List[int]]:
    """Resample questions (non-brand and brand sets apart) with replacement, recompute the score,
    return the 5th-95th percentile."""
    rng = random.Random(seed)
    non_brand_groups = list(by_question(non_brand).values())
    brand_groups = list(by_question(brand_runs).values())
    scores: List[float] = []

    for _ in range(resamples):
        sample_nb = [run for _ in non_brand_groups for run in rng.choice(non_brand_groups)]
        sample_b = [run for _ in brand_groups for run in rng.choice(brand_groups)]
        value = composite(components(sample_nb, sample_b, checks, own))

        if value is not None:
            scores.append(value)

    if not scores:
        return None

    scores.sort()

    return [int(round(percentile(scores, 0.05))), int(round(percentile(scores, 0.95)))]


def infer_mode(non_brand: List[Run]) -> str:
    groups = by_question(non_brand)

    if groups and all(len({r.run for r in runs}) >= FULL_MODE_RUNS for runs in groups.values()):
        return "full"

    return "quick"


def engine_report(engine: str, runs: List[Run], checks: Dict[str, bool], own: List[str],
                  args: argparse.Namespace) -> EngineReport:
    """Presence counts for one engine and, when the sample allows it, its score, bootstrap range and band.

    The score stays None, with reason_if_null, below --min-runs, outside full mode or with a component missing.
    """
    non_brand = [r for r in runs if not r.brand_question]
    brand_runs = [r for r in runs if r.brand_question]
    named = sum(r.named for r in non_brand)
    mode = infer_mode(non_brand)
    parts = components(non_brand, brand_runs, checks, own)
    report: EngineReport = {
        "engine": untrusted(engine),
        "runs": len(runs),
        "non_brand_runs": len(non_brand),
        "brand_runs": len(brand_runs),
        "mode_inferred": mode,
        "presence_counts": {
            "named": named,
            "non_brand_runs": len(non_brand),
            "text": f"named in {named} of {len(non_brand)} non-brand runs",
            "wilson_95_presence_only": wilson(named, len(non_brand)),
        },
        "unreviewed_ambiguous_runs": sum(r.ambiguous for r in runs),
        "components": None,
        "score": None,
        "status": NO_SCORE,
        "reason_if_null": None,
        "band": None,
        "range": None,
        "range_label": "estimated",
    }

    reasons = []

    if len(non_brand) < args.min_runs:
        reasons.append(f"sample too small: {len(non_brand)} non-brand runs, minimum {args.min_runs}")

    if mode != "full":
        reasons.append(f"not full mode: fewer than {FULL_MODE_RUNS} runs for some non-brand question")

    if reasons:
        report["reason_if_null"] = "score not computed: " + "; ".join(reasons)
        return report

    report["components"] = {
        "presence": rounded(parts["presence"]),
        "prominence": rounded(parts["prominence"]),
        "coverage": rounded(parts["coverage"]),
        "accuracy": rounded(parts["accuracy"]),
        "weights": WEIGHTS,
        "coverage_top_domains": [untrusted(d) for d in parts["top_domains"]],
        "coverage_not_read_counted_absent": [untrusted(d) for d in parts["top_domains_not_read"]],
        "accuracy_brand_runs_reviewed": parts["brand_runs_reviewed"],
    }

    total = composite(parts)

    if total is None:
        missing = [name for name, value in measured(parts).items() if value is None]
        hints = {
            "accuracy": "no brand run with an 'accurate' yes/no column filled",
            "coverage": "no cited domain in non-brand runs",
            "presence": "no non-brand run",
            "prominence": "no non-brand run",
        }
        report["reason_if_null"] = "score not computed: " + "; ".join(
            f"{name} not measurable ({hints[name]})" for name in missing)
        return report

    score = int(round(total))
    low_high = bootstrap(non_brand, brand_runs, checks, own, args.seed, args.resamples)
    report["score"] = score
    report["status"] = "scored"
    report["range"] = low_high
    report["band"] = band_label(score, low_high[0], low_high[1]) if low_high else band_for(score)

    return report


def rounded(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 3)


def competitor_ranking(non_brand: List[Run]) -> List[CompetitorRow]:
    """Competitors named in non-brand runs, by share of runs then mean position value."""
    names: List[str] = []

    for run in non_brand:
        for name in run.named_instead:
            if name not in names:
                names.append(name)

    total = len(non_brand)
    families = sorted({r.family for r in non_brand})
    ranking: List[CompetitorRow] = []

    for name in names:
        hits = [r for r in non_brand if name in r.named_instead]
        values = [position_value(True, r.competitor_position(name)) if name in r.named_instead else 0.0
                  for r in non_brand]
        leads = [family for family in families if leads_family(name, family, non_brand)]
        ranking.append({
            "competitor_name": untrusted(name),
            "runs_naming": len(hits),
            "share": round(len(hits) / total, 3) if total else None,
            "mean_position_value": round(sum(values) / total, 3) if total else None,
            "families_led": leads,
            "engines": sorted({untrusted(r.engine) for r in hits}),
        })

    ranking.sort(key=lambda item: (-(item["share"] or 0), -(item["mean_position_value"] or 0),
                                 item["competitor_name"]))

    return ranking


def leads_family(name: str, family: str, non_brand: List[Run]) -> bool:
    """True when this competitor is named in more runs of the family than the brand and
    than every other competitor."""
    runs = [r for r in non_brand if r.family == family]
    counts: Counter = Counter()

    for run in runs:
        for other in run.named_instead:
            counts[other] += 1

    mine = counts.get(name, 0)

    if mine == 0:
        return False

    brand = sum(r.named for r in runs)
    rivals = [count for other, count in counts.items() if other != name] + [brand]

    return all(mine > count for count in rivals)


def families_report(non_brand: List[Run]) -> Dict[str, object]:
    """Brand presence in non-brand runs per question family, overall and per engine."""
    result: Dict[str, object] = {}

    for family in sorted({r.family for r in non_brand}):
        runs = [r for r in non_brand if r.family == family]
        named = sum(r.named for r in runs)
        per_engine = {}

        for engine in sorted({r.engine for r in runs}):
            engine_runs = [r for r in runs if r.engine == engine]
            per_engine[untrusted(engine)] = {
                "non_brand_runs": len(engine_runs),
                "named": sum(r.named for r in engine_runs),
            }

        result[untrusted(family)] = {
            "non_brand_runs": len(runs),
            "named": named,
            "share": round(named / len(runs), 3) if runs else None,
            "per_engine": per_engine,
        }

    return result


def cited_domains_report(runs: List[Run], checks: Dict[str, bool], own: List[str]) -> List[Dict[str, object]]:
    """Every cited domain, most cited first, with its engines and whether the brand was found on it."""
    counts: Counter = Counter()
    engines: Dict[str, set] = {}

    for run in runs:
        for domain in run.domains:
            counts[domain] += 1
            engines.setdefault(domain, set()).add(run.engine)

    rows: List[Dict[str, object]] = []

    for domain, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        if domain in checks:
            present = "yes" if checks[domain] else "no"
            label = "measured"
        else:
            present = "not read"
            label = "not read"

        rows.append({
            "domain": untrusted(domain),
            "times_cited": count,
            "engines": sorted(untrusted(e) for e in engines[domain]),
            "brand_present": present,
            "brand_present_label": label,
            "own_site": is_own(domain, own),
        })

    return rows


def load_checks(path: Optional[str]) -> Dict[str, bool]:
    if not path:
        return {}

    checks: Dict[str, bool] = {}

    for record in read_records(path, ["domain", "brand_present"]):
        value = flag(record["brand_present"])

        if value is None:
            continue

        checks[normalise_domain(record["domain"])] = value

    return checks


def build_runs(panel: List[Dict[str, str]], records: List[Dict[str, str]],
               warnings: List[str]) -> List[Run]:
    """Runs matched to their panel question (by market too when the panel has several); others become a warning."""
    multi_market = len({q.get("market", "") for q in panel}) > 1
    questions: Dict[Tuple[str, str], Dict[str, str]] = {}

    for question in panel:
        market = question.get("market", "") if multi_market else ""
        questions[(market, question["question_id"].strip())] = question

    runs: List[Run] = []
    unknown: List[str] = []

    for record in records:
        market = record.get("market", "") if multi_market else ""
        key = (market, record["question_id"].strip())
        matched = questions.get(key)

        if matched is None:
            unknown.append(record["question_id"])
            continue

        runs.append(Run(record, matched))

    if unknown:
        warnings.append(f"{len(unknown)} runs ignored: question_id not in the panel "
                        f"({untrusted(', '.join(sorted(set(unknown))))})")

    return runs


def panel_warnings(panel: List[Dict[str, str]], runs: List[Run], brand: List[str],
                   warnings: List[str]) -> None:
    """Warn about questions an engine was not asked, ambiguous runs and brand names in non-brand questions."""
    asked = {(r.engine, r.question_id) for r in runs}
    engines = sorted({r.engine for r in runs})

    for engine in engines:
        missing = [q["question_id"] for q in panel if (engine, q["question_id"].strip()) not in asked]

        if missing:
            warnings.append(f"{untrusted(engine)}: no run for {untrusted(', '.join(missing))}")

    ambiguous = [f"{r.engine} {r.question_id} run {r.run}" for r in runs if r.ambiguous]

    if ambiguous:
        warnings.append("ambiguous=yes still set (counted as given in 'named'; review by hand): "
                        + (untrusted("; ".join(ambiguous), limit=1000)))

    if not brand:
        return

    for question in panel:
        if flag(question["brand_question"]) is True:
            continue

        text = question.get("question", "").casefold()

        for name in brand:
            if name.casefold() in text:
                warnings.append(f"non-brand question {untrusted(question['question_id'])} contains "
                                f"the brand name '{untrusted(name)}': panel not neutral")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score AI visibility per references/scoring.md (no network). Weights, bands, "
                    "position values and the minimum sample are heuristics, design choices of this "
                    "skill, to calibrate. Add an 'accurate' yes/no column to brand-question runs.",
    )
    parser.add_argument("--panel", required=True, help="frozen panel.csv (templates/panel.csv)")
    parser.add_argument("--runs", required=True, help="runs CSV from parse_answers.py, ambiguous rows reviewed")
    parser.add_argument("--presence-checks", help="CSV domain,brand_present (yes/no) from reading cited pages")
    parser.add_argument("--brand-domain", default="", help="comma-separated brand domains, excluded from coverage")
    parser.add_argument("--brand", default="", help="comma-separated brand aliases, to check panel neutrality")
    parser.add_argument("--seed", type=int, default=20261016, help="bootstrap seed (fixed by default)")
    parser.add_argument("--resamples", type=int, default=1000, help="bootstrap resamples (default 1000)")
    parser.add_argument("--min-runs", type=int, default=30,
                        help="minimum non-brand runs per engine for a score (default 30, heuristic)")
    parser.add_argument("--out", help="also write the JSON to this path")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Score the runs per engine and print the JSON (also written to --out); returns 2 on bad input."""
    args = build_parser().parse_args(argv)

    if args.resamples < 1 or args.min_runs < 1:
        print("error: --resamples and --min-runs must be positive", file=sys.stderr)
        return 2

    try:
        panel = read_records(args.panel, PANEL_COLUMNS)
        records = read_records(args.runs, RUN_COLUMNS)
        checks = load_checks(args.presence_checks)
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    warnings: List[str] = []
    runs = build_runs(panel, records, warnings)

    if not runs:
        print("error: no run matches a panel question", file=sys.stderr)
        return 2

    own = [normalise_domain(d) for d in args.brand_domain.split(",") if d.strip()]
    brand = [b.strip() for b in args.brand.split(",") if b.strip()]
    panel_warnings(panel, runs, brand, warnings)

    if not own:
        warnings.append("no --brand-domain: the brand's own site is not excluded from coverage")

    engines = sorted({r.engine for r in runs})
    reports = [engine_report(e, [r for r in runs if r.engine == e], checks, own, args) for e in engines]
    scores = [rep["score"] for rep in reports if rep["score"] is not None]
    overall: Dict[str, object] = {"score": None, "reason_if_null": None}

    if len(scores) == len(reports) and len(reports) > 1:
        overall_score = int(round(sum(scores) / len(scores)))
        overall["score"] = overall_score
        overall["band"] = band_for(overall_score)
        overall["engines"] = [rep["engine"] for rep in reports]
    elif len(reports) == 1:
        overall["reason_if_null"] = "single engine: see its own score, labelled with that engine only"
    else:
        overall["reason_if_null"] = "engines are averaged only when every engine meets the minimum sample"

    non_brand = [r for r in runs if not r.brand_question]
    possible = Counter(name for r in non_brand for name in r.possible)
    output = {
        "generated_on": today(),
        "method": "references/scoring.md; weights, bands and thresholds are heuristics to calibrate; "
                  "a sample score, not a measure of any engine's ranking",
        "seed": args.seed,
        "resamples": args.resamples,
        "engines": reports,
        "overall": overall,
        "competitors": competitor_ranking(non_brand),
        "possible_competitors_unreviewed": [
            {"name_text": untrusted(name), "runs": count} for name, count in possible.most_common(20)
        ],
        "cited_domains": cited_domains_report(runs, checks, own),
        "families": families_report(non_brand),
        "warnings": warnings,
        "not_measured": [
            "recommendation vs passing or negative mention (parse_answers counts any mention)",
            "brand presence on cited domains without --presence-checks ('not read', counted absent)",
            "engines not present in the runs file",
        ],
    }

    emit_json(output)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            emit_json(output, handle)

    return 0


if __name__ == "__main__":
    sys.exit(main())
