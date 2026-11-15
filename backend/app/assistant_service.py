"""Local-only assistant boundary. Providers receive aggregates, never sessions or records."""
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

from .financial_schemas import AssistantResponse, DateRange, FinancialSummary
from .currencies import currency_money

HELP = ('I can summarize income, expenses, net balance, top spending categories, and monthly changes. '
        'Try "Summarise my finances", "What are my total expenses?", "What is my biggest spending category?", '
        'or "How did expenses change last month?". Use the date controls or say '
        '"this month", "last month", or "all time". I cannot modify transactions or predict outcomes.')


def resolve_question(query: str, period: DateRange, as_of: date):
    text = re.sub(r'\s+', ' ', query.casefold()).strip(' ?.!')
    # Explicitly refuse unsupported dates, actions, and forecasts instead of
    # silently answering a different question. No arbitrary SQL or tool execution.
    if re.search(r'\b(delete|remove|create|edit|update|invest|predict|forecast|tomorrow|next|yesterday|today|week|year|quarter)\b|\d', text):
        return None
    temporal = [phrase for phrase in ('this month', 'last month', 'all time') if phrase in text]
    if len(temporal) > 1 or (temporal and (period.start_date or period.end_date)):
        return None
    # Full sentence patterns deliberately reject unrecognized qualifiers such as
    # "spend on groceries"; returning overall spending for that would be misleading.
    base = text
    for phrase in temporal:
        base = base.replace(phrase, '')
    base = re.sub(r'\s+', ' ', base).strip()
    base = re.sub(r'\s+(in|for|during|over)$', '', base)
    patterns = {
        'summary': r'(?:(?:(?:can|could|would) you )?(?:please )?(?:summari[sz]e(?: (?:my )?(?:finances|financial (?:situation|position|activity)))?|(?:give|show) me (?:an? |my )?(?:financial summary|summary of my finances|overview of my finances)|(?:a |my )?financial summary)(?: please)?)',
        'income_change': r'(?:how (?:did|has) (?:my )?income (?:change|changed)|compare (?:my )?income|(?:show (?:my )?)?income (?:trends|month.over.month))',
        'expense_change': r'(?:how (?:did|have) (?:my )?expenses (?:change|changed)|compare (?:my )?expenses|(?:show (?:my )?)?(?:expense|spending|monthly) trends)',
        'top_categories': r'(?:what (?:is|are) my (?:top|biggest|largest) (?:spending )?categor(?:y|ies)|(?:show |list )?(?:my )?top spending categories|where (?:did|do) i spend (?:the )?most)',
        'balance': r'(?:what is my (?:net )?balance|(?:show (?:me )?)?(?:my )?net balance)',
        'income': r'(?:what is my (?:total )?income|how much (?:did i earn|have i earned)|show (?:my )?(?:total )?income|(?:total )?income)',
        'expenses': r'(?:what are my (?:total )?expenses|how much (?:did i spend|have i spent)|show (?:my )?(?:total )?expenses|(?:total )?expenses)',
    }
    intent = next((intent for intent, pattern in patterns.items() if re.fullmatch(pattern, base)), None)
    if intent is None or (intent.endswith('_change') and temporal and temporal[0] != 'last month'):
        return None
    resolved = period
    if temporal == ['this month']:
        resolved = DateRange(start_date=as_of.replace(day=1), end_date=as_of)
    elif temporal == ['last month']:
        if as_of.replace(day=1) == date.min:
            return None
        end = as_of.replace(day=1) - timedelta(days=1)
        resolved = DateRange(start_date=end.replace(day=1), end_date=end)
    return intent, resolved


def dollars(value: Decimal, currency='USD') -> str:
    return currency_money(value, currency)


def period_label(summary: FinancialSummary) -> str:
    period = summary.period
    if period.start_date and period.end_date:
        return f'{period.start_date.isoformat()} through {period.end_date.isoformat()}'
    if period.start_date:
        return f'{period.start_date.isoformat()} onward'
    if period.end_date:
        return f'all recorded dates through {period.end_date.isoformat()}'
    return 'all recorded dates'


class AssistantProvider(Protocol):
    # A future provider requires a separate explicit implementation and privacy review.
    # This boundary deliberately cannot access credentials or individual records.
    def answer(self, intent: str, summary: FinancialSummary) -> AssistantResponse: ...


