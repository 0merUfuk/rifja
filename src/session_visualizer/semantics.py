"""Bounded prose classification, never command execution or evidence verification.

Rules identify explicit status language and retain its surrounding conditions.
They do not infer resolution from chronology or similarity between projects.
"""

import re
from pathlib import PurePosixPath

from .models import Candidate, Record

CHAT = re.compile(
    r"(?i)(?:\b(?:continue|resume)\s+(?:this|the|our|previous)\s+(?:chat|session|conversation)\b|"
    r"\bcarry on\s+(?:with\s+)?(?:this|the|our)\s+(?:chat|session|conversation)\b|"
    r"\b(?:repeat|restate|reproduce|give me|show me|send me)\b.{0,70}\b(?:prompt|message|brief|explanation|what you said)\b|"
    r"\b(?:sohbet|oturum|konuşma)(?:e|a|u|ı|ya)?\s+(?:devam|sürdür)|"
    r"\b(?:önceki|son)\s+(?:mesaj|istem).{0,35}(?:tekrar|göster))"
)
PENDING = re.compile(
    r"(?i)\b(?:pending|unfinished|uncompleted|(?:is|are|remains?)\s+incomplete|unverified|unresolved|blocked|"
    r"still\s+(?:need|needs|waiting|required|missing)|remain(?:s)?\s+(?:to|open|unavailable)|"
    r"(?:has|have)\s+yet\s+to\b|"
    r"(?:not|never)\s+(?:yet\s+)?(?:been\s+)?(?:run|verified|completed|tested|checked|started|reached)|"
    r"(?:did|has|have|could)\s+not\s+(?:start|reach|run|verify|complete)|"
    r"(?:couldn't|wasn't|weren't)\s+(?:run|verified|completed|available)|"
    r"bekliyor|beklemede|tamamlanmadı|doğrulanmadı|çalıştırılmadı|bitmedi|eksik|engellendi|h[aâ]l[aâ]\s+gerekli)\b"
)
BLOCKED = re.compile(
    r"(?i)\b(?:blocked|precondition|preflight|contingent|waiting|could not|couldn't|"
    r"unavailable because|no .{0,25}window|engel|önkoşul|beklemek)\b"
)
CONDITION = re.compile(
    r"(?i)\b(?:requires?|required|must|only|before|until|within|unless|precondition|"
    r"preflight|continuous|deadline|allowance|separate|distinct|guarantee|read.only|"
    r"not a prerequisite|does not depend|never a prerequisite|normal runtime|"
    r"concurrent|unavailable is not|sadece|gerekir|gerekiyor|önce|boyunca|koşul|"
    r"bağımsız|salt.okunur|ayrı)\b"
)
DEFERRED = re.compile(
    r"(?i)\b(?:deferred|out.of.scope|future (?:work|release)|non.goals?|"
    r"not (?:planned|required)|optional feature|locked .{0,8}cuts|ertelendi|kapsam dışı)\b"
)
HISTORICAL = re.compile(
    r"(?i)\b(?:historical|earlier|previous|initial|obsolete|superseded|draft|taslak|eski)\b"
)
LIMITATION = re.compile(
    r"(?i)\b(?:coverage|limitations?|known incomplete|not recorded|no (?:remote|publication)|"
    r"nothing was pushed|not published|unparsed|unreadable|encrypted|corrupt|"
    r"platform|linux|windows|not real.data.verified|kapsama|yayımlanmadı)\b"
)
SUCCESS = re.compile(r"(?i)\b(?:passed|completed|verified|succeeded|tamamlandı|geçti)\b")
DECISION = re.compile(
    r"(?i)\b(?:decided|decision|we chose|we use|because|rationale|karar|seçtik|gerekçe)\b"
)
EXAMPLE = re.compile(r"(?i)\b(?:example|hypothetical|for instance|imagine|örnek|varsayalım)\b")
NEGATIVE_PENDING = re.compile(
    r"(?i)\b(?:no\s+(?:pending|unfinished|remaining|outstanding)\s+(?:work|checks?|tasks?)|no longer\s+(?:pending|blocked)|all\s+(?:previously\s+)?pending\s+.{0,45}(?:passed|completed)|bekleyen\s+.{0,30}yok)\b"
)


def prose(text: str) -> str:
    """Remove presentation decoration, retaining words, links' labels and negation."""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", "")).strip()


def conversational(text: str) -> bool:
    return bool(CHAT.search(text))


