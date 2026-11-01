"""RT1: the PUBLIC shared-report surface.

`/api/reports/shared/<token>` and `/shared/<token>/pdf` are unauthenticated and
serve one user's financial aggregates to anyone holding the link, yet had no
tests. These pin the whole lifecycle — issue, view, revoke, expire — plus the
guarantees that make the link safe to hand out: only a SHA-256 hash is stored,
the raw token is shown exactly once, and a revoked/expired/orphaned link stops
resolving.
"""

from datetime import timedelta

from app import db
from app.models import User
from app.models.report_share import ReportShare
from app.models.vehicle import Vehicle
from app.utils.timeutils import utc_naive_now

SHARES_URL = "/api/reports/shares"
PASSWORD = "StrongPass123!"


def _owner(email="share@example.com"):
    u = User(username=email.split("@")[0], email=email, is_active=True, currency="GBP")
    u.set_password(PASSWORD)
    db.session.add(u)
    db.session.commit()
    db.session.add(Vehicle(user_id=u.id, name="Shared Car", make="VW", model="Golf"))
    db.session.commit()
    return u.id


def _create_share(client, uid, auth_headers, **payload):
    body = {"period": "current_month", **payload}
    resp = client.post(SHARES_URL, json=body, headers=auth_headers(uid))
    assert resp.status_code == 201, resp.data[:200]
    return resp.get_json()


# --- happy path ---------------------------------------------------------------

def test_share_link_serves_the_report_without_auth(app, client, auth_headers):
    with app.app_context():
        uid = _owner()
    share = _create_share(client, uid, auth_headers, label="Q3")

    # No Authorization header at all — this is the point of a share link.
    resp = client.get(f"/api/reports/shared/{share['token']}")
    assert resp.status_code == 200, resp.data[:200]
    body = resp.get_json()
    assert body["label"] == "Q3"
    for key in ("period_label", "entry_counts", "totals", "currency"):
        assert key in body


def test_raw_token_is_never_persisted(app, client, auth_headers):
    """Only the SHA-256 hash is stored, so a DB leak yields no working link."""
    with app.app_context():
        uid = _owner("share2@example.com")
    share = _create_share(client, uid, auth_headers)
    raw = share["token"]

    with app.app_context():
        db.session.remove()
        row = ReportShare.query.filter_by(token_hash=ReportShare.hash_token(raw)).first()
        assert row is not None
        assert row.token_hash != raw
        assert len(row.token_hash) == 64
        # The stored hash must not itself work as a token.
    assert client.get(f"/api/reports/shared/{row.token_hash}").status_code == 404


def test_listing_shares_never_returns_raw_tokens(app, client, auth_headers):
    with app.app_context():
        uid = _owner("share3@example.com")
    raw = _create_share(client, uid, auth_headers)["token"]

    listed = client.get(SHARES_URL, headers=auth_headers(uid)).get_json()["shares"]
    assert listed and all(raw not in str(s.values()) for s in listed)


# --- revocation & expiry ------------------------------------------------------

def test_revoked_link_returns_410(app, client, auth_headers):
    with app.app_context():
        uid = _owner("share4@example.com")
    share = _create_share(client, uid, auth_headers)
    assert client.get(f"/api/reports/shared/{share['token']}").status_code == 200

    assert client.delete(f"{SHARES_URL}/{share['id']}", headers=auth_headers(uid)).status_code == 200

    resp = client.get(f"/api/reports/shared/{share['token']}")
    assert resp.status_code == 410, resp.data[:200]
    assert resp.get_json()["status"] == "revoked"


def test_expired_link_returns_410(app, client, auth_headers):
    with app.app_context():
        uid = _owner("share5@example.com")
    share = _create_share(client, uid, auth_headers)

    with app.app_context():
        row = db.session.get(ReportShare, share["id"])
        row.expires_at = utc_naive_now() - timedelta(minutes=1)
        db.session.commit()

    resp = client.get(f"/api/reports/shared/{share['token']}")
    assert resp.status_code == 410, resp.data[:200]
    assert resp.get_json()["status"] == "expired"


def test_pdf_endpoint_honours_revocation_too(app, client, auth_headers):
    """The PDF route is a second public entry point — it must not outlive a revoke."""
    with app.app_context():
        uid = _owner("share6@example.com")
    share = _create_share(client, uid, auth_headers)
    client.delete(f"{SHARES_URL}/{share['id']}", headers=auth_headers(uid))

    assert client.get(f"/api/reports/shared/{share['token']}/pdf").status_code == 410


# --- rejection paths ----------------------------------------------------------

def test_garbage_and_short_tokens_return_404(app, client):
    assert client.get("/api/reports/shared/not-a-real-token-but-long-enough").status_code == 404
    assert client.get("/api/reports/shared/short").status_code == 404


