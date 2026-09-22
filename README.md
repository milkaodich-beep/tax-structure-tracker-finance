# International Tax Structure Tracker

A risk-surfacing and documentation tracker for multi-entity international tax structures.

> **Important:** This application organizes evidence and surfaces configurable risk flags. It does **not** determine final tax liability, treaty eligibility, CFC attribution, QDMTT/UTPR liability, or other legal conclusions. Those decisions require qualified professional review and current jurisdiction-specific law.

## Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy 2.x async, asyncpg, Alembic, PostgreSQL 16, Pydantic v2
- Frontend: React 19.3, TypeScript, Vite 8.3
- Local orchestration: Docker Compose
- CI: GitHub Actions

## Finance invoice controls

The invoice milestone uses a controlled lifecycle:

```text
DRAFT → PENDING_APPROVAL → APPROVED → ISSUED → POSTED → PARTIALLY_SETTLED → SETTLED
```

Cancellation is limited to pre-issuance. After posting, financial values are treated as immutable at the service/API boundary; corrections use controlled adjustment documents rather than direct mutation. Issuance requires completed approval and finalized tax determination.

Approval records retain actor, decision, timestamp, comment and sequence. The invoice creator cannot approve their own invoice.

Payments are standalone records with PaymentAllocation relationships. One payment can settle multiple invoices and one invoice can receive multiple payments. Allocation uses PostgreSQL row locks and rejects over-allocation or currency mismatches without an explicit FX mechanism. Payment reversal reverses active allocations and reopens settlement state.

State-changing invoice, tax, approval, payment, allocation and settlement operations write audit events in the same database transaction as the business mutation. Audit events are append-only at the application API boundary.

Invoice date, accounting date, posting date and settlement date are distinct fields. Full accounting-period locking is outside this milestone.

## Repository layout

```text
backend/       FastAPI application, models, migrations and tests
frontend/      React/TypeScript dashboard
infra/         Local Docker Compose configuration
.github/       CI workflow
.env.example   Local configuration template
```

## Local development

Copy `.env.example` to `.env` for local overrides, then:

```bash
docker compose -f infra/docker-compose.yml up --build
```

API docs: `http://localhost:8000/docs`

## Tests

Backend:

```bash
python -m compileall -q backend/app
PYTHONPATH=backend pytest -q backend/tests
```

Frontend:

```bash
cd frontend
npm ci
npm run build
```

## Known production gaps

Authentication/RBAC, tenant isolation, formal accounting-period locks, configurable legal-entity invoice series, FX accounting, full reconciliation workflows, production-grade evidence storage, and regulatory/reference-data versioning remain future work.

Do not commit `.env`, production credentials, taxpayer identifiers, tax documents, database dumps or confidential sample data.
