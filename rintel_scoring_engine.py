"""
==============================================================================
 RINTEL SCORING ENGINE  ·  v0.2  ·  "Multivariable cold-start expert scorecard"
==============================================================================

WHAT CHANGED FROM v0.1  (all grounded in the Cashflow Scoring Methodology doc)
------------------------------------------------------------------------------
1. CONCENTRATION via HHI.  Payer concentration is now the Herfindahl-Hirschman
   Index (Sum of squared income shares) + effective-payer count + normalised
   entropy -- the validated concentration measure. HHI handles the single-payer
   case correctly, which Gini/top-1-share never did.
2. ROBUST DISPERSION.  Income volatility uses a MAD-based robust coefficient
   (1.4826*MAD/median) instead of the outlier-fragile CV; CV kept for context.
3. MAX DRAWDOWN.  Resilience now includes the deepest peak-to-trough fall in
   the balance series -- the depth of the worst crunch, which "days-below" hides.
4. NON-COMPENSATORY AGGREGATION (the multivariable core).  Pillars are combined
   with a generalised power-mean (p<1, geometric-leaning) instead of a linear
   weighted sum, so a critical weakness is NOT fully compensable by strength
   elsewhere. (Same rationale the UNDP used switching the HDI to a geometric
   mean in 2010.)  Linear aggregation remains available via Config.
5. FRAGILITY INTERACTION.  Co-occurring stresses (>=2 critical pillars) get a
   small super-additive penalty -- real risk compounds, it doesn't add.
6. BEHAVIOURAL SIGNALS NOW SCORE.  India signals previously informational now
   move the composite, bounded and documented: gambling & digital-distress
   borrowing penalise / knock-out; GST-verified income & investing reward;
   month-end squeeze penalises resilience; cash-heavy lowers CONFIDENCE (opaque,
   not bad), GST/UPI raise it.
7. GRADED CONFIDENCE.  Confidence is a numeric function of data depth + data
   completeness + verifiability + gaming, then banded -- not a step ladder.
8. EWMA early-warning for the living layer.

WHAT THIS STILL IS  (read before quoting any number)
----------------------------------------------------
Still a COLD-START EXPERT SCORECARD. Still NOT validated -- every weight,
anchor, the aggregation exponent p, and every interaction/behaviour magnitude
is an EXPERT PRIOR, not learned from outcomes. There is no AUC/KS/Gini here
because there is no seasoned book. Do not invent one. The additive within-pillar
structure is deliberately preserved so a backtest-fitted WOE/logistic scorecard
drops straight in. Deterministic, stdlib-only, fully reason-coded.

IP NOTE: Config (weights, anchors, p, knockouts, behaviour magnitudes) is the
core IP. The feature/normalisation + India-detection layer that feeds this is
safe to share; Config is not.
==============================================================================
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from collections import defaultdict
from statistics import median, pstdev, mean
from typing import Optional
import re as _re
import calendar as _cal
import math as _math


# =============================================================================
#  INDIA-SPECIFIC DETECTION PATTERNS  (feature layer, NOT Config/IP)
# =============================================================================
_NACH_DEBIT  = _re.compile(r"\b(nach|ecs|e-?mandate|si\s*debit|standing\s*instr|auto\s*debit|mandate\s*debit|nach\s*dr|ach\s*debit)\b", _re.I)
_NACH_RETURN = _re.compile(r"\b(nach\s*ret(?:urn)?|ecs\s*ret(?:urn)?|mandate\s*ret(?:urn)?|nach\s*rtn|ecs\s*rtn|si\s*ret(?:urn)?|si\s*rtn)\b", _re.I)
_CC_PAYMENT  = _re.compile(r"\b(cc\s*pay(?:ment)?|ccpay|credit\s*card\s*pay|cc\s*bill|(?:hdfc|icici|sbi|axis|kotak|rbl|yes|indusind|amex|bob)\s*cc|creditcard[\s\-]?emi|card[\s\-]?emi|card\s*pay(?:ment)?)\b", _re.I)
_INSURANCE   = _re.compile(r"\b(lic(?:\s*prem(?:ium)?)?|life\s*ins|hdfc\s*life|sbi\s*life|icici\s*pru|tata\s*aia|max\s*life|bajaj\s*allianz|star\s*health|niva\s*bupa|care\s*health|religare\s*health|new\s*india\s*ass|united\s*india|national\s*ins|oriental\s*ins|acko|digit\s*ins|insur(?:ance)?\s*prem(?:ium)?)\b", _re.I)
_CHIT_FUND   = _re.compile(r"\b(chit\s*fund|chitty|chitfund|kuri\b|chit\s*inst|chit\s*subs)\b", _re.I)
_DIGITAL_LEND = _re.compile(r"\b(kreditbee|moneyview|fibe\b|nira\b|mpokket|payrupik|cashe\b|stashfin|prefr|smartcoin|kissht|indifi|lendingkart|early\s*salary|earlysalary|fatakpay|paysense|ringplus|rupeeredee|ringcash|slice\b|bharatpe\s*lend|flexsalary|krazybee|dmi\s*finance|homebazaar\s*loan)\b", _re.I)
_ATM_CASH    = _re.compile(r"\b(atm[\s\-/](?:w/?d|cash|with(?:drawal)?)|cash[\s\-/](?:w/?d|with(?:drawal)?)|atm\s*dr)\b", _re.I)
_UPI         = _re.compile(r"\b(upi[\s/\-]|/upi|bhim|gpay|phonepe|paytm|cred\b|amazon\s*pay|whatsapp\s*pay|mobikwik|fampay)\b", _re.I)
_INVESTMENT  = _re.compile(r"\b(sip\b|mutual\s*fund|mf[\s\-](?:debit|sip|purchase)|zerodha|groww\b|upstox|angel\s*brok|iifl\s*sec|5paisa|motilal|(?:nippon|sbi|hdfc|axis|kotak|franklin|dsp|uti)\s*mf|ppf\b|nps\b|elss\b|nav\s*debit)\b", _re.I)
_GAMBLING    = _re.compile(r"\b(dream\s*11|dream11|my11circle|mpl\s*sports|winzo\b|rummy\b|teen\s*patti|junglee\s*rummy|ace2three|adda52|spartan\s*poker|rummy\s*circle|paytm\s*first\s*games|fantasy\s*sports|11wickets|howzat\b)\b", _re.I)
_GST_INCOME  = _re.compile(r"\b(gst|igst|cgst|sgst|gstin|b2b[\s\-]pay|vendor\s*pay(?:ment)?|client\s*pay(?:ment)?|invoice\s*pay(?:ment)?|prof(?:essional)?\s*fee|consult(?:ing)?\s*fee|service\s*fee)\b", _re.I)
_RENT_INCOME = _re.compile(r"\b(rent(?:al)?\s*(?:inc(?:ome)?|rcvd|received)?|house\s*rent|property\s*inc|tenant|lease\s*rent|pg\s*pay)\b", _re.I)


# =============================================================================
#  CONFIG  --  the IP surface. All values are EXPERT PRIORS.
# =============================================================================
@dataclass
class Config:
    # ---- Pillar weights (sum 1.0) ----
    w_income:     float = 0.22
    w_stability:  float = 0.24
    w_resilience: float = 0.20
    w_discipline: float = 0.24
    w_maturity:   float = 0.10

    # ---- Aggregation (the multivariable core) ----
    #  "power": generalised power-mean across pillars, exponent agg_p in (0,1].
    #   p=1 -> linear (full compensation). p<1 -> non-compensatory (a weak pillar
    #   drags harder). p->0 -> geometric mean.
    aggregation: str   = "power"
    agg_p:       float = 0.5
    pillar_floor:float = 1.0     # clamp pillar to >= this before the mean (avoids 0-collapse)

    # ---- Fragility interaction (super-additive co-occurring stress) ----
    frag_critical_cut: float = 40.0   # a pillar below this is "critical"
    frag_pen_per:      float = 4.0    # penalty pts per critical pillar beyond the first
    frag_pen_max:      float = 12.0

    # ---- Sub-feature weights ----
    sw_income_median: float = 0.70
    sw_income_floor:  float = 0.30
    sw_stab_disp:     float = 0.35    # robust income dispersion
    sw_stab_active:   float = 0.25
    sw_stab_trend:    float = 0.20
    sw_stab_payer:    float = 0.20    # HHI (self-emp) / recurrence (salaried/gig)
    sw_res_buffer:    float = 0.38
    sw_res_daysbelow: float = 0.27
    sw_res_minfloor:  float = 0.15
    sw_res_drawdown:  float = 0.20    # NEW: max drawdown depth
    sw_disc_savings:  float = 0.40
    sw_disc_foir:     float = 0.35
    sw_disc_bounce:   float = 0.25
    sw_mat_months:    float = 0.60
    sw_mat_density:   float = 0.40

    # ---- Transform anchors (raw -> 0..100 points), piecewise-linear, clamped ----
    a_income_median: tuple = ((0,0),(8000,25),(15000,45),(25000,60),(45000,75),(80000,88),(150000,97),(300000,100))
    a_income_floor:  tuple = ((0,0),(5000,30),(12000,60),(25000,85),(50000,100))
    a_disp:          tuple = ((0.0,100),(0.15,90),(0.30,72),(0.5,52),(0.8,30),(1.2,12),(2.0,0))   # robust dispersion (lower better)
    a_cov:           tuple = ((0.0,100),(0.15,90),(0.30,72),(0.5,52),(0.8,30),(1.2,12),(2.0,0))
    a_active:        tuple = ((0,0),(0.5,40),(0.75,70),(0.9,88),(1.0,100))
    a_trend:         tuple = ((-0.15,0),(-0.05,40),(0.0,60),(0.03,78),(0.08,92),(0.15,100))
    a_hhi:           tuple = ((0.0,100),(0.05,92),(0.12,76),(0.22,58),(0.38,40),(0.6,20),(1.0,0))  # concentration (lower better)
    a_payer_rec:     tuple = ((0.0,0),(0.5,55),(0.75,80),(1.0,100))                                # recurrence (higher better)
    a_buffer_days:   tuple = ((0,0),(2,22),(5,45),(10,62),(20,80),(40,93),(60,100))
    a_daysbelow:     tuple = ((0.0,100),(0.05,85),(0.10,72),(0.20,52),(0.33,33),(0.5,15),(0.7,0))
    a_minfloor:      tuple = ((0.0,0),(0.02,30),(0.05,55),(0.10,75),(0.25,100))
    a_drawdown:      tuple = ((0.0,100),(0.25,82),(0.45,62),(0.65,42),(0.85,18),(1.0,0))           # rel. drawdown (lower better)
    a_savings:       tuple = ((-0.30,0),(-0.10,25),(0.0,50),(0.10,70),(0.25,88),(0.40,100))
    a_foir:          tuple = ((0.0,100),(0.20,82),(0.35,62),(0.50,42),(0.65,22),(0.80,5),(1.0,0))
    a_bounce:        tuple = ((0,100),(1,55),(2,30),(3,12),(5,0))
    a_months:        tuple = ((0,0),(1,25),(3,50),(6,72),(12,90),(24,100))
    a_density:       tuple = ((0,0),(3,30),(8,55),(20,78),(50,92),(150,100))
    a_confidence:    tuple = ((0,8),(1,28),(2,48),(3,63),(6,82),(12,92),(24,98))                   # months -> base confidence

    low_balance_line: float = 1000.0

    # ---- Knockouts / caps (on the composite) ----
    knock_bounce_count: int   = 3
    knock_bounce_cap:   float = 35.0
    cap_lt_2_months:    float = 72.0
    cap_lt_3_months:    float = 85.0
    dissave_savings:    float = -0.10
    dissave_buffer:     float = 3.0
    dissave_cap:        float = 45.0
    gaming_grossnet:    float = 2.5
    gaming_selfshare:   float = 0.50
    gaming_cap:         float = 50.0
    # India behavioural knockouts
    knock_gamble_share: float = 0.05    # >5% of spend on gambling -> cap
    knock_gamble_cap:   float = 45.0
    knock_distress_cnt: int   = 3       # >=3 digital-loan-app credits -> cap
    knock_distress_cap: float = 50.0

    # ---- Bounded behavioural adjustments (pts, applied to pillars pre-aggregation) ----
    adj_gamble_scale:   float = 500.0   # gambling_share * scale -> penalty pts (cap below)
    adj_gamble_max:     float = 25.0
    adj_distress_per:   float = 7.0     # per digital-loan credit
    adj_distress_max:   float = 20.0
    adj_invest_scale:   float = 80.0    # investment_share * scale -> bonus pts
    adj_invest_max:     float = 8.0
    adj_squeeze_scale:  float = 60.0    # (0.5 - squeeze) * scale -> resilience penalty
    adj_squeeze_max:    float = 18.0
    adj_gst_scale:      float = 20.0    # gst_income_share * scale -> stability bonus
    adj_gst_max:        float = 6.0

    # ---- Confidence modifiers ----
    conf_cash_heavy_cut:  float = 0.30  # cash withdrawal share above this lowers confidence
    conf_cash_pen:        float = 15.0
    conf_gst_bonus:       float = 8.0   # GST-verified income raises confidence
    conf_upi_bonus:       float = 4.0
    conf_incomplete_mult: float = 0.6   # missing categories/balances
    conf_gaming_mult:     float = 0.6
    conf_lowdensity_pen:  float = 10.0  # txn_density < 3
    conf_band_high:       float = 75.0
    conf_band_med:        float = 50.0

    # ---- Living-score stress triggers ----
    stress_drop_amber:  float = 8.0
    stress_drop_red:    float = 15.0
    stress_income_drop: float = 0.25
    stress_buffer_floor:float = 3.0
    stress_ewma_dd:     float = 0.25    # recent EWMA drawdown fraction -> amber

    tiers: tuple = (("A",80),("B",65),("C",50),("D",35),("E",0))


# =============================================================================
#  HELPERS
# =============================================================================
def _pw(x, anchors):
    if x <= anchors[0][0]: return float(anchors[0][1])
    if x >= anchors[-1][0]: return float(anchors[-1][1])
    for (x0,y0),(x1,y1) in zip(anchors, anchors[1:]):
        if x0 <= x <= x1:
            t = 0.0 if x1==x0 else (x-x0)/(x1-x0)
            return float(y0 + t*(y1-y0))
    return float(anchors[-1][1])

def _slope_pct(values, base):
    n=len(values)
    if n<2 or base<=0: return 0.0
    xs=list(range(n)); xbar=mean(xs); ybar=mean(values)
    num=sum((x-xbar)*(y-ybar) for x,y in zip(xs,values))
    den=sum((x-xbar)**2 for x in xs)
    return (num/den)/base if den else 0.0

def _robust_disp(values):
    """1.4826 * MAD / median  -- robust analogue of CV. Stable near zero."""
    if len(values) < 2: return 0.0
    m = median(values)
    if m <= 0: return 0.0
    mad = median([abs(v-m) for v in values])
    return (1.4826*mad)/m

def _hhi(shares):
    """Herfindahl-Hirschman Index = sum of squared shares. 1/n .. 1."""
    return sum(s*s for s in shares) if shares else 1.0

def _norm_entropy(shares):
    """Shannon entropy normalised to [0,1]; 1 = perfectly diverse."""
    n=len(shares)
    if n<=1: return 0.0
    h=-sum(s*_math.log(s) for s in shares if s>0)
    return h/_math.log(n)

def _power_mean(pairs, p, floor):
    """Weighted generalised power-mean over (weight, value0..100). p in (0,1]."""
    tw=sum(w for w,_ in pairs) or 1.0
    acc=0.0
    for w,v in pairs:
        u=max(floor, v)/100.0
        acc += (w/tw)*(u**p)
    return (acc**(1.0/p))*100.0

def _max_drawdown(series):
    """Largest relative peak-to-trough fall in a balance series. [0,1)."""
    peak=series[0] if series else 0.0; mdd=0.0
    for b in series:
        if b>peak: peak=b
        if peak>0:
            dd=(peak-b)/peak
            if dd>mdd: mdd=dd
    return mdd

def _ewma(series, lam=0.1):
    if not series: return []
    out=[series[0]]
    for x in series[1:]: out.append(lam*x+(1-lam)*out[-1])
    return out


# =============================================================================
#  FEATURES
# =============================================================================
@dataclass
class Features:
    median_monthly_income: float = 0.0
    min_monthly_income: float = 0.0
    income_cov: float = 0.0
    income_disp: float = 0.0          # robust dispersion (primary)
    active_month_ratio: float = 0.0
    income_trend_pct: float = 0.0
    payer_hhi: float = 1.0            # concentration (primary)
    effective_payers: float = 1.0
    payer_entropy: float = 0.0
    top_payer_share: float = 1.0
    top_payer_recurrence: float = 0.0
    archetype: str = "MIXED"
    buffer_days: float = 0.0
    days_below_ratio: float = 1.0
    min_balance_floor: float = 0.0
    max_drawdown: float = 0.0         # NEW
    ewma_drawdown: float = 0.0        # NEW (recent, for living layer)
    net_savings_rate: float = 0.0
    foir: float = 0.0
    bounce_freq_90d: float = 0.0
    months_history: float = 0.0
    txn_density: float = 0.0
    platform_income_share: float = 0.0
    gross_net_ratio: float = 1.0
    self_transfer_share: float = 0.0
    has_balances: bool = True
    has_categories: bool = True
    n_txn: int = 0
    # India signals
    nach_mandate_count: int = 0
    cc_obligation_monthly: float = 0.0
    insurance_monthly: float = 0.0
    chit_fund_monthly: float = 0.0
    gst_income_share: float = 0.0
    rent_income_share: float = 0.0
    income_source_count: int = 0
    upi_txn_ratio: float = 0.0
    cash_withdrawal_ratio: float = 0.0
    investment_debit_share: float = 0.0
    gambling_debit_share: float = 0.0
    digital_loan_credit: int = 0
    end_month_squeeze: float = 1.0


def extract_features(transactions, cfg):
    f=Features()
    if not transactions: return f
    txns=sorted(transactions, key=lambda t:t["date"])
    f.n_txn=len(txns)
    d0=datetime.strptime(txns[0]["date"],"%Y-%m-%d").date()
    d1=datetime.strptime(txns[-1]["date"],"%Y-%m-%d").date()
    total_days=max(1,(d1-d0).days+1)
    f.months_history=total_days/30.4375
    has_cat=any("category" in t for t in txns)
    has_bal=all("balance" in t for t in txns)
    f.has_categories=has_cat; f.has_balances=has_bal

    def cat(t):
        if has_cat: return t.get("category","other")
        return "income" if t["amount"]>0 else "expense"

    gross_in=sum(t["amount"] for t in txns if t["amount"]>0)
    self_in=sum(t["amount"] for t in txns if t["amount"]>0 and cat(t)=="self_transfer")
    net_in=gross_in-self_in
    f.gross_net_ratio=(gross_in/net_in) if net_in>0 else 99.0
    f.self_transfer_share=(self_in/gross_in) if gross_in>0 else 0.0

    inc_by_month=defaultdict(float); exp_by_month=defaultdict(float)
    months_in_span=set(); cur=date(d0.year,d0.month,1)
    while cur<=d1:
        months_in_span.add((cur.year,cur.month))
        cur=date(cur.year+(cur.month//12),(cur.month%12)+1,1)

    income_txns=[]; obligations=0.0; bounces=0
    payer_amt=defaultdict(float); payer_months=defaultdict(set); inc_txn_count=0
    _upi=0;_atm=0.0;_inv=0.0;_gam=0.0;_tot_deb=0.0;_dlc=0;_gst=0.0;_rent=0.0
    _nach=set();_cc=defaultdict(float);_ins=defaultdict(float);_chit=defaultdict(float)

    for t in txns:
        c=cat(t); ym=tuple(int(x) for x in t["date"].split("-")[:2])
        s=((t.get("description","") or "")+" "+(t.get("counterparty","") or ""))
        if _UPI.search(s): _upi+=1
        if t["amount"]<0:
            d=-t["amount"]; _tot_deb+=d
            if _ATM_CASH.search(s): _atm+=d
            if _INVESTMENT.search(s): _inv+=d
            if _GAMBLING.search(s): _gam+=d
            if _NACH_RETURN.search(s) and not t.get("is_bounce"): bounces+=1
            if c!="obligation":
                if _CC_PAYMENT.search(s): obligations+=d; _cc[ym]+=d
                elif _INSURANCE.search(s): obligations+=d; _ins[ym]+=d
                elif _CHIT_FUND.search(s): obligations+=d; _chit[ym]+=d
                elif _NACH_DEBIT.search(s): obligations+=d; _nach.add((t.get("counterparty","") or s[:40]).strip())
            else:
                if _NACH_DEBIT.search(s): _nach.add((t.get("counterparty","") or s[:40]).strip())
        elif t["amount"]>0:
            if _DIGITAL_LEND.search(s): _dlc+=1
            if c=="income":
                if _GST_INCOME.search(s): _gst+=t["amount"]
                if _RENT_INCOME.search(s): _rent+=t["amount"]
        if t.get("is_bounce"): bounces+=1
        if t["amount"]>0:
            if c=="income":
                inc_by_month[ym]+=t["amount"]; income_txns.append(t); inc_txn_count+=1
                p=t.get("counterparty","unknown"); payer_amt[p]+=t["amount"]; payer_months[p].add(ym)
        else:
            if c=="self_transfer": pass
            elif c=="obligation": obligations+=-t["amount"]; exp_by_month[ym]+=-t["amount"]
            else: exp_by_month[ym]+=-t["amount"]

    active_months=[m for m in months_in_span if inc_by_month.get(m,0)>0]
    monthly_vals=[inc_by_month[m] for m in sorted(active_months)]
    if monthly_vals:
        f.median_monthly_income=median(monthly_vals); f.min_monthly_income=min(monthly_vals)
        mm=mean(monthly_vals)
        f.income_cov=(pstdev(monthly_vals)/mm) if mm>0 and len(monthly_vals)>1 else 0.0
        f.income_disp=_robust_disp(monthly_vals)
        f.active_month_ratio=len(active_months)/max(1,len(months_in_span))
        f.income_trend_pct=_slope_pct(monthly_vals,f.median_monthly_income)

    total_income=sum(inc_by_month.values()); total_expense=sum(exp_by_month.values())
    f.net_savings_rate=((total_income-total_expense)/total_income) if total_income>0 else -1.0
    f.foir=(obligations/total_income) if total_income>0 else 1.0
    f.bounce_freq_90d=bounces*(90.0/total_days)
    f.txn_density=f.n_txn/max(1.0,f.months_history)

    # India feature values
    f.nach_mandate_count=len(_nach); f.digital_loan_credit=_dlc
    f.upi_txn_ratio=_upi/max(1,f.n_txn)
    f.cash_withdrawal_ratio=_atm/max(1.0,_tot_deb)
    f.investment_debit_share=_inv/max(1.0,_tot_deb)
    f.gambling_debit_share=_gam/max(1.0,_tot_deb)
    f.gst_income_share=_gst/max(1.0,total_income)
    f.rent_income_share=_rent/max(1.0,total_income)
    f.income_source_count=len(payer_amt)
    nma=max(1,len(active_months))
    f.cc_obligation_monthly=sum(_cc.values())/nma
    f.insurance_monthly=sum(_ins.values())/nma
    f.chit_fund_monthly=sum(_chit.values())/nma

    # ---- concentration (HHI/entropy) ----
    if payer_amt and total_income>0:
        shares=[a/total_income for a in payer_amt.values()]
        f.payer_hhi=_hhi(shares)
        f.effective_payers=1.0/f.payer_hhi if f.payer_hhi>0 else 1.0
        f.payer_entropy=_norm_entropy(shares)
        top=max(payer_amt,key=payer_amt.get)
        f.top_payer_share=payer_amt[top]/total_income
        f.top_payer_recurrence=len(payer_months[top])/max(1,len(active_months))

    # ---- archetype ----
    _PLAT={"ola","uber","rapido","swiggy","zomato","blinkit","zepto","dunzo","bigbasket",
           "instamart","urban company","urbanclap","porter","shadowfax","borzo","wefast","meesho","glowroad"}
    def _isplat(cp): cl=cp.lower(); return any(k in cl for k in _PLAT)
    pmc=defaultdict(int)
    for t in income_txns: pmc[tuple(int(x) for x in t["date"].split("-")[:2])]+=1
    med_inc_txns=median(list(pmc.values())) if pmc else 0
    plat_inc=sum(a for cp,a in payer_amt.items() if _isplat(cp))
    f.platform_income_share=(plat_inc/total_income) if total_income>0 else 0.0
    if med_inc_txns<=2 and f.top_payer_recurrence>=0.7: f.archetype="SALARIED"
    elif f.platform_income_share>=0.5: f.archetype="GIG"
    elif med_inc_txns>=8: f.archetype="SELF_EMPLOYED"
    else: f.archetype="MIXED"

    # ---- balance-derived ----
    if has_bal:
        eod={}
        for t in txns: eod[datetime.strptime(t["date"],"%Y-%m-%d").date()]=t["balance"]
        series=[]; last=txns[0]["balance"]; cur=d0
        while cur<=d1:
            if cur in eod: last=eod[cur]
            series.append(last); cur+=timedelta(days=1)
        adb=mean(series); mdb=min(series); ado=total_expense/total_days
        f.buffer_days=(adb/ado) if ado>0 else 60.0
        f.days_below_ratio=sum(1 for b in series if b<cfg.low_balance_line)/len(series)
        f.min_balance_floor=(mdb/f.median_monthly_income) if f.median_monthly_income>0 else 0.0
        f.max_drawdown=_max_drawdown(series)
        ew=_ewma(series,0.1)
        if ew:
            pk=max(ew); f.ewma_drawdown=(pk-ew[-1])/pk if pk>0 else 0.0
        # end-of-month squeeze
        sq=[]; cm=date(d0.year,d0.month,1)
        while cm<=d1:
            y,m=cm.year,cm.month; ld=_cal.monthrange(y,m)[1]
            f5=[series[(date(y,m,dd)-d0).days] for dd in range(1,6) if d0<=date(y,m,dd)<=d1 and (date(y,m,dd)-d0).days<len(series)]
            l5=[series[(date(y,m,dd)-d0).days] for dd in range(max(1,ld-4),ld+1) if d0<=date(y,m,dd)<=d1 and (date(y,m,dd)-d0).days<len(series)]
            if f5 and l5:
                af=sum(f5)/len(f5); al=sum(l5)/len(l5)
                if af>0: sq.append(al/af)
            cm=date(y+(m//12),(m%12)+1,1)
        f.end_month_squeeze=median(sq) if sq else 1.0
    else:
        f.buffer_days=0.0; f.days_below_ratio=1.0; f.min_balance_floor=0.0
        f.max_drawdown=1.0; f.ewma_drawdown=0.0
    return f


# =============================================================================
#  RESULT
# =============================================================================
@dataclass
class ScoreResult:
    score:int; tier:str; confidence:str; confidence_score:float; archetype:str
    pillars:dict; subscores:dict; reason_codes:list; caps_applied:list; features:Features
    def explain(self):
        L=[f"RintelScore {self.score}  |  Tier {self.tier}  |  {self.confidence} confidence ({self.confidence_score:.0f})  |  {self.archetype}"]
        L.append("  Pillars: "+"  ".join(f"{k}={v:.0f}" for k,v in self.pillars.items()))
        L.append("  Reasons:")
        for rc in self.reason_codes: L.append(f"    {rc['sign']}  {rc['text']}")
        if self.caps_applied: L.append("  Caps: "+"; ".join(self.caps_applied))
        return "\n".join(L)


_REASON={
 "income_median":("Income level",lambda f:f"median monthly income Rs {f.median_monthly_income:,.0f}"),
 "income_floor":("Income floor",lambda f:f"lowest monthly income Rs {f.min_monthly_income:,.0f}"),
 "stab_disp":("Income volatility",lambda f:f"robust month-to-month swing {f.income_disp:.2f}"),
 "stab_active":("Earning consistency",lambda f:f"earned in {f.active_month_ratio*100:.0f}% of months"),
 "stab_trend":("Income trajectory",lambda f:f"income trend {f.income_trend_pct*100:+.0f}%/month"),
 "stab_payer":("Payer profile",lambda f:(f"employer recurs in {f.top_payer_recurrence*100:.0f}% of months" if f.archetype=="SALARIED"
               else f"platform income = {f.platform_income_share*100:.0f}% of earnings" if f.archetype=="GIG"
               else f"income concentration HHI {f.payer_hhi:.2f} (~{f.effective_payers:.0f} effective payers)")),
 "res_buffer":("Liquidity buffer",lambda f:f"balance covers {f.buffer_days:.0f} days of spend"),
 "res_daysbelow":("Low-balance days",lambda f:f"{f.days_below_ratio*100:.0f}% of days under the low line"),
 "res_minfloor":("Balance floor",lambda f:f"min balance = {f.min_balance_floor*100:.0f}% of monthly income"),
 "res_drawdown":("Worst cash crunch",lambda f:f"max drawdown {f.max_drawdown*100:.0f}% from peak balance"),
 "disc_savings":("Net saving",lambda f:f"net savings rate {f.net_savings_rate*100:+.0f}%"),
 "disc_foir":("Existing obligations",lambda f:f"obligations = {f.foir*100:.0f}% of income (FOIR)"),
 "disc_bounce":("Payment failures",lambda f:f"{f.bounce_freq_90d:.1f} bounces / 90 days"),
 "mat_months":("History depth",lambda f:f"{f.months_history:.1f} months of data"),
 "mat_density":("Account usage",lambda f:f"{f.txn_density:.0f} transactions/month"),
}


def score(transactions, cfg=None):
    cfg=cfg or Config()
    f=extract_features(transactions,cfg)
    s={}
    s["income_median"]=_pw(f.median_monthly_income,cfg.a_income_median)
    s["income_floor"]=_pw(f.min_monthly_income,cfg.a_income_floor)
    s["stab_disp"]=_pw(f.income_disp,cfg.a_disp)
    s["stab_active"]=_pw(f.active_month_ratio,cfg.a_active)
    s["stab_trend"]=_pw(f.income_trend_pct,cfg.a_trend)
    if f.archetype in ("SALARIED","GIG"):
        s["stab_payer"]=_pw(f.top_payer_recurrence,cfg.a_payer_rec)
    elif f.archetype=="SELF_EMPLOYED":
        s["stab_payer"]=_pw(f.payer_hhi,cfg.a_hhi)
    else:
        s["stab_payer"]=0.5*_pw(f.top_payer_recurrence,cfg.a_payer_rec)+0.5*_pw(f.payer_hhi,cfg.a_hhi)
    s["res_buffer"]=_pw(f.buffer_days,cfg.a_buffer_days)
    s["res_daysbelow"]=_pw(f.days_below_ratio,cfg.a_daysbelow)
    s["res_minfloor"]=_pw(f.min_balance_floor,cfg.a_minfloor)
    s["res_drawdown"]=_pw(f.max_drawdown,cfg.a_drawdown)
    s["disc_savings"]=_pw(f.net_savings_rate,cfg.a_savings)
    s["disc_foir"]=_pw(f.foir,cfg.a_foir)
    s["disc_bounce"]=_pw(f.bounce_freq_90d,cfg.a_bounce)
    s["mat_months"]=_pw(f.months_history,cfg.a_months)
    s["mat_density"]=_pw(f.txn_density,cfg.a_density)

    def clamp(v): return max(0.0,min(100.0,v))
    P={}
    P["income"]=cfg.sw_income_median*s["income_median"]+cfg.sw_income_floor*s["income_floor"]
    P["stability"]=(cfg.sw_stab_disp*s["stab_disp"]+cfg.sw_stab_active*s["stab_active"]+
                    cfg.sw_stab_trend*s["stab_trend"]+cfg.sw_stab_payer*s["stab_payer"])
    P["resilience"]=(cfg.sw_res_buffer*s["res_buffer"]+cfg.sw_res_daysbelow*s["res_daysbelow"]+
                     cfg.sw_res_minfloor*s["res_minfloor"]+cfg.sw_res_drawdown*s["res_drawdown"])
    P["discipline"]=(cfg.sw_disc_savings*s["disc_savings"]+cfg.sw_disc_foir*s["disc_foir"]+
                     cfg.sw_disc_bounce*s["disc_bounce"])
    P["maturity"]=cfg.sw_mat_months*s["mat_months"]+cfg.sw_mat_density*s["mat_density"]

    # ---- bounded behavioural adjustments (pre-aggregation) ----
    notes=[]
    gpen=min(cfg.adj_gamble_max,f.gambling_debit_share*cfg.adj_gamble_scale)
    dpen=min(cfg.adj_distress_max,f.digital_loan_credit*cfg.adj_distress_per)
    ibon=min(cfg.adj_invest_max,f.investment_debit_share*cfg.adj_invest_scale)
    P["discipline"]=clamp(P["discipline"]-gpen-dpen+ibon)
    if f.has_balances and f.end_month_squeeze<0.5:
        spen=min(cfg.adj_squeeze_max,(0.5-f.end_month_squeeze)*cfg.adj_squeeze_scale)
        P["resilience"]=clamp(P["resilience"]-spen)
    gbon=min(cfg.adj_gst_max,f.gst_income_share*cfg.adj_gst_scale)
    P["stability"]=clamp(P["stability"]+gbon)

    # ---- NON-COMPENSATORY AGGREGATION ----
    pairs=[(cfg.w_income,P["income"]),(cfg.w_stability,P["stability"]),
           (cfg.w_resilience,P["resilience"]),(cfg.w_discipline,P["discipline"]),
           (cfg.w_maturity,P["maturity"])]
    if cfg.aggregation=="power":
        composite=_power_mean(pairs,cfg.agg_p,cfg.pillar_floor)
    else:
        tw=sum(w for w,_ in pairs); composite=sum(w*v for w,v in pairs)/tw

    # ---- fragility interaction (super-additive co-occurring stress) ----
    n_crit=sum(1 for _,v in pairs if v<cfg.frag_critical_cut)
    if n_crit>=2:
        composite=clamp(composite-min(cfg.frag_pen_max,(n_crit-1)*cfg.frag_pen_per))

    # ---- knockouts / caps ----
    caps=[]
    def cap(v,c,msg):
        nonlocal composite
        if composite>c: composite=c; caps.append(msg)
    if f.bounce_freq_90d>=cfg.knock_bounce_count: cap(composite,cfg.knock_bounce_cap,f"bounces>={cfg.knock_bounce_count} -> cap {cfg.knock_bounce_cap:.0f}")
    if f.gambling_debit_share>cfg.knock_gamble_share: cap(composite,cfg.knock_gamble_cap,f"gambling>{cfg.knock_gamble_share*100:.0f}% spend -> cap {cfg.knock_gamble_cap:.0f}")
    if f.digital_loan_credit>=cfg.knock_distress_cnt: cap(composite,cfg.knock_distress_cap,f"distress borrowing ({f.digital_loan_credit} app credits) -> cap {cfg.knock_distress_cap:.0f}")
    if f.net_savings_rate<cfg.dissave_savings and f.buffer_days<cfg.dissave_buffer: cap(composite,cfg.dissave_cap,f"dissaving+thin buffer -> cap {cfg.dissave_cap:.0f}")
    if f.gross_net_ratio>cfg.gaming_grossnet or f.self_transfer_share>cfg.gaming_selfshare: cap(composite,cfg.gaming_cap,"circular-flow / self-transfer -> cap & flag")

    # ---- graded confidence ----
    conf=_pw(f.months_history,cfg.a_confidence)
    if not f.has_categories or not f.has_balances: conf*=cfg.conf_incomplete_mult; caps.append("missing normalisation/balance inputs")
    if f.gross_net_ratio>cfg.gaming_grossnet or f.self_transfer_share>cfg.gaming_selfshare: conf*=cfg.conf_gaming_mult
    if f.cash_withdrawal_ratio>cfg.conf_cash_heavy_cut: conf-=cfg.conf_cash_pen
    if f.gst_income_share>0.25: conf+=cfg.conf_gst_bonus
    if f.upi_txn_ratio>0.5: conf+=cfg.conf_upi_bonus
    if f.txn_density<3: conf-=cfg.conf_lowdensity_pen
    conf=clamp(conf)
    confidence="HIGH" if conf>=cfg.conf_band_high else ("MEDIUM" if conf>=cfg.conf_band_med else "LOW")

    # thin-data score caps (independent of confidence band)
    if f.months_history<2: cap(composite,cfg.cap_lt_2_months,f"<2mo data -> cap {cfg.cap_lt_2_months:.0f}")
    elif f.months_history<3: cap(composite,cfg.cap_lt_3_months,f"<3mo data -> cap {cfg.cap_lt_3_months:.0f}")

    composite=clamp(composite)
    tier="E"
    for nm,ct in cfg.tiers:
        if composite>=ct: tier=nm; break

    # ---- reason codes ----
    ranked=sorted(s.items(),key=lambda kv:kv[1])
    adverse=[];positive=[]
    for k,v in ranked:
        if v<50 and len(adverse)<3:
            lab,fn=_REASON[k]; adverse.append({"sign":"-","code":k.upper(),"text":f"{lab}: {fn(f)}"})
    for k,v in reversed(ranked):
        if v>=70 and len(positive)<2:
            lab,fn=_REASON[k]; positive.append({"sign":"+","code":k.upper(),"text":f"{lab}: {fn(f)}"})
    ia=[];ip=[]
    if f.digital_loan_credit>=2: ia.append({"sign":"-","code":"IND_DISTRESS_LOAN","text":f"Digital lending: {f.digital_loan_credit} app credits — possible distress borrowing"})
    if f.gambling_debit_share>0.02: ia.append({"sign":"-","code":"IND_GAMBLING","text":f"Gambling/fantasy: {f.gambling_debit_share*100:.1f}% of spend"})
    if f.cash_withdrawal_ratio>0.30: ia.append({"sign":"-","code":"IND_CASH_HEAVY","text":f"Cash-heavy: {f.cash_withdrawal_ratio*100:.0f}% of spend via ATM — limits traceability"})
    if f.end_month_squeeze<0.50 and f.has_balances: ia.append({"sign":"-","code":"IND_SQUEEZE","text":f"Paycheck-to-paycheck: month-end balance {f.end_month_squeeze*100:.0f}% of month-start"})
    if f.nach_mandate_count>=3: ia.append({"sign":"-","code":"IND_NACH_LOAD","text":f"{f.nach_mandate_count} NACH/ECS mandates — verify FOIR completeness"})
    if f.investment_debit_share>0.05: ip.append({"sign":"+","code":"IND_INVESTING","text":f"Wealth-building: {f.investment_debit_share*100:.0f}% of spend on SIP/MF/equity"})
    if f.gst_income_share>0.25: ip.append({"sign":"+","code":"IND_GST_INCOME","text":f"Verified business income: {f.gst_income_share*100:.0f}% of inflows carry GST/B2B markers"})
    if f.upi_txn_ratio>0.50: ip.append({"sign":"+","code":"IND_DIGITAL","text":f"Digitally active: {f.upi_txn_ratio*100:.0f}% of txns via UPI/digital rails"})
    if f.income_source_count>=5 and f.archetype in ("SELF_EMPLOYED","MIXED"): ip.append({"sign":"+","code":"IND_DIVERSITY","text":f"Diversified income: {f.income_source_count} payers (~{f.effective_payers:.0f} effective)"})
    if f.rent_income_share>0.15: ip.append({"sign":"+","code":"IND_RENT","text":f"Rental income: {f.rent_income_share*100:.0f}% of inflows"})
    reason_codes=adverse+ia+positive+ip

    return ScoreResult(round(composite),tier,confidence,conf,f.archetype,P,s,reason_codes,caps,f)


# =============================================================================
#  LIVING SCORE
# =============================================================================
def score_on_window(transactions, as_of, window_days=180, cfg=None):
    cfg=cfg or Config()
    end=datetime.strptime(as_of,"%Y-%m-%d").date(); start=end-timedelta(days=window_days)
    win=[t for t in transactions if start<datetime.strptime(t["date"],"%Y-%m-%d").date()<=end]
    return score(win,cfg)

def stress_signals(prev, curr, cfg=None):
    cfg=cfg or Config(); out=[]
    drop=prev.score-curr.score
    if drop>=cfg.stress_drop_red: out.append({"severity":"RED","text":f"Score fell {drop} pts ({prev.score}->{curr.score})"})
    elif drop>=cfg.stress_drop_amber: out.append({"severity":"AMBER","text":f"Score slipping {drop} pts ({prev.score}->{curr.score})"})
    pi,ci=prev.features.median_monthly_income,curr.features.median_monthly_income
    if pi>0 and (pi-ci)/pi>=cfg.stress_income_drop: out.append({"severity":"AMBER","text":f"Income down {(pi-ci)/pi*100:.0f}%"})
    if prev.features.buffer_days>=cfg.stress_buffer_floor>curr.features.buffer_days: out.append({"severity":"AMBER","text":f"Buffer thinned to {curr.features.buffer_days:.0f} days"})
    if curr.features.ewma_drawdown>=cfg.stress_ewma_dd: out.append({"severity":"AMBER","text":f"Balance trend down {curr.features.ewma_drawdown*100:.0f}% from recent peak (EWMA)"})
    if curr.features.bounce_freq_90d>prev.features.bounce_freq_90d: out.append({"severity":"RED","text":"New payment failure(s) detected"})
    return out
