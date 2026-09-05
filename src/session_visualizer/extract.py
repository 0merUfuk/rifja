"""Conservative, local extraction of explicit continuity statements.

This module classifies text. It neither resolves project identity nor applies
state transitions. In particular, a correction target is only a reference for
the application to resolve within the originating scope and chronology.
"""

from __future__ import annotations

import re

from .models import Candidate, Record
from .semantics import conversational, document_candidates, natural

MAX_CANDIDATES = 256


class ExtractionLimitError(ValueError):
    """One source record contains more structured items than the safe limit."""


_MARKERS = {
    "GOAL": "objective",
    "OBJECTIVE": "objective",
    "HEDEF": "objective",
    "AMAÇ": "objective",
    "TASK": "task",
    "GÖREV": "task",
    "GOREV": "task",
    "NEXT": "next_action",
    "NEXT ACTION": "next_action",
    "SONRA": "next_action",
    "SONRAKİ ADIM": "next_action",
    "SONRAKI ADIM": "next_action",
    "BLOCKER": "blocker",
    "ENGEL": "blocker",
    "DECISION": "decision",
    "KARAR": "decision",
    "CANCEL": "cancelled",
    "CANCELLED": "cancelled",
    "İPTAL": "cancelled",
    "IPTAL": "cancelled",
    "SUPERSEDES": "superseded",
    "SUPERSEDE": "superseded",
    "REPLACES": "superseded",
    "CORRECTION": "superseded",
    "DÜZELTME": "superseded",
    "DUZELTME": "superseded",
    "DONE": "user_completed",
    "COMPLETED": "user_completed",
    "BİTTİ": "user_completed",
    "BITTI": "user_completed",
    "TAMAMLANDI": "user_completed",
    "PRINCIPLE": "principle",
    "İLKE": "principle",
    "ILKE": "principle",
}
_MARKER_RE = re.compile(
    r"^(?P<marker>"
    + "|".join(re.escape(x) for x in sorted(_MARKERS, key=len, reverse=True))
    + r")\s*:\s*(?P<body>.+)$",
    re.IGNORECASE,
)
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")
_LIST_RE = re.compile(r"^\s{0,3}(?:[-*+] |\d+[.)] )(?:(\[[ xX]\]) )?")
_INLINE_CODE_RE = re.compile(r"(`+).*?\1")
_REQUEST_RE = re.compile(
    r"^(?:please\s+(?!note\b|remember\s+that\b)|"
    r"lütfen\s+|lutfen\s+|"
    r"(?:can|could|would)\s+you\s+(?:please\s+)?|"
    r"(?:i\s+want|i\s+need)\s+you\s+to\s+)",
    re.IGNORECASE,
)
_SUCCESS_RE = re.compile(
    r"(?:\bdone\b|\bcompleted\b|\bfixed\b|\bverified\b|\bdeployed\b|"
    r"\btests?\s+(?:all\s+)?(?:pass(?:ed)?|succeed(?:ed)?)\b|"
    r"\b\d+\s+(?:tests?\s+)?passed\b|\btamamlandı\b|\bbitti\b|"
    r"\bdüzeltildi\b|\btestler\s+(?:başarıyla\s+)?geçti\b)",
    re.IGNORECASE,
)
_ATTRIBUTE_RE = re.compile(
    r"^(?P<name>RATIONALE|REASON|GEREKÇE|GEREKCE|PRIORITY|ÖNCELİK|ONCELIK|"
    r"DEPENDS_ON|DEPENDENCIES|BAĞIMLILIKLAR|BAGIMLILIKLAR)\s*:\s*(?P<value>.+)$",
    re.IGNORECASE,
)
_TARGET_AT_START_RE = re.compile(
    r"^(?:\[(?P<bracket>[A-Za-z0-9][A-Za-z0-9_.:-]*)\]|"
    r"<(?P<angle>[A-Za-z0-9][A-Za-z0-9_.:-]*)>|"
    r"\#(?P<hash>[A-Za-z0-9][A-Za-z0-9_-]*)|"
    r"(?P<bare>[A-Za-z0-9][A-Za-z0-9_-]*))(?=$|[\s,.;:])"
)
_TRANSITIONS = {"cancelled", "superseded", "user_completed"}


def _fold(value: str) -> str:
    """Fold Turkish dotted I consistently for the ASCII marker aliases."""
    return value.upper().replace("İ", "I")


_FOLDED_MARKERS = {_fold(key): value for key, value in _MARKERS.items()}


def _lines(text: str) -> list[str]:
    """Return prose lines, excluding quoted and code regions.

    A fence with no close consumes the remainder. We do not guess that text
    inside malformed code was meant as a new instruction.
    """
    result: list[str] = []
    fence_char: str | None = None
    fence_length = 0
    quoted_paragraph = False
    comment = False
    for raw in text.splitlines():
        if "<!--" in raw:
            comment = True
        if comment:
            if "-->" in raw:
                comment = False
            continue
        listed = _LIST_RE.match(raw)
        fence_input = raw[listed.end() :] if listed else raw
        fence = _FENCE_RE.match(fence_input)
        if fence:
            token, suffix = fence.groups()
            if fence_char is None:
                fence_char, fence_length = token[0], len(token)
            elif token[0] == fence_char and len(token) >= fence_length and not suffix.strip():
                fence_char = None
            continue
        if fence_char is not None:
            continue
        # Markdown indented code, blockquotes and explicit quote-only lines.
        if raw.startswith(("    ", "\t")):
            continue
        line = raw.strip()
        if not line:
            quoted_paragraph = False
            continue
        if line.startswith(">"):
            quoted_paragraph = True
            continue
        if quoted_paragraph or line.startswith(('"', "'", "“", "‘")):
            continue
        if listed:
            if listed.group(1) and "x" in listed.group(1).lower():
                continue
            line = raw[listed.end() :].strip()
        # Preserve inline filenames/commands in real instructions. A marker
        # inside inline code cannot match the anchored marker/request grammar.
        if line:
            result.append(line)
    return result


