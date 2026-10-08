"""Conservative candidate-set diagnosis for watch-workflow boundaries.

The module deliberately separates three concerns:

* ``record_signature`` maps one executed episode to an observable outcome;
* ``predict_signature`` states the small, ordered fault model used for planning;
* ``choose_intervention`` selects a repair set that minimizes the largest
  remaining candidate bucket, with repair breadth used only as a tie-breaker.

A mismatch between an executed signature and every model candidate is reported
as unmodeled evidence.  The implementation never substitutes the planner model
for the final-state oracle in :mod:`watchdelta.run`.
"""
from __future__ import annotations

from itertools import combinations
from typing import Any, Iterable, Sequence

UPSTREAM_BOUNDARIES: tuple[str, ...] = (
    "selection",
    "observation_scope",
    "state_predicate",
)
DOWNSTREAM_BOUNDARIES: tuple[str, ...] = (
    "scheduling",
    "consumer",
    "publication",
)
BOUNDARIES: tuple[str, ...] = UPSTREAM_BOUNDARIES + DOWNSTREAM_BOUNDARIES
PIPELINE_ORDER: dict[str, int] = {name: index for index, name in enumerate(BOUNDARIES)}

SIGNATURES: tuple[str, ...] = (
    "matched",
    "upstream_silence",
    "scheduling_failure",
    "consumer_failure",
    "publication_failure",
)

Hypothesis = frozenset[str]
Intervention = frozenset[str]


def _ordered(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(values, key=lambda value: (PIPELINE_ORDER.get(value, 99), value)))


def serialize_set(values: Iterable[str]) -> list[str]:
    """Return a stable JSON-friendly boundary order."""
    return list(_ordered(values))


def hypothesis_space() -> tuple[Hypothesis, ...]:
    """Enumerate the declared fault model.

    The three observer-side mutations are mutually exclusive configurations,
    while downstream scheduling, consumer, and publication faults may coexist.
    The empty set represents a healthy relevant-edit episode.
    """
    result: list[Hypothesis] = []
    for upstream in (None, *UPSTREAM_BOUNDARIES):
        for width in range(len(DOWNSTREAM_BOUNDARIES) + 1):
            for downstream in combinations(DOWNSTREAM_BOUNDARIES, width):
                values = set(downstream)
                if upstream is not None:
                    values.add(upstream)
                result.append(frozenset(values))
    result.sort(key=lambda item: (len(item), _ordered(item)))
    return tuple(result)


def intervention_catalog() -> tuple[Intervention, ...]:
    """Return every nonempty repair subset in deterministic order."""
    result: list[Intervention] = []
    for width in range(1, len(BOUNDARIES) + 1):
        for repair in combinations(BOUNDARIES, width):
            result.append(frozenset(repair))
    return tuple(result)


def predict_signature(hypothesis: Hypothesis, repairs: Intervention) -> str:
    """Predict the first observable boundary after applying ``repairs``.

    Observer-side failures intentionally collapse to ``upstream_silence``:
    the runtime record alone cannot tell a wrong filter, wrong watch root, and
    an inadequate metadata predicate apart.  Targeted interventions provide
    the information needed to split those candidates.
    """
    remaining = hypothesis.difference(repairs)
    if any(boundary in remaining for boundary in UPSTREAM_BOUNDARIES):
        return "upstream_silence"
    if "scheduling" in remaining:
        return "scheduling_failure"
    if "consumer" in remaining:
        return "consumer_failure"
    if "publication" in remaining:
        return "publication_failure"
    return "matched"


def record_signature(record: dict[str, Any]) -> str:
    """Map one real episode record to a planner observation.

    ``unknown_stale`` is intentionally outside ``SIGNATURES``.  It causes all
    modeled candidates to be rejected rather than forcing an attractive label.
    Infrastructure and oracle failures are likewise kept outside the model.
    """
    status = record.get("status")
    if status == "matched":
        return "matched"
    if status != "stale":
        return f"noncomparable:{status}"
    metrics = record.get("metrics", {})
    if metrics.get("failed_builds", 0) > 0:
        return "consumer_failure"
    if record.get("unpublished_matches_clean") is True:
        return "publication_failure"
    if metrics.get("accepted_events", 0) > 0 and record.get("completed_builds", 0) == 0:
        return "scheduling_failure"
    if metrics.get("accepted_events", 0) == 0 and record.get("completed_builds", 0) == 0:
        return "upstream_silence"
    return "unknown_stale"


