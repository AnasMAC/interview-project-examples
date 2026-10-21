from .base import *  # noqa: F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = env("ATLAS_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0,web").split(",")

# Dev clock (atlas.core.clock): the stack starts at the seed's anchor so expiring
# certificates and "changed in last 24h" match the demo data. Empty = real time.
ATLAS_NOW = env("ATLAS_NOW", "")
