import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft7Validator
from rest_framework.exceptions import ValidationError

SCHEMA_DIR = Path(__file__).resolve().parent / 'schemas'


@lru_cache(maxsize=None)
def _get_validator(schema_name: str) -> Draft7Validator:
    with open(SCHEMA_DIR / schema_name, encoding='utf-8') as f:
        schema = json.load(f)
    return Draft7Validator(schema)


def get_errors(data, schema_name: str) -> list[str]:
    """Zwraca listę komunikatów błędów (pustą, jeśli dane są poprawne)."""
    validator = _get_validator(schema_name)
    messages = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        location = '.'.join(str(p) for p in err.path) or '(root)'
        messages.append(f'{location}: {err.message}')
    return messages


def validate_or_raise(data, schema_name: str) -> None:
    """Waliduje dane; przy błędach rzuca DRF ValidationError (HTTP 400)."""
    errors = get_errors(data, schema_name)
    if errors:
        raise ValidationError({'schema_errors': errors})
