from slowapi import Limiter
from slowapi.util import get_remote_address

from app.infrastructure.config import settings

# Keyed by client IP, not user OID — slowapi's key_func is synchronous and
# only receives the raw Request, while validating the bearer JWT (JWKS
# fetch + cache) is async and already happens in the route's own auth
# dependency. Re-deriving the user's identity here would duplicate that
# work in a sync context. IP-based limiting is coarser (shared NATs/
# proxies share a bucket) but still meaningfully caps abuse and runaway
# cost per client, and is what most public APIs do at the edge regardless
# of auth.
#
# Backed by Redis (not in-memory) so the limit is shared across every
# stateless replica of this API, not reset per-instance.
limiter = Limiter(key_func=get_remote_address, storage_uri=settings.redis_url)