def update_candidates(
    candidates: Sequence[Hypothesis], repairs: Intervention, observed: str
) -> tuple[Hypothesis, ...]:
    """Keep exactly the candidates compatible with one observation."""
    return tuple(candidate for candidate in candidates if predict_signature(candidate, repairs) == observed)


def partition_sizes(candidates: Sequence[Hypothesis], repairs: Intervention) -> dict[str, int]:
    parts: dict[str, int] = {}
    for candidate in candidates:
        signature = predict_signature(candidate, repairs)
        parts[signature] = parts.get(signature, 0) + 1
    return dict(sorted(parts.items()))


def choose_intervention(
    candidates: Sequence[Hypothesis], used: Iterable[Intervention] = ()
) -> Intervention | None:
    """Choose a deterministic minimax intervention.

    The primary objective minimizes the largest possible remaining candidate
    bucket.  The squared bucket sum is the second objective.  Only then do we
    prefer a narrower repair and a stable lexical order.  No failure-prior or
    field prevalence is assumed.
    """
    used_set = set(used)
    best: tuple[tuple[Any, ...], Intervention] | None = None
    for repairs in intervention_catalog():
        if repairs in used_set:
            continue
        sizes = tuple(sorted(partition_sizes(candidates, repairs).values(), reverse=True))
        if len(sizes) <= 1:
            continue
        score = (
            sizes[0],
            sum(size * size for size in sizes),
            len(repairs),
            _ordered(repairs),
        )
        if best is None or score < best[0]:
            best = (score, repairs)
    return None if best is None else best[1]


def greedy_separating_panel() -> tuple[Intervention, ...]:
    """Construct a fixed nonadaptive panel that separates the model space.

    This is a deterministic greedy test-cover construction, not a claim of
    minimum cardinality.  It is used only as an interpretable nonadaptive
    reference for the active planner's episode count.
    """
    hypotheses = hypothesis_space()
    pairs = {
        (left, right)
        for left in range(len(hypotheses))
        for right in range(left + 1, len(hypotheses))
    }
    catalog = intervention_catalog()
    distinguished: dict[Intervention, set[tuple[int, int]]] = {}
    for repairs in catalog:
        distinguished[repairs] = {
            pair
            for pair in pairs
            if predict_signature(hypotheses[pair[0]], repairs)
            != predict_signature(hypotheses[pair[1]], repairs)
        }
    uncovered = set(pairs)
    panel: list[Intervention] = []
    while uncovered:
        choices = []
        for repairs in catalog:
            if repairs in panel:
                continue
            gain = len(distinguished[repairs].intersection(uncovered))
            choices.append((-gain, len(repairs), _ordered(repairs), repairs))
        gain_neg, _breadth, _name, selected = min(choices)
        if gain_neg == 0:
            raise RuntimeError("No intervention can complete the separating panel")
        panel.append(selected)
        uncovered.difference_update(distinguished[selected])
    return tuple(panel)


def simulate_active_trace(truth: Hypothesis) -> tuple[tuple[Hypothesis, ...], list[dict[str, Any]]]:
    """Run the planner against its declared model; useful for protocol checks."""
    candidates = hypothesis_space()
    used: list[Intervention] = []
    trace: list[dict[str, Any]] = []
    repairs: Intervention = frozenset()
    while True:
        observed = predict_signature(truth, repairs)
        before = len(candidates)
        candidates = update_candidates(candidates, repairs, observed)
        trace.append(
            {
                "repairs": serialize_set(repairs),
                "observed": observed,
                "candidates_before": before,
                "candidates_after": len(candidates),
            }
        )
        used.append(repairs)
        if len(candidates) <= 1:
            return candidates, trace
        selected = choose_intervention(candidates, used)
        if selected is None:
            return candidates, trace
        repairs = selected
