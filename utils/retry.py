"""
Async retry helper with exponential backoff.

Wrap any async REST call that can transiently fail (rate limit, network
hiccup, exchange 5xx). Reconnect logic for websockets is handled separately.

Usage:
    from utils.retry import async_retry

    @async_retry(attempts=3, base_delay=0.5)
    async def fetch_candles(...): ...

    # or inline:
    candles = await async_retry_call(
        lambda: exchange.get_candles(pair, "5m", 100),
        attempts=3,
    )
"""
from __future__ import annotations

import asyncio
import functools
import logging
from typing import Awaitable, Callable, TypeVar

log = logging.getLogger("apex.retry")

T = TypeVar("T")


def async_retry(
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
):
    """
    Decorator: retry an async function with exponential backoff.

    Backoff: base_delay, base_delay*2, base_delay*4, ... capped at max_delay.
    Last exception is re-raised after attempts exhausted.
    """
    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs) -> T:
            delay = base_delay
            last: BaseException | None = None
            for i in range(attempts):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as e:
                    last = e
                    if i == attempts - 1:
                        break
                    log.debug("%s attempt %d/%d failed (%s) — retrying in %.1fs",
                              fn.__name__, i + 1, attempts, e, delay)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, max_delay)
            assert last is not None
            raise last
        return wrapper
    return decorator


async def async_retry_call(
    fn: Callable[[], Awaitable[T]],
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Inline form: retry a zero-arg async callable with exponential backoff."""
    delay = base_delay
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return await fn()
        except exceptions as e:
            last = e
            if i == attempts - 1:
                break
            log.debug("attempt %d/%d failed (%s) — retrying in %.1fs",
                      i + 1, attempts, e, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
    assert last is not None
    raise last
