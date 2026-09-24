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


def describe(p: dict) -> str:
    """A short, factually-computed (never LLM-generated) reason string."""
    minutes = p["MIN"] + " Minutes"
    pts = p["PTS"] + " Points (" + p["FGM"] + "-" + p["FGA"] + " FG, " + \
        p["3PM"] + "-" + p["3PA"] + " 3PT, " + \
        p["FTM"] + "-" + p["FTA"] + " FT)"
    rb = p["REB"] + " Rebounds (" + p["OREB"] + " OREB, " + p["DREB"] + " DREB)"
    ast = p["AST"] + " Assists (" + p["TO"] + " Turnovers)"
    stl = p["STL"] + " Steals"
    blk = p["BLK"] + " Blocks"
    pf = p["PF"] + " Fouls"
    pm = "+/- " + p["+/-"]

    return ", ".join([minutes, pts, rb, ast, stl, blk, pf, pm])


def rule_based_candidates(team_name: str, players: list[dict], threshold: bool = True) -> list[dict]:
    """Players whose raw stat line clears any THRESHOLDS value, or a triple-double.
    Each candidate gets a REASON computed straight from the numbers — never from
    the LLM — so the eventual highlight caption can't misstate the box score."""
    candidates = []
    for p in players:
        if threshold:
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
                    {**p, "TEAM": team_name, "REASON": describe(p)}
                )
        else:
            minutes = p["MIN"]
            if minutes.startswith("0"):
                minutes = minutes[1:]
            minutes = int(minutes.split(":")[0]) * 60 + int(minutes.split(":")[1])
            if minutes >= 15 * 60:
                candidates.append(
                    {**p, "TEAM": team_name, "REASON": describe(p)}
                )

    return candidates


def ollama_judge(game_label: str, candidates: list[dict]) -> list[dict]:
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
            "stream": True,
        },
        timeout=120,
    )
    resp.raise_for_status()

    content = ""

    for line in resp.iter_lines():
        if line:
            chunk = line.decode("utf-8")
            data = json.loads(chunk)

            content += data.get("message", {}).get("content", "")

    try:
        keep_ids = set(json.loads(content).get("keep", []))
    except (json.JSONDecodeError, KeyError):
        # Model didn't return clean JSON — fail safe to the full rule-based
        # list rather than silently dropping a real performance.
        return candidates

    return [c for c in candidates if id_for(c) in keep_ids]
