import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft7Validator, FormatChecker

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


@lru_cache
def _get_validator(schema_name: str) -> Draft7Validator:
    with open(SCHEMA_DIR / schema_name, encoding="utf-8") as f:
        schema = json.load(f)
    return Draft7Validator(schema, format_checker=FormatChecker())


def get_errors(data, schema_name: str) -> list[str]:
    validator = _get_validator(schema_name)
    return [
        f"{'.'.join(str(part) for part in error.path) or '$'}: {error.message}"
        for error in sorted(validator.iter_errors(data), key=lambda e: e.path)
    ]


def validate_event(data, schema_name: str) -> None:
    errors = get_errors(data, schema_name)
    if errors:
        raise ValueError(f"Invalid event schema: {errors}")
