"""Pure calculations on aggregates. No database access or external requests."""
import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from .financial_schemas import CategorySpending, FinancialInsights, MonthComparison

ZERO = Decimal('0.00')


def month_key(day: date) -> str:
    return f'{day.year:04d}-{day.month:02d}'


def month_end(day: date) -> date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def comparison_months(as_of: date, end_date: date | None):
    # Never compare the current incomplete calendar month by default.
    anchor = min(end_date, as_of) if end_date else as_of
    if anchor >= as_of or anchor != month_end(anchor):
        if anchor.replace(day=1) == date.min:
            return None
        anchor = anchor.replace(day=1) - timedelta(days=1)
    current_start = anchor.replace(day=1)
    if current_start == date.min:
        return None
    previous_end = current_start - timedelta(days=1)
    return previous_end.replace(day=1), current_start, anchor


def percent_change(current: Decimal, previous: Decimal) -> Decimal | None:
    if previous == 0:
        return None
    return ((current - previous) / previous * 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def build_insights(categories: list[CategorySpending], monthly: dict, bounds) -> FinancialInsights:
    comparison = None
    if bounds:
        previous_start, current_start, _ = bounds
        current = monthly.get(month_key(current_start), {'income': ZERO, 'expenses': ZERO, 'count': 0})
        previous = monthly.get(month_key(previous_start), {'income': ZERO, 'expenses': ZERO, 'count': 0})
        comparison = MonthComparison(
            current_month=month_key(current_start), previous_month=month_key(previous_start),
            current_income=current['income'], previous_income=previous['income'],
            income_change=current['income'] - previous['income'],
            income_change_percent=percent_change(current['income'], previous['income']),
            current_expenses=current['expenses'], previous_expenses=previous['expenses'],
            expense_change=current['expenses'] - previous['expenses'],
            expense_change_percent=percent_change(current['expenses'], previous['expenses']),
            current_transaction_count=current['count'], previous_transaction_count=previous['count'],
            note='Compares complete calendar months, independently of start_date. '
                 'Months without recorded transactions total zero; a zero baseline has no percentage change. '
                 'Missing records cannot be distinguished from no activity.',
        )
    return FinancialInsights(top_spending_categories=categories[:3], month_over_month=comparison)
