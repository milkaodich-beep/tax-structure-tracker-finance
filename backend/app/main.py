from __future__ import annotations

from datetime import datetime, timezone
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import CSRF_COOKIE, SESSION_COOKIE, CurrentUser, _hash_password, authenticate, get_current_user, require_csrf, require_permission
from .db import get_db, settings
from .invoicing import FinanceError, allocate_payment, approve_invoice, cancel_invoice, create_invoice, create_payment, finalize_tax, get_invoice, issue_invoice, post_invoice, reject_invoice, reverse_payment, submit_invoice
from .models import Membership, Organization, User
from .risk import risk_flags
from .schemas import ApprovalDecision, BootstrapRequest, InvoiceCreate, LoginRequest, PaymentAllocationCreate, PaymentCreate, TaxDeterminationCreate

app = FastAPI(title="International Tax Structure Tracker", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()], allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"])

def fail(exc: FinanceError):
    raise HTTPException(status_code=409, detail={"error": {"code": "FINANCE_RULE_VIOLATION", "message": str(exc)}})

@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.app_env == "production": response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

@app.get("/health/live")
async def live(): return {"status": "ok"}

@app.get("/health/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    await db.execute(select(func.now()))
    return {"status": "ready"}

@app.post("/api/v1/auth/bootstrap")
async def bootstrap(payload: BootstrapRequest, response: Response, db: AsyncSession = Depends(get_db)):
    if not settings.bootstrap_token or not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        raise HTTPException(status_code=404, detail={"error": {"code": "BOOTSTRAP_DISABLED", "message": "Bootstrap is disabled."}})
    if payload.bootstrap_token != settings.bootstrap_token or payload.admin_email.lower() != settings.bootstrap_admin_email.lower() or payload.admin_password != settings.bootstrap_admin_password:
        raise HTTPException(status_code=403, detail={"error": {"code": "BOOTSTRAP_DENIED", "message": "Bootstrap credentials are invalid."}})
    if await db.scalar(select(User.id).limit(1)):
        raise HTTPException(status_code=409, detail={"error": {"code": "BOOTSTRAP_ALREADY_COMPLETE", "message": "Bootstrap has already been completed."}})
    org = Organization(name=payload.organization_name)
    user = User(email=payload.admin_email.strip().lower(), password_hash=_hash_password(payload.admin_password), display_name=payload.admin_display_name)
    db.add_all([org, user]); await db.flush(); db.add(Membership(organization_id=org.id, user_id=user.id, role="owner"))
    session, _, _, session_token, csrf_token = await authenticate(db, user.email, payload.admin_password, org.id)
    await db.commit()
    response.set_cookie(SESSION_COOKIE, session_token, secure=settings.auth_cookie_secure, httponly=True, samesite="strict", path="/", expires=session.expires_at)
    response.set_cookie(CSRF_COOKIE, csrf_token, secure=settings.auth_cookie_secure, httponly=False, samesite="strict", path="/", expires=session.expires_at)
    return {"organization_id": org.id, "user_id": user.id, "role": "owner"}

@app.post("/api/v1/auth/login")
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    session, user, membership, session_token, csrf_token = await authenticate(db, payload.email, payload.password, payload.organization_id)
    await db.commit()
    response.set_cookie(SESSION_COOKIE, session_token, secure=settings.auth_cookie_secure, httponly=True, samesite="strict", path="/", expires=session.expires_at)
    response.set_cookie(CSRF_COOKIE, csrf_token, secure=settings.auth_cookie_secure, httponly=False, samesite="strict", path="/", expires=session.expires_at)
    return {"user_id": user.id, "organization_id": membership.organization_id, "role": membership.role, "display_name": user.display_name}

@app.post("/api/v1/auth/logout")
async def logout(response: Response, user: CurrentUser = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    from .models import Session
    session = await db.get(Session, user.session_id)
    if session: session.revoked_at = datetime.now(timezone.utc)
    await db.commit(); response.delete_cookie(SESSION_COOKIE, path="/"); response.delete_cookie(CSRF_COOKIE, path="/")
    return {"status": "logged_out"}

@app.get("/api/v1/auth/me")
async def me(user: CurrentUser = Depends(get_current_user)):
    return {"user_id": user.user_id, "organization_id": user.organization_id, "email": user.email, "display_name": user.display_name, "role": user.role}

@app.get("/api/v1/risk-flags")
async def get_risk_flags(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await risk_flags(db, organization_id=user.organization_id)

@app.post("/api/v1/transactions/{transaction_id}/invoices")
async def create_invoice_endpoint(transaction_id:int, payload:InvoiceCreate, db:AsyncSession=Depends(get_db), user:CurrentUser=Depends(require_permission("finance:write")), x_request_id:str|None=Header(None)):
    try:
        invoice=await create_invoice(db, organization_id=user.organization_id, transaction_id=transaction_id, actor=str(user.user_id), invoice_type=payload.invoice_type, currency=payload.currency, issue_date=payload.issue_date, due_date=payload.due_date, related_invoice_id=payload.related_invoice_id, notes=payload.notes, lines=[x.model_dump() for x in payload.lines], correlation_id=x_request_id); await db.commit(); await db.refresh(invoice); return invoice
    except FinanceError as e: await db.rollback(); fail(e)

@app.get("/api/v1/invoices/{invoice_id}")
async def invoice_endpoint(invoice_id:int, user:CurrentUser=Depends(get_current_user), db:AsyncSession=Depends(get_db)):
    try: return await get_invoice(db, invoice_id, organization_id=user.organization_id)
    except FinanceError as e: fail(e)

async def transition(endpoint, db, invoice_id, user:CurrentUser, x_request_id):
    try:
        result=await endpoint(db, invoice_id, str(user.user_id), correlation_id=x_request_id, organization_id=user.organization_id); await db.commit(); return result
    except FinanceError as e: await db.rollback(); fail(e)

@app.post("/api/v1/invoices/{invoice_id}/submit")
async def submit(invoice_id:int, db:AsyncSession=Depends(get_db), user:CurrentUser=Depends(require_permission("finance:write")), x_request_id:str|None=Header(None)): return await transition(submit_invoice,db,invoice_id,user,x_request_id)
@app.post("/api/v1/invoices/{invoice_id}/approve")
async def approve(invoice_id:int, payload:ApprovalDecision, db:AsyncSession=Depends(get_db), user:CurrentUser=Depends(require_permission("finance:approve")), x_request_id:str|None=Header(None)):
    try: result=await approve_invoice(db,invoice_id,str(user.user_id),payload.comment,x_request_id,organization_id=user.organization_id); await db.commit(); return result
    except FinanceError as e: await db.rollback(); fail(e)
@app.post("/api/v1/invoices/{invoice_id}/reject")
async def reject(invoice_id:int, payload:ApprovalDecision, db:AsyncSession=Depends(get_db), user:CurrentUser=Depends(require_permission("finance:approve")), x_request_id:str|None=Header(None)):
    try: result=await reject_invoice(db,invoice_id,str(user.user_id),payload.comment,x_request_id,organization_id=user.organization_id); await db.commit(); return result
    except FinanceError as e: await db.rollback(); fail(e)
@app.post("/api/v1/invoices/{invoice_id}/finalize-tax")
async def finalize_tax_endpoint(invoice_id:int, payload:list[TaxDeterminationCreate], db:AsyncSession=Depends(get_db), user:CurrentUser=Depends(require_permission("tax:write")), x_request_id:str|None=Header(None)):
    try: result=await finalize_tax(db,invoice_id,str(user.user_id),[x.model_dump() for x in payload],x_request_id,organization_id=user.organization_id); await db.commit(); return result
    except FinanceError as e: await db.rollback(); fail(e)
@app.post("/api/v1/invoices/{invoice_id}/issue")
async def issue(invoice_id:int, db:AsyncSession=Depends(get_db), user:CurrentUser=Depends(require_permission("finance:write")), x_request_id:str|None=Header(None)): return await transition(issue_invoice,db,invoice_id,user,x_request_id)
@app.post("/api/v1/invoices/{invoice_id}/post")
async def post(invoice_id:int, db:AsyncSession=Depends(get_db), user:CurrentUser=Depends(require_permission("finance:post")), x_request_id:str|None=Header(None)): return await transition(post_invoice,db,invoice_id,user,x_request_id)
@app.post("/api/v1/invoices/{invoice_id}/cancel")
async def cancel(invoice_id:int, db:AsyncSession=Depends(get_db), user:CurrentUser=Depends(require_permission("finance:write")), x_request_id:str|None=Header(None)): return await transition(cancel_invoice,db,invoice_id,user,x_request_id)
@app.post("/api/v1/payments")
async def payment(payload:PaymentCreate, db:AsyncSession=Depends(get_db), user:CurrentUser=Depends(require_permission("finance:write")), x_request_id:str|None=Header(None)):
    try: result=await create_payment(db,organization_id=user.organization_id,actor=str(user.user_id),data=payload.model_dump(),correlation_id=x_request_id); await db.commit(); return result
    except Exception as e: await db.rollback(); raise HTTPException(status_code=409,detail={"error":{"code":"PAYMENT_CREATE_FAILED","message":str(e)}})
@app.post("/api/v1/payments/{payment_id}/allocate")
async def allocation(payment_id:int,payload:PaymentAllocationCreate,db:AsyncSession=Depends(get_db),user:CurrentUser=Depends(require_permission("finance:write")),x_request_id:str|None=Header(None)):
    try: result=await allocate_payment(db,payment_id,organization_id=user.organization_id,invoice_id=payload.invoice_id,amount=payload.allocated_amount,allocation_date=payload.allocation_date,actor=str(user.user_id),correlation_id=x_request_id); await db.commit(); return result
    except FinanceError as e: await db.rollback(); fail(e)
@app.post("/api/v1/payments/{payment_id}/reverse")
async def reverse(payment_id:int,db:AsyncSession=Depends(get_db),user:CurrentUser=Depends(require_permission("finance:write")),x_request_id:str|None=Header(None)):
    try: result=await reverse_payment(db,payment_id,str(user.user_id),x_request_id,organization_id=user.organization_id); await db.commit(); return result
    except FinanceError as e: await db.rollback(); fail(e)
