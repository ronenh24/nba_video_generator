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
        "You are an NBA highlights producer picking which players from the team " 
        "get a highlight video made tonight.\n\n"

        "INPUT\n"
        "Each line below is a candidate who already cleared a statistical "
        "bar. The REASON text for each was the statline directly from the box "
        "score and is a verified, immutable fact. Treat it exactly like a "
        "number handed to you by a calculator.\n\n"
        + "\n".join(lines)
        + "\n\n"

        "HARD RULES (breaking any of these makes your answer invalid)\n"
        "1. You may only choose from the exact candidates listed above. "
        "Never add a player, team, or stat that isn't already there.\n"
        "2. Never restate, rephrase, round, recompute, or 'correct' a "
        "REASON or +/- value. If you disagree with how impressive it "
        "sounds, cut the player rather than editing the text.\n"
        "3. Do not invent context you weren't given (final score, game time, "
        "opponent record, role, injury, etc.). Judge only from the REASON shown.\n"
        "4. Do not use the player name as a substitute for the REASON.\n"
        "5. Do not use the player team as a substitute for the REASON.\n"
        "6. +/- may be considered as supporting evidence, but it can NEVER "
        "by itself make an otherwise unimpressive statline worth a highlight.\n"
        "7. Output ONLY the JSON object described below — no markdown code "
        "fences, no commentary, no explanation before or after it.\n\n"

        "HIGHLIGHT STANDARD\n"
        "A player should be KEEP only when the statline itself clearly "
        "supports a compelling NBA highlight video. The bar is high.\n\n"

        "STRONG REASONS TO KEEP\n"
        "- Elite scoring volume or efficiency.\n"
        "- A triple-double or quadruple-double.\n"
        "- Exceptional rebounding, especially dominant offensive rebounding.\n"
        "- Defensive dominance through a high number of steals and/or blocks.\n"
        "- A combination of multiple strong categories that clearly represents "
        "an unusually impactful performance.\n\n"

        "AUTOMATIC OR NEAR-AUTOMATIC CUTS\n"
        "- Very low scoring without an exceptional contribution elsewhere.\n"
        "- Poor scoring efficiency without enough other production to offset it.\n"
        "- Ordinary or modest rebounding/assists that do not form a standout "
        "overall statline.\n"
        "- A statline with zero steals and zero blocks that otherwise lacks "
        "elite scoring, rebounding, playmaking, or a major statistical milestone.\n"
        "- High fouls without exceptional positive production.\n"
        "- A strong +/- attached to an otherwise ordinary or inefficient "
        "statline. Do not interpret +/- as proof that the player deserves "
        "a highlight.\n\n"

        "IMPORTANT EXAMPLE OF THE BAR\n"
        "A player who scores only a few points, shoots poorly from the line "
        "or field, has modest rebounds/assists, records no steals or blocks, "
        "and has several fouls should generally be CUT. A positive +/- does "
        "not override this. Do not manufacture a highlight case from the "
        "plus-minus alone.\n\n"

        "DECISION RULE\n"
        "Ask: 'If someone saw only this REASON line, would this statline "
        "clearly justify an NBA highlight video tonight?' If the answer is "
        "no or even borderline, CUT the player. Prefer a false negative "
        "over selecting an ordinary performance.\n\n"

        "OUTPUT FORMAT\n"
        'Respond with exactly one JSON object: {"keep": ["Player Name (TEAM)", ...]} '
        "using the identical \"Player Name (TEAM)\" strings shown in the "
        'candidate list above (copy them verbatim). Use {"keep": []} if no '
        "candidate from this game's list clearly meets the highlight standard."
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
        except:
            pass

    resp.raise_for_status()

    content = ""
    try:
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue

            chunk = json.loads(line)

            message = chunk.get("message", {})
            content += message.get("content", "")

            if chunk.get("done"):
                break

        keep_ids = set(json.loads(content).get("keep", []))
    except (json.JSONDecodeError, KeyError, TypeError):
        return candidates

    return [c for c in candidates if id_for(c) in keep_ids]
