"""Distance-constrained intervention panels for watch-workflow diagnosis.

The active planner in :mod:`watchdelta.active_diagnosis` minimizes the next
candidate bucket.  This module serves a different operational need: a fixed,
reviewable panel that can be executed by a CI job or handed to a maintainer.

Each hypothesis is encoded by the observable signatures produced by a chosen
intervention panel.  Requiring every pair of codewords to differ in at least
``2 * max_errors + 1`` positions permits nearest-codeword correction of up to
``max_errors`` corrupted observations.  Panel synthesis is a binary multicover
problem: every hypothesis pair must be separated by the required number of
selected interventions.

The decoder is deliberately conservative.  It returns ``unmodeled`` when the
closest codeword exceeds the declared error budget and ``unresolved`` when the
closest codeword is not unique.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Sequence

from .active_diagnosis import (
    Intervention,
    Hypothesis,
    SIGNATURES,
    hypothesis_space,
    intervention_catalog,
    predict_signature,
    serialize_set,
)

SignatureVector = tuple[str, ...]


@dataclass(frozen=True)
class PanelCertificate:
    """Machine-checkable properties of a diagnostic intervention panel."""

    panel: tuple[Intervention, ...]
    max_errors: int
    required_distance: int
    minimum_distance: int
    hypothesis_count: int
    pair_count: int
    selected_count: int
    repair_breadth: int
    solver: str | None = None
    solver_status: str | None = None
    mip_gap: float | None = None
    optimal: bool | None = None
    objective_cost: float | None = None
    candidate_count: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "panel": [serialize_set(item) for item in self.panel],
            "max_errors": self.max_errors,
            "required_distance": self.required_distance,
            "minimum_distance": self.minimum_distance,
            "hypothesis_count": self.hypothesis_count,
            "pair_count": self.pair_count,
            "selected_count": self.selected_count,
            "repair_breadth": self.repair_breadth,
            "solver": self.solver,
            "solver_status": self.solver_status,
            "mip_gap": self.mip_gap,
            "optimal": self.optimal,
            "objective_cost": self.objective_cost,
            "candidate_count": self.candidate_count,
        }


@dataclass(frozen=True)
class DecodeResult:
    """Result of conservative nearest-codeword decoding."""

    status: str
    hypothesis: Hypothesis | None
    distance: int
    tied_hypotheses: tuple[Hypothesis, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "hypothesis": None if self.hypothesis is None else serialize_set(self.hypothesis),
            "distance": self.distance,
            "tied_hypotheses": [serialize_set(item) for item in self.tied_hypotheses],
        }


def signature_vector(hypothesis: Hypothesis, panel: Sequence[Intervention]) -> SignatureVector:
    """Return the model codeword for ``hypothesis`` under ``panel``."""
    return tuple(predict_signature(hypothesis, repairs) for repairs in panel)


def hamming_distance(left: Sequence[str], right: Sequence[str]) -> int:
    if len(left) != len(right):
        raise ValueError("Signature vectors have different lengths")
    return sum(a != b for a, b in zip(left, right, strict=True))


def minimum_distance(
    panel: Sequence[Intervention], hypotheses: Sequence[Hypothesis] | None = None
) -> int:
    """Return the minimum pairwise Hamming distance of the panel codebook."""
    hypotheses = tuple(hypotheses or hypothesis_space())
    if len(hypotheses) < 2:
        return 0
    vectors = [signature_vector(hypothesis, panel) for hypothesis in hypotheses]
    return min(
        hamming_distance(vectors[left], vectors[right])
        for left in range(len(vectors))
        for right in range(left + 1, len(vectors))
    )


def certify_panel(
    panel: Sequence[Intervention],
    max_errors: int,
    *,
    hypotheses: Sequence[Hypothesis] | None = None,
    solver: str | None = None,
    solver_status: str | None = None,
    mip_gap: float | None = None,
    optimal: bool | None = None,
    objective_cost: float | None = None,
    candidate_count: int | None = None,
) -> PanelCertificate:
    if max_errors < 0:
        raise ValueError("max_errors must be nonnegative")
    hypotheses = tuple(hypotheses or hypothesis_space())
    normalized = tuple(frozenset(item) for item in panel)
    if not normalized:
        raise ValueError("Panel must contain at least one intervention")
    if len(set(normalized)) != len(normalized):
        raise ValueError("Panel contains duplicate interventions")
    distance = minimum_distance(normalized, hypotheses)
    required = 2 * max_errors + 1
    if distance < required:
        raise ValueError(
            f"Panel minimum distance {distance} is below required distance {required}"
        )
    return PanelCertificate(
        panel=normalized,
        max_errors=max_errors,
        required_distance=required,
        minimum_distance=distance,
        hypothesis_count=len(hypotheses),
        pair_count=len(hypotheses) * (len(hypotheses) - 1) // 2,
        selected_count=len(normalized),
        repair_breadth=sum(len(item) for item in normalized),
        solver=solver,
        solver_status=solver_status,
        mip_gap=mip_gap,
        optimal=optimal,
        objective_cost=objective_cost,
        candidate_count=candidate_count,
    )


def decode_nearest(
    observed: Sequence[str],
    panel: Sequence[Intervention],
    max_errors: int,
    *,
    hypotheses: Sequence[Hypothesis] | None = None,
) -> DecodeResult:
    """Decode a transcript without forcing unsupported certainty.

    A unique closest codeword within the declared error budget is returned as
    ``exact``.  Equal closest distances produce ``unresolved``.  A unique or
    tied closest distance outside the budget produces ``unmodeled``.
    """
    if max_errors < 0:
        raise ValueError("max_errors must be nonnegative")
    panel = tuple(panel)
    observed = tuple(observed)
    if len(observed) != len(panel):
        raise ValueError("Observed transcript length does not match panel length")
    hypotheses = tuple(hypotheses or hypothesis_space())
    scored = [
        (hamming_distance(observed, signature_vector(hypothesis, panel)), hypothesis)
        for hypothesis in hypotheses
    ]
    best_distance = min(score for score, _ in scored)
    best = tuple(hypothesis for score, hypothesis in scored if score == best_distance)
    if best_distance > max_errors:
        return DecodeResult("unmodeled", None, best_distance, best)
    if len(best) != 1:
        return DecodeResult("unresolved", None, best_distance, best)
    return DecodeResult("exact", best[0], best_distance, best)


def _distinguishing_matrix(
    hypotheses: Sequence[Hypothesis], interventions: Sequence[Intervention]
) -> list[list[float]]:
    rows: list[list[float]] = []
    for left, right in combinations(range(len(hypotheses)), 2):
        rows.append(
            [
                1.0
                if predict_signature(hypotheses[left], repairs)
                != predict_signature(hypotheses[right], repairs)
                else 0.0
                for repairs in interventions
            ]
        )
    return rows


def synthesize_panel(
    max_errors: int,
    *,
    hypotheses: Sequence[Hypothesis] | None = None,
    interventions: Sequence[Intervention] | None = None,
    mandatory: Iterable[Intervention] = (frozenset(),),
    intervention_costs: dict[Intervention, float] | None = None,
) -> PanelCertificate:
    """Synthesize a minimum-cardinality distance-constrained panel.

    The optimization is solved in two stages with SciPy/HiGHS.  Stage one
    minimizes the number of selected interventions.  Stage two fixes that
    optimum and minimizes caller-supplied execution cost, or total repair
    breadth when no costs are supplied.  The mandatory baseline is
    included by default.  The returned certificate is independently checked by
    :func:`certify_panel` before it is exposed to callers.
    """
    if max_errors < 0:
        raise ValueError("max_errors must be nonnegative")
    try:
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import csr_matrix, vstack
    except ImportError as exc:  # pragma: no cover - exercised in setup guidance
        raise RuntimeError(
            "Panel synthesis requires the optional numpy/scipy research dependencies"
        ) from exc

    hypotheses = tuple(hypotheses or hypothesis_space())
    interventions = tuple(interventions or ((frozenset(),) + intervention_catalog()))
    if len(set(interventions)) != len(interventions):
        raise ValueError("Candidate intervention catalog contains duplicates")
    mandatory = tuple(frozenset(item) for item in mandatory)
    missing = [item for item in mandatory if item not in interventions]
    if missing:
        raise ValueError(f"Mandatory intervention not in catalog: {missing}")

    rows = _distinguishing_matrix(hypotheses, interventions)
    matrix = csr_matrix(np.asarray(rows, dtype=float))
    required = float(2 * max_errors + 1)
    lower = np.zeros(len(interventions), dtype=float)
    upper = np.ones(len(interventions), dtype=float)
    for repairs in mandatory:
        index = interventions.index(repairs)
        lower[index] = 1.0
        upper[index] = 1.0
    integrality = np.ones(len(interventions), dtype=int)
    bounds = Bounds(lower, upper)
    pair_constraint = LinearConstraint(matrix, required, np.inf)

    first = milp(
        np.ones(len(interventions), dtype=float),
        integrality=integrality,
        bounds=bounds,
        constraints=pair_constraint,
        options={"presolve": True},
    )
    if not first.success or first.x is None:
        raise RuntimeError(f"Panel cardinality optimization failed: {first.message}")
    cardinality = int(round(float(first.fun)))

    count_row = csr_matrix(np.ones((1, len(interventions)), dtype=float))
    constraints = (
        LinearConstraint(vstack([matrix, count_row]),
                         np.concatenate([np.full(len(rows), required), [cardinality]]),
                         np.concatenate([np.full(len(rows), np.inf), [cardinality]]))
    )
    breadth = np.asarray([len(item) for item in interventions], dtype=float)
    if intervention_costs is None:
        objective = breadth
    else:
        normalized_costs = {
            frozenset(key): float(value) for key, value in intervention_costs.items()
        }
        missing_costs = [item for item in interventions if item not in normalized_costs]
        if missing_costs:
            raise ValueError(f"Missing intervention costs for {len(missing_costs)} candidates")
        if any(value < 0 for value in normalized_costs.values()):
            raise ValueError("Intervention costs must be nonnegative")
        objective = np.asarray([normalized_costs[item] for item in interventions], dtype=float)
    second = milp(
        objective,
        integrality=integrality,
        bounds=bounds,
        constraints=constraints,
        options={"presolve": True},
    )
    if not second.success or second.x is None:
        raise RuntimeError(f"Panel cost optimization failed: {second.message}")

    panel = tuple(
        intervention for intervention, selected in zip(interventions, second.x, strict=True)
        if selected > 0.5
    )
    status = f"{first.message}; {second.message}"
    gap_values = [
        float(value)
        for value in (getattr(first, "mip_gap", None), getattr(second, "mip_gap", None))
        if value is not None
    ]
    gap = max(gap_values) if gap_values else None
    return certify_panel(
        panel,
        max_errors,
        hypotheses=hypotheses,
        solver="scipy.optimize.milp/HiGHS",
        solver_status=status,
        mip_gap=gap,
        optimal=True,
        objective_cost=float(second.fun),
        candidate_count=len(interventions),
    )


def exhaustive_single_corruptions(
    truth: Hypothesis,
    panel: Sequence[Intervention],
    *,
    alphabet: Sequence[str] = SIGNATURES + ("unknown_stale",),
) -> tuple[SignatureVector, ...]:
    """Enumerate every one-position substitution of a truth codeword."""
    codeword = signature_vector(truth, panel)
    cases: list[SignatureVector] = []
    for position, original in enumerate(codeword):
        for replacement in alphabet:
            if replacement == original:
                continue
            mutated = list(codeword)
            mutated[position] = replacement
            cases.append(tuple(mutated))
    return tuple(cases)