def test_deactivated_owner_disables_the_link(app, client, auth_headers):
    """Disabling an account must take its public links down with it."""
    with app.app_context():
        uid = _owner("share7@example.com")
    share = _create_share(client, uid, auth_headers)
    assert client.get(f"/api/reports/shared/{share['token']}").status_code == 200

    with app.app_context():
        db.session.get(User, uid).is_active = False
        db.session.commit()

    resp = client.get(f"/api/reports/shared/{share['token']}")
    assert resp.status_code == 404, resp.data[:200]


def test_another_user_cannot_revoke_your_share(app, client, auth_headers):
    with app.app_context():
        owner = _owner("share8@example.com")
        attacker = _owner("share9@example.com")
    share = _create_share(client, owner, auth_headers)

    assert client.delete(f"{SHARES_URL}/{share['id']}",
                         headers=auth_headers(attacker)).status_code == 404
    # Still live for the real owner.
    assert client.get(f"/api/reports/shared/{share['token']}").status_code == 200


def test_creating_a_share_requires_authentication(app, client):
    assert client.post(SHARES_URL, json={"period": "current_month"}).status_code == 401

# GC-006: public representation and PDF disclosure must stay identical.
from datetime import date
from io import BytesIO
import json
import os
from pathlib import Path
import re

import pytest
from pypdf import PdfReader

from app.models import (Attachment, FuelEntry, ServiceEntry, RepairEntry, TaxEntry,
                        ParkingEntry, InsurancePolicy)


PRIVATE_MARKERS = (
    'private_owner_gc006', 'private-owner-gc006@example.invalid',
    'PRIVATE_FIRST_gc006', 'PRIVATE_LAST_gc006', 'GC006-PLATE-X', 'GC006VINSECRET123',
    'PRIVATE_NOTE_gc006', 'PRIVATE_REPAIR_gc006', 'PRIVATE_LOCATION_gc006',
    'PRIVATE_PROVIDER_gc006', 'PRIVATE_POLICY_gc006', 'PRIVATE_ATTACHMENT_gc006',
    'PRIVATE_OCR_gc006', 'PRIVATE_PATH_gc006', 'PRIVATE_PHOTO_gc006',
    'PRIVATE_UNSELECTED_gc006', 'PRIVATE_OTHER_OWNER_gc006',
)


@pytest.fixture
def private_canary_report(app, user, client, auth_headers, monkeypatch):
    monkeypatch.setattr('app.services.currency.get_rates_cached', lambda *args: {'EUR': 1, 'GBP': .8})
    user.username, user.email = PRIVATE_MARKERS[:2]
    user.first_name, user.last_name = PRIVATE_MARKERS[2:4]
    user.currency = 'GBP'
    vehicle = Vehicle(user_id=user.id, name='Șofer & Público <Family>', make='Ford', model='Focus',
                      year=1987, license_plate='GC006-PLATE-X', vin='GC006VINSECRET123',
                      photo='/uploads/vehicles/PRIVATE_PHOTO_gc006.jpg')
    db.session.add(vehicle); db.session.flush()
    common = {'user_id': user.id, 'vehicle_id': vehicle.id, 'date': date(2026, 6, 5),
              'currency': 'GBP', 'notes': 'PRIVATE_NOTE_gc006'}
    db.session.add_all([
        FuelEntry(**common, amount=11.11, total_price=11.11, liters=10, price_per_liter=1.111),
        ServiceEntry(**common, amount=22.22, service_type='oil_change'),
        RepairEntry(**common, amount=33.33, description='PRIVATE_REPAIR_gc006'),
        TaxEntry(**common, amount=44.44, tax_type='road_tax'),
        ParkingEntry(**common, amount=55.55, location='PRIVATE_LOCATION_gc006'),
        InsurancePolicy(user_id=user.id, vehicle_id=vehicle.id, currency='GBP', premium=66.66,
            provider='PRIVATE_PROVIDER_gc006', policy_number='PRIVATE_POLICY_gc006',
            start_date=date(2026, 6, 5), end_date=date(2026, 6, 30), notes='PRIVATE_NOTE_gc006'),
        Attachment(user_id=user.id, vehicle_id=vehicle.id, filename='PRIVATE_ATTACHMENT_gc006.pdf',
            original_filename='PRIVATE_ATTACHMENT_gc006.pdf', filepath='/PRIVATE_PATH_gc006/document.pdf',
            ocr_text='PRIVATE_OCR_gc006', description='PRIVATE_NOTE_gc006'),
    ])
    excluded = Vehicle(user_id=user.id, name='PRIVATE_UNSELECTED_gc006')
    other = User(username='other_report_owner', email='other-report@example.invalid', password_hash='synthetic')
    db.session.add_all([excluded, other]); db.session.flush()
    foreign = Vehicle(user_id=other.id, name='PRIVATE_OTHER_OWNER_gc006')
    db.session.add(foreign)
    db.session.add(ServiceEntry(user_id=user.id, vehicle_id=excluded.id, date=date(2026, 6, 5),
                                currency='GBP', amount=9999))
    db.session.commit()
    share = _create_share(client, user.id, auth_headers, vehicle_ids=[vehicle.id],
                          period='custom', year=2026, month=6, label='Summer summary')
    return {'share': share, 'owner_id': user.id, 'vehicle_id': vehicle.id, 'foreign_id': foreign.id}