def topic(text: str) -> str:
    """Exact explicit-subject key, not synonym, embedding or fuzzy resolution."""
    text = prose(text).casefold().replace("\u0307", "").strip(" .!?\"'")
    text = re.sub(
        r"^(?:please |lütfen |the |cancel |complete |supersede |drop |can you |i want you to )+",
        "",
        text,
    )
    text = re.sub(
        r"\s+(?:(?:is|are|remains?|was|has been)\s+)?(?:still\s+)?"
        r"(?:pending|unfinished|blocked|cancelled|canceled|completed|superseded|"
        r"bekliyor|iptal edildi|tamamlandı|ertelendi)[.!?]*$",
        "",
        text,
    )
    text = text.strip(" .!?")
    if re.search(r"\bimza\b", text):
        text = "signature verification"
    for verb, endings in (
        ("validate", ("doğrula", "doğrulaması", "doğrulamasını")),
        ("check", ("kontrol et", "kontrolü", "kontrolünü", "denetle", "denetimi", "denetimini")),
    ):
        for ending in endings:
            if text.endswith(" " + ending):
                subject = text[: -(len(ending) + 1)]
                if ending in {"doğrula", "kontrol et", "denetle"}:
                    subject = re.sub(r"(?<=\w)[ny][ıiuü]$", "", subject)
                return verb + ":" + subject
    for verb, nominal in (
        ("verify", "verification"),
        ("validate", "validation"),
        ("check", "check"),
        ("test", "test"),
    ):
        if text.startswith(nominal + " of "):
            return verb + ":" + re.sub(r"^the\s+", "", text[len(nominal) + 4 :])
        if text.startswith(verb + " "):
            return verb + ":" + re.sub(r"^the\s+", "", text[len(verb) + 1 :])
        if text.endswith(" " + nominal):
            return verb + ":" + text[: -(len(nominal) + 1)]
    return text


def blocked(text: str) -> bool:
    return bool(
        BLOCKED.search(
            re.sub(r"(?i)\b(?:not\s+(?:currently\s+)?blocked|no longer blocked)\b", "", text)
        )
    )


def topic_matches(target: str, text: str) -> bool:
    """Finite explicit subject forms; the caller must still require uniqueness."""
    actual = topic(text)
    if target == actual:
        return True
    return (
        target == "verify:signature"
        and actual.startswith("verify:")
        and "signature" in actual.split(":", 1)[1].split()
    )


def natural(line: str, actor: str) -> list[Candidate]:
    text = prose(line)
    if not text or EXAMPLE.search(text):
        return []
    if actor == "user" and conversational(text):
        return [
            Candidate(
                "conversation", text, "unresolved", "conversation_management", method="prose-v1"
            )
        ]
    if actor not in {"user", "assistant"}:
        return []
    if NEGATIVE_PENDING.search(text):
        return [
            Candidate(
                "context",
                text,
                "reported",
                "user_report" if actor == "user" else "agent_claim",
                method="prose-v1",
            )
        ]
    if re.match(r"(?i)^(?:if|when|in case|eğer)\b", text):
        return [
            Candidate(
                "constraint",
                text,
                "recorded",
                "recorded_instruction" if actor == "user" else "agent_proposal",
                method="prose-v1",
            )
        ]
    first, *rest = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    turkish_cancel = re.match(r"(?i)^(.+?)\s+iptal\s+et[.!]?$", first)
    if actor == "user" and turkish_cancel:
        return [
            Candidate(
                "correction",
                first,
                "cancelled",
                "user_correction",
                target="text:" + topic(turkish_cancel[1]),
                method="prose-v1",
            ),
            *(natural(rest[0], actor) if rest else []),
        ]
    transition = re.search(
        r"(?i)^(?:cancel|drop|supersede)\s+(.+)$|^(.+?)\s+(?:(?:is|was|has been)\s+)?"
        r"(cancelled|canceled|completed|superseded|iptal edildi|tamamlandı)[.!]?$",
        first,
    )
    if transition and actor == "user" and not re.search(r"(?i)\b(?:not|never|henüz)\b", first):
        status = "cancelled"
        if re.search(r"(?i)completed|tamamlandı", first):
            status = "user_completed"
        elif re.search(r"(?i)supersed", first):
            status = "superseded"
        target = topic(transition.group(1) or transition.group(2))
        return [
            Candidate(
                "correction",
                first,
                status,
                "user_correction",
                target="text:" + target,
                method="prose-v1",
            )
        ] + (natural(rest[0], actor) if rest else [])
    if DEFERRED.search(text):
        return [
            Candidate(
                "context",
                text,
                "deferred",
                "recorded_instruction" if actor == "user" else "agent_proposal",
                method="prose-v1",
            )
        ]
    if PENDING.search(text):
        kind = "blocker" if blocked(text) else "task"
        return [
            Candidate(
                kind,
                text,
                "blocked" if kind == "blocker" else "active",
                "user_intent" if actor == "user" else "agent_claim",
                method="prose-v1",
            )
        ]
    if actor == "user" and re.match(
        r"(?i)^(?:we (?:still )?need to|we must|(?:run|check|verify|inspect|fix|repair|implement|capture|rerun)\b)",
        text,
    ):
        return [Candidate("next_action", text, "active", "user_intent", method="prose-v1")]
    if actor == "assistant" and re.search(
        r"(?i)\b(?:passed|complete|completed|verified|succeeded)\b", text
    ):
        return [Candidate("claim", text, "unverified", "agent_claim", method="prose-v1")]
    return []


