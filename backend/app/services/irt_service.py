from __future__ import annotations
"""IRT (Item Response Theory) Service — question difficulty calibration and ability estimation.

Implements the 2PL (Two-Parameter Logistic) model:
P(correct | ability, difficulty, discrimination) = 1 / (1 + exp(-discrimination * (ability - difficulty)))

Key concepts:
- ability (θ): student's latent proficiency, estimated from response patterns
- difficulty (b): question difficulty parameter (logit scale)
- discrimination (a): how well the question distinguishes ability levels
- information: how much a question reduces uncertainty about ability

Used for:
1. Calibrating question difficulty from response data
2. Estimating student ability from quiz results
3. Adaptive question selection (CAT) — pick the most informative question
"""

import logging
import math
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ItemParams:
    """IRT parameters for a question."""
    difficulty: float = 0.0      # b: -3 to 3 (logit scale, 0 = average)
    discrimination: float = 1.0  # a: 0.5 to 2.5 (1 = average)
    guessing: float = 0.0        # c: 0 to 0.3 (for 3PL, typically 0 for open-ended)


@dataclass
class AbilityEstimate:
    """Student ability estimate."""
    theta: float = 0.0           # ability: -3 to 3 (logit scale, 0 = average)
    se: float = 1.0              # standard error of estimate
    n_items: int = 0             # number of items answered


def _irf(theta: float, item: ItemParams) -> float:
    """Item Response Function — probability of correct response.

    2PL model: P(θ) = 1 / (1 + exp(-a * (θ - b)))
    """
    z = item.discrimination * (theta - item.difficulty)
    z = max(-10, min(10, z))  # prevent overflow
    return 1.0 / (1.0 + math.exp(-z))


def _item_information(theta: float, item: ItemParams) -> float:
    """Fisher information for an item at ability θ.

    I(θ) = a² * P(θ) * (1 - P(θ))
    """
    p = _irf(theta, item)
    return item.discrimination ** 2 * p * (1 - p)


def estimate_ability(
    responses: List[dict],
    item_params: dict[str, ItemParams],
) -> AbilityEstimate:
    """Estimate student ability from response pattern using MLE.

    Args:
        responses: list of {question_id: str, is_correct: bool}
        item_params: dict of question_id -> ItemParams

    Returns:
        AbilityEstimate with theta and standard error
    """
    if not responses:
        return AbilityEstimate(theta=0.0, se=1.0, n_items=0)

    # Filter to items with known parameters
    valid = [(r, item_params[r["question_id"]]) for r in responses if r["question_id"] in item_params]
    if not valid:
        return AbilityEstimate(theta=0.0, se=1.0, n_items=0)

    # MLE estimation via Newton-Raphson
    theta = 0.0  # initial estimate
    for _ in range(20):
        gradient = 0.0
        hessian = 0.0
        for resp, item in valid:
            p = _irf(theta, item)
            correct = 1.0 if resp["is_correct"] else 0.0
            gradient += item.discrimination * (correct - p)
            hessian -= item.discrimination ** 2 * p * (1 - p)

        if abs(hessian) < 1e-10:
            break

        delta = gradient / hessian
        theta -= delta
        theta = max(-4, min(4, theta))  # bound

        if abs(delta) < 0.001:
            break

    # Standard error from information
    total_info = sum(_item_information(theta, item) for _, item in valid)
    se = 1.0 / math.sqrt(total_info) if total_info > 0 else 1.0

    return AbilityEstimate(theta=theta, se=se, n_items=len(valid))


