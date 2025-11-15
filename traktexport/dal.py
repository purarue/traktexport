# some DAL https://beepb00p.xyz/exports.html#dal
# code to parse the export into an ADT-like format
#
# this uses dataclasses sometimes so that I can possibly
# fix datetimes for items which I watched
# a *long* time ago, i.e. movies I watched
# as a kid but added when I created my account

import sys
import json
from datetime import datetime, timezone
from typing import (
    NamedTuple,
    Any,
    Optional,
    Union,
    TextIO,
)
from collections.abc import Iterator
from dataclasses import dataclass

TRAKT_BASE = "https://app.trakt.tv"


# Note: I currently don't parse the following, because I don't have anything there
#
# collection
# comments
# lists
# recommendations
#
# TODO: add some stuff there are re-do an export so I can parse it


class Follow(NamedTuple):
    followed_at: datetime
    username: str


class SiteIds(NamedTuple):
    trakt_id: int
    trakt_slug: Optional[str]
    imdb_id: Optional[str]
    tmdb_id: Optional[int]
    tvdb_id: Optional[int]
    tvrage_id: Optional[int]


class Movie(NamedTuple):
    title: str
    year: int
    ids: SiteIds

    @property
    def url(self) -> str:
        return f"{TRAKT_BASE}/movies/{self.ids.trakt_slug}"


class Show(NamedTuple):
    title: str
    year: int
    ids: SiteIds

    @property
    def url(self) -> str:
        return f"{TRAKT_BASE}/shows/{self.ids.trakt_slug}"


class Season(NamedTuple):
    season: int
    ids: SiteIds
    show: Show

    @property
    def url(self) -> str:
        return f"{TRAKT_BASE}/shows/{self.show.ids.trakt_slug}/seasons/{self.season}"


class Episode(NamedTuple):
    title: str
    season: int
    episode: int
    ids: SiteIds
    show: Show

    @property
    def url(self) -> str:
        return f"{TRAKT_BASE}/shows/{self.show.ids.trakt_slug}/seasons/{self.season}/episodes/{self.episode}"


class Comment(NamedTuple):
    comment_id: int
    text: str
    created_at: datetime
    updated_at: datetime
    likes: int
    username: str


class TraktList(NamedTuple):
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    likes: int
    username: str


class Like(NamedTuple):
    liked_at: datetime
    media_type: str
    media_data: Union[TraktList, Comment]


class WatchListEntry(NamedTuple):
    listed_at: datetime
    listed_at_id: int
    media_type: str
    media_data: Union[Movie, Show]


@dataclass
class Rating:
    rated_at: datetime
    rating: int
    media_type: str
    media_data: Union[Movie, Show, Season, Episode]


@dataclass
class HistoryEntry:
    history_id: int
    watched_at: datetime
    action: str
    media_type: str
    media_data: Union[Movie, Episode]


class PartialHistoryExport(NamedTuple):
    history: list[HistoryEntry]


class FullTraktExport(NamedTuple):
    username: str
    followers: list[Follow]
    following: list[Follow]
    likes: list[Like]
    stats: dict[str, Any]
    settings: dict[str, Any]
    watchlist: list[WatchListEntry]
    ratings: list[Rating]
    history: list[HistoryEntry]


def _parse_trakt_datetime(ds: str) -> datetime:
    utc_naive = datetime.fromisoformat(ds.rstrip("Z"))
    return utc_naive.replace(tzinfo=timezone.utc)


def test_parse_utc_date() -> None:
    expected = datetime(2021, 9, 30, 1, 44, 33, tzinfo=timezone.utc)
    assert _parse_trakt_datetime("2021-09-30T01:44:33.000Z") == expected


def _parse_followers(d: Any) -> Iterator[Follow]:
    for i in d:
        yield Follow(
            followed_at=_parse_trakt_datetime(i["followed_at"]),
            username=i["user"]["username"],
        )


def _parse_comment(d: Any) -> Comment:
    return Comment(
        comment_id=d["id"],
        text=d["comment"],
        created_at=_parse_trakt_datetime(d["created_at"]),
        updated_at=_parse_trakt_datetime(d["updated_at"]),
        likes=d["likes"],
        username=d["user"]["username"],
    )


def _parse_trakt_list(d: Any) -> TraktList:
    return TraktList(
        name=d["name"],
        description=d["description"],
        created_at=_parse_trakt_datetime(d["created_at"]),
        updated_at=_parse_trakt_datetime(d["updated_at"]),
        likes=d["likes"],
        username=d["user"]["username"],
    )


