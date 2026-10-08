"""Construction of fresh actual-process cases for the diagnosis experiments."""
from __future__ import annotations

from typing import Any, Iterable

from .active_diagnosis import BOUNDARIES, DOWNSTREAM_BOUNDARIES, Intervention, serialize_set

UNKNOWN_FAULT = "post_build_corruption"


def slug(values: Iterable[str]) -> str:
    ordered = list(values)
    return "none" if not ordered else "+".join(value.replace("_", "-") for value in ordered)


def case_for_hypothesis(
    *,
    unit_id: str,
    numeric_base: int,
    truth: Iterable[str],
    repairs: Intervention,
    step: int,
    transient_injections: Iterable[str] = (),
) -> dict[str, Any]:
    """Map a declared boundary hypothesis and repair set to one fresh process.

    The planner never receives ``truth``; it is used only by the mutation
    harness.  ``transient_injections`` is reserved for explicitly labelled
    sensitivity experiments and is never folded into field-failure counts.
    """
    truth_set = set(truth)
    repaired = set(repairs)
    scenario = "preserved_stat" if "state_predicate" in truth_set else "same_size"

    if "selection" in truth_set and "selection" not in repaired:
        mode = "wrong_filter"
    elif "observation_scope" in truth_set and "observation_scope" not in repaired:
        mode = "blind_default" if "selection" in repaired else "blind"
    elif "state_predicate" in truth_set and "state_predicate" not in repaired:
        mode = "poll"
    else:
        mode = "relevant"

    injections: list[str] = []
    mapping = {
        "scheduling": "drop",
        "consumer": "fail",
        "publication": "publish_stale",
    }
    for boundary in DOWNSTREAM_BOUNDARIES:
        if boundary in truth_set and boundary not in repaired:
            injections.append(mapping[boundary])
    if UNKNOWN_FAULT in truth_set:
        injections.append("corrupt_output")
    injections.extend(transient_injections)

    repair_list = serialize_set(repairs)
    unknown_boundaries = truth_set.difference(BOUNDARIES).difference({UNKNOWN_FAULT})
    if unknown_boundaries:
        raise ValueError(f"Unknown truth boundaries: {sorted(unknown_boundaries)}")
    return {
        "id": f"{unit_id}--s{step:02d}-{slug(repair_list)}",
        "numeric_id": int(numeric_base) + step,
        "tool": "docs",
        "mode": mode,
        "scenario": scenario,
        "inject": "none" if not injections else ",".join(injections),
        "diagnostic": False,
        "diagnosis_unit": unit_id,
        "diagnosis_repairs": repair_list,
    }
