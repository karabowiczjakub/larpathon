"""orjson for Flask: numpy values serialize as-is, NaN/inf become null, datetimes are ISO 8601."""
from __future__ import annotations

from typing import Any

import orjson
from flask.json.provider import JSONProvider

_OPTIONS = orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NON_STR_KEYS


def _default(obj: Any) -> Any:
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    raise TypeError(f"{type(obj).__name__} is not JSON serializable")


class OrjsonProvider(JSONProvider):
    def dumps(self, obj: Any, **kwargs: Any) -> str:
        return orjson.dumps(obj, default=_default, option=_OPTIONS).decode()

    def loads(self, s: str | bytes, **kwargs: Any) -> Any:
        return orjson.loads(s)