def public_pdf(client, token):
    response = client.get(f'/api/reports/shared/{token}/pdf')
    assert response.status_code == 200, response.data[:300]
    reader = PdfReader(BytesIO(response.data))
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    return response, reader, text


def test_public_pdf_contains_only_shared_aggregates(app, client, user, auth_headers, private_canary_report):
    token = private_canary_report['share']['token']
    body = client.get(f'/api/reports/shared/{token}').json
    response, reader, text = public_pdf(client, token)
    public_values = json.dumps(body, ensure_ascii=False)
    metadata = str(dict(reader.metadata or {}))
    for marker in (*PRIVATE_MARKERS, token):
        assert marker not in public_values
        assert marker not in text
        assert marker not in metadata
        assert marker not in str(response.headers)
    assert body['vehicles'] == [{'name': 'Șofer & Público <Family>', 'make': 'Ford', 'model': 'Focus'}]
    assert body['entry_counts']['total'] == 6
    assert body['totals']['grand_total'] == pytest.approx(233.31)
    assert body['period_label'] in text and body['start_date'] in text and body['end_date'] in text
    assert body['label'] in text and body['currency'] in text and 'Șofer & Público <Family>' in text
    for category in ('fuel', 'service', 'repair', 'tax', 'parking', 'insurance'):
        assert re.search(r'\b1\s+' + re.escape(f'{body["totals"][category]:,.2f}'), text), category
    assert '233.31' in text and re.search(r'Grand total\s+6\s+233\.31', text)
    assert reader.metadata.author == 'GearCargo'
    assert reader.metadata.title == 'Shared Expense Report'
    assert not reader.attachments
    assert reader.xmp_metadata is None
    assert not reader.trailer['/Root'].get('/OpenAction')
    assert all(not page.get('/Annots') for page in reader.pages)
    assert 'GearCargo_Shared_Report_2026-06-01_2026-06-30.pdf' in response.headers['Content-Disposition']
    private = client.post('/api/reports/generate', headers=auth_headers(user.id),
        json={'vehicle_ids': [private_canary_report['vehicle_id']], 'period': 'custom', 'year': 2026, 'month': 6})
    assert private.status_code == 200
    private_text = '\n'.join(p.extract_text() or '' for p in PdfReader(BytesIO(private.data)).pages)
    assert user.email in private_text and 'GC006-PLATE-X' in private_text
    if os.environ.get('GC_PUBLIC_PDF_OUTPUT_DIR'):
        folder = Path(os.environ['GC_PUBLIC_PDF_OUTPUT_DIR']); folder.mkdir(parents=True, exist_ok=True)
        (folder/'public-aggregate.pdf').write_bytes(response.data)


@pytest.mark.parametrize('suffix', ['', '/pdf'])
@pytest.mark.parametrize('state,status', [('revoked',410), ('expired',410), ('inactive',404), ('invalid',404)])
def test_public_representation_access_checks_match(app, client, private_canary_report, suffix, state, status):
    share = private_canary_report['share']
    row = db.session.get(ReportShare, share['id'])
    token = share['token']
    if state == 'revoked': row.revoked = True
    elif state == 'expired': row.expires_at = utc_naive_now() - timedelta(seconds=1)
    elif state == 'inactive': db.session.get(User, private_canary_report['owner_id']).is_active = False
    else: token = 'unknown-token-that-is-long-enough'
    db.session.commit()
    response = client.get(f'/api/reports/shared/{token}{suffix}')
    assert response.status_code == status, response.data[:200]
    assert response.mimetype == 'application/json'
    assert 'private-owner-gc006' not in response.get_data(as_text=True)


def test_both_public_representations_ignore_foreign_vehicle_ids(app, client, private_canary_report):
    share = private_canary_report['share']
    row = db.session.get(ReportShare, share['id'])
    row.vehicle_ids = [private_canary_report['vehicle_id'], private_canary_report['foreign_id']]
    db.session.commit()
    body = client.get(f'/api/reports/shared/{share["token"]}').json
    _, _, text = public_pdf(client, share['token'])
    assert body['vehicle_count'] == 1 and body['totals']['grand_total'] == pytest.approx(233.31)
    assert 'PRIVATE_OTHER_OWNER_gc006' not in json.dumps(body) and 'PRIVATE_OTHER_OWNER_gc006' not in text


