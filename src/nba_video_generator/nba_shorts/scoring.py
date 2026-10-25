"""Score plays for short-worthiness and pick the best ones."""
import re
from dataclasses import dataclass, field


PRIORITY_SCORE = {
    "buzzer-beater winner": 70.0,
    "buzzer-beater tie": 60.0,
    "game winner": 50.0,
    "game tying": 40.0,
    "and-one dunk": 32.0,
    "and-one three": 30.0,
    "dunk": 20.0,
}


@dataclass
class Play:
    score: float
    action: dict
    reasons: list = field(default_factory=list)

    @property
    def event_id(self) -> int:
        return self.action["actionNumber"]

    @property
    def description(self) -> str:
        return self.action.get("description") or ""

    @property
    def period(self) -> int:
        return self.action.get("period", 1)

    @property
    def clock(self) -> str:
        return fmt_clock(self.action.get("clock", ""))


def clock_seconds(iso_clock: str) -> float:
    """'PT04M12.00S' -> 252.0"""
    m = re.match(r"PT(\d+)M([\d.]+)S", iso_clock or "")
    return int(m.group(1)) * 60 + float(m.group(2)) if m else 9999.0


def fmt_clock(iso_clock: str) -> str:
    s = clock_seconds(iso_clock)
    return f"{int(s // 60):02d}:{int(s % 60):02d}"


def _score_total(action: dict) -> int | None:
    try:
        return int(action["scoreHome"]) + int(action["scoreAway"])
    except (KeyError, TypeError, ValueError):
        return None


def _is_made_bucket(action: dict) -> bool:
    result = str(action.get("shotResult") or "").strip().lower()
    if result:
        return result == "made"
    action_type = str(action.get("actionType") or "").strip().lower()
    description = str(action.get("description") or "").strip().lower()
    return "made" in action_type or description.startswith("made ")


def _is_garbage_time_bucket(
        action: dict, prev_diff: int | None, prev_total: int
) -> bool:
    """Exclude scoring plays in a late fourth-quarter blowout."""
    if action.get("period") != 4 or prev_diff is None or abs(prev_diff) < 15:
        return False
    if clock_seconds(action.get("clock", "")) > 5 * 60:
        return False

    total = _score_total(action)
    if total is not None:
        return total > prev_total
    return _is_made_bucket(action)


def _is_non_result_changing_buzzer_beater(
        action: dict, prev_diff: int | None
) -> bool:
    if action.get("period") != 4 or clock_seconds(action.get("clock", "")) > 3:
        return False

    made = str(action.get("shotResult") or "").lower() == "made"
    action_type = str(action.get("actionType") or "").lower()
    is_field_goal = bool(action.get("isFieldGoal")) or action_type in (
        "2pt", "3pt"
    )
    if not made or not is_field_goal or prev_diff is None:
        return False

    try:
        final_diff = int(action["scoreHome"]) - int(action["scoreAway"])
    except (KeyError, TypeError, ValueError):
        return False

    return (
        prev_diff != 0
        and final_diff != 0
        and (prev_diff > 0) == (final_diff > 0)
    )


def _is_made_three(action: dict) -> bool:
    if str(action.get("shotResult") or "").lower() != "made":
        return False
    description = str(action.get("description") or "").lower()
    action_type = str(action.get("actionType") or "").lower()
    return action_type == "3pt" or bool(
        re.search(r"\b(?:3\s*pt|3\s*point|three\s*point)\b", description)
    )


def _is_shooting_foul_after(action: dict, next_action: dict | None) -> bool:
    if not next_action:
        return False

    if next_action.get("period", action.get("period", 1)) != \
            action.get("period", 1):
        return False
    if clock_seconds(next_action.get("clock", "")) != \
            clock_seconds(action.get("clock", "")):
        return False

    foul_description = str(next_action.get("description") or "").lower()
    foul_type = str(next_action.get("actionType") or "").lower()
    foul_subtype = str(next_action.get("subType") or "").lower()
    is_foul = (
        "foul" in foul_type or "foul" in foul_subtype
        or "foul" in foul_description
    )
    if not is_foul:
        return False

    shooting_foul_text = re.sub(
        r"[^a-z]", "", f"{foul_subtype} {foul_description}"
    )
    if not (
        "shoot" in shooting_foul_text
        or "sfoul" in shooting_foul_text
    ):
        return False

    shooter_id = action.get("personId")
    fouled_player_id = next_action.get("foulDrawnPersonId")
    return (
        shooter_id is None
        or fouled_player_id is None
        or str(shooter_id) == str(fouled_player_id)
    )


def _has_and_one_marker(description: str) -> bool:
    normalized = re.sub(r"[\s-]+", " ", description.lower())
    return any(
        marker in normalized
        for marker in ("and 1", "and1", "and one", "plus one")
    )


def _is_and_one_dunk(
        action: dict, next_action: dict | None = None
) -> bool:
    is_dunk = "dunk" in str(action.get("description") or "").lower() or \
        "dunk" in str(action.get("subType") or "").lower()
    if not is_dunk or str(action.get("shotResult") or "").lower() != "made":
        return False
    return _has_and_one_marker(str(action.get("description") or "")) or \
        _is_shooting_foul_after(action, next_action)


def _is_and_one_three(
        action: dict, next_action: dict | None = None
) -> bool:
    return _is_made_three(action) and (
        _has_and_one_marker(str(action.get("description") or ""))
        or _is_shooting_foul_after(action, next_action)
    )


