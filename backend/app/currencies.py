from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

Currency = Literal['USD', 'INR', 'AED']
RatePolicy = Literal['historical', 'latest']


class RateQuote(BaseModel):
    base: Currency
    quote: Currency
    rate: Decimal
    requested_date: date | None
    rate_date: date
    fetched_at: datetime
    cache_hit: bool = False
    source: str = 'Frankfurter v2 blended reference rates'


def currency_money(value: Decimal, currency: Currency = 'USD') -> str:
    whole, fraction = format(value.copy_abs(), '.2f').split('.')
    if currency == 'INR' and len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while head:
            groups.insert(0, head[-2:])
            head = head[:-2]
        grouped = ','.join([*groups, tail])
    else:
        grouped = format(int(whole), ',')
    symbol = {'USD': '$', 'INR': '₹', 'AED': 'AED '}[currency]
    return f'{"-" if value < 0 else ""}{symbol}{grouped}.{fraction}'