def test_public_routes_do_not_use_private_pdf_renderer(client, private_canary_report, monkeypatch):
    from app.routes import reports
    def forbidden(*args, **kwargs):
        pytest.fail('Public endpoint called private PDF renderer')
    monkeypatch.setattr(reports, 'generate_pdf_report', forbidden)
    assert client.get(f'/api/reports/shared/{private_canary_report["share"]["token"]}').status_code == 200
    public_pdf(client, private_canary_report['share']['token'])


def test_future_summary_fields_do_not_expand_disclosure(client, private_canary_report, monkeypatch):
    from app.routes import reports
    original = reports._report_summary
    def with_private_fields(*args):
        data = original(*args)
        data['owner_email'] = 'FUTURE_PRIVATE_gc006'
        data['vehicles'][0]['license_plate'] = 'FUTURE_PRIVATE_gc006'
        data['entry_counts']['debug'] = 'FUTURE_PRIVATE_gc006'
        data['totals']['debug'] = 'FUTURE_PRIVATE_gc006'
        return data
    monkeypatch.setattr(reports, '_report_summary', with_private_fields)
    token = private_canary_report['share']['token']
    body = client.get(f'/api/reports/shared/{token}').json
    _, _, text = public_pdf(client, token)
    assert 'FUTURE_PRIVATE_gc006' not in json.dumps(body) and 'FUTURE_PRIVATE_gc006' not in text
    assert set(body) == {'basis', 'basis_label', 'as_of', 'period_label','start_date','end_date','vehicle_count','vehicles',
        'entry_counts','totals','currency','display_currency','converted','fx_applied','label','app_name','expires_at'}
    assert set(body['vehicles'][0]) == {'name','make','model'}


def test_shared_renderer_rejects_private_objects(user):
    from app.services.pdf_report_service import generate_shared_pdf_report, get_shared_report_filename
    with pytest.raises(TypeError): generate_shared_pdf_report(user)
    with pytest.raises(TypeError): get_shared_report_filename(user)


def test_public_free_text_is_literal_not_pdf_markup(app, client, private_canary_report):
    share = private_canary_report['share']
    label = '<link href="https://example.invalid/public">A & B</link>'
    db.session.get(ReportShare, share['id']).label = label
    db.session.commit()
    _, reader, text = public_pdf(client, share['token'])
    assert ''.join(label.split()) in ''.join(text.split())
    assert all(not page.get('/Annots') for page in reader.pages)


def test_shared_pdf_wraps_long_names_and_repeats_page_footers(app, client, user, private_canary_report):
    share = private_canary_report['share']
    row = db.session.get(ReportShare, share['id'])
    for index in range(28):
        db.session.add(Vehicle(user_id=user.id, name=f'Public {index} ' + 'long vehicle name ' * 4,
                              make='Make & Co', model='Model with a longer name'))
    row.vehicle_ids = None
    db.session.commit()
    _, reader, text = public_pdf(client, share['token'])
    assert len(reader.pages) > 1
    for index, page in enumerate(reader.pages, 1):
        assert f'Page {index}' in page.extract_text()
    for marker in PRIVATE_MARKERS[:-2]: assert marker not in text
    if os.environ.get('GC_PUBLIC_PDF_OUTPUT_DIR'):
        folder = Path(os.environ['GC_PUBLIC_PDF_OUTPUT_DIR'])
        folder.mkdir(parents=True, exist_ok=True)
        (folder/'public-multipage.pdf').write_bytes(reader.stream.getvalue())


def test_empty_expenses_keep_zero_counts_in_public_pdf(app, client, auth_headers):
    with app.app_context():
        uid = _owner('zero-report@example.invalid')
    share = _create_share(client, uid, auth_headers)
    body = client.get(f'/api/reports/shared/{share["token"]}').json
    _, _, text = public_pdf(client, share['token'])
    assert body['entry_counts']['total'] == body['totals']['grand_total'] == 0
    assert re.search(r'Grand total\s+0\s+0\.00', text)


@pytest.mark.parametrize('available', [True, False])
def test_public_pdf_currency_flags_match_json(client, private_canary_report, monkeypatch, available):
    rates = {'EUR': 1, 'GBP': .8} if available else {'EUR': 1}
    monkeypatch.setattr('app.services.currency.get_rates_cached', lambda *args: rates)
    row = ServiceEntry.query.filter_by(vehicle_id=private_canary_report['vehicle_id']).one()
    row.currency = 'EUR'; db.session.commit()
    token = private_canary_report['share']['token']
    body = client.get(f'/api/reports/shared/{token}').json
    _, _, text = public_pdf(client, token)
    assert body['fx_applied'] is True and body['converted'] is available
    assert f'{body["totals"]["grand_total"]:,.2f}' in text
    assert ('Partial totals:' in text) is (not available)
