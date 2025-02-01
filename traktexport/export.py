import sys
import os
import logging
import shlex
from time import sleep
from typing import Dict, Any, Iterator, List, Optional, Literal
from functools import lru_cache

import backoff  # type: ignore[import]
from trakt.core import api, BASE_URL  # type: ignore[import]
from trakt.api import TokenAuth  # type: ignore[import]
from trakt.errors import RateLimitException  # type: ignore[import]
from logzero import logger  # type: ignore[import]


@lru_cache(maxsize=1)
def _check_config() -> None:
    from . import traktexport_cfg

    if not os.path.exists(traktexport_cfg):
        raise FileNotFoundError(
            f"Config file '{traktexport_cfg}' not found. Run '{shlex.quote(sys.executable)} -m traktexport auth' to create it."
        )

    # loads config and refreshes token if needed
    client = api()
    auth: Optional[TokenAuth] = client.auth
    if auth is None:
        raise ValueError(f"No auth config found on client={client}")

    # this refreshes the token, if needed
    auth.get_token()


SLEEP_TIME = int(os.environ.get("TRAKTEXPORT_SLEEP_TIME", 2))


@backoff.on_exception(backoff.expo, (RateLimitException,))
def _trakt_request(
    endpoint: str,
    data: Any = None,
    *,
    sleep_time: int = SLEEP_TIME,
    logger: Optional[logging.Logger] = None,
    method: Literal["get", "post", "patch"] = "get",
) -> Any:
    """
    Uses api().request (configured trakt session handled by trakt)
    to request information from Trakt

    This uses the bare base request instead of the wrapper
    types so that I have access to more info

    the trakt module here is used for authentication, I just
    create the URLs/save the entire response

    endpoint: The URL to make a request to, doesn't include the domain
    method is lowercase because api().request expects it to be a relative URI
    """
    _check_config()
    if endpoint.startswith("/"):
        endpoint = endpoint[1:]
    if logger:
        logger.debug(f"Requesting '{BASE_URL}{endpoint}'...")
    # api is lru_cache(maxsize=None), returns the globally configured client
    json_data = api().request(method=method, url=endpoint, data=data)
    if sleep_time:
        sleep(sleep_time)
    return json_data


def _trakt_paginate(
    endpoint_bare: str,
    limit: int = 100,
    request_pages: Optional[int] = None,
    logger: Optional[logging.Logger] = None,
) -> Iterator[Any]:
    page = 1
    while True:
        items: List[Any] = _trakt_request(
            f"{endpoint_bare}?limit={limit}&page={page}", logger=logger
        )
        if len(items) == 0:
            break
        if logger:
            logger.debug(f"First item: {items[0]}")
        yield from items
        page += 1
        if request_pages is not None and page > request_pages:
            break


def full_export(username: str) -> Dict[str, Any]:
    """Runs a full export for a trakt user"""
    return {
        "type": "full",
        "username": username,
        "followers": _trakt_request(f"users/{username}/followers", logger=logger),
        "following": _trakt_request(f"users/{username}/following", logger=logger),
        "settings": _trakt_request("users/settings", logger=logger),
        "likes": _trakt_request("users/likes", logger=logger),
        "profile": _trakt_request(f"users/{username}", logger=logger),
        "comments": _trakt_request(f"users/{username}/comments", logger=logger),
        "lists": _trakt_request(f"users/{username}/lists", logger=logger),
        "ratings": _trakt_request(f"users/{username}/ratings", logger=logger),
        "recommendations": _trakt_request(
            f"users/{username}/recommendations", logger=logger
        ),
        "watchlist": _trakt_request(f"users/{username}/watchlist", logger=logger),
        "watched": _trakt_request(f"users/{username}/watched/movies", logger=logger)
        + _trakt_request(f"users/{username}/watched/shows", logger=logger),
        "collection": _trakt_request(
            f"users/{username}/collection/movies", logger=logger
        )
        + _trakt_request(f"users/{username}/collection/shows", logger=logger),
        "stats": _trakt_request(f"users/{username}/stats", logger=logger),
        "history": list(_trakt_paginate(f"users/{username}/history", logger=logger)),
    }


def partial_export(username: str, pages: Optional[int] = None) -> Dict[str, Any]:
    """Runs a partial history export for a trakt user, i.e. grabs the first 'n' pages of history entries"""
    return {
        "type": "partial",
        "history": list(
            _trakt_paginate(
                f"users/{username}/history", request_pages=pages, logger=logger
            )
        ),
    }
