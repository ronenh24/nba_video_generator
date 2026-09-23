"""Rule-based pre-filter + Ollama-based judgment of "must-see" performances."""
import json
import requests

from .config import OLLAMA_HOST, OLLAMA_MODEL, THRESHOLDS, TRIPLE_DOUBLE_MIN, STAT_COLUMNS


def _num(value, default: float = 0.0) -> float:
    if value in ("", "-", None):
        return default
    try:
        return float(str(value).replace("+", ""))
    except ValueError:
        return default


def _triple_double_label(pts: float, reb: float, ast: float, stl: float, blk: float) -> str | None:
    """Return a factual 'Triple-double: 10 PTS, 11 AST, 10 REB' style label,
    or None if fewer than 3 categories are actually double-digit."""
    cats = [
        (label, val)
        for label, val in (("PTS", pts), ("REB", reb), ("AST", ast), ("STL", stl), ("BLK", blk))
        if val >= TRIPLE_DOUBLE_MIN
    ]
    if len(cats) < 3:
        return None
    name = "Quadruple-double" if len(cats) >= 4 else "Triple-double"
    return f"{name}: " + ", ".join(f"{v:.0f} {l}" for l, v in cats)


def describe(pts: float, reb: float, ast: float, stl: float, blk: float, tpm: float) -> str:
    """A short, factually-computed (never LLM-generated) reason string."""
    td = _triple_double_label(pts, reb, ast, stl, blk)
    if td:
        return td
    if pts >= THRESHOLDS["PTS"]:
        return f"{pts:.0f}-point game"
    if reb >= THRESHOLDS["REB"]:
        return f"{reb:.0f} rebounds"
    if ast >= THRESHOLDS["AST"]:
        return f"{ast:.0f} assists"
    if stl >= THRESHOLDS["STL"]:
        return f"{stl:.0f} steals"
    if blk >= THRESHOLDS["BLK"]:
        return f"{blk:.0f} blocks"
    if tpm >= THRESHOLDS["3PM"]:
        return f"{tpm:.0f} made threes"
    return "notable stat line"


def rule_based_candidates(team_name: str, players: list[dict]) -> list[dict]:
    """Players whose raw stat line clears any THRESHOLDS value, or a triple-double.
    Each candidate gets a REASON computed straight from the numbers — never from
    the LLM — so the eventual highlight caption can't misstate the box score."""
    candidates = []
    for p in players:
        pts, reb, ast = _num(p.get("PTS")), _num(p.get("REB")), _num(p.get("AST"))
        stl, blk, tpm = _num(p.get("STL")), _num(p.get("BLK")), _num(p.get("3PM"))

        double_digit_cats = sum(1 for v in (pts, reb, ast, stl, blk) if v >= TRIPLE_DOUBLE_MIN)

        hit_threshold = (
            pts >= THRESHOLDS["PTS"]
            or reb >= THRESHOLDS["REB"]
            or ast >= THRESHOLDS["AST"]
            or stl >= THRESHOLDS["STL"]
            or blk >= THRESHOLDS["BLK"]
            or tpm >= THRESHOLDS["3PM"]
            or double_digit_cats >= 3
        )

        if hit_threshold:
            candidates.append(
                {**p, "TEAM": team_name, "REASON": describe(pts, reb, ast, stl, blk, tpm)}
            )

    return candidates


