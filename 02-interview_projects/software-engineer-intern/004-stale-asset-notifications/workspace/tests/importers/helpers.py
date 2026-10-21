from pathlib import Path

from django.conf import settings


def fixture_text(relative: str) -> str:
    return (Path(settings.ATLAS_IMPORT_ROOT) / relative).read_text(encoding="utf-8")


def by_value(batch) -> dict:
    return {observation.value: observation for observation in batch.observations}