# ============================================================ scoring
def score_play(
        a: dict, prev_margin: int, prev_diff=None,
        next_action: dict | None = None,
):
    """Return (score, reasons). Higher = better short material. Tune freely.

    prev_diff = home minus away score *before* this play
    (used to spot go-ahead / game-tying baskets).
    """
    desc = (a.get("description") or "").lower()
    atype = (a.get("actionType") or "").lower()
    sub = (a.get("subType") or "").lower()
    made = (a.get("shotResult") or "").lower() == "made"
    is_fg = bool(a.get("isFieldGoal")) or atype in ("2pt", "3pt")
    period = a.get("period", 1)
    secs = clock_seconds(a.get("clock", ""))

    try:
        diff = int(a["scoreHome"]) - int(a["scoreAway"])
        margin = abs(diff)
    except (KeyError, ValueError, TypeError):
        diff, margin = None, prev_margin

    s, why = 0.0, []
    priority = None

    if made and ("dunk" in desc or "dunk" in sub):
        priority = "dunk"
        s += 5
        why.append("dunk")
        if "alley" in desc or "alley" in sub:
            s += 2
            why.append("alley-oop")
        if "putback" in desc or "tip" in desc:
            s += 1
    if atype == "block" or "block" in desc:
        s += 4
        why.append("block")
    if atype == "steal" or "steal" in desc:
        s += 2.5
        why.append("steal")
    if made and "3pt" in desc:
        s += 3
        why.append("three")
        try:
            if float(a.get("shotDistance") or 0) >= 30:
                s += 2
                why.append("deep")
        except (TypeError, ValueError):
            pass
    if made and any(
        k in desc for k in (
            "fadeaway", "bank", "reverse",
            "step back", "turnaround", "hook")):
        s += 1.5
        why.append("tough shot")
    if made and is_fg and\
            ("dunk" not in desc) and ("tip" in desc or "putback" in desc):
        s += 1.5
        why.append("tip-in")

    # Classify late-game outcomes separately so their order is not
    # affected by style bonuses or clutch multipliers.
    if made and is_fg and period >= 4 and\
            secs <= 30 and diff is not None and prev_diff is not None:
        if secs <= 3 and diff != 0 and (
            prev_diff == 0 or (prev_diff > 0) != (diff > 0)
        ):
            priority = "buzzer-beater winner"
            why.append("buzzer-beater winner")
        elif secs <= 3 and diff == 0 and prev_diff != 0:
            priority = "buzzer-beater tie"
            why.append("buzzer-beater tie")
        elif diff != 0 and (
            prev_diff == 0 or (prev_diff > 0) != (diff > 0)
        ):
            priority = "game winner"
            why.append("game winner")
        elif diff == 0 and prev_diff != 0:
            priority = "game tying"
            why.append("game tying")

    if made and _is_and_one_dunk(a, next_action):
        if priority is None or priority == "dunk":
            priority = "and-one dunk"
        why.append("and-one dunk")

    if made and is_fg and _is_and_one_three(a, next_action):
        if priority is None or priority == "dunk":
            priority = "and-one three"
        why.append("and-one three")

    # Beating the clock: a big bonus in the final period / OT,
    # a small one at the end of a quarter.
    if made and is_fg and secs <= 3:
        if period >= 4:
            s += 6
            why.append("buzzer-beater")
        else:
            s += 2.5
            why.append("end of quarter")

    if s > 0:  # situational multipliers only for plays already interesting
        if period >= 4 and secs <= 120 and margin <= 5:
            s *= 1.6
            why.append("clutch")
        elif period >= 4 and secs <= 300 and margin <= 8:
            s *= 1.2
        if period > 4:
            s *= 1.2
            why.append("OT")
    if priority is not None:
        s = PRIORITY_SCORE[priority] + min(s, 9.99)
    else:
        s = min(s, PRIORITY_SCORE["dunk"] - 0.01)
    return s, why


def pick_plays(
        actions: list, top: int = 8,
        min_score: float = 3.0, player: str = ""
) -> list:
    """Best `top` plays scoring >= min_score, returned in game order."""
    scored, margin, prev_diff, prev_total = [], 99, None, 0
    for index, a in enumerate(actions):
        garbage_time_bucket = _is_garbage_time_bucket(
            a, prev_diff, prev_total
        )
        non_result_changing_buzzer = _is_non_result_changing_buzzer_beater(
            a, prev_diff
        )
        next_action = actions[index + 1] if index + 1 < len(actions) else None
        s, why = score_play(a, margin, prev_diff, next_action)
        total = _score_total(a)
        try:
            diff = int(a["scoreHome"]) - int(a["scoreAway"])
            margin, prev_diff = abs(diff), diff
        except (KeyError, ValueError, TypeError):
            pass
        if total is not None:
            prev_total = total
        if garbage_time_bucket or non_result_changing_buzzer:
            continue
        if player and player.lower() not in (
            a.get("description") or ""
        ).lower():
            continue
        if s >= min_score:
            scored.append(Play(s, a, why))
    scored.sort(key=lambda p: p.score, reverse=True)
    picks = scored[:top]
    picks.sort(
        key=lambda p: (
            p.action["period"], -clock_seconds(p.action["clock"])
        )
    )
    return picks
