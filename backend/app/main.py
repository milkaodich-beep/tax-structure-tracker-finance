from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from .db import get_db, settings
from .invoicing import FinanceError, allocate_payment, approve_invoice, cancel_invoice, create_invoice, create_payment, finalize_tax, get_invoice, issue_invoice, post_invoice, reject_invoice, reverse_payment, submit_invoice
from .models import Invoice, Payment
from .risk import risk_flags
from .schemas import ApprovalDecision, InvoiceCreate, PaymentAllocationCreate, PaymentCreate, TaxDeterminationCreate

app=FastAPI(title="International Tax Structure Tracker", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def actor(x_actor: str|None): return x_actor or "system"
def fail(exc: FinanceError): raise HTTPException(status_code=409, detail=str(exc))

@app.get("/health")
async def health(): return {"status":"ok"}

@app.get("/api/v1/risk-flags")
async def get_risk_flags(db: AsyncSession=Depends(get_db)): return await risk_flags(db)

@app.post("/api/v1/transactions/{transaction_id}/invoices")
async def create_invoice_endpoint(transaction_id:int, payload:InvoiceCreate, db:AsyncSession=Depends(get_db), x_actor:str|None=Header(None), x_request_id:str|None=Header(None)):
    try:
        invoice=await create_invoice(db, transaction_id=transaction_id, actor=actor(x_actor), invoice_type=payload.invoice_type, currency=payload.currency,
          issue_date=payload.issue_date, due_date=payload.due_date, related_invoice_id=payload.related_invoice_id, notes=payload.notes,
          lines=[x.model_dump() for x in payload.lines], correlation_id=x_request_id)
        await db.commit(); await db.refresh(invoice); return invoice
    except FinanceError as e: await db.rollback(); fail(e)

@app.get("/api/v1/invoices/{invoice_id}")
async def invoice_endpoint(invoice_id:int, db:AsyncSession=Depends(get_db)):
    try: return await get_invoice(db, invoice_id)
    except FinanceError as e: fail(e)

async def transition(endpoint, db, invoice_id, x_actor, x_request_id, *args):
    try:
        result=await endpoint(db, invoice_id, actor(x_actor), *args, correlation_id=x_request_id); await db.commit(); return result
    except FinanceError as e: await db.rollback(); fail(e)

@app.post("/api/v1/invoices/{invoice_id}/submit")
async def submit(invoice_id:int, db:AsyncSession=Depends(get_db), x_actor:str|None=Header(None), x_request_id:str|None=Header(None)): return await transition(submit_invoice,db,invoice_id,x_actor,x_request_id)

@app.post("/api/v1/invoices/{invoice_id}/approve")
async def approve(invoice_id:int, payload:ApprovalDecision, db:AsyncSession=Depends(get_db), x_actor:str|None=Header(None), x_request_id:str|None=Header(None)):
    try: result=await approve_invoice(db,invoice_id,actor(x_actor),payload.comment,x_request_id); await db.commit(); return result
    except FinanceError as e: await db.rollback(); fail(e)

@app.post("/api/v1/invoices/{invoice_id}/reject")
async def reject(invoice_id:int, payload:ApprovalDecision, db:AsyncSession=Depends(get_db), x_actor:str|None=Header(None), x_request_id:str|None=Header(None)):
    try: result=await reject_invoice(db,invoice_id,actor(x_actor),payload.comment,x_request_id); await db.commit(); return result
    except FinanceError as e: await db.rollback(); fail(e)

@app.post("/api/v1/invoices/{invoice_id}/finalize-tax")
async def finalize_tax_endpoint(invoice_id:int, payload:list[TaxDeterminationCreate], db:AsyncSession=Depends(get_db), x_actor:str|None=Header(None), x_request_id:str|None=Header(None)):
    try:
        result=await finalize_tax(db,invoice_id,actor(x_actor),[x.model_dump() for x in payload],x_request_id); await db.commit(); return result
    except FinanceError as e: await db.rollback(); fail(e)

@app.post("/api/v1/invoices/{invoice_id}/issue")
async def issue(invoice_id:int, db:AsyncSession=Depends(get_db), x_actor:str|None=Header(None), x_request_id:str|None=Header(None)): return await transition(issue_invoice,db,invoice_id,x_actor,x_request_id)

@app.post("/api/v1/invoices/{invoice_id}/post")
async def post(invoice_id:int, db:AsyncSession=Depends(get_db), x_actor:str|None=Header(None), x_request_id:str|None=Header(None)): return await transition(post_invoice,db,invoice_id,x_actor,x_request_id)

@app.post("/api/v1/invoices/{invoice_id}/cancel")
async def cancel(invoice_id:int, db:AsyncSession=Depends(get_db), x_actor:str|None=Header(None), x_request_id:str|None=Header(None)): return await transition(cancel_invoice,db,invoice_id,x_actor,x_request_id)

@app.post("/api/v1/payments")
async def payment(payload:PaymentCreate, db:AsyncSession=Depends(get_db), x_actor:str|None=Header(None), x_request_id:str|None=Header(None)):
    try:
        result=await create_payment(db,actor=actor(x_actor),data=payload.model_dump(),correlation_id=x_request_id); await db.commit(); return result
    except Exception as e: await db.rollback(); raise HTTPException(status_code=409,detail=str(e))

@app.post("/api/v1/payments/{payment_id}/allocate")
async def allocation(payment_id:int,payload:PaymentAllocationCreate,db:AsyncSession=Depends(get_db),x_actor:str|None=Header(None),x_request_id:str|None=Header(None)):
    try:
        result=await allocate_payment(db,payment_id,invoice_id=payload.invoice_id,amount=payload.allocated_amount,allocation_date=payload.allocation_date,actor=actor(x_actor),correlation_id=x_request_id); await db.commit(); return result
    except FinanceError as e: await db.rollback(); fail(e)

@app.post("/api/v1/payments/{payment_id}/reverse")
async def reverse(payment_id:int,db:AsyncSession=Depends(get_db),x_actor:str|None=Header(None),x_request_id:str|None=Header(None)):
    try: result=await reverse_payment(db,payment_id,actor(x_actor),x_request_id); await db.commit(); return result
    except FinanceError as e: await db.rollback(); fail(e)
