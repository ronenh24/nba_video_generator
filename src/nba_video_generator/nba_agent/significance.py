"""Rule-based pre-filter + Ollama-based judgment of "must-see" performances."""
import json
import requests
import time
import random

from .config import OLLAMA_HOST, OLLAMA_MODEL, THRESHOLDS, TRIPLE_DOUBLE_MIN, SCHEMA, system_prompt


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
    pm_value = _num(p.get("+/-"))
    pm = f"+/- {pm_value:+g}"

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
    Ask a local Ollama model to evaluate pre-filtered NBA performances
    and decide which deserve highlight videos.

    Candidates are sorted by points scored, and player and team names
    are excluded from the prompt. The model evaluates each statline
    across scoring, rebounding, playmaking, defense, and overall impact,
    identifying only categories that are clearly impressive.

    After the initial evaluation, the model reconsiders its reasoning
    and strengths before making its final keep decision. It must verify
    that every listed strength is supported by the numbers and that the
    performance as a whole genuinely deserves a highlight video. Having
    three or more strengths does not automatically qualify a candidate.

    The model returns a structured JSON evaluation for every candidate.
    Candidates with a final keep decision of True are retained. If the
    model request fails, or its response cannot be parsed or validated,
    the original sorted candidate list is returned as a fallback.

    Original candidate dictionaries are returned unchanged, including
    REASON and all other fields.
    """
    if not candidates:
        return []

    candidates = sorted(candidates, key=lambda p: int(p["PTS"]))

    lines = [
        f"- ID {i}: {c['REASON'].split('+/-')[0]}"
        for i, c in enumerate(candidates)
    ]

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
                    "keep_alive": -1,
                    "options": {"temperature": 0.2, "num_ctx": 10000}
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

        print(content)

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
