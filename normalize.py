"""
Normalisation layer  ·  raw bank data  ->  the engine's transaction schema.

This is the seam for Ritam's Task-2 pipeline. Today it validates/passes through
already-structured transactions. PDF parsing is intentionally NOT implemented:
real statement parsing is per-bank-format and must be built and tested before it
can feed the engine (a misclassified loan-disbursal-as-income corrupts the score).
"""
class NormalizationError(Exception):
    pass

REQUIRED = ("date", "amount")
ALLOWED_CATEGORIES = {"income","expense","self_transfer","obligation","reversal","other"}

def normalize_transactions(raw):
    """Validate + coerce a list of transaction dicts into the engine schema.
    Engine schema per txn: date 'YYYY-MM-DD', amount float(+credit/-debit),
    optional balance, counterparty, category, description, is_bounce."""
    if not isinstance(raw, list):
        raise NormalizationError("transactions must be a list")
    out = []
    for i, t in enumerate(raw):
        if not all(k in t for k in REQUIRED):
            raise NormalizationError(f"txn {i} missing required field(s) {REQUIRED}")
        cat = t.get("category", "other")
        if cat not in ALLOWED_CATEGORIES:
            cat = "other"
        out.append({
            "date": str(t["date"])[:10],
            "amount": float(t["amount"]),
            "balance": float(t["balance"]) if "balance" in t and t["balance"] is not None else None,
            "counterparty": str(t.get("counterparty", "") or ""),
            "category": cat,
            "description": str(t.get("description", "") or ""),
            "is_bounce": bool(t.get("is_bounce", False)),
        })
    # drop the None balance key so the engine's "all balances present" check behaves
    for t in out:
        if t["balance"] is None:
            del t["balance"]
    return out

def parse_pdf(file_bytes):
    """TODO (Ritam, Task 2): per-bank PDF -> raw transactions.
    Steps when implemented:
      1. extract text/tables (pdfplumber/camelot) per bank-format adapter
      2. parse date / amount / running balance / narration
      3. tag category from narration (income / expense / self_transfer / obligation)
      4. return a list of raw txn dicts for normalize_transactions()
    Until then this raises so the API responds honestly instead of guessing."""
    raise NotImplementedError("statement parsing pipeline not yet implemented")