def _parse_likes(d: Any) -> Iterator[Like]:
    for i in d:
        media_type = i["type"]
        media_data_raw = i[media_type]
        media_data: Union[TraktList, Comment]
        if media_type == "comment":
            media_data = _parse_comment(media_data_raw)
        elif media_type == "list":
            media_data = _parse_trakt_list(media_data_raw)
        else:
            print(f"_parse_likes: No case to parse: {i}", file=sys.stderr)
            continue
        yield Like(
            liked_at=_parse_trakt_datetime(i["liked_at"]),
            media_type=media_type,
            media_data=media_data,
        )


def _parse_ids(d: Any) -> SiteIds:
    return SiteIds(
        trakt_id=d["trakt"],
        trakt_slug=d.get("slug"),
        imdb_id=d.get("imdb"),
        tmdb_id=d.get("tmdb"),
        tvdb_id=d.get("tvdb"),
        tvrage_id=d.get("tvrage"),
    )


def _parse_media(d: Any) -> dict[str, Any]:
    return dict(
        title=d["title"],
        year=d["year"],
        ids=_parse_ids(d["ids"]),
    )


def _parse_movie(d: Any) -> Movie:
    return Movie(**_parse_media(d))


def _parse_show(d: Any) -> Show:
    return Show(**_parse_media(d))


def _parse_season(d: Any, show_data: Any) -> Season:
    return Season(
        season=d["number"],
        show=_parse_show(show_data),
        ids=_parse_ids(d["ids"]),
    )


def _parse_episode(d: Any, show_data: Any) -> Episode:
    return Episode(
        title=d["title"],
        season=d["season"],
        episode=d["number"],
        show=_parse_show(show_data),
        ids=_parse_ids(d["ids"]),
    )


# extracts the common schema from ratings/history/watchlist
def _parse_list_info(
    d: Any,
) -> Optional[tuple[str, Union[Movie, Show, Season, Episode]]]:
    media_type: str = d["type"]
    media_data_raw = d[media_type]
    media_data: Union[Movie, Show, Season, Episode]
    if media_type == "movie":
        media_data = _parse_movie(media_data_raw)
    elif media_type == "show":
        media_data = _parse_show(media_data_raw)
    elif media_type == "season":
        media_data = _parse_season(media_data_raw, d["show"])
    elif media_type == "episode":
        media_data = _parse_episode(media_data_raw, d["show"])
    else:
        print(f"While parsing list, no case to parse: {d}", file=sys.stderr)
        return None
    return media_type, media_data


def _parse_watchlist(d: Any) -> Iterator[WatchListEntry]:
    for i in d:
        data = _parse_list_info(i)
        if data is None:
            continue
        media_type, media_data = data
        yield WatchListEntry(
            listed_at_id=i["id"],
            listed_at=_parse_trakt_datetime(i["listed_at"]),
            media_type=media_type,
            media_data=media_data,  # type: ignore[arg-type]
        )


def _parse_ratings(d: Any) -> Iterator[Rating]:
    for i in d:
        data = _parse_list_info(i)
        if data is None:
            continue
        media_type, media_data = data
        yield Rating(
            rated_at=_parse_trakt_datetime(i["rated_at"]),
            rating=i["rating"],
            media_type=media_type,
            media_data=media_data,
        )


def _parse_history(d: Any) -> Iterator[HistoryEntry]:
    for i in d:
        data = _parse_list_info(i)
        if data is None:
            continue
        media_type, media_data = data
        yield HistoryEntry(
            history_id=i["id"],
            watched_at=_parse_trakt_datetime(i["watched_at"]),
            action=i["action"],
            media_type=media_type,
            media_data=media_data,  # type: ignore[arg-type]
        )


# a helper to parse items that are left as python primitives
def _read_unparsed(f: TextIO, data: Optional[Any] = None) -> dict[str, Any]:
    ldata: Any
    if data is None:
        ldata = json.loads(f.read())
    else:
        ldata = data
    return {
        "username": ldata["username"],
        "stats": ldata["stats"],
        "settings": ldata["settings"],
    }


def _guess_export_type(data: Any) -> str:
    if "type" in data:
        return str(data["type"])
    else:
        if len(data.keys()) < 4:
            return "partial"
        else:
            return "full"


TraktExport = Union[FullTraktExport, PartialHistoryExport]


def parse_export(f: TextIO) -> TraktExport:
    data: Any = json.loads(f.read())

    # is there any point in parsing 'watched', if we're also parsing 'history'?
    # going to only parse history for now, since its better structured for parsing
    # and seems to have more info

    if _guess_export_type(data) == "full":
        return FullTraktExport(
            **_read_unparsed(f, data),
            followers=list(_parse_followers(data["followers"])),
            following=list(_parse_followers(data["following"])),
            likes=list(_parse_likes(data["likes"])),
            watchlist=list(_parse_watchlist(data["watchlist"])),
            ratings=list(_parse_ratings(data["ratings"])),
            history=list(_parse_history(data["history"])),
        )
    else:
        return PartialHistoryExport(history=list(_parse_history(data["history"])))
