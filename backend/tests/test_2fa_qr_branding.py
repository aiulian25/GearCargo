"""The 2FA QR carries the app mark — without becoming unscannable.

Putting artwork in the middle of a QR costs error-correction budget. If that
budget is overspent the symbol stops decoding, and the failure is invisible
server-side: setup returns 200, the image looks fine, and the user simply
cannot enrol. These tests pin the properties that keep it readable, and the
fallback that keeps enrolment working when the artwork cannot be loaded at all.
"""

import base64
import io

import pyotp
import pytest
from PIL import Image

# Imported inside the tests that need them: the endpoint-level tests below must
# still run (and fail) against a build that has no branding at all, rather than
# collapsing into a collection error.

SETUP_URL = '/api/auth/2fa/setup'
PASSWORD = 'StrongPass123!'

# ERROR_CORRECT_H recovers 30% of the symbol. Staying well inside that is what
# makes the mark safe; the pad is the larger of the two squares drawn.
MAX_SAFE_AREA_FRACTION = 0.10


def _decoded_png(data_uri):
    assert data_uri.startswith('data:image/png;base64,')
    raw = base64.b64decode(data_uri.split(',', 1)[1])
    return Image.open(io.BytesIO(raw))


def test_setup_returns_a_png_carrying_the_mark(app, client, user, auth_headers):
    response = client.post(SETUP_URL, headers=auth_headers(user.id))

    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    image = _decoded_png(payload['qr_code'])
    assert image.size[0] == image.size[1]

    # The centre must no longer be plain QR: a run of identical white/black
    # modules through the middle would mean the mark never landed.
    width = image.size[0]
    centre = image.convert('RGB').crop((
        int(width * 0.45), int(width * 0.45), int(width * 0.55), int(width * 0.55)))
    assert len(set(centre.getdata())) > 2, 'centre looks like bare QR modules'


def test_the_mark_stays_inside_the_error_correction_budget():
    """The guard that keeps the symbol decodable."""
    from app.routes.auth import QR_LOGO_PAD_RATIO, QR_LOGO_RATIO

    assert QR_LOGO_PAD_RATIO >= QR_LOGO_RATIO, 'the pad must enclose the mark'
    assert QR_LOGO_PAD_RATIO ** 2 < MAX_SAFE_AREA_FRACTION, (
        f'mark pad covers {QR_LOGO_PAD_RATIO ** 2:.1%} of the symbol')


def test_setup_uses_high_error_correction(app, client, user, auth_headers):
    """H is what pays for the obscured modules; M would not."""
    import qrcode

    response = client.post(SETUP_URL, headers=auth_headers(user.id))
    assert response.status_code == 200

    # A version-1 symbol at H holds less data, so the rendered symbol must be
    # larger than the same URI would produce at the default correction level.
    uri = pyotp.TOTP(response.get_json()['secret']).provisioning_uri(
        name=user.email, issuer_name='GearCargo')
    low = qrcode.QRCode(version=1, box_size=10, border=5)
    low.add_data(uri)
    low.make(fit=True)

    high = qrcode.QRCode(version=1, box_size=10, border=5,
                         error_correction=qrcode.constants.ERROR_CORRECT_H)
    high.add_data(uri)
    high.make(fit=True)

    assert high.version > low.version, 'setup should be rendering at ERROR_CORRECT_H'
    assert _decoded_png(response.get_json()['qr_code']).size[0] == \
        high.make_image().size[0]


def test_the_secret_behind_the_branded_qr_still_enrols(app, client, user, auth_headers):
    """End to end: the code a user types after scanning must be accepted."""
    setup = client.post(SETUP_URL, headers=auth_headers(user.id))
    secret = setup.get_json()['secret']

    verify = client.post('/api/auth/2fa/verify',
                         json={'code': pyotp.TOTP(secret).now()},
                         headers=auth_headers(user.id))

    assert verify.status_code == 200, verify.get_json()


def test_an_unreadable_mark_never_blocks_enrolment(app, monkeypatch):
    """A mark that cannot be found anywhere must degrade to a plain QR, not a 500.

    The resolver looks in the deployed static folder AND in the copy packaged
    with the backend, so emptying one is not enough — patch the resolver itself,
    which is the contract the caller depends on.
    """
    import qrcode
    import app.routes.auth as auth_module

    monkeypatch.setattr(auth_module, 'app_mark_path', lambda filename: None)

    with app.app_context():
        plain = qrcode.make('otpauth://totp/x').convert('RGB')

        result = auth_module._overlay_app_mark(plain)

        assert result.size == plain.size
        assert list(result.getdata()) == list(plain.getdata()), 'should be untouched'


def test_the_mark_is_found_without_a_built_frontend(app, monkeypatch):
    """CI and a fresh clone have no backend/static — the packaged copy covers it."""
    from app.utils.branding import app_mark_path

    with app.app_context():
        monkeypatch.setattr(app, 'static_folder', '/nonexistent/path')

        assert app_mark_path('logo-192.png'), 'no packaged fallback for the mark'


def test_the_mark_is_centred_and_no_bigger_than_the_pad(app):
    """An off-centre mark would eat into a finder pattern and stop the scan."""
    import qrcode
    from PIL import ImageChops
    from app.routes.auth import QR_LOGO_PAD_RATIO, _overlay_app_mark

    with app.app_context():
        plain = qrcode.make('otpauth://totp/centred').convert('RGB')
        marked = _overlay_app_mark(plain)

    changed = ImageChops.difference(plain, marked).convert('L').point(
        lambda pixel: 255 if pixel > 8 else 0).getbbox()
    assert changed, 'the mark did not alter the QR at all'

    width, height = marked.size
    centre_x = (changed[0] + changed[2]) / 2
    centre_y = (changed[1] + changed[3]) / 2
    tolerance = width * 0.02
    assert abs(centre_x - width / 2) < tolerance, f'mark off-centre: x={centre_x}'
    assert abs(centre_y - height / 2) < tolerance, f'mark off-centre: y={centre_y}'

    # And it stays within the pad it is supposed to occupy.
    assert (changed[2] - changed[0]) <= width * QR_LOGO_PAD_RATIO + 2
