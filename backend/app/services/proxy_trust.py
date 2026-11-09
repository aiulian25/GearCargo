"""Which reverse-proxy hops may set the client address (S11/GC-104).

Flask-Limiter, BlockedIP/BlockedDevice, ActivityLog, the security audit log and
sessions all read request.remote_addr. This middleware decides whether
X-Forwarded-For, -Proto, -Host and -Prefix may set request.remote_addr, scheme,
host and script root. Code that reads those headers itself is not covered, for
example auth._request_host() (X-Forwarded-Host, for the ADMIN_DOMAIN/USER_DOMAIN
login policy) and Talisman (X-Forwarded-Proto, for HSTS).
"""
import ipaddress

from werkzeug.middleware.proxy_fix import ProxyFix

AUTOMATIC_PROXY_TRUST = 'auto'
AUTOMATIC_TRUSTED_HOPS = 1
PEER_ADDRESS_KEY = 'REMOTE_ADDR'
FORWARDED_FOR_KEY = 'HTTP_X_FORWARDED_FOR'
INVALID_SETTING_MESSAGE = 'TRUSTED_PROXY_COUNT must be auto or a whole number of proxies (0 or more), not %r'
# The log messages carry no address: RedactionFilter would rewrite any IP literal.
STARTUP_MESSAGE = (
    'Proxy trust: TRUSTED_PROXY_COUNT=%s (auto = one hop, only from a non-public peer such as '
    'loopback, Docker, the LAN or Tailscale; N = N hops from every peer; 0 = none).'
)
IGNORED_FORWARDED_FOR_WARNING = (
    'TRUSTED_PROXY_COUNT=%s: X-Forwarded-For arrived from an address not trusted as a proxy and '
    'was ignored; the connecting address is used as the client IP. With no proxy in front, a '
    'client tried to choose its own address and nothing needs changing. If a reverse proxy or CDN '
    'fronts GearCargo, set TRUSTED_PROXY_COUNT to the number of proxies in front of it (auto '
    'covers one proxy on this host, a Docker network, the LAN or Tailscale).'
)
UNPROXIED_PUBLIC_PEER_WARNING = (
    'TRUSTED_PROXY_COUNT=%s, but a public address connected without X-Forwarded-For: the app port '
    'is reachable without the proxy, and on that path a client can choose the IP used for rate '
    'limits, IP blocks and the audit log. Limit the app port to the proxy. If the proxy runs on '
    'this host, a Docker network, the LAN or Tailscale, TRUSTED_PROXY_COUNT=auto also closes this '
    'path; with no proxy at all, set 0.'
)


def parse_trusted_proxy_count(configured):
    setting = str(configured).strip().lower()
    if not setting or setting == AUTOMATIC_PROXY_TRUST:
        return AUTOMATIC_PROXY_TRUST
    if not setting.isdecimal():
        raise ValueError(INVALID_SETTING_MESSAGE % (configured,))
    return int(setting)


def is_non_public_address(address):
    # ponytail: "a non-public peer is our proxy" heuristic. NAT that gives clients a private
    # source (rootless Docker, Docker Desktop, Docker's userland proxy for IPv6 clients or with
    # iptables off) and the routable ranges ipaddress calls non-global (6to4, Teredo) defeat it.
    # There, set 0 when no proxy is used, or limit the app port to the proxy when one is (a count
    # above 0 trusts every peer); the upgrade is a configured list of proxy networks.
    try:
        peer = ipaddress.ip_address(address)
    except ValueError:
        return False  # empty or unreadable (e.g. a unix socket): never trusted as a proxy
    return not peer.is_global


class ProxyTrustMiddleware:
    """Apply ProxyFix only to a request whose peer the setting trusts as a proxy."""

    def __init__(self, wsgi_app, trusted_proxy_count, logger):
        self.trusted_proxy_count = trusted_proxy_count
        self.automatic = trusted_proxy_count == AUTOMATIC_PROXY_TRUST
        hops = AUTOMATIC_TRUSTED_HOPS if self.automatic else trusted_proxy_count
        self.direct_app = wsgi_app
        self.proxied_app = ProxyFix(wsgi_app, x_for=hops, x_proto=hops, x_host=hops, x_prefix=hops)
        self.logger = logger
        self.issued_warnings = set()

    def __call__(self, environ, start_response):
        peer_may_be_proxy = is_non_public_address(environ.get(PEER_ADDRESS_KEY))
        carries_forwarded_for = bool(environ.get(FORWARDED_FOR_KEY))
        trusted = peer_may_be_proxy if self.automatic else self.trusted_proxy_count > 0
        if carries_forwarded_for and not trusted:
            self.warn_once(IGNORED_FORWARDED_FOR_WARNING)
        if trusted and not peer_may_be_proxy and not carries_forwarded_for:
            self.warn_once(UNPROXIED_PUBLIC_PEER_WARNING)
        selected_app = self.proxied_app if trusted else self.direct_app
        return selected_app(environ, start_response)

    def warn_once(self, message):
        # ponytail: once per middleware instance, i.e. once per worker process (sync workers fork
        # after preload and are recycled at max_requests); share the set across processes if the
        # repeated lines ever matter.
        if message in self.issued_warnings:
            return
        self.issued_warnings.add(message)
        self.logger.warning(message, self.trusted_proxy_count)


def install_proxy_trust(app):
    trusted_proxy_count = parse_trusted_proxy_count(app.config.get('TRUSTED_PROXY_COUNT', AUTOMATIC_PROXY_TRUST))
    app.wsgi_app = ProxyTrustMiddleware(app.wsgi_app, trusted_proxy_count, app.logger)
    app.logger.info(STARTUP_MESSAGE, trusted_proxy_count)
