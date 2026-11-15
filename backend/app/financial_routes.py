from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .assistant_service import HELP, AssistantProvider, RuleBasedProvider, resolve_question
from .database import get_db
from .financial_schemas import AssistantQuery, AssistantResponse, DateRange, FinancialSummary, ReportOptions
from .currencies import Currency, RateQuote
from .exchange_rates import get_exchange_rates
from datetime import date
from .financial_service import financial_summary

router = APIRouter(tags=['financial intelligence'])


def reporting_today():
    return datetime.now(ZoneInfo('America/Chicago')).date()


def get_assistant_provider() -> AssistantProvider:
    return RuleBasedProvider()


@router.get('/api/summary', response_model=FinancialSummary)
def get_summary(period: Annotated[ReportOptions, Query()], db: Annotated[Session, Depends(get_db)]):
    return financial_summary(db, DateRange(start_date=period.start_date, end_date=period.end_date), reporting_today(),
                             period.reporting_currency, period.rate_policy, period.profile_id)


@router.get('/api/exchange-rates', response_model=RateQuote)
def exchange_rate(base: Currency, quote: Currency, rate_date: date | None = None):
    return get_exchange_rates().get(base, quote, rate_date)


@router.post('/api/assistant/query', response_model=AssistantResponse)
def assistant_query(payload: AssistantQuery, db: Annotated[Session, Depends(get_db)],
                    provider: Annotated[AssistantProvider, Depends(get_assistant_provider)]):
    today = reporting_today()
    resolved = resolve_question(payload.query, DateRange(start_date=payload.start_date, end_date=payload.end_date), today)
    if resolved is None:
        return AssistantResponse(status='unsupported', message=HELP)
    intent, period = resolved
    summary = financial_summary(db, period, today, payload.reporting_currency, payload.rate_policy, payload.profile_id)
    return provider.answer(intent, summary)
