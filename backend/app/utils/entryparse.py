"""Parsing of user-supplied dates and amounts on entry write paths.

R2 guarded the vehicle/identity routes with an inline try/except per field. The
tax and parking routes parse fifteen date fields plus an amount between them, so
they raise a typed error instead and the handler catches once — same 400 payload
shape (``error`` + ``message_key``) the inline guards return, so clients cannot
tell which style produced it.

The message keys already exist in en/ro/es under the ``validation.*`` namespace.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation

# ISO 4217 code snapshot from the system iso-codes dataset (iso_4217.json).
# Unknown/test markers XXX/XTS are not usable currencies. The existing client
# BGN option is retained for vehicle history; FX availability is separate.
CURRENCY_CODES = frozenset("""
AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BOV BRL BSD
BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP CVE CZK DJF DKK
DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF
IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP
LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD
NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD
SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD
TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES VND VUV WST XAD XAF XAG XAU XBA
XBB XBC XBD XCD XCG XDR XOF XPD XPF XPT XSU XUA YER ZAR ZMW ZWG
""".split())

REQUIRED_FIELD_KEY = 'validation.required'
INVALID_DATE_KEY = 'validation.invalidDate'
INVALID_NUMBER_KEY = 'validation.invalidNumber'
INVALID_CURRENCY_KEY = 'validation.invalidCurrency'


class InvalidFieldError(ValueError):
    """A user-supplied value that cannot be parsed. Carries its localization key."""

    def __init__(self, message_key, error='Invalid value', field=None):
        super().__init__(error)
        self.message_key = message_key
        self.error = error
        self.field = field


def parse_iso_date(value):
    """ISO date/datetime string (optionally 'Z'-suffixed) -> date.

    Raises InvalidFieldError rather than the bare ValueError that used to
    escape the handler and surface as a 500.
    """
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).date()
    except (TypeError, ValueError):
        raise InvalidFieldError(INVALID_DATE_KEY, 'Invalid date format')


def parse_optional_date(value):
    """Nullable date column -> date or None, or InvalidFieldError.

    ``None`` and ``''`` mean "not provided" and give None; anything else has to
    parse. Completes the optional-parser family alongside ``parse_optional_int``
    and ``parse_optional_amount``.
    """
    if value is None or value == '':
        return None
    return parse_iso_date(value)


def parse_amount(value, error='Amount must be a number'):
    """Finite decimal from an API number/string; storage scale is field-specific."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise InvalidFieldError(INVALID_NUMBER_KEY, error)
    try:
        parsed = Decimal(str(value))
        # Bound before arithmetic/quantization; no supported column is this wide.
        if not parsed.is_finite() or abs(parsed) >= Decimal('1e20'):
            raise ValueError()
        return parsed
    except (ValueError, InvalidOperation, OverflowError):
        raise InvalidFieldError(INVALID_NUMBER_KEY, error) from None


# PostgreSQL INTEGER is 32-bit signed. A value outside this range parses fine in
# Python but fails at flush time with a DataError — i.e. a 500 for input we can
# see is unstorable. Rejected here as a 400 instead. (SQLite, used by the test
# suite, stores it happily, so only production would ever have noticed.)
_INT32_MIN = -2_147_483_648
_INT32_MAX = 2_147_483_647


def parse_optional_int(value, error='Value must be a number'):
    """Nullable integer column -> int or None, or InvalidFieldError.

    Accepts what real clients send: an int, a float, or the string an HTML
    number input submits. ``None`` and ``''`` mean "not provided" and give None —
    but ``0`` is a real reading and is preserved.

    Rejects, as a typed 400 rather than a 500:
      * free text, containers, and thousands-separated strings;
      * fractional values — whole numbers are never silently truncated;
      * booleans — ``int(True) == 1`` would silently invent a reading;
      * ``nan`` / ``inf`` / ``1e400``, which float() accepts and int() then
        raises ValueError **or OverflowError** on;
      * values outside the column's 32-bit range.
    """
    if value is None or value == '':
        return None
    parsed = parse_amount(value, error)
    if parsed != parsed.to_integral_value() or not (_INT32_MIN <= parsed <= _INT32_MAX):
        raise InvalidFieldError(INVALID_NUMBER_KEY, error)
    return int(parsed)


def parse_optional_amount(value, error='Amount must be a number'):
    """Nullable decimal column -> Decimal or None, or InvalidFieldError.

    ``parse_amount`` is for a column that must hold a number; this is for one the
    user may legitimately leave blank (coverage_amount, deductible, labor_cost…),
    where '' and None mean "not provided" rather than "invalid".
    """
    if value is None or value == '':
        return None
    return parse_amount(value, error)


def parse_currency_code(value, error='Currency must be a recognized code'):
    """Recognized ISO currency code, uppercased, or a localized field error."""
    code = value.strip().upper() if isinstance(value, str) else ''
    if code not in CURRENCY_CODES:
        raise InvalidFieldError(INVALID_CURRENCY_KEY, error)
    return code


def invalid_field_response(exc):
    """Build the (payload, status) pair for an InvalidFieldError.

    Matches the shape the inline R2 guards return in routes/vehicles.py.
    """
    payload = {'error': exc.error, 'message_key': exc.message_key}
    if exc.field is not None:
        payload['field'] = exc.field
    return payload, 400
