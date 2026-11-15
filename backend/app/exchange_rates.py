"""Only currency pairs/dates are sent upstream. No financial rows or credentials."""
import json
import threading
import time
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from functools import lru_cache
from zoneinfo import ZoneInfo

import httpx

from .currencies import Currency, RatePolicy, RateQuote


class RatesUnavailable(Exception):
    def __init__(self, base, quote, requested_date, reason='No usable exchange rate is available'):
        self.detail = {'code': 'exchange_rates_unavailable', 'base': base, 'quote': quote,
                       'requested_date': str(requested_date) if requested_date else None, 'message': reason}
        super().__init__(reason)


class ExchangeRates:
    def __init__(self, client=None, clock=None):
        self.client = client or httpx.Client(base_url='https://api.frankfurter.dev', follow_redirects=False,
                                             timeout=httpx.Timeout(5, connect=2), trust_env=False)
        self.clock = clock or (lambda: datetime.now(ZoneInfo('America/Chicago')).date())
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def get(self, base: Currency, quote: Currency, requested_date: date | None = None, deadline=None) -> RateQuote:
        now = datetime.now(timezone.utc)
        if base == quote:
            return RateQuote(base=base, quote=quote, rate=Decimal('1'), requested_date=requested_date,
                             rate_date=requested_date or self.clock(), fetched_at=now, source='Identity; no exchange needed')
        if requested_date and requested_date > self.clock():
            raise RatesUnavailable(base, quote, requested_date, 'Historical rates for future transactions are unavailable; choose latest valuation explicitly')
        deadline = deadline or time.monotonic() + 12
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not self.lock.acquire(timeout=max(0, remaining)):
            raise RatesUnavailable(base, quote, requested_date, 'Rate lookup timed out; retry to use cached results')
        key = (base, quote, requested_date)
        try:
            cached = self.cache.get(key)
            if cached and cached[0] > time.monotonic():
                self.cache.move_to_end(key)
                if isinstance(cached[1], RatesUnavailable):
                    raise cached[1]
                return cached[1].model_copy(update={'cache_hit': True})
            for days in range(8 if requested_date else 1):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RatesUnavailable(base, quote, requested_date, 'Rate lookup budget exceeded; retry to use cached results')
                lookup = requested_date - timedelta(days=days) if requested_date and requested_date.toordinal() > days else requested_date
                try:
                    response = self.client.get(f'/v2/rate/{base.lower()}/{quote.lower()}',
                                               params={'date': lookup.isoformat()} if lookup else {},
                                               timeout=min(5, remaining))
                    if response.status_code == 404 and requested_date:
                        continue
                    response.raise_for_status()
                    data = json.loads(response.content, parse_float=Decimal)
                    rate = Decimal(str(data['rate']))
                    actual_date = date.fromisoformat(data['date'])
                    if data['base'].upper() != base or data['quote'].upper() != quote or not rate.is_finite() or rate <= 0:
                        raise ValueError('Invalid provider rate')
                    reference = requested_date or datetime.now(timezone.utc).date()
                    if not 0 <= (reference - actual_date).days <= 7:
                        raise ValueError('Rate is outside the allowed date window')
                    value = RateQuote(base=base, quote=quote, rate=rate, requested_date=requested_date,
                                      rate_date=actual_date, fetched_at=datetime.now(timezone.utc))
                    self.cache[key] = (time.monotonic() + (86400 if requested_date else 3600), value)
                    break
                except (httpx.HTTPError, ValueError, KeyError, TypeError, InvalidOperation):
                    raise RatesUnavailable(base, quote, requested_date) from None
            else:
                raise RatesUnavailable(base, quote, requested_date)
            self.cache.move_to_end(key)
            while len(self.cache) > 2048:
                self.cache.popitem(last=False)
            return value
        except RatesUnavailable as error:
            self.cache[key] = (time.monotonic() + 30, error)
            while len(self.cache) > 2048:
                self.cache.popitem(last=False)
            raise
        finally:
            self.lock.release()

    def convert(self, amount: Decimal, base: Currency, quote: Currency, day: date,
                policy: RatePolicy = 'historical', deadline=None):
        rate = self.get(base, quote, day if policy == 'historical' else None, deadline)
        with localcontext() as context:
            context.prec = 50
            converted = (amount * rate.rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return converted, rate


@lru_cache
def get_exchange_rates():
    return ExchangeRates()
