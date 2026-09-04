"""Parsing of user-supplied dates and amounts on entry write paths.

R2 guarded the vehicle/identity routes with an inline try/except per field. The
tax and parking routes parse fifteen date fields plus an amount between them, so
they raise a typed error instead and the handler catches once — same 400 payload
shape (``error`` + ``message_key``) the inline guards return, so clients cannot
tell which style produced it.

The message keys already exist in en/ro/es under the ``validation.*`` namespace.
"""

from datetime import datetime

REQUIRED_FIELD_KEY = 'validation.required'
INVALID_DATE_KEY = 'validation.invalidDate'
INVALID_NUMBER_KEY = 'validation.invalidNumber'
INVALID_CURRENCY_KEY = 'validation.invalidCurrency'


class InvalidFieldError(ValueError):
    """A user-supplied value that cannot be parsed. Carries its localization key."""

    def __init__(self, message_key, error='Invalid value'):
        super().__init__(error)
        self.message_key = message_key
        self.error = error


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
    """Money amount -> float, or InvalidFieldError."""
    try:
        return float(value)
    except (TypeError, ValueError):
        raise InvalidFieldError(INVALID_NUMBER_KEY, error)


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
      * booleans — ``int(True) == 1`` would silently invent a reading;
      * ``nan`` / ``inf`` / ``1e400``, which float() accepts and int() then
        raises ValueError **or OverflowError** on;
      * values outside the column's 32-bit range.
    """
    if value is None or value == '':
        return None
    # bool is a subclass of int, so this must precede the numeric conversion.
    if isinstance(value, bool):
        raise InvalidFieldError(INVALID_NUMBER_KEY, error)
    try:
        parsed = int(float(value))
    except (TypeError, ValueError, OverflowError):
        raise InvalidFieldError(INVALID_NUMBER_KEY, error)
    if not (_INT32_MIN <= parsed <= _INT32_MAX):
        raise InvalidFieldError(INVALID_NUMBER_KEY, error)
    return parsed


def parse_optional_amount(value, error='Amount must be a number'):
    """Nullable money column -> float or None, or InvalidFieldError.

    ``parse_amount`` is for a column that must hold a number; this is for one the
    user may legitimately leave blank (coverage_amount, deductible, labor_cost…),
    where '' and None mean "not provided" rather than "invalid".
    """
    if value is None or value == '':
        return None
    return parse_amount(value, error)


def parse_currency_code(value, error='Currency must be a 3-letter code'):
    """ISO-4217-shaped currency code, upper-cased, or InvalidFieldError.

    Entry.currency is String(3) and InsurancePolicy.currency is String(3), so a
    longer value is a guaranteed DataError at flush — a 500 for input we can see
    is unstorable. Normalising to upper-case also keeps the FX lookups (which
    upper-case before comparing) consistent with what is stored.
    """
    code = str(value or '').strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise InvalidFieldError(INVALID_CURRENCY_KEY, error)
    return code


def invalid_field_response(exc):
    """Build the (payload, status) pair for an InvalidFieldError.

    Matches the shape the inline R2 guards return in routes/vehicles.py.
    """
    return {'error': exc.error, 'message_key': exc.message_key}, 400
