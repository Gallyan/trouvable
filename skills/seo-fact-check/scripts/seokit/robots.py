"""robots.txt matching per RFC 9309, the way Google applies it.

urllib.robotparser is not used: it applies the first matching rule in file order, so
"Allow: /" written before "Disallow: /private" allows everything. RFC 9309 uses the most
specific rule (longest pattern), Allow winning ties, and merges every group that names
the same user agent.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import List, Optional, Tuple

Rule = Tuple[str, str, str]           # (allow|disallow, pattern, literal line)
Group = Tuple[List[str], List[Rule]]  # (lowercased user agents, rules)


def parse(text: str) -> List[Group]:
    """Groups in file order. A user-agent line after rules starts a new group; rules
    before any user-agent line are ignored."""
    groups: List[Group] = []
    agents: List[str] = []
    rules: List[Rule] = []

    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()

        if ":" not in line:
            continue

        name, value = line.split(":", 1)
        name = name.strip().lower()
        value = value.strip()

        if name == "user-agent":
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []

            agents.append(value.lower())
        elif name in ("allow", "disallow") and agents:
            rules.append((name, value, raw.strip()))

    if agents:
        groups.append((agents, rules))

    return groups


def product_token(user_agent: str) -> str:
    """'seokit-audit/0.1 (+...)' -> 'seokit-audit'."""
    token = re.split(r"[/\s]", (user_agent or "").strip(), maxsplit=1)[0]

    return token.lower() or "*"


def rules_for(groups: List[Group], agent: str) -> Tuple[List[str], List[Rule]]:
    """Rules of every group naming this agent, else of every '*' group (merged)."""
    agent = agent.lower()
    specific = [g for g in groups if agent != "*" and agent in g[0]]
    chosen = specific or [g for g in groups if "*" in g[0]]
    agents: List[str] = []
    rules: List[Rule] = []

    for group_agents, group_rules in chosen:
        agents += group_agents
        rules += group_rules

    return agents, rules


def rule_matches(pattern: str, path: str) -> bool:
    """'*' matches any run of characters, a final '$' anchors the end. No regex: the pieces
    between '*' are searched left to right (leftmost match is always enough for '*'-only
    patterns), so a hostile pattern such as '/*a*a*a*a*b' cannot cause backtracking."""
    if not pattern:
        return False

    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    pieces = body.split("*")

    if len(pieces) == 1:
        return path == body if anchored else path.startswith(body)

    first, middle, last = pieces[0], pieces[1:-1], pieces[-1]

    if not path.startswith(first):
        return False

    position = len(first)

    for piece in middle:
        found = path.find(piece, position)

        if found < 0:
            return False

        position = found + len(piece)

    if anchored:
        return path.endswith(last) and len(path) - len(last) >= position

    return path.find(last, position) >= 0


def path_of(url: str) -> str:
    """Path and query of a URL, as robots.txt rules match them ("/" for an empty path)."""
    parts = urllib.parse.urlsplit(url)

    return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")


def deciding_rule(groups: List[Group], agent: str, url: str) -> Optional[Rule]:
    """The rule that decides url for agent: longest pattern, Allow on ties. None: no rule."""
    _, rules = rules_for(groups, agent)
    path = path_of(url)
    best: Optional[Rule] = None

    for kind, pattern, literal in rules:
        if not rule_matches(pattern, path):
            continue

        if best is None or len(pattern) > len(best[1]) or (len(pattern) == len(best[1]) and kind == "allow"):
            best = (kind, pattern, literal)

    return best


def disallowing_rule(groups: List[Group], agent: str, url: str) -> Optional[Tuple[List[str], str]]:
    """(agents of the group, literal Disallow line) when url is blocked for agent, else None."""
    best = deciding_rule(groups, agent, url)

    if best is None or best[0] == "allow":
        return None

    return rules_for(groups, agent)[0], best[2]


def allowed(groups: List[Group], agent: str, url: str) -> bool:
    """True unless a Disallow rule decides the URL for the agent; /robots.txt itself is always allowed."""
    if urllib.parse.urlsplit(url).path == "/robots.txt":
        return True

    return disallowing_rule(groups, agent, url) is None