def ollama_judge_rule_based(game_label: str, candidates: list[dict]) -> list[dict]:
    """
    Ask a local Ollama model which of the pre-filtered (and already
    factually-labeled) candidates is genuinely highlight-reel worthy —
    e.g. skip someone who padded a triple-double in a 30-point blowout loss.
    The model only returns keep/cut decisions; it never restates or invents
    stats, so its output can't misdescribe a player's line.
    Returns the kept candidate dicts unchanged (REASON included).
    """
    if not candidates:
        return []

    id_for = lambda c: f"{c['PLAYER']} ({c['TEAM']})"
    lines = [f"- {id_for(c)}: {c['REASON']}, +/- {c.get('+/-','0')}" for c in candidates]

    prompt = (
        "ROLE\n"
        "You are an NBA highlights producer picking which players from one "
        f"game ({game_label}) get a highlight video made tonight.\n\n"
        "INPUT\n"
        "Each line below is a candidate who already cleared a statistical "
        "bar. The REASON text for each was computed directly from the box "
        "score and is a verified, immutable fact — treat it the same way "
        "you'd treat a number handed to you by a calculator.\n\n"
        + "\n".join(lines)
        + "\n\n"
        "HARD RULES (breaking any of these makes your answer invalid)\n"
        "1. You may only choose from the exact candidates listed above. "
        "Never add a player, team, or stat that isn't already there.\n"
        "2. Never restate, rephrase, round, recompute, or 'correct' a "
        "REASON or +/- value. If you disagree with how impressive it "
        "sounds, that's a reason to cut the player, not to edit the text.\n"
        "3. Do not invent context you weren't given (final score, minute of "
        "the game, opponent record, etc.). Judge only from the REASON and "
        "+/- shown.\n"
        "4. Output ONLY the JSON object described below — no markdown code "
        "fences, no commentary, no explanation before or after it.\n\n"
        "SELECTION CRITERIA\n"
        "KEEP a player if their line reflects real, winning-relevant impact: "
        "elite scoring, a triple/quadruple-double, a rare stat combo, "
        "defensive dominance (steals/blocks), or a hot shooting night that "
        "plausibly moved the game (+/- is positive or close to even).\n"
        "CUT a player if the line looks like empty garbage-time stat "
        "padding: a clearly negative +/- (their team got blown out while "
        "they compiled the counting stats) with no other signal of impact.\n\n"
        "WORKED EXAMPLE (uses generic names, not part of this game — for "
        "format and judgment reference only)\n"
        "- A. Sample (XYZ): 34-point game, +/- 22\n"
        "- B. Example (XYZ): Triple-double: 11 PTS, 10 REB, 10 AST, +/- -28\n"
        'Correct output: {"keep": ["A. Sample (XYZ)"]}\n'
        "(B. Example is cut despite the triple-double label because a -28 "
        "+/- means it came in a lopsided loss with no real impact — this is "
        "exactly the kind of case to cut. Do not keep a player just because "
        "REASON contains an impressive-sounding phrase.)\n\n"
        "OUTPUT FORMAT\n"
        'Respond with exactly one JSON object: {"keep": ["Player Name (TEAM)", ...]} '
        "using the identical \"Player Name (TEAM)\" strings shown in the "
        'candidate list above (copy them verbatim). Use {"keep": []} if no '
        "one from this game's candidates is worth a highlight video."
    )

    resp = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "format": "json",
            "stream": False,
        },
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]

    try:
        keep_ids = set(json.loads(content).get("keep", []))
    except (json.JSONDecodeError, KeyError):
        # Model didn't return clean JSON — fail safe to the full rule-based
        # list rather than silently dropping a real performance.
        return candidates

    return [c for c in candidates if id_for(c) in keep_ids]


def ollama_judge(game_label: str, teams: dict[str, list[dict]]) -> list[dict]:
    """
    Send every player's full box-score stat line to Ollama.
    Ollama decides which players are worth highlighting.
    Returns the original player dictionaries unchanged.
    """

    players = []

    for team_name, team_players in teams.items():
        for player in team_players:
            players.append({
                **player,
                "TEAM": team_name,
            })

    if not players:
        return []

    lines = []

    for i, p in enumerate(players):
        stats = ", ".join(
            f"{column}={p.get(column, '')}"
            for column in STAT_COLUMNS
        )

        lines.append(
            f'{i}: {p["PLAYER"]} ({p["TEAM"]}): {stats}'
        )

    prompt = (
        "ROLE\n"
        "You are an NBA highlights producer. "
        f"Review every player from this game ({game_label}) and decide "
        "which performances deserve a highlight video.\n\n"

        "PLAYER DATA\n"
        "The following contains the complete box-score stat line for every "
        "player who played. Treat these numbers as authoritative.\n\n"

        + "\n".join(lines)

        + "\n\n"
        "RULES\n"
        "1. You may ONLY select players from the supplied list.\n"
        "2. Judge the complete stat line, including scoring, efficiency, "
        "rebounds, assists, steals, blocks, turnovers, and +/-.\n"
        "3. Consider genuinely notable performances such as elite scoring, "
        "triple-doubles, unusual statistical combinations, exceptional "
        "shooting, or major defensive production.\n"
        "4. Do not invent game context that is not provided.\n"
        "5. Do not invent, modify, or restate player statistics.\n"
        "6. Return player indexes rather than player names so there is no "
        "ambiguity when names are duplicated.\n"
        "7. It is valid to select nobody.\n\n"

        "OUTPUT\n"
        'Return exactly one JSON object in this format: '
        '{"keep": [0, 3, 7]}\n'
        "The numbers must correspond exactly to the player indexes above."
    )

    resp = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "format": "json",
            "stream": False,
        },
        timeout=120,
    )
    resp.raise_for_status()

    content = resp.json()["message"]["content"]

    try:
        keep_indexes = json.loads(content).get("keep", [])
        keep_indexes = {
            int(i) for i in keep_indexes
            if isinstance(i, (int, float, str)) and str(i).isdigit()
        }
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        # Fail safe: return nobody if the model gives malformed selection.
        return []

    return [
        player
        for i, player in enumerate(players)
        if i in keep_indexes
    ]
