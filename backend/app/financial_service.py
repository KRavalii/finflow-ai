"""Read-only conversion before aggregation; never loads descriptions or IDs."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext
import time

from sqlalchemy import and_, literal, or_, select
from sqlalchemy.orm import Session

from .financial_schemas import CategorySpending, DateRange, FinancialSummary, MonthlyTrend, ReportingPeriod
from .insights import ZERO, build_insights, comparison_months, month_end, month_key
from .models import Transaction, LegacyTransaction
from .profile_scope import ProfileScope, resolve_profile, scope_statement
from .transaction_storage import transaction_model
from .currencies import Currency, RatePolicy
from .exchange_rates import get_exchange_rates


def financial_summary(db: Session, period: DateRange, as_of: date,
                      reporting_currency: Currency = 'USD', rate_policy: RatePolicy = 'historical', profile_id: ProfileScope = None) -> FinancialSummary:
    profile = resolve_profile(db, profile_id)
    model = transaction_model(db)
    bounds = comparison_months(as_of, period.end_date)
    selected = []
    if period.start_date:
        selected.append(model.transaction_date >= period.start_date)
    if period.end_date:
        selected.append(model.transaction_date <= period.end_date)
    selected_condition = and_(*selected) if selected else True
    condition = selected_condition
    if bounds:
        condition = or_(selected_condition, and_(model.transaction_date >= bounds[0], model.transaction_date <= bounds[2]))
    statement = select(
        model.transaction_date, model.category, model.transaction_type, model.amount,
        literal('USD') if model is LegacyTransaction else model.currency,
    ).where(condition)
    statement = scope_statement(statement, model, profile)

    # One data SELECT gives a consistent snapshot for summary and comparisons.
    # Convert per row before summing: round(a*r)+round(b*r) may differ from
    # round((a+b)*r). Do not aggregate original amounts before conversion.
    # 50 digits covers NUMERIC(14,2) even across very large record counts.
    with localcontext() as context:
        context.prec = 50
        income, expenses, count = ZERO, ZERO, 0
        categories: dict[str, Decimal] = {}
        months: dict[str, dict] = {}
        comparison_data: dict[str, dict] = {}
        rates = get_exchange_rates()
        evidence = {}
        deadline = time.monotonic() + 12
        for day, category, kind, amount, original_currency in db.execute(statement):
            total, rate = rates.convert(Decimal(amount), original_currency, reporting_currency, day, rate_policy, deadline)
            if original_currency != reporting_currency:
                evidence[(rate.base, rate.quote, rate.requested_date)] = rate
            row_count = 1
            key = month_key(day)
            metric = 'income' if kind == 'income' else 'expenses'
            if bounds and bounds[0] <= day <= bounds[2]:
                value = comparison_data.setdefault(key, {'income': ZERO, 'expenses': ZERO, 'count': 0})
                value[metric] += total
                value['count'] += row_count
            if (period.start_date and day < period.start_date) or (period.end_date and day > period.end_date):
                continue
            count += row_count
            if kind == 'income':
                income += total
            else:
                expenses += total
                categories[category] = categories.get(category, ZERO) + total
            value = months.setdefault(key, {'income': ZERO, 'expenses': ZERO, 'count': 0})
            value[metric] += total
            value['count'] += row_count
        spending = [CategorySpending(category=category, total=total,
                                    share_percent=(total / expenses * 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if expenses else ZERO)
                    for category, total in sorted(categories.items(), key=lambda pair: (-pair[1], pair[0]))]
        trends = [MonthlyTrend(month=month, income=value['income'], expenses=value['expenses'],
                               net_balance=value['income'] - value['expenses'], transaction_count=value['count'])
                  for month, value in sorted(months.items())]
        partial = bool((period.start_date and period.start_date.day != 1) or
                       (period.end_date and period.end_date != month_end(period.end_date)) or
                       (not period.end_date or period.end_date >= as_of))
        return FinancialSummary(
            profile_id=profile.id if profile else ('all' if profile_id == 'all' else None),
            profile_name=profile.name if profile else ('All Profiles (including archived)' if profile_id == 'all' else 'My Profile'),
            period=ReportingPeriod(**period.model_dump(), as_of=as_of, partial_months=partial),
            income=income, expenses=expenses, net_balance=income - expenses,
            currency=reporting_currency, rate_policy=rate_policy, rates=list(evidence.values()),
            conversion_policy=f'Per-transaction {rate_policy} rates; rounded half-up to 2 decimal places before aggregation. Historical rates use the transaction date or a prior published rate within 7 days.',
            transaction_count=count, spending_by_category=spending, monthly_trends=trends,
            insights=build_insights(spending, comparison_data, bounds),
        )
