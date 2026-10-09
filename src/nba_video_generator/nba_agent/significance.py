"""Rule-based pre-filter + Ollama-based judgment of "must-see" performances."""
import json
import requests

from .config import OLLAMA_HOST, OLLAMA_MODEL, THRESHOLDS, TRIPLE_DOUBLE_MIN


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
                if minutes[0] == ":":
                    minutes = "0" + minutes
            minutes = int(minutes.split(":")[0]) * 60 + int(minutes.split(":")[1])
            if minutes >= 15 * 60:
                candidates.append(
                    {**p, "TEAM": team_name, "REASON": describe(p)}
                )

    return candidates


def ollama_judge(candidates: list[dict]) -> list[dict]:
    """
    Ask a local Ollama model which pre-filtered candidates deserve
    highlight videos. Player and team names are excluded from the prompt.
    The model returns candidate IDs only; original candidate dicts
    are returned unchanged, including REASON.
    """
    if not candidates:
        return []

    lines = [
        f"- ID {i}: {c['REASON']}, +/- {c.get('+/-', '0')}"
        for i, c in enumerate(candidates)
    ]

    prompt = (
        "ROLE\n"
        "You are an NBA highlights producer deciding which performances "
        "deserve a highlight video tonight.\n\n"

        "INPUT\n"
        "Each candidate has a numeric ID and a verified statline. "
        "The REASON text is an immutable fact copied directly from the "
        "box score. Player and team identities are intentionally omitted. "
        "Judge performances solely on the supplied statistics.\n\n"

        + "\n".join(lines)
        + "\n\n"

        "HARD RULES\n"
        "1. Select only IDs present in the input.\n"
        "2. Never invent, restate, rephrase, round, recompute, or correct "
        "any statline or +/- value.\n"
        "3. Do not invent game context, such as the final score, opponent, "
        "game time, player role, or injuries.\n"
        "4. Judge only the statistics shown. Do not infer player or team "
        "identity.\n"
        "5. +/- is supporting evidence only and cannot independently "
        "justify a highlight.\n"
        "6. Return only the JSON object specified below.\n\n"

        "HIGHLIGHT STANDARD\n"
        "Keep a candidate only when the statline clearly supports a "
        "compelling NBA highlight video. The bar is high.\n\n"

        "STRONG REASONS TO KEEP\n"
        "- Elite scoring volume or efficiency.\n"
        "- A triple-double or quadruple-double.\n"
        "- Exceptional rebounding, especially offensive rebounding.\n"
        "- Defensive dominance through numerous steals or blocks.\n"
        "- Multiple strong statistical categories combining into an "
        "unusually impactful performance.\n\n"

        "AUTOMATIC OR NEAR-AUTOMATIC CUTS\n"
        "- Very low scoring without exceptional contributions elsewhere.\n"
        "- Poor scoring efficiency without enough production to offset it.\n"
        "- Ordinary rebounding or assists without standout overall output.\n"
        "- Zero steals and zero blocks without elite scoring, rebounding, "
        "playmaking, or a major statistical milestone.\n"
        "- High foul counts without exceptional positive production.\n"
        "- Strong +/- attached to an ordinary or inefficient statline.\n\n"

        "DECISION RULE\n"
        "Would this statline alone clearly justify an NBA highlight video? "
        "If no or borderline, cut it. Prefer false negatives over "
        "ordinary performances.\n\n"

        "OUTPUT FORMAT\n"
        'Return exactly one JSON object: {"keep": [0, 2, ...]}. '
        "Include only the numeric IDs of candidates to keep. "
        "Return {\"keep\": []} if none qualify. Do not return names, "
        "teams, statistics, explanations, or markdown."
    )

    while True:
        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "format": "json",
                    "stream": True,
                },
                timeout=1000,
            )
            break
        except Exception:
            continue

    resp.raise_for_status()

    content = ""
    try:
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue

            chunk = json.loads(line)
            content += chunk.get("message", {}).get("content", "")

            if chunk.get("done"):
                break

        keep_ids = set(json.loads(content)["keep"])

        # Validate IDs before filtering.
        if not isinstance(json.loads(content)["keep"], list):
            return candidates

        if any(
            type(i) is not int or i < 0 or i >= len(candidates)
            for i in keep_ids
        ):
            return candidates

    except (json.JSONDecodeError, KeyError, TypeError):
        return candidates

    return [
        candidate
        for i, candidate in enumerate(candidates)
        if i in keep_ids
    ]
