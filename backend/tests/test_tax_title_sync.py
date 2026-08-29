"""Step 6 — editing a tax's type must carry its title along.

`create_tax_entry` derives `title` from `tax_type`, but the PUT alias map has no
`title` key, so an edited type left the old name behind everywhere `Entry.title`
is rendered. The visible symptom is the due feed, which builds its label as
`tx.title or tx.tax_type` (services/due.py:216) — so a road_tax renamed to
registration kept nagging as "road tax".

The expenses table is NOT affected: VehicleExpenses.jsx renders
`entry.tax_type || entry.title`, type first.
"""

from datetime import date, timedelta

from app import db
from app.models import Vehicle, TaxEntry
from app.services.due import build_due_items

TODAY = date.today()
TAXES_URL = '/api/taxes'


def _vehicle(user_id, name='Qashqai'):
    vehicle = Vehicle(user_id=user_id, name=name, make='Nissan', model='Qashqai')
    db.session.add(vehicle)
    db.session.commit()
    db.session.refresh(vehicle)
    return vehicle


def _tax(user_id, vehicle_id, **kwargs):
    fields = dict(
        user_id=user_id, vehicle_id=vehicle_id, date=TODAY, amount=15,
        currency='EUR', tax_type='road_tax', title='road_tax', status='paid',
    )
    fields.update(kwargs)
    entry = TaxEntry(**fields)
    db.session.add(entry)
    db.session.commit()
    db.session.refresh(entry)
    return entry


def _reload(app, entry_id):
    with app.app_context():
        db.session.remove()
        return db.session.get(TaxEntry, entry_id)


def test_editing_tax_type_updates_title(app, client, user, auth_headers):
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _tax(user.id, vehicle.id)
        entry_id = entry.id

    resp = client.put(f'{TAXES_URL}/{entry_id}', json={'tax_type': 'registration'},
                      headers=auth_headers(user.id))

    assert resp.status_code == 200, resp.data[:200]
    body = resp.get_json()['entry']
    assert body['tax_type'] == 'registration'
    assert body['title'] == 'registration'
    assert _reload(app, entry_id).title == 'registration'


def test_due_feed_shows_the_new_name(app, client, user, auth_headers):
    """The user-visible symptom, end to end."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _tax(user.id, vehicle.id, status='pending',
                     due_date=TODAY + timedelta(days=3))
        entry_id = entry.id

    client.put(f'{TAXES_URL}/{entry_id}', json={'tax_type': 'emissions'},
               headers=auth_headers(user.id))

    with app.app_context():
        db.session.remove()
        labels = [item['title'] for item in build_due_items(user.id)
                  if item['kind'] == 'tax']
        assert 'emissions' in labels
        assert 'road tax' not in labels, 'the due feed kept the old name'


def test_an_explicit_title_is_not_clobbered(app, client, user, auth_headers):
    """A caller that manages its own title keeps it."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _tax(user.id, vehicle.id, title='Annual road levy')
        entry_id = entry.id

    client.put(f'{TAXES_URL}/{entry_id}',
               json={'tax_type': 'registration', 'title': 'Annual road levy'},
               headers=auth_headers(user.id))

    entry = _reload(app, entry_id)
    assert entry.tax_type == 'registration'
    assert entry.title == 'Annual road levy'


def test_editing_other_fields_leaves_title_alone(app, client, user, auth_headers):
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _tax(user.id, vehicle.id, title='Custom label')
        entry_id = entry.id

    client.put(f'{TAXES_URL}/{entry_id}', json={'amount': 25, 'notes': 'x'},
               headers=auth_headers(user.id))

    entry = _reload(app, entry_id)
    assert entry.title == 'Custom label'
    assert float(entry.amount) == 25.0


def test_rejected_edit_does_not_change_the_title(app, client, user, auth_headers):
    """A 400 from the parse guards must not half-apply the title sync."""
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _tax(user.id, vehicle.id)
        entry_id = entry.id

    resp = client.put(f'{TAXES_URL}/{entry_id}',
                      json={'tax_type': 'registration', 'date': 'garbage'},
                      headers=auth_headers(user.id))

    assert resp.status_code == 400
    entry = _reload(app, entry_id)
    assert entry.title == 'road_tax'
    assert entry.tax_type == 'road_tax'


def test_cross_user_update_still_forbidden(app, client, user, auth_headers):
    from app.models import User
    with app.app_context():
        vehicle = _vehicle(user.id)
        entry = _tax(user.id, vehicle.id)
        entry_id = entry.id

        intruder = User(username='title-intruder',
                        email='title-intruder@example.com', is_active=True)
        intruder.set_password('StrongPass123!')
        db.session.add(intruder)
        db.session.commit()
        intruder_id = intruder.id

    resp = client.put(f'{TAXES_URL}/{entry_id}', json={'tax_type': 'registration'},
                      headers=auth_headers(intruder_id))
    assert resp.status_code == 404
    assert _reload(app, entry_id).title == 'road_tax'
