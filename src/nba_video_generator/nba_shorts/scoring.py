"""Score plays for short-worthiness and pick the best ones."""
import re
from dataclasses import dataclass, field


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


# ============================================================ scoring
def score_play(a: dict, prev_margin: int):
    """Return (score, reasons). Higher = better short material. Tune freely."""
    desc = (a.get("description") or "").lower()
    atype = (a.get("actionType") or "").lower()
    sub = (a.get("subType") or "").lower()
    made = (a.get("shotResult") or "").lower() == "made"
    period = a.get("period", 1)
    secs = clock_seconds(a.get("clock", ""))

    try:
        margin = abs(int(a["scoreHome"]) - int(a["scoreAway"]))
    except (KeyError, ValueError, TypeError):
        margin = prev_margin

    s, why = 0.0, []

    if made and ("dunk" in desc or "dunk" in sub):
        s += 5; why.append("dunk")
        if "alley" in desc or "alley" in sub:
            s += 2; why.append("alley-oop")
        if "putback" in desc or "tip" in desc:
            s += 1
    if atype == "block" or "block" in desc:
        s += 4; why.append("block")
    if atype == "steal" or "steal" in desc:
        s += 2.5; why.append("steal")
    if made and "3pt" in desc:
        s += 3; why.append("three")
        try:
            if float(a.get("shotDistance") or 0) >= 28:
                s += 2; why.append("deep")
        except (TypeError, ValueError):
            pass
    if made and any(k in desc for k in ("fadeaway", "bank", "reverse", "step back",
                                        "turnaround", "hook")):
        s += 1.5; why.append("tough shot")

    if s > 0:  # situational multipliers only for plays already interesting
        if period >= 4 and secs <= 120 and margin <= 5:
            s *= 1.8; why.append("clutch")
        elif period >= 4 and secs <= 300 and margin <= 8:
            s *= 1.3
        if made and secs <= 3 and a.get("isFieldGoal"):
            s += 6; why.append("buzzer-beater")
        if period > 4:
            s *= 1.3; why.append("OT")
    return s, why


def pick_plays(actions: list, top: int = 8, min_score: float = 3.0, player: str = "") -> list:
    """Best `top` plays scoring >= min_score, returned in game order."""
    scored, margin = [], 99
    for a in actions:
        s, why = score_play(a, margin)
        try:
            margin = abs(int(a["scoreHome"]) - int(a["scoreAway"]))
        except (KeyError, ValueError, TypeError):
            pass
        if player and player.lower() not in (a.get("description") or "").lower():
            continue
        if s >= min_score:
            scored.append(Play(s, a, why))
    scored.sort(key=lambda p: p.score, reverse=True)
    picks = scored[:top]
    picks.sort(key=lambda p: (p.action["period"], -clock_seconds(p.action["clock"])))
    return picks