class RuleBasedProvider:
    def answer(self, intent: str, summary: FinancialSummary) -> AssistantResponse:
        result = self._answer(intent, summary)
        if 'Reporting period:' not in result.message:
            result.message += f' Reporting period: {period_label(summary)}.'
        dates = sorted({rate.rate_date.isoformat() for rate in summary.rates})
        rate_label = ', '.join(dates) if len(dates) <= 4 else f'{dates[0]} through {dates[-1]} ({len(dates)} published dates)'
        result.message += f' Reporting currency: {summary.currency}. {summary.conversion_policy}'
        result.message += f' Rate date(s): {rate_label}.' if dates else ' No currency exchange was required.'
        result.message += f' Profile: {summary.profile_name}.'
        return result

    def _answer(self, intent: str, summary: FinancialSummary) -> AssistantResponse:
        label = period_label(summary)
        if intent == 'summary':
            categories = summary.insights.top_spending_categories
            category_text = ('Top spending categories: ' + '; '.join(
                f'{item.category}: {dollars(item.total, summary.currency)} ({item.share_percent:.2f}%)'
                for item in categories
            ) + '.') if categories else 'Top spending categories: none; no expenses are recorded in this period.'
            message = (f'Financial summary ({summary.currency}). Income: {dollars(summary.income, summary.currency)}. '
                       f'Expenses: {dollars(summary.expenses, summary.currency)}. '
                       f'Net balance (income minus expenses): {dollars(summary.net_balance, summary.currency)}. '
                       f'{category_text} Reporting period: {label}. '
                       f'Based on {summary.transaction_count} recorded transaction(s).')
            if summary.period.partial_months:
                message += ' This reporting range may include partial calendar months.'
            if summary.transaction_count == 0:
                message += (' No transactions are recorded in this period. Zero totals mean no recorded activity, '
                            'not confirmation that your finances are complete. Add transactions or choose another reporting period.')
            else:
                if summary.income == 0:
                    message += ' No income is recorded in this period.'
                message += ' Totals reflect recorded transactions only; missing or unrecorded activity cannot be inferred.'
            return AssistantResponse(status='answered' if summary.transaction_count else 'no_data',
                                     intent=intent, message=message, summary=summary)
        if intent.endswith('_change'):
            comparison = summary.insights.month_over_month
            if not comparison or not (comparison.current_transaction_count or comparison.previous_transaction_count):
                return AssistantResponse(status='no_data', intent=intent, summary=summary,
                                         message='There are no recorded transactions in the comparison months, so there is not enough data to describe a change.')
            metric = 'income' if intent == 'income_change' else 'expenses'
            current = getattr(comparison, f'current_{metric}')
            previous = getattr(comparison, f'previous_{metric}')
            change = comparison.income_change if metric == 'income' else comparison.expense_change
            percentage = comparison.income_change_percent if metric == 'income' else comparison.expense_change_percent
            percent_text = f'{abs(percentage):.2f}%' if percentage is not None else 'percentage unavailable because the previous total is zero'
            direction = 'increased' if change > 0 else 'decreased' if change < 0 else 'did not change'
            message = (f'Comparing complete calendar months {comparison.current_month} and {comparison.previous_month}, '
                       f'{metric} {direction}: {dollars(current, summary.currency)} versus {dollars(previous, summary.currency)}. '
                       f'Difference: {dollars(change, summary.currency)}; {percent_text}. {comparison.note}')
            return AssistantResponse(status='answered', intent=intent, message=message, summary=summary)
        if summary.transaction_count == 0:
            return AssistantResponse(status='no_data', intent=intent, summary=summary,
                                     message=f'No transactions are recorded for {label}. Add transactions or choose another reporting period.')
        if intent == 'top_categories':
            categories = summary.insights.top_spending_categories
            message = ('Top spending categories: ' + '; '.join(f'{item.category}: {dollars(item.total, summary.currency)} ({item.share_percent:.2f}%)' for item in categories)) if categories else 'There are no recorded expenses in this period'
        else:
            value = {'income': summary.income, 'expenses': summary.expenses, 'balance': summary.net_balance}[intent]
            message = f'{"Net balance (income minus expenses)" if intent == "balance" else "Total " + intent}: {dollars(value, summary.currency)}'
        return AssistantResponse(status='answered', intent=intent, summary=summary,
                                 message=f'{message}. Reporting period: {label}. Amounts are in {summary.currency} and reflect recorded transactions only.')
