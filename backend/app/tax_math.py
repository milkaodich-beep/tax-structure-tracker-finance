from decimal import Decimal
ETR_FLOOR = Decimal("15")
def compute_etr(globe_income: Decimal | None, covered_taxes: Decimal | None) -> Decimal | None:
    if globe_income is None or covered_taxes is None or globe_income <= 0: return None
    return (covered_taxes / globe_income) * Decimal("100")
