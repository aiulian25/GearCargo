"""R10: `datetime.utcnow()` is gone, replaced by `utc_naive_now()`.

utcnow() is deprecated since Python 3.12 and scheduled for removal. The
replacement must keep NAIVE-UTC semantics: the db.DateTime columns are tz-naive,
so returning an aware datetime would reintroduce the naive/aware comparison
TypeError that broke every token-verification path in round 1 (C1).
"""

import pathlib
import re
from datetime import datetime, timezone

from app.utils.timeutils import utc_naive_now

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def test_returns_naive_utc():
    now = utc_naive_now()
    assert now.tzinfo is None, "must stay naive — aware values re-open the C1 bug class"
    # Matches what datetime.utcnow() produced, within clock tolerance.
    reference = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((reference - now).total_seconds()) < 5


def test_usable_as_a_column_default_callable():
    """SQLAlchemy stores the function itself (default=utc_naive_now)."""
    assert callable(utc_naive_now)
    assert isinstance(utc_naive_now(), datetime)


def test_no_datetime_utcnow_left_in_backend_sources():
    """Guard: keep the deprecated call from creeping back in."""
    pattern = re.compile(r"\bdatetime\.utcnow\b")
    offenders = []
    for path in list((BACKEND / "app").rglob("*.py")) + list((BACKEND / "tests").rglob("*.py")):
        # The helper's docstring and this guard both name the API they replace.
        if "__pycache__" in path.parts or path.name in ("timeutils.py", pathlib.Path(__file__).name):
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(BACKEND)))
    assert not offenders, f"use utc_naive_now() instead: {offenders}"
