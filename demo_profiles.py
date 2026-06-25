"""Synthetic borrowers so the API works before real data is wired. Demo only."""
import random
from datetime import date, timedelta
def _mk(d,a,b,cp,cat,desc="",bounce=False):
    return {"date":d,"amount":a,"balance":b,"counterparty":cp,"category":cat,"description":desc,"is_bounce":bounce}
def merchant(seed=1,gambling=False):
    rng=random.Random(seed);t=[];bal=5000.0;d=date(2025,12,1);end=date(2026,6,1);mi=0
    while d<end:
        if d.day==1:mi+=1
        sc=1200*(1.04)**mi
        for _ in range(rng.randint(10,18)):
            a=round(rng.uniform(20,sc/8),2);bal+=a;t.append(_mk(d.isoformat(),a,round(bal,2),f"cust_{rng.randint(1,40)}","income","UPI/cust"))
        for _ in range(rng.randint(2,5)):
            a=round(rng.uniform(50,sc/10),2);bal=max(80.0,bal-a);t.append(_mk(d.isoformat(),-a,round(bal,2),f"supp_{rng.randint(1,8)}","expense","UPI/supplier"))
        if d.day==5:bal=max(80.0,bal-1500);t.append(_mk(d.isoformat(),-1500,round(bal,2),"nbfc","obligation","NACH EMI BAJAJ"))
        if gambling and d.day in (3,12,22):
            a=round(rng.uniform(800,2500),2);bal=max(50.0,bal-a);t.append(_mk(d.isoformat(),-a,round(bal,2),"dream11","expense","UPI/DREAM11 fantasy"))
        d+=timedelta(days=1)
    return t
def salaried(seed=3):
    rng=random.Random(seed);t=[];bal=20000.0;d=date(2025,9,1);end=date(2026,6,1)
    while d<end:
        if d.day==1:bal+=45000;t.append(_mk(d.isoformat(),45000,round(bal,2),"acme_payroll","income","NEFT SALARY ACME"))
        if d.day==3:bal=max(500.0,bal-12000);t.append(_mk(d.isoformat(),-12000,round(bal,2),"hloan","obligation","NACH HOME LOAN EMI"))
        if d.day==4:bal=max(500.0,bal-5000);t.append(_mk(d.isoformat(),-5000,round(bal,2),"zerodha","expense","SIP ZERODHA MF"))
        d+=timedelta(days=1)
    return t
def stressed(seed=2):
    rng=random.Random(seed);t=[];bal=900.0;d=date(2026,3,14);end=date(2026,6,14)
    while d<=end:
        if rng.random()<0.55:
            a=round(rng.uniform(150,700),2);bal+=a;t.append(_mk(d.isoformat(),a,round(bal,2),f"p_{rng.randint(1,200)}","income","UPI/p2p"))
        for _ in range(rng.randint(1,3)):
            a=round(min(bal*rng.uniform(0.5,0.95),rng.uniform(50,500)),2);bal=max(4.0,bal-a);t.append(_mk(d.isoformat(),-a,round(bal,2),f"p_{rng.randint(1,200)}","expense","UPI/p2p"))
        if d.day==7:
            b=bal<1200;t.append(_mk(d.isoformat(),-800,round(bal,2),"emi","obligation","NACH EMI",bounce=b))
            if not b:bal-=800
        d+=timedelta(days=1)
    return t
