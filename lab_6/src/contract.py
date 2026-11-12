import re
import unicodedata
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "RUB"}
SUPPORTED_SOURCES = {"openlibrary_api", "html_books_toscrape"}


def _normalize_text(v: str) -> str:
    v = unicodedata.normalize("NFKC", v)
    v = v.replace("\xa0", " ").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    return re.sub(r"\s+", " ", v).strip()


class BookRecord(BaseModel):
    book_key: str = Field(..., min_length=3, max_length=200)
    title: str = Field(..., min_length=1, max_length=500)

    author_key: Optional[str] = Field(None, max_length=200)
    price: Optional[Decimal] = Field(None, gt=0, le=Decimal("100000"))
    price_currency: Optional[str] = Field(None, min_length=3, max_length=3)
    rating: Optional[int] = Field(None, ge=1, le=5)
    availability: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=100)
    isbn: Optional[str] = Field(None, min_length=10, max_length=17)
    publish_year: Optional[int] = Field(None, ge=1000, le=2100)

    source: str
    source_url: str
    parser_version: str
    collected_at: datetime

    @field_validator("title", "category", "availability", mode="before")
    @classmethod
    def _norm(cls, v):
        return _normalize_text(v) if isinstance(v, str) else v

    @field_validator("price_currency")
    @classmethod
    def _currency(cls, v):
        if v is None:
            return v
        v = v.upper().strip()
        if v not in SUPPORTED_CURRENCIES:
            raise ValueError(f"unsupported currency: {v}")
        return v

    @field_validator("isbn")
    @classmethod
    def _isbn(cls, v):
        if v is None:
            return v
        digits = re.sub(r"[-\s]", "", v)
        if len(digits) not in (10, 13) or not digits[:-1].isdigit():
            raise ValueError("ISBN must be 10 or 13 digits")
        return digits

    @model_validator(mode="after")
    def _consistency(self):
        if self.source not in SUPPORTED_SOURCES:
            raise ValueError(f"unknown source: {self.source}")
        if self.source == "html_books_toscrape":
            if self.price is None:
                raise ValueError("HTML source requires price")
            if self.rating is None:
                raise ValueError("HTML source requires rating")
        if self.source == "openlibrary_api":
            if self.isbn is None and self.publish_year is None:
                raise ValueError("API book requires isbn or publish_year")
            if self.price is not None and self.price_currency is None:
                raise ValueError("price without currency")
        return self


class AuthorRecord(BaseModel):
    author_key: str = Field(..., min_length=2, max_length=200)
    name: str = Field(..., min_length=1, max_length=300)
    birth_date: Optional[str] = None
    work_count: Optional[int] = Field(None, ge=0, le=1_000_000)
    source: str
    source_url: str
    parser_version: str
    collected_at: datetime

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        return _normalize_text(v)