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
    pts = p["PTS"] + " Points (" + p["FGM"] + "-" + p["FGA"] + " Field Goals, " + \
        p["3PM"] + "-" + p["3PA"] + " 3 Point Field Goals, " + \
        p["FTM"] + "-" + p["FTA"] + " Free Throws)"
    rb = p["REB"] + " Rebounds (" + p["OREB"] + " Offensive Rebounds, " + p["DREB"] + " Defensive Rebounds)"
    ast = p["AST"] + " Assists (" + p["TO"] + " Turnovers)"
    stl = p["STL"] + " Steals"
    blk = p["BLK"] + " Blocks"
    pf = p["PF"] + " Fouls"
    pm = "+/- "
    if int(p["+/-"]) > 0:
        pm += "+"
    pm += p["+/-"]

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


import time


SCHEMA = {
    "type": "object",
    "properties": {
        "evaluations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "thinking": {"type": "string"},
                    "strengths": {
                        "type": "array",
                        "uniqueItems": True,
                        "maxItems": 5,
                        "items": {
                            "type": "string",
                            "enum": ["scoring", "rebounding", "playmaking", "defense"],
                        },
                    },
                    "keep": {"type": "boolean"},
                },
                "required": ["id", "thinking", "strengths", "keep"],
            },
        }
    },
    "required": ["evaluations"],
}


def ollama_judge(candidates: list[dict]) -> list[dict]:
    """
    Ask a local Ollama model which pre-filtered candidates deserve
    highlight videos. Player and team names are excluded from the prompt.
    The model returns per-candidate strength lists; a candidate is kept
    when the model finds three or more distinct strengths.
    Original candidate dicts are returned unchanged, including REASON.
    """
    if not candidates:
        return []

    candidates = sorted(candidates, key=lambda c: int(c["PTS"]), reverse=True)

    # +/- is stripped from the text the model sees; REASON itself is unchanged.
    lines = [
        f"- ID {i}: {c['REASON']}"
        for i, c in enumerate(candidates)
    ]

    system_prompt = (
        "ROLE\n"
        "You are an NBA highlights producer deciding which performances "
        "deserve a highlight video tonight.\n\n"

        "INPUT\n"
        "The user sends a list of candidates, each with an ID and a "
        "verified box-score line. IDs are arbitrary labels with no "
        "ranking. Player and team identities are omitted on purpose.\n\n"

        "HOW TO JUDGE\n"
        "- Judge each line against what a genuinely memorable NBA "
        "performance looks like, NOT against the other candidates tonight. "
        "Many nights have no deserving candidate, and returning none is "
        "correct and expected. Never keep a line just because it is the "
        "best of a weak group.\n"
        "- Look at the whole line: volume and efficiency of scoring, "
        "rebounding, playmaking, and defensive stats (steals, blocks).\n"
        "- Efficiency matters. Heavy volume on poor shooting, many "
        "turnovers, or foul trouble weighs against a line.\n"
        "- When in doubt, cut.\n\n"

        "RULES\n"
        "- Use only the numbers shown. Do not invent context such as "
        "opponent, final score, injuries, or identity.\n"
        "- Do not alter or restate any statline.\n"
        "- All statistics are numbers; compare them numerically, not as "
        "text.\n"
        "- A category counts only if it is clearly impressive on its own "
        "for a memorable NBA performance. Modest or average numbers do "
        "not count. Never list a category just to fill the list.\n"
        "- Evaluate every candidate, using the same standard for all.\n\n"

        "OUTPUT FORMAT\n"
        "Return exactly one JSON object and nothing else (no markdown). "
        "It has one key, \"evaluations\", a list with exactly one entry "
        "per candidate, in ID order. Each entry has these fields, in this "
        "order:\n"
        "- \"id\": integer, the candidate's ID from the input.\n"
        "- \"thinking\": string, your reasoning about this line before you "
        "decide. Assess each category (scoring, rebounding, playmaking, "
        "defense) in turn. Note whether each is clearly impressive "
        "or merely ordinary. For scoring, consider both volume and "
        "efficiency together: high efficiency on few attempts is not "
        "elite scoring. For playmaking, consider the absolute assist "
        "total, not just the assist-to-turnover ratio: a low assist count "
        "is not playmaking regardless of turnovers. "
        "Keep it to two or three sentences.\n"
        "- \"strengths\": list of every category in which this line is "
        "clearly impressive, based on your thinking above. Use only these "
        "values, each at most once:\n"
        "    \"scoring\"     - high points volume, or high volume with good "
        "efficiency. Low volume shooting, however efficient, does not count: "
        "making 3 from 3 attempts is not elite scoring.\n"
        "    \"rebounding\"  - total rebounds, especially offensive\n"
        "    \"playmaking\"  - a high number of assists with few turnovers. "
        "A low assist total does not count even with zero turnovers: "
        "keeping the ball does not make someone a playmaker.\n"
        "    \"defense\"      - steals and blocks weighted against fouls.\n"
        "  Use an empty list [] if nothing stands out.\n"
        "- \"keep\": boolean. True if this performance deserves a highlight "
        "video, based on your thinking and strengths above. False otherwise.\n"
        "Example:\n"
        "{\n"
        '  "evaluations": [\n'
        '    {"id": 0, "thinking": "5 points on 1-4 shooting is poor '
        'scoring. 3 rebounds and 3 assists are ordinary. 1 steal is '
        'unremarkable.", "strengths": [], "keep": false},\n'
        '    {"id": 1, "thinking": "28 points on 11-16 shooting is elite '
        'scoring volume and efficiency. 12 rebounds is exceptional. '
        '3 steals is very strong defensively.", '
        '"strengths": ["scoring", "rebounding", "steals"], "keep": true}\n'
        "  ]\n"
        "}"
    )

    user_prompt = (
        f"CANDIDATES ({len(candidates)} total, IDs 0 to {len(candidates) - 1})\n"
        + "\n".join(lines)
        + "\n\nEvaluate every candidate above and return the JSON object."
    )

    resp = None
    for attempt in range(5):
        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "format": SCHEMA,
                    "stream": True,
                    "think": False,
                    "keep_alive": "30m",
                    "options": {"temperature": 0, "num_ctx": 8192},
                },
                timeout=600,
                stream=True,
            )
            break
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))

    if resp is None:
        return candidates

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

        data = json.loads(content)
        evaluations = data["evaluations"]

        if not isinstance(evaluations, list) or len(evaluations) != len(candidates):
            return candidates

        keep_ids = set()
        for e in evaluations:
            i = e["id"]
            if type(i) is not int or i < 0 or i >= len(candidates):
                return candidates
            if e.get("keep") is True:
                keep_ids.add(i)

    except (json.JSONDecodeError, KeyError, TypeError):
        return candidates

    return [
        candidate
        for i, candidate in enumerate(candidates)
        if i in keep_ids
    ]
