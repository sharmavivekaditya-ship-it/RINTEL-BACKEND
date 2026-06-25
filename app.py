"""
Rintel Scoring API  ·  private backend service
------------------------------------------------
The proprietary scoring engine runs HERE and only here. It is never shipped to
the frontend, to Supabase, or to any third-party builder. The Lovable app calls
this API and renders the JSON it returns; it never sees the engine code.

Endpoints
  GET  /health                 -> liveness
  POST /api/score              -> score from structured transactions OR demo profile
  POST /api/score/upload       -> score from an uploaded PDF (normalisation stub)

Auth: every /api/* call must send header  X-API-Key: <RINTEL_API_KEY>
CORS: locked to ALLOWED_ORIGIN (your Lovable app URL).
"""
import os, json
from flask import Flask, request, jsonify
from flask_cors import CORS

from rintel_scoring_engine import score, Config          # the IP — stays server-side
from normalize import normalize_transactions, parse_pdf, NormalizationError

API_KEY        = os.environ.get("RINTEL_API_KEY", "dev-key-change-me")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")   # set to your Lovable URL in prod

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ALLOWED_ORIGIN}})

# ---- consumer-facing presentation (kept server-side; no engine internals exposed) ----
PILLAR_LABEL = {"income":"Income","stability":"Income Stability","resilience":"Savings Buffer",
                "discipline":"Financial Discipline","maturity":"Track Record"}
TIPS = {"income":"Grow and document a steady monthly inflow.",
        "stability":"Even out month-to-month income swings; keep earning every month.",
        "resilience":"Build a cash cushion so more days stay above a healthy balance.",
        "discipline":"Avoid bounced payments, keep obligations below income, and save a little each month.",
        "maturity":"Keep the account active to build a longer, richer history."}
# Plain-language reason copy by code (so technique names never leave the backend)
FRIENDLY = {
    "INCOME_MEDIAN":"Healthy monthly income","INCOME_FLOOR":"Reliable income even in lean months",
    "STAB_DISP":"Income swings month to month","STAB_ACTIVE":"Earns consistently across months",
    "STAB_TREND":"Income trend over time","STAB_PAYER":"Income spread across several sources",
    "RES_BUFFER":"Cash buffer to absorb a shock","RES_DAYSBELOW":"Often runs a very low balance",
    "RES_MINFLOOR":"Low point of balance vs income","RES_DRAWDOWN":"Depth of the worst cash dip",
    "DISC_SAVINGS":"Saves part of what comes in","DISC_FOIR":"Existing obligations vs income",
    "DISC_BOUNCE":"Bounced / failed payments",
    "MAT_MONTHS":"Length of financial history","MAT_DENSITY":"How actively the account is used",
    "IND_GAMBLING":"Significant fantasy-gaming / gambling spend","IND_DISTRESS_LOAN":"Borrowing from digital loan apps",
    "IND_CASH_HEAVY":"Heavy cash use limits visibility","IND_SQUEEZE":"Runs out of money before month-end",
    "IND_NACH_LOAD":"Several auto-debit mandates running","IND_INVESTING":"Regularly invests (SIP / mutual funds)",
    "IND_GST_INCOME":"Verified business income (GST/B2B)","IND_DIGITAL":"Highly active on digital payments",
    "IND_DIVERSITY":"Income from many different sources","IND_RENT":"Earns rental / property income",
}

# sign-aware copy for reasons that can appear as either a strength or a weakness
SIGNED = {
    "INCOME_MEDIAN":("Healthy monthly income","Modest monthly income"),
    "INCOME_FLOOR":("Reliable income even in lean months","Income drops sharply in lean months"),
    "STAB_DISP":("Steady, predictable income","Income swings month to month"),
    "STAB_ACTIVE":("Earns every month","Gaps in monthly earning"),
    "STAB_TREND":("Income trending up","Income trending down"),
    "STAB_PAYER":("Income well spread across sources","Income concentrated in too few sources"),
    "RES_BUFFER":("Strong cash buffer","Thin cash buffer for a shock"),
    "RES_DAYSBELOW":("Rarely runs low","Often runs a very low balance"),
    "RES_MINFLOOR":("Maintains a healthy minimum balance","Balance drops very low"),
    "RES_DRAWDOWN":("Stable balance through the period","Deep dips in balance"),
    "DISC_SAVINGS":("Saves consistently","Spends more than earned"),
    "DISC_FOIR":("Low existing obligations","High existing obligations vs income"),
    "DISC_BOUNCE":("No missed or bounced payments","Bounced / failed payments"),
    "MAT_MONTHS":("Solid length of financial history","Short financial history"),
    "MAT_DENSITY":("Actively used account","Low account activity"),
}
def humanize(rc):
    code, sign = rc.get("code",""), rc.get("sign","")
    if code in SIGNED:
        return SIGNED[code][0] if sign == "+" else SIGNED[code][1]
    return FRIENDLY.get(code, rc.get("text","").split(":")[0])

def serialize(result):
    pillars = {PILLAR_LABEL[k]: round(v) for k, v in result.pillars.items()}
    strengths = [humanize(rc) for rc in result.reason_codes if rc["sign"] == "+"][:4]
    improve   = [humanize(rc) for rc in result.reason_codes if rc["sign"] == "-"][:4]
    weak = sorted(result.pillars.items(), key=lambda kv: kv[1])[:2]
    tips = [TIPS[k] for k, _ in weak]
    return {"score": result.score, "tier": result.tier, "confidence": result.confidence,
            "archetype": result.archetype.title().replace("_", " "),
            "pillars": pillars, "strengths": strengths, "improve": improve, "tips": tips}

def require_key():
    return request.headers.get("X-API-Key") == API_KEY

# ---- demo profiles (so the app works before live data is wired) ----
def _demo(profile):
    import demo_profiles
    gen = {"merchant": demo_profiles.merchant, "salaried": demo_profiles.salaried,
           "stressed": demo_profiles.stressed,
           "hidden":  lambda: demo_profiles.merchant(gambling=True)}.get(profile, demo_profiles.merchant)
    return gen()

@app.get("/health")
def health():
    return jsonify(status="ok")

@app.post("/api/score")
def api_score():
    if not require_key():
        return jsonify(error="unauthorized"), 401
    body = request.get_json(silent=True) or {}
    try:
        if body.get("demo"):
            txns = _demo(body.get("profile", "merchant"))
        else:
            txns = normalize_transactions(body.get("transactions", []))
        if not txns:
            return jsonify(error="no transactions provided"), 400
        return jsonify(serialize(score(txns)))
    except NormalizationError as e:
        return jsonify(error=f"normalization failed: {e}"), 422
    except Exception as e:
        app.logger.exception("scoring error")
        return jsonify(error="scoring failed"), 500

@app.post("/api/score/upload")
def api_score_upload():
    if not require_key():
        return jsonify(error="unauthorized"), 401
    if "file" not in request.files:
        return jsonify(error="no file"), 400
    try:
        raw = parse_pdf(request.files["file"].read())   # <-- Ritam's Task-2 parser drops in here
        txns = normalize_transactions(raw)
        return jsonify(serialize(score(txns)))
    except NotImplementedError:
        # Honest until the parser exists. The AA route is the real production path.
        return jsonify(error="pdf_parsing_not_available",
                       detail="Statement parsing (normalisation pipeline) is not yet wired. "
                              "Use structured transactions or the Account Aggregator flow."), 501
    except NormalizationError as e:
        return jsonify(error=f"normalization failed: {e}"), 422

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
