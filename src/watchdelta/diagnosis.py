from __future__ import annotations
from typing import Any

def _metric(record: dict[str, Any], name: str) -> int | float:
    return record.get("metrics", {}).get(name, 0)

def classify(base: dict[str, Any], interventions: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    """Classify a controlled watch-workflow outcome from observable intervention signatures.

    The classifier deliberately returns an unresolved label rather than guessing when
    the supplied interventions do not distinguish a boundary.
    """
    evidence: list[str] = []
    obligation = bool(base.get("edit", {}).get("obligation"))
    if base.get("status") == "matched":
        if not obligation and _metric(base, "builds") > 0:
            repaired = interventions.get("relevance_filter")
            if repaired and _metric(repaired, "builds") == 0:
                return "unnecessary_work", ["output-neutral edit rebuilt", "relevance filter removed rebuild"]
        return "healthy", ["terminal projection matches isolated reference"]
    if base.get("status") != "stale":
        return "unresolved", [f"non-comparable status={base.get('status')}"]
    if _metric(base, "failed_builds") > 0:
        return "consumer_failure", ["accepted work ended with a failed consumer"]
    if base.get("unpublished_matches_clean") is True:
        return "publication_failure", ["successful unpublished output matches reference", "served output remains stale"]
    if _metric(base, "accepted_events") > 0 and base.get("completed_builds", 0) == 0:
        return "scheduling_failure", ["change accepted", "no successful build completion", "manual rebuild repairs output"]
    broad = interventions.get("broad_filter")
    if broad and broad.get("status") == "matched":
        return "selection_failure", ["same edit succeeds after broadening selection"]
    blind_broad = interventions.get("broad_filter_same_scope")
    correct_scope = interventions.get("correct_scope")
    if blind_broad and correct_scope and blind_broad.get("status") == "stale" and correct_scope.get("status") == "matched":
        return "observation_scope_failure", ["broader filter cannot repair wrong scope", "correct scope repairs output"]
    native = interventions.get("native_notification")
    content = interventions.get("content_scan")
    if native and content and native.get("status") == "matched" and content.get("status") == "matched":
        return "state_predicate_failure", ["metadata predicate misses final state", "native notification and content scan both repair"]
    return "unresolved", evidence or ["available observations do not isolate a boundary"]
