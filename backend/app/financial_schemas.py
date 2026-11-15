from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer, StringConstraints, model_validator
from .currencies import Currency, RatePolicy, RateQuote
from .profile_scope import ProfileScope

Money = Annotated[Decimal, PlainSerializer(lambda value: format(value, '.2f'), return_type=str, when_used='json')]


class DateRange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode='after')
    def validate_range(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError('start_date must be on or before end_date')
        return self


class ReportingPeriod(DateRange):
    as_of: date
    partial_months: bool


class ReportOptions(DateRange):
    profile_id: ProfileScope = None
    reporting_currency: Currency = 'USD'
    rate_policy: RatePolicy = 'historical'


class CategorySpending(BaseModel):
    category: str
    total: Money
    share_percent: Money


class MonthlyTrend(BaseModel):
    month: str
    income: Money
    expenses: Money
    net_balance: Money
    transaction_count: int


class MonthComparison(BaseModel):
    current_month: str
    previous_month: str
    current_income: Money
    previous_income: Money
    income_change: Money
    income_change_percent: Money | None
    current_expenses: Money
    previous_expenses: Money
    expense_change: Money
    expense_change_percent: Money | None
    current_transaction_count: int
    previous_transaction_count: int
    note: str


class FinancialInsights(BaseModel):
    top_spending_categories: list[CategorySpending]
    month_over_month: MonthComparison | None


class FinancialSummary(BaseModel):
    profile_id: int | Literal['all'] | None = None
    profile_name: str = 'My Profile'
    period: ReportingPeriod
    currency: Currency = 'USD'
    rate_policy: RatePolicy = 'historical'
    rates: list[RateQuote] = []
    conversion_policy: str = 'Per-transaction historical rates; rounded half-up to 2 decimal places before aggregation'
    income: Money
    expenses: Money
    net_balance: Money
    transaction_count: int
    spending_by_category: list[CategorySpending]
    monthly_trends: list[MonthlyTrend]
    insights: FinancialInsights


class AssistantQuery(ReportOptions):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class AssistantResponse(BaseModel):
    provider: Literal['rule_based'] = 'rule_based'
    status: Literal['answered', 'no_data', 'unsupported']
    intent: str | None = None
    message: str
    summary: FinancialSummary | None = None
