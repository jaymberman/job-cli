import difflib
import re

AUTO_THRESHOLD = 0.80
CONFIRM_THRESHOLD = 0.55
AUTO_MARGIN = 0.12


def normalize(name):
    return re.sub(r"[^a-z0-9]", "", name.strip().lower())


def active_records(data):
    return {k: v for k, v in data.items() if not v.get("deleted", False)}


def deleted_records(data):
    return {k: v for k, v in data.items() if v.get("deleted", False)}


def company_records(pool, norm_key):
    return [rec for rec in pool.values() if normalize(rec["company"]) == norm_key]


def score(a, b):
    if a == b:
        return 1.0
    if a and b and (a in b or b in a):
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        containment = 0.75 + 0.25 * (len(shorter) / len(longer))
        return max(containment, difflib.SequenceMatcher(None, a, b).ratio())
    return difflib.SequenceMatcher(None, a, b).ratio()


def confirm(prompt):
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def resolve_company_key(pool, query, data=None):
    """Find the normalized company name (fuzzily, if needed) among the
    records in `pool` (an id-keyed dict) matching `query`. Returns the
    normalized company string, or None if there's no match (or the user
    declines a fuzzy guess). Matches against distinct normalized company
    names rather than individual records, since `pool` may legitimately
    contain several records (e.g. declined history) sharing one company.

    If `data` (the full, unfiltered dataset) is given and `query` exactly
    matches some company that exists in `data` but happens to fall outside
    `pool` (e.g. a soft-deleted company being looked up in the active-only
    pool), resolution stops there instead of falling through to a fuzzy
    guess against some unrelated company that *is* in `pool` — a company
    name typed exactly right should never be reinterpreted as a typo of
    something else just because it isn't in this particular pool."""
    norm = normalize(query)

    distinct = {}
    for rec in pool.values():
        key = normalize(rec["company"])
        if key not in distinct or rec["applied"] > distinct[key][1]:
            distinct[key] = (rec["company"], rec["applied"])
    if norm in distinct:
        return norm

    if data is not None and any(normalize(rec["company"]) == norm for rec in data.values()):
        return None
    if not distinct:
        return None

    scored = sorted(
        ((key, score(norm, key)) for key in distinct),
        key=lambda pair: pair[1],
        reverse=True,
    )
    top_key, top_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0.0

    if top_score >= AUTO_THRESHOLD and (top_score - second_score) >= AUTO_MARGIN:
        return top_key
    if top_score >= CONFIRM_THRESHOLD:
        display = distinct[top_key][0]
        if confirm(f"Did you mean '{display}'?"):
            return top_key
        return None
    return None


def resolve_active(data, query):
    """Fuzzy-resolves `query` to the id of the single active (non-deleted)
    record for that company, or None. Since at most one active record can
    exist per company, this is the resolution used everywhere a command
    targets "the" record for a company: lookup, status, delete, interview."""
    pool = active_records(data)
    norm_key = resolve_company_key(pool, query, data=data)
    if norm_key is None:
        return None
    for key, rec in pool.items():
        if normalize(rec["company"]) == norm_key:
            return key
    return None
