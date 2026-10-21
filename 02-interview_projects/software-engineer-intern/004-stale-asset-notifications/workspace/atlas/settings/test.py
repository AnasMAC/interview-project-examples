from .base import *  # noqa: F403
from .base import BASE_DIR

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
ATLAS_IMPORT_ROOT = BASE_DIR / "fixtures" / "imports"
ATLAS_WEBHOOK_ALLOWED_HOSTS = ["mockhook", "localhost", "*.example.test"]
