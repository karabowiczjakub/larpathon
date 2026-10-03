import time
from threading import Lock
from typing import Any, Callable

from cachetools import TTLCache

class ThreadSafeTTLCache:
    """Prosty, wątkowo bezpieczny cache z TTL dla zapytań API."""
    
    def __init__(self, maxsize: int = 100, ttl_seconds: float = 1800):
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl_seconds)
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._cache[key] = value

    def get_or_compute(self, key: str, compute_func: Callable[[], Any]) -> Any:
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        
        # Obliczenia poza blokadą, aby nie blokować całego cache
        value = compute_func()
        
        with self._lock:
            self._cache[key] = value
            return value

    def clear(self):
        with self._lock:
            self._cache.clear()

# Globalne instancje cache dla pogody (30 min) i AQ (1 godzina)
weather_cache = ThreadSafeTTLCache(maxsize=100, ttl_seconds=30 * 60)
pollution_cache = ThreadSafeTTLCache(maxsize=100, ttl_seconds=60 * 60)
