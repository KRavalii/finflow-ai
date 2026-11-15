from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from .currencies import Currency, RateQuote


class TransactionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    category: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    transaction_type: Literal["income", "expense"]
    transaction_date: date
    currency: Currency = 'USD'
    profile_id: int | None = Field(default=None, gt=0)


class TransactionRead(TransactionWrite):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    converted_amount: str | None = None
    reporting_currency: Currency | None = None
    conversion: RateQuote | None = None
    conversion_error: dict | None = None
    profile_name: str | None = None
