from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from .models import Entity, SubstanceRecord, IntercompanyTransaction, PillarTwoStatus, TreatyRate
from .tax_math import ETR_FLOOR, compute_etr

async def risk_flags(db: AsyncSession, *, organization_id: int) -> list[dict]:
    flags: list[dict] = []
    today = date.today()
    cutoff = today - timedelta(days=365)
    pillar_two_rows = (await db.scalars(select(PillarTwoStatus).join(PillarTwoStatus.entity).where(PillarTwoStatus.organization_id == organization_id))).all()
    for s in pillar_two_rows:
        etr = compute_etr(s.globe_income, s.covered_taxes)
        if etr is not None and etr < ETR_FLOOR:
            flags.append({"type":"PILLAR_TWO_ETR","severity":"high","entity_id":s.entity_id,"message":"Computed ETR is below 15%; review QDMTT/UTPR treatment with a tax professional.","details":{"etr":str(etr),"qdmtt_applicable":s.qdmtt_applicable,"safe_harbour_type":s.safe_harbour_type}})
    substance_entities = (await db.scalars(select(Entity).where(Entity.organization_id == organization_id, Entity.entity_type.in_(["holdco","ip_co"])))).all()
    for entity in substance_entities:
        records = (await db.scalars(select(SubstanceRecord).options(selectinload(SubstanceRecord.board_meetings)).where(SubstanceRecord.organization_id == organization_id, SubstanceRecord.entity_id==entity.id,SubstanceRecord.period>=cutoff,SubstanceRecord.period<=today))).all()
        employees = sum(r.local_employee_count for r in records)
        meetings = sum(1 for record in records for meeting in record.board_meetings if cutoff <= meeting.meeting_date <= today)
        if employees == 0 and meetings == 0:
            flags.append({"type":"SUBSTANCE_RISK","severity":"high","entity_id":entity.id,"message":"No local employees and no board meetings recorded in the trailing 12 months.","details":{"period_start":cutoff.isoformat(),"period_end":today.isoformat()}})
    transactions = (await db.scalars(select(IntercompanyTransaction))).all()
    for tx in transactions:
        if tx.stated_price < tx.benchmark_low or tx.stated_price > tx.benchmark_high:
            flags.append({"type":"TP_RISK","severity":"medium","entity_id":tx.from_entity_id,"message":"Stated transfer price is outside the benchmark range; review required.","details":{"transaction_id":tx.id,"stated_price":str(tx.stated_price),"benchmark":[str(tx.benchmark_low),str(tx.benchmark_high)]}})
    treaties = (await db.scalars(select(TreatyRate))).all()
    for treaty in treaties:
        if treaty.last_verified_date < today - timedelta(days=365):
            flags.append({"type":"TREATY_STALE","severity":"low","entity_id":None,"message":"Treaty rate has not been re-verified in the last 12 months.","details":{"treaty_rate_id":treaty.id,"last_verified_date":treaty.last_verified_date.isoformat()}})
    return flags
