"""Topic classification: candidate evidence plus controlled-object check.

The matcher is intentionally simple and reproducible. Sentence-level matching
only produces candidates; a candidate is accepted only when it describes the
same engine that is being speed-controlled. Two-stroke mentions in comparison
clauses do not promote a record, and piston evidence must be explicit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

RULE_VERSION = "rule-v1"

E1 = (
    "aircraft", "aviation", "airplane", "aeroplane", "uav",
    "unmanned aerial vehicle", "drone", "flight", "aerospace",
)
E2 = (
    "piston engine", "piston engines", "reciprocating engine",
    "spark-ignition engine", "si engine",
)
E3 = ("two-stroke", "two stroke", "2-stroke", "2 stroke", "two-cycle", "2-cycle")
E4 = (
    "engine speed control", "engine speed regulation", "engine speed tracking",
    "speed control of the engine", "speed regulation", "rpm control",
    "idle speed control", "governor", "engine governor", "speed tracking",
)
X1 = ("bldc", "pmsm", "induction motor", "brushless dc", "electric motor")
X2 = ("gas turbine", "turbojet", "turbofan", "turboprop", "turboshaft", "spool speed")
X3 = ("vehicle speed", "cruise control", "road speed", "vehicle velocity")
X4 = ("propeller speed", "propeller pitch")
X5 = ("combustion", "emissions", "knock", "thermal efficiency", "spray")

COMPARISON = re.compile(
    r"(compared\s+(?:with|to)|in\s+contrast|for\s+(?:\w+\s+){0,4}comparison|"
    r"reference\s+engine|baseline\s+engine|second\s+engine|another\s+engine|whereas|while)",
    re.IGNORECASE,
)


def _compile(terms: tuple[str, ...]) -> list[tuple[str, re.Pattern[str]]]:
    return [
        (term, re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", re.IGNORECASE))
        for term in terms
    ]


_GROUPS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "E1": _compile(E1),
    "E2": _compile(E2),
    "E3": _compile(E3),
    "E4": _compile(E4),
    "X1": _compile(X1),
    "X2": _compile(X2),
    "X3": _compile(X3),
    "X4": _compile(X4),
    "X5": _compile(X5),
}


def find_terms(group: str, text: str) -> list[str]:
    return [term for term, pattern in _GROUPS[group] if pattern.search(text)]


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?;])\s+", normalized) if part.strip()]


def main_clause(sentence: str) -> str:
    """Drop comparison clauses so their evidence cannot be co-referent."""
    match = COMPARISON.search(sentence)
    return sentence[: match.start()] if match else sentence


@dataclass(frozen=True)
class ClassifyResult:
    category: str
    reason: str
    evidence: dict[str, list[str]] = field(default_factory=dict)
    rule_version: str = RULE_VERSION


def _excluded(reason: str, evidence: dict[str, list[str]] | None = None) -> ClassifyResult:
    return ClassifyResult("excluded", reason, evidence or {})


def classify_record(title: str, abstract: str | None) -> ClassifyResult:
    text = f"{title}. {abstract or ''}".strip()
    sentences = split_sentences(text)
    if not sentences:
        return _excluded("step3:no_evidence")

    anchors = [i for i, s in enumerate(sentences) if find_terms("E4", s)]
    if not anchors:
        return _excluded("step3:no_e4")
    anchors.sort(key=lambda i: (0 if "engine" in sentences[i].lower() else 1, i))
    anchor_index = anchors[0]
    anchor = main_clause(sentences[anchor_index])

    x1 = find_terms("X1", anchor)
    x2 = find_terms("X2", anchor)
    e2_anchor = find_terms("E2", anchor)
    e3_anchor = find_terms("E3", anchor)
    if (x1 or x2) and not e2_anchor and not e3_anchor:
        kind = "x1_electric" if x1 else "x2_turbine"
        return _excluded(f"step1:{kind}", {"X1": x1, "X2": x2})

    evidence: dict[str, list[str]] = {}
    for group in ("E1", "E2", "E3", "E4"):
        found = find_terms(group, anchor)
        if found:
            evidence[group] = found

    # Neighbouring sentences may supply context, but only if they describe an
    # engine and are not comparison clauses.
    for offset in (-1, 1):
        index = anchor_index + offset
        if not 0 <= index < len(sentences):
            continue
        neighbour = sentences[index]
        if "engine" not in neighbour.lower():
            continue
        if COMPARISON.search(neighbour):
            continue
        for group in ("E1", "E2", "E3"):
            found = find_terms(group, neighbour)
            if not found:
                continue
            merged = sorted({*evidence.get(group, []), *found})
            evidence[group] = merged

    has_e1 = "E1" in evidence
    has_e2 = "E2" in evidence
    has_e3 = "E3" in evidence

    if not evidence.get("E4"):
        return _excluded("step3:no_e4", evidence)
    if has_e1 and has_e2 and has_e3:
        return ClassifyResult("direct", "step4:direct", evidence)
    if has_e3 and not has_e1:
        return ClassifyResult("near_two_stroke", "step5:near_two_stroke", evidence)
    if has_e1 and has_e2 and not has_e3:
        return ClassifyResult("near_aircraft", "step6:near_aircraft", evidence)
    return _excluded("step7:otherwise", evidence)