def _targets(body: str) -> list[str]:
    """Read only explicit leading identifiers, never freeform task matching."""
    targets: list[str] = []
    rest = body.strip()
    while match := _TARGET_AT_START_RE.match(rest):
        target = next(value for value in match.groupdict().values() if value is not None)
        # A bare natural word such as 'everything' is not an explicit ID.
        # Brackets, a # prefix, or an identifier with digits/-/_ are explicit.
        if match.group("bare") and not re.search(r"[\d_-]", target):
            break
        targets.append(target)
        if len(targets) > MAX_CANDIDATES:
            raise ExtractionLimitError("record_extraction_limit")
        rest = rest[match.end() :].lstrip()
        if not rest.startswith(","):
            break
        rest = rest[1:].lstrip()
    return list(dict.fromkeys(targets))


def _attribute(candidate: Candidate, name: str, value: str) -> None:
    folded = _fold(name)
    if folded in {"RATIONALE", "REASON", "GEREKÇE", "GEREKCE"}:
        candidate.rationale = value.strip()
    elif folded in {"PRIORITY", "ÖNCELIK", "ONCELIK"}:
        candidate.priority = value.strip()
    else:
        candidate.dependencies = [
            part.strip().strip("[]") for part in value.split(",") if part.strip().strip("[]")
        ]


def _attributes(candidate: Candidate) -> None:
    parts = candidate.text.split(" | ")
    retained = [parts[0]]
    for part in parts[1:]:
        match = _ATTRIBUTE_RE.match(part.strip())
        if match:
            _attribute(candidate, match.group("name"), match.group("value"))
        else:
            retained.append(part)
    candidate.text = " | ".join(retained)
    if candidate.priority is None and re.match(
        r"^(?:critical\b|kritik\b|\[critical\]|\[kritik\])\s*:?", candidate.text, re.IGNORECASE
    ):
        candidate.priority = "critical"


def extract(record: Record) -> list[Candidate]:
    """Extract explicit statements, retaining actor-specific claim categories.

    No candidate carries a verified-complete status. Tool records remain
    historical captured results, even when their text contains intent markers.
    """
    if not record.text or not record.text.strip():
        return []
    if record.kind in {"metadata", "source_status", "revision"}:
        return []
    actor = record.actor.lower()
    if record.provider == "project_document" and record.kind == "document_section":
        if record.metadata.get("source_context") in {"code", "quote"}:
            return []
        result = document_candidates(record, _lines(record.text))
        if len(result) > MAX_CANDIDATES:
            raise ExtractionLimitError("record_extraction_limit")
        return result
    if actor == "tool" or record.kind in {"tool_result", "tool_output", "recorded_tool_result"}:
        return [Candidate("claim", record.text.strip(), "recorded", "recorded_tool_result")]
    if record.kind == "agent_proposal" and record.metadata.get("tool"):
        return [Candidate("context", record.text.strip(), "proposed", "agent_proposal")]

    candidates: list[Candidate] = []
    for line in _lines(record.text):
        if len(candidates) > MAX_CANDIDATES:
            raise ExtractionLimitError("record_extraction_limit")
        attr = _ATTRIBUTE_RE.match(line)
        if attr:
            if candidates:
                _attribute(candidates[-1], attr.group("name"), attr.group("value"))
            continue
        match = _MARKER_RE.match(line)
        if match:
            kind = _FOLDED_MARKERS[_fold(match.group("marker"))]
            body = match.group("body").strip()
            if kind in _TRANSITIONS:
                if actor == "user":
                    targets = _targets(body)
                    # An unresolved explicit correction is retained, but
                    # cannot authorize a broad or fuzzy state transition.
                    resolved_targets: list[str | None] = list(targets) if targets else [None]
                    for target in resolved_targets:
                        candidates.append(
                            Candidate("correction", body, kind, "user_correction", target=target)
                        )
                elif kind == "user_completed":
                    candidates.append(
                        Candidate(
                            "claim",
                            body,
                            "unverified",
                            "agent_claim" if actor == "assistant" else "interpretation",
                        )
                    )
                else:
                    candidates.append(
                        Candidate(
                            "correction",
                            body,
                            "proposed",
                            "agent_proposal" if actor == "assistant" else "interpretation",
                        )
                    )
                continue
            if kind == "principle":
                candidate = Candidate(kind, body, "proposed", "interpretation")
            elif actor == "user":
                status = "blocked" if kind == "blocker" else "active"
                candidate = Candidate(kind, body, status, "user_intent")
            elif actor == "assistant" and kind == "blocker":
                candidate = Candidate(kind, body, "blocked", "agent_claim")
            else:
                candidate = Candidate(
                    kind,
                    body,
                    "proposed",
                    "agent_proposal" if actor == "assistant" else "interpretation",
                )
            _attributes(candidate)
            candidates.append(candidate)
        elif actor == "user" and conversational(line):
            candidates.extend(natural(line, actor))
        elif actor == "user" and _REQUEST_RE.match(line):
            candidate = Candidate("next_action", line, "active", "user_intent")
            _attributes(candidate)
            candidates.append(candidate)
        else:
            ordinary = natural(line, actor)
            if ordinary:
                candidates.extend(ordinary)
            elif actor == "assistant" and _SUCCESS_RE.search(_INLINE_CODE_RE.sub(" ", line)):
                candidates.append(Candidate("claim", line, "unverified", "agent_claim"))
    if len(candidates) > MAX_CANDIDATES:
        raise ExtractionLimitError("record_extraction_limit")
    return candidates
