"""Trusted host validation with explicit IP-network entries."""
from ipaddress import ip_address, ip_network

from starlette.datastructures import Headers
from starlette.middleware.trustedhost import TrustedHostMiddleware


class NetworkTrustedHostMiddleware(TrustedHostMiddleware):
    def __init__(self, app, allowed_hosts=None, **kwargs):
        entries = list(allowed_hosts) if allowed_hosts is not None else ['*']
        self.networks = [ip_network(entry, strict=True) for entry in entries if '/' in entry]
        super().__init__(app, allowed_hosts=[entry for entry in entries if '/' not in entry], **kwargs)

    async def __call__(self, scope, receive, send):
        if self.networks and scope['type'] in {'http', 'websocket'}:
            host = Headers(scope=scope).get('host', '')
            # Brackets enclose IPv6 literals; IPv4 may have a port suffix.
            literal = host[1:host.index(']')] if host.startswith('[') and ']' in host else host.split(':')[0]
            try:
                address = ip_address(literal)
            except ValueError:
                pass
            else:
                if any(address in network for network in self.networks):
                    await self.app(scope, receive, send)
                    return
        await super().__call__(scope, receive, send)
