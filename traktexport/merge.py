from collections.abc import Iterator

from .dal import (
    parse_export,
    FullTraktExport,
    PartialHistoryExport,
    TraktExport,
    HistoryEntry,
)


def read_and_merge_exports(files: list[str]) -> FullTraktExport:
    """
    Given multiple files as inputs, parses and merges
    the exports into one full, combined export
    """
    exp: list[TraktExport] = []
    for fl in files:
        with open(fl) as f:
            exp.append(parse_export(f))

    return merge_exports(exp)


def _merge_history_entries(unsorted: list[TraktExport]) -> Iterator[HistoryEntry]:
    emitted: set[int] = set()
    for u in unsorted:
        for hist in u.history:
            # unique scrobble ID from trakt
            if hist.history_id in emitted:
                continue
            yield hist
            emitted.add(hist.history_id)


def merge_exports(unsorted: list[TraktExport]) -> FullTraktExport:
    """
    Given multiple (parsed) exports, grabs the latest information
    from the most recent full export and returns unique
    history entries
    """
    full_exports: list[FullTraktExport] = []
    partial_exports: list[PartialHistoryExport] = []

    # split into full and partial exports
    for u in unsorted:
        if isinstance(u, FullTraktExport):
            full_exports.append(u)
        else:
            partial_exports.append(u)

    # sort exports by history count (full exports will have more
    # history entries) so that the latest stats are preserved
    full_exports.sort(key=lambda e: len(e.history))
    trakt_dict = full_exports[-1]._asdict()

    hist = list(_merge_history_entries(unsorted))
    hist.sort(key=lambda h: h.watched_at, reverse=True)  # ordered to most recent first
    trakt_dict["history"] = hist

    return FullTraktExport(**trakt_dict)