def document_candidates(record: Record, lines: list[str]) -> list[Candidate]:
    """Classify maintained prose with document-level authority and short excerpts.

    Headings only scope text; they cannot turn fenced commands or quoted prompts
    into executable intent. A stated gap is pending; a reported pass is a claim.
    """
    meta = record.metadata
    section = str(meta.get("section", ""))
    name = PurePosixPath(str(meta.get("relative_path", ""))).name.lower()
    historical_section = bool(
        HISTORICAL.search(section) or re.search(r"master.prompt|draft|archive|plan", name)
    )
    deferred_section = bool(DEFERRED.search(section))
    candidates = []
    if not re.search(r"(?m)^\s*(?:[-*+] |\d+[.)] |\||`{3}|~{3}|>|<!--)", record.text):
        lines = [" ".join(lines)]
    paragraphs = [prose(line) for line in lines if not line.lstrip().startswith(("#", "<!--"))]
    # The collector bounds each section. Keep conditions as independent evidence
    # too, so a short opening pending statement cannot lose a later precondition.
    for index, text in enumerate(paragraphs):
        # An inline example does not erase the factual prefix. The example
        # itself remains inert, including any apparent task it contains.
        if re.search(r"(?i)\b(?:for example|for instance)\b", text):
            text = re.split(r"(?i)\b(?:for example|for instance)\b", text, maxsplit=1)[0].rstrip(
                " :;,"
            )
        if not text or text.startswith(("| ---", "---", "BEGIN ", "END ")) or EXAMPLE.search(text):
            continue
        if (
            name.startswith("readme")
            and (not section or int(meta.get("line_start", 9999)) < 14)
            and index < 3
            and not text.startswith("|")
            and (
                " > " not in section or re.search(r"(?i)(?:purpose|overview|about|amaç)$", section)
            )
            and not re.search(
                r"(?i)\b(?:current status|pending|unfinished|tests passed|checks passed)\b", text
            )
        ):
            candidates.append(
                Candidate(
                    "purpose", text, "documented", "documented_purpose", method="document-prose-v1"
                )
            )
        table = text.startswith("|")
        if table and re.fullmatch(r"[| :\-]+", text):
            continue
        # Capability tables describe conditional runtime behavior, not an
        # observed unfinished operation. Header rows are never status evidence.
        if table and (
            re.search(r"(?i)\b(?:decision|claim|harness|warning code|flag)\s*\|", text)
            or not re.search(
                r"(?i)status|pending|unresolved|checks|support|limitation|assumptions|decision",
                section,
            )
        ):
            continue
        pending = bool(PENDING.search(text))
        if re.search(r"(?i)architecture|changelog", name) and not re.search(
            r"(?i)\b(?:pending|unfinished|unverified|still|not yet)\b", text
        ):
            pending = False
        # Negative availability phrasing describes a verification gap but never
        # proves broken software. Keep its original wording intact.
        gap = bool(
            re.search(r"(?i)\b(?:checks?|verification|QA|test|doğrulama)\b", text)
            and re.search(r"(?i)\b(?:unavailable|not available|yapılamadı)\b", text)
        )
        if deferred_section or DEFERRED.search(text):
            kind, status, category = "context", "deferred", "documented_deferred"
        elif NEGATIVE_PENDING.search(text):
            kind, status, category = "claim", "unverified", "documented_claim"
        elif historical_section or re.match(r"(?i)historical\b|earlier\b", text):
            kind, status, category = "context", "historical", "documented_history"
        elif re.match(r"(?i)(?:if|when|in case|should .* fail|eğer)\b", text):
            kind, status, category = "constraint", "documented", "documented_constraint"
        elif pending or gap:
            if LIMITATION.search(text) and not re.search(
                r"(?i)\b(?:release|browser|visual|interactive|sürüm|tarayıcı)\b", text
            ):
                kind, status, category = "limitation", "documented", "documented_limitation"
            else:
                kind = "blocker" if blocked(text) else "task"
                status, category = (
                    ("blocked" if kind == "blocker" else "pending"),
                    "documented_pending",
                )
        elif re.search(
            r"(?i)\b(?:ran|reviewed|built|passed|completed|returned)\b", text
        ) and not re.search(
            r"(?i)\b(?:must|requires?|always|guarantee|continuous|preflight|prerequisite)\b", text
        ):
            kind, status, category = "claim", "unverified", "documented_claim"
        elif CONDITION.search(text):
            kind, status, category = "constraint", "documented", "documented_constraint"
        elif LIMITATION.search(text) and re.search(
            r"(?i)\b(?:incomplete|unparsed|unreadable|unavailable|corrupt|not|no|missing|limitation)\b",
            text,
        ):
            kind, status, category = "limitation", "documented", "documented_limitation"
        elif SUCCESS.search(text):
            kind, status, category = "claim", "unverified", "documented_claim"
        elif DECISION.search(text) and re.search(
            r"(?i)decision|assumption|architecture|karar", section
        ):
            kind, status, category = "decision", "documented", "documented_decision"
        else:
            continue
        candidate = Candidate(kind, text, status, category, method="document-prose-v1")
        # Retain nearby prose under the same meaningful heading. This is source
        # context, not inferred dependency execution or an invented next step.
        candidates.append(candidate)
    return candidates
