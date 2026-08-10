"""Regression tests for M2: timeline pagination must not duplicate entries or
drop insurance policies.

The old `get_vehicle_timeline` spliced insurance into every entry page with
buffer/offset arithmetic (`db_offset = (page-1)*per_page - insurance_total`,
`db_limit = per_page + len(insurance)`). Two bugs fell out of it:

  * page 2+ re-served entries already shown on page 1 (the offset was clamped
    back by insurance_total), and
  * policies that sorted past page 1's cut were never emitted again.

The fix paginates ENTRIES ONLY (plain offset/limit) and ships the full, small
insurance set once under a top-level ``insurance`` key on page 1 of the ``all``
view, which the client merges in. These tests pin that contract.

NB: the endpoint clamps per_page to a minimum of 10, so a real multi-page
dataset needs > 10 entries — we seed 25 and page by 10.
"""

from datetime import date

from app import db
from app.models import User
from app.models.fuel import FuelEntry
from app.models.vehicle import Vehicle
from app.models.insurance import InsurancePolicy

PER_PAGE = 10          # the endpoint's minimum; smaller values are clamped up
N_ENTRIES = 25         # → 3 entry pages (10/10/5)
N_POLICIES = 3


def _seed(n_entries=N_ENTRIES, n_policies=N_POLICIES):
    """Create a user + vehicle, `n_entries` fuel entries with distinct
    descending dates, and `n_policies` insurance policies whose start dates sit
    OLDER than every entry (the arrangement that made the old code both drop
    them and re-serve entries). Returns (user_id, vehicle_id, entry_ids,
    policy_ids)."""
    u = User(username="tluser", email="tl@example.com", is_active=True)
    u.set_password("StrongPass123!")
    db.session.add(u)
    db.session.commit()

    v = Vehicle(user_id=u.id, name="Timeline Car")
    db.session.add(v)
    db.session.commit()

    entry_ids = []
    for i in range(n_entries):
        # e[0] newest … e[n-1] oldest. FuelEntry is the polymorphic subclass for
        # type='fuel'; a bare Entry(type='fuel') would mis-map subclass columns.
        e = FuelEntry(
            title=f"Fill {i}",
            description=f"Fill {i}",
            amount=50 + i,
            date=date(2026, 1, n_entries - i),  # 25,24,…,1 → strictly descending
            user_id=u.id,
            vehicle_id=v.id,
        )
        db.session.add(e)
        db.session.commit()
        entry_ids.append(e.id)

    policy_ids = []
    for i in range(n_policies):
        p = InsurancePolicy(
            vehicle_id=v.id,
            user_id=u.id,
            provider=f"Provider {i}",
            premium=100 + i,
            payment_frequency="annual",
            start_date=date(2025, 6, i + 1),   # older than all 2026 entries
            end_date=date(2026, 6, i + 1),
        )
        db.session.add(p)
        db.session.commit()
        policy_ids.append(p.id)

    return u.id, v.id, entry_ids, policy_ids


def _get(client, headers, vid, page, per_page=PER_PAGE, type_="all"):
    resp = client.get(
        f"/api/vehicles/{vid}/timeline?page={page}&per_page={per_page}&type={type_}",
        headers=headers,
    )
    assert resp.status_code == 200, (resp.status_code, resp.data[:200])
    return resp.get_json()


def test_no_duplicate_entries_across_pages(app, client, auth_headers):
    """Walking every page of the combined feed yields each entry exactly once
    (the old code re-served page-1 entries on later pages)."""
    with app.app_context():
        uid, vid, entry_ids, _ = _seed()
    headers = auth_headers(uid)

    seen, page = [], 1
    while True:
        data = _get(client, headers, vid, page)
        seen += [r["id"] for r in data["entries"] if r["type"] != "insurance"]
        if not data["has_next"]:
            break
        page += 1
        assert page < 20  # runaway guard

    assert len(seen) == len(set(seen)) == N_ENTRIES   # no dupes, none dropped
    assert set(seen) == set(entry_ids)


def test_all_policies_delivered_once_on_page_one(app, client, auth_headers):
    """Every policy ships on page 1 under `insurance`, and only there (the old
    code emitted policies inline and dropped those past page 1's cut)."""
    with app.app_context():
        uid, vid, _, policy_ids = _seed()
    headers = auth_headers(uid)

    p1 = _get(client, headers, vid, 1)
    assert "insurance" in p1
    assert {r["id"] for r in p1["insurance"]} == set(policy_ids)
    assert all(r["type"] == "insurance" for r in p1["insurance"])
    # page-1 `entries` are pure entries — no insurance spliced in
    assert all(r["type"] != "insurance" for r in p1["entries"])

    p2 = _get(client, headers, vid, 2)
    assert "insurance" not in p2  # never repeated on later pages
    assert all(r["type"] != "insurance" for r in p2["entries"])


def test_total_counts_entries_plus_insurance(app, client, auth_headers):
    """`total` still reflects entries + policies (the displayed count)."""
    with app.app_context():
        uid, vid, _, _ = _seed()
    data = _get(client, auth_headers(uid), vid, 1)
    assert data["total"] == N_ENTRIES + N_POLICIES  # 25 + 3


def test_has_next_tracks_entries_only(app, client, auth_headers):
    """Navigation is driven by entries (all insurance is on page 1), so the
    page count is ceil(entry_total / per_page) = ceil(25/10) = 3."""
    with app.app_context():
        uid, vid, _, _ = _seed()
    headers = auth_headers(uid)
    assert _get(client, headers, vid, 1)["has_next"] is True
    assert _get(client, headers, vid, 2)["has_next"] is True
    assert _get(client, headers, vid, 3)["has_next"] is False


def test_filtered_view_has_no_insurance_key(app, client, auth_headers):
    """A type filter (e.g. fuel) paginates only that type and carries no
    insurance payload."""
    with app.app_context():
        uid, vid, _, _ = _seed()
    data = _get(client, auth_headers(uid), vid, 1, type_="fuel")
    assert "insurance" not in data
    assert data["total"] == N_ENTRIES        # entries only, no policies counted
    assert all(r["type"] == "fuel" for r in data["entries"])


def test_insurance_only_view_paginates_policies(app, client, auth_headers):
    """The dedicated insurance view still paginates the policy list in
    `entries` (unchanged branch) and exposes no separate `insurance` key."""
    with app.app_context():
        uid, vid, _, policy_ids = _seed()
    data = _get(client, auth_headers(uid), vid, 1, type_="insurance")
    assert "insurance" not in data
    assert data["total"] == N_POLICIES
    assert {r["id"] for r in data["entries"]} == set(policy_ids)
    assert all(r["type"] == "insurance" for r in data["entries"])
