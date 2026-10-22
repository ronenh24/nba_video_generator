"""Rule-based pre-filter + Ollama-based judgment of "must-see" performances."""
import json
import requests
from tqdm import tqdm

from .config import (
    AUTO_KEEP_THRESHOLDS, OLLAMA_HOST, OLLAMA_MODEL, SCHEMA,
    SINGLE_STAT_THRESHOLDS, SYSTEM_PROMPT, THRESHOLDS,
    TRIPLE_DOUBLE_CATS, TRIPLE_DOUBLE_MIN,
)


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
    pts = (
        p["PTS"] + " Points (" + p["FGM"] + "-" + p["FGA"]
        + " Field Goals, " + p["3PM"] + "-" + p["3PA"]
        + " 3 Point Field Goals, " + p["FTM"] + "-" + p["FTA"]
        + " Free Throws)"
    )
    rb = (
        p["REB"] + " Rebounds (" + p["OREB"] + " Offensive Rebounds, "
        + p["DREB"] + " Defensive Rebounds)"
    )
    ast = p["AST"] + " Assists (" + p["TO"] + " Turnovers)"
    stl = p["STL"] + " Steals"
    blk = p["BLK"] + " Blocks"
    pf = p["PF"] + " Fouls"
    pm_value = _num(p.get("+/-"))
    pm = f"+/- {pm_value:+g}"

    return ", ".join([minutes, pts, rb, ast, stl, blk, pf, pm])


def rule_based_candidates(
        team_name: str, players: list[dict], threshold: bool = True
) -> list[dict]:
    """Filter players by configured categories and annotate their statline."""
    candidates = []
    for p in players:
        if threshold:
            stats = {
                key: _num(p.get(key))
                for key in set(THRESHOLDS)
                | set(SINGLE_STAT_THRESHOLDS)
                | set(TRIPLE_DOUBLE_CATS)
            }

            double_digit_cats = sum(
                1
                for category in TRIPLE_DOUBLE_CATS
                if stats[category] >= TRIPLE_DOUBLE_MIN
            )

            hit_threshold = (
                sum(
                    stats[category] >= cutoff
                    for category, cutoff in THRESHOLDS.items()
                ) >= 2
                or any(
                    stats[category] >= cutoff
                    for category, cutoff in SINGLE_STAT_THRESHOLDS.items()
                )
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
            minutes = int(
                minutes.split(":")[0]
            ) * 60 + int(minutes.split(":")[1])
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

    Candidates meeting AUTO_KEEP_THRESHOLDS bypass model judgment and are
    retained. Other candidates are kept only when the response matches the
    configured schema and its `keep` value is True. Failed or invalid model
    responses are not retained.

    Original candidate dictionaries are returned unchanged, including
    REASON and all other fields.
    """
    if not candidates:
        return []

    candidates = sorted(candidates, key=lambda p: _num(p["PTS"]))

    lines = get_stats_dictionary(candidates)

    keep_ids = set()

    for i, (line, candidate) in tqdm(enumerate(zip(lines, candidates))):
        if any(
            _num(candidate.get(category)) >= cutoff
            for category, cutoff in AUTO_KEEP_THRESHOLDS.items()
        ):
            keep_ids.add(i)
            continue

        user_prompt = (
            f"{line} \n\nEvaluate the candidate above and return the "
            "JSON object.\n"
        )

        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "format": SCHEMA,
                    "keep_alive": "30m",
                    "options": {"temperature": 0.2, "num_ctx": 10000}
                },
                timeout=240,
            )

            resp.raise_for_status()

            result = resp.json()
            output = result["message"]["content"]

            data = json.loads(output)
            evaluation = data["evaluation"]

            if evaluation.get("keep") is True:
                keep_ids.add(i)
        except Exception:
            pass

    return [
        candidate
        for i, candidate in enumerate(candidates)
        if i in keep_ids
    ]


def get_stats_dictionary(candidates: list[dict]):
    stats = []
    for p in candidates:
        stats.append(
            json.dumps(
                {
                    "Minutes": p["MIN"], "Points": p["PTS"],
                    "Field Goals Made": p["FGM"],
                    "Field Goals Attempted": p["FGA"],
                    "3 Point Field Goals Made": p["3PM"],
                    "3 Point Field Goals Attempted": p["3PA"],
                    "Free Throws Made": p["FTM"],
                    "Free Throws Attempted": p["FTA"], "Rebounds": p["REB"],
                    "Offensive Rebounds": p["OREB"],
                    "Defensive Rebounds": p["DREB"],
                    "Assists": p["AST"], "Turnovers": p["TO"],
                    "Steals": p["STL"],
                    "Blocks": p["BLK"], "Fouls": p["PF"]
                },
                indent=4
            )
        )
    return stats