def select_next_question(
    current_theta: float,
    available_questions: List[dict],
    item_params: dict[str, ItemParams],
    exclude_ids: Optional[set] = None,
) -> Optional[dict]:
    """Select the most informative question for the current ability estimate (CAT).

    Uses maximum information criterion: pick the question with highest
    Fisher information at the current theta estimate.

    Args:
        current_theta: current ability estimate
        available_questions: list of question dicts with 'id' field
        item_params: known item parameters
        exclude_ids: question IDs to exclude (already answered)

    Returns:
        The most informative question, or None if no suitable question found
    """
    exclude = exclude_ids or set()
    best_question = None
    best_info = -1.0

    for q in available_questions:
        qid = str(q.get("id", ""))
        if qid in exclude:
            continue

        params = item_params.get(qid)
        if params is None:
            # Default parameters for uncalibrated items
            params = ItemParams(difficulty=0.0, discrimination=1.0)

        info = _item_information(current_theta, params)
        if info > best_info:
            best_info = info
            best_question = q

    return best_question


def calibrate_item(
    responses: List[dict],
    known_abilities: dict[str, float],
) -> ItemParams:
    """Calibrate item parameters from response data.

    Uses a simplified JML (Joint Maximum Likelihood) approach.
    For production, use a proper IRT library like girth or py-irt.

    Args:
        responses: list of {user_id: str, is_correct: bool}
        known_abilities: dict of user_id -> theta

    Returns:
        Estimated ItemParams
    """
    if not responses:
        return ItemParams(difficulty=0.0, discrimination=1.0)

    # Simple proportion-correct based difficulty
    n_correct = sum(1 for r in responses if r.get("is_correct"))
    n_total = len(responses)
    p_correct = n_correct / n_total if n_total > 0 else 0.5

    # Convert proportion to logit scale
    p_correct = max(0.01, min(0.99, p_correct))
    difficulty = -math.log(p_correct / (1 - p_correct))

    # Discrimination from point-biserial correlation (simplified)
    if len(responses) >= 5 and known_abilities:
        correct_thetas = [known_abilities[r["user_id"]] for r in responses if r.get("is_correct") and r["user_id"] in known_abilities]
        incorrect_thetas = [known_abilities[r["user_id"]] for r in responses if not r.get("is_correct") and r["user_id"] in known_abilities]

        if correct_thetas and incorrect_thetas:
            mean_correct = sum(correct_thetas) / len(correct_thetas)
            mean_incorrect = sum(incorrect_thetas) / len(incorrect_thetas)
            discrimination = max(0.5, min(2.5, (mean_correct - mean_incorrect) / 1.5))
        else:
            discrimination = 1.0
    else:
        discrimination = 1.0

    return ItemParams(difficulty=difficulty, discrimination=discrimination)


def get_adaptive_questions(
    user_id: str,
    knowledge_point: str,
    n_questions: int = 5,
) -> List[dict]:
    """Get adaptively selected questions for a knowledge point.

    Selects questions that are most informative for the student's current ability.
    """
    from app.repositories.vertical_loop_repository import repository

    # Get student's current ability estimate
    profile = None
    try:
        from app.services import profile_service
        profile = profile_service.get_profile_by_id(user_id)
    except Exception:
        pass

    theta = 0.0
    if profile:
        dims = profile.knowledge_profile.topic_dimensions.get(knowledge_point)
        if dims:
            theta = (dims.composite_score - 0.5) * 4  # map 0-1 to -2 to 2

    # Get available questions
    questions = repository.list_questions(knowledge_point=knowledge_point, limit=50)
    if not questions:
        return []

    # Get item parameters (from metadata or defaults)
    item_params: dict[str, ItemParams] = {}
    for q in questions:
        qid = str(q.get("id", ""))
        meta = q.get("metadata", {}) or {}
        irt = meta.get("irt", {})
        if irt:
            item_params[qid] = ItemParams(
                difficulty=irt.get("difficulty", 0.0),
                discrimination=irt.get("discrimination", 1.0),
            )

    # Select questions adaptively
    selected = []
    exclude_ids = set()
    current_theta = theta

    for _ in range(n_questions):
        q = select_next_question(current_theta, questions, item_params, exclude_ids)
        if not q:
            break
        selected.append(q)
        exclude_ids.add(str(q.get("id", "")))

    return selected
