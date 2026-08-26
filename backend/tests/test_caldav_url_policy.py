"""R9: CalDAV URL validation must not accept cloud-metadata endpoints.

`_host_is_private_or_local` treated link-local (169.254.0.0/16) as "a LAN host
where plaintext http is fine", so `http://169.254.169.254` — the AWS/GCP/Azure
metadata service — passed validation. backup.py's SSRF guard already blocks
those targets; the two policies now agree.

RFC-1918 / loopback stay allowed on purpose: this is self-hosted software and
users really do run Nextcloud/Radicale/Baikal on their LAN over plain http.

NOTE: unlike backup.py (SEC-01 resolve+validate+pin), CalDAV has no connect-time
IP validation, so a *hostname* that resolves to an internal address is still
reachable. That residual gap is recorded as a follow-up in the review report.
"""

import pytest

from app.services.calendar_service import _host_is_private_or_local, _is_allowed_caldav_url


# --- the metadata targets this step closes ------------------------------------

@pytest.mark.parametrize("url", [
    "http://169.254.169.254/",                 # AWS / GCP / Azure IMDS
    "https://169.254.169.254/",                # blocked for https too
    "http://169.254.169.254/latest/meta-data/",
    "http://metadata.google.internal/computeMetadata/v1/",   # by NAME
    "https://metadata.google.internal/",
    "http://metadata/",
    "http://100.100.100.200/",                 # Alibaba Cloud
    "http://[fe80::1]/",                       # IPv6 link-local
])
def test_metadata_endpoints_are_rejected(url):
    assert _is_allowed_caldav_url(url) is False, url


def test_link_local_is_not_treated_as_lan():
    assert _host_is_private_or_local("169.254.169.254") is False
    assert _host_is_private_or_local("fe80::1") is False


# --- deliberate self-hosted LAN support must survive --------------------------

@pytest.mark.parametrize("url", [
    "http://192.168.1.10/remote.php/dav/calendars/me/",   # RFC-1918
    "http://10.0.0.5/dav.php/calendars/me/",
    "http://172.16.4.4/",
    "http://127.0.0.1:5232/",                             # loopback (Radicale)
    "http://localhost:5232/",
    "http://nas.local/caldav/",
    "http://server.lan/dav/",
])
def test_lan_and_loopback_still_allowed_over_http(url):
    assert _is_allowed_caldav_url(url) is True, url


@pytest.mark.parametrize("host", ["192.168.1.10", "10.0.0.5", "127.0.0.1", "localhost"])
def test_private_hosts_still_classified_as_local(host):
    assert _host_is_private_or_local(host) is True


# --- unchanged baseline -------------------------------------------------------

def test_public_https_allowed_and_public_http_rejected():
    assert _is_allowed_caldav_url("https://caldav.fastmail.com/dav/") is True
    # Plaintext to a public host would leak credentials — still refused.
    assert _is_allowed_caldav_url("http://caldav.fastmail.com/dav/") is False


def test_non_http_schemes_and_empty_rejected():
    assert _is_allowed_caldav_url("file:///etc/passwd") is False
    assert _is_allowed_caldav_url("") is False
