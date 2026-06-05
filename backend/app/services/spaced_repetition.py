from __future__ import annotations
"""FSRS (Free Spaced Repetition Scheduler) — modern spaced repetition algorithm.

Based on the FSRS algorithm by Jarrett Ye (open-spaced-repetition/fsrs4anki).
Uses a 3-parameter memory model: stability (S), difficulty (D), retrievability (R).
Much more accurate than SM-2 for scheduling review intervals.

Key concepts:
- Stability: days until retrievability drops to 90%
- Difficulty: 0-1 scale, how hard the card is
- Retrievability: probability of recall at current time
- Rating: 1=Again, 2=Hard, 3=Good, 4=Easy
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

# ── FSRS Parameters (optimized default weights) ─────────────────────
# From: https://github.com/open-spaced-repetition/fsrs4anki
W = [
    0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01,
    1.49, 0.14, 0.94, 2.18, 0.05, 0.34, 1.26, 0.29,
    2.61, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
]

DECAY = -0.5
FACTOR = 0.9 ** (1 / DECAY) - 1

# Rating constants
RATING_AGAIN = 1
RATING_HARD = 2
RATING_GOOD = 3
RATING_EASY = 4


@dataclass
class CardState:
    """FSRS card state for a knowledge point."""
    stability: float = 0.0
    difficulty: float = 0.0
    due: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reps: int = 0
    lapses: int = 0
    last_review: Optional[datetime] = None
    last_rating: int = 0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _initial_stability(rating: int) -> float:
    """Initial stability after first review."""
    return max(W[rating - 1], 0.1)


def _initial_difficulty(rating: int) -> float:
    """Initial difficulty after first review."""
    return _clamp(W[4] - W[5] * (rating - 3), 0.0, 1.0)


def _mean_reversion(difficulty: float, rating: int) -> float:
    """Apply mean reversion to difficulty."""
    return _clamp(W[7] * _initial_difficulty(3) + (1 - W[7]) * difficulty, 0.0, 1.0)


def _stability_after_success(difficulty: float, stability: float, retrievability: float, rating: int) -> float:
    """Update stability after a successful review."""
    hard_penalty = W[15] if rating == RATING_HARD else 1.0
    easy_bonus = W[16] if rating == RATING_EASY else 1.0
    new_stability = (
        stability
        * (1 + W[8] * (11 - difficulty) * (stability ** -W[9])
           * (W[10] * (1 - retrievability) + 1)
           * hard_penalty * easy_bonus)
    )
    return max(new_stability, 0.1)


def _stability_after_failure(difficulty: float, stability: float, retrievability: float) -> float:
    """Update stability after a failed review (Again)."""
    new_stability = min(
        W[11] * (difficulty ** -W[12]) * ((stability + 1) ** W[13] - 1) * W[14],
        stability / FACTOR ** (1 / DECAY),
    )
    return max(new_stability, 0.1)


def _next_interval(stability: float) -> float:
    """Calculate next review interval in days."""
    return stability * FACTOR


def review_card(state: CardState, rating: int) -> CardState:
    """Apply FSRS algorithm to update card state after a review.

    Args:
        state: Current card state
        rating: Review rating (1=Again, 2=Hard, 3=Good, 4=Easy)

    Returns:
        Updated card state with new stability, difficulty, and due date
    """
    now = datetime.now(timezone.utc)

    if state.reps == 0:
        # First review
        new_stability = _initial_stability(rating)
        new_difficulty = _initial_difficulty(rating)
    else:
        # Subsequent reviews
        elapsed_days = max((now - (state.last_review or now)).total_seconds() / 86400, 0.001)
        retrievability = (1 + FACTOR * elapsed_days / state.stability) ** DECAY

        new_difficulty = _mean_reversion(state.difficulty, rating)

        if rating == RATING_AGAIN:
            new_stability = _stability_after_failure(new_difficulty, state.stability, retrievability)
        else:
            new_stability = _stability_after_success(new_difficulty, state.stability, retrievability, rating)

    # Calculate next interval
    interval_days = _next_interval(new_stability)
    # Apply rating-specific multipliers
    if rating == RATING_HARD:
        interval_days *= 0.8
    elif rating == RATING_EASY:
        interval_days *= 1.3

    interval_days = max(interval_days, 0.007)  # minimum ~10 minutes

    return CardState(
        stability=new_stability,
        difficulty=new_difficulty,
        due=now + timedelta(days=interval_days),
        reps=state.reps + 1,
        lapses=state.lapses + (1 if rating == RATING_AGAIN else 0),
        last_review=now,
        last_rating=rating,
    )


def get_due_cards(cards: dict[str, CardState]) -> list[str]:
    """Return knowledge points that are due for review, sorted by urgency."""
    now = datetime.now(timezone.utc)
    due = []
    for kp, state in cards.items():
        if state.due <= now:
            due.append(kp)
    # Sort by overdue-ness (most overdue first)
    due.sort(key=lambda kp: cards[kp].due)
    return due


def get_review_stats(cards: dict[str, CardState]) -> dict:
    """Get review statistics."""
    now = datetime.now(timezone.utc)
    total = len(cards)
    due = sum(1 for s in cards.values() if s.due <= now)
    overdue = sum(1 for s in cards.values() if s.due <= now - timedelta(days=1))
    avg_stability = sum(s.stability for s in cards.values()) / total if total else 0
    avg_difficulty = sum(s.difficulty for s in cards.values()) / total if total else 0

    return {
        "total_cards": total,
        "due_now": due,
        "overdue": overdue,
        "avg_stability": round(avg_stability, 2),
        "avg_difficulty": round(avg_difficulty, 2),
        "next_review": min((s.due for s in cards.values() if s.due > now), default=now).isoformat(),
    }


# ── Persistence helpers ──────────────────────────────────────────────

def card_state_to_dict(state: CardState) -> dict:
    """Serialize CardState to dict for storage."""
    return {
        "stability": state.stability,
        "difficulty": state.difficulty,
        "due": state.due.isoformat(),
        "reps": state.reps,
        "lapses": state.lapses,
        "last_review": state.last_review.isoformat() if state.last_review else None,
        "last_rating": state.last_rating,
    }


def card_state_from_dict(data: dict) -> CardState:
    """Deserialize CardState from dict."""
    def _parse_dt(val):
        if isinstance(val, str):
            return datetime.fromisoformat(val)
        if isinstance(val, datetime):
            return val
        return datetime.now(timezone.utc)

    return CardState(
        stability=data.get("stability", 0.0),
        difficulty=data.get("difficulty", 0.0),
        due=_parse_dt(data.get("due", datetime.now(timezone.utc).isoformat())),
        reps=data.get("reps", 0),
        lapses=data.get("lapses", 0),
        last_review=_parse_dt(data["last_review"]) if data.get("last_review") else None,
        last_rating=data.get("last_rating", 0),
    )
