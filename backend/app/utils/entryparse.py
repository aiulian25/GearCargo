"""Parsing of user-supplied dates and amounts on entry write paths.

R2 guarded the vehicle/identity routes with an inline try/except per field. The
tax and parking routes parse fifteen date fields plus an amount between them, so
they raise a typed error instead and the handler catches once — same 400 payload
shape (``error`` + ``message_key``) the inline guards return, so clients cannot
tell which style produced it.

The message keys already exist in en/ro/es under the ``validation.*`` namespace.
"""

from datetime import datetime

INVALID_DATE_KEY = 'validation.invalidDate'
INVALID_NUMBER_KEY = 'validation.invalidNumber'


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


def parse_amount(value):
    """Money amount -> float, or InvalidFieldError."""
    try:
        return float(value)
    except (TypeError, ValueError):
        raise InvalidFieldError(INVALID_NUMBER_KEY, 'Amount must be a number')


def invalid_field_response(exc):
    """Build the (payload, status) pair for an InvalidFieldError.

    Matches the shape the inline R2 guards return in routes/vehicles.py.
    """
    return {'error': exc.error, 'message_key': exc.message_key}, 400
