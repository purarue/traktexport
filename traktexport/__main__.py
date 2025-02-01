import sys
import json
from typing import Optional, Sequence, Generator
from contextlib import contextmanager

import click
from trakt import init  # type: ignore[import]
from trakt.errors import TraktUnavailable  # type: ignore[import]

from .export import full_export, partial_export
from .dal import parse_export, TraktExport, FullTraktExport
from .merge import read_and_merge_exports


# if trakt unavailable, exit with code 3
@contextmanager
def handle_trakt_unavailable() -> Generator[None, None, None]:
    try:
        yield
    except TraktUnavailable as e:
        print(f"Error: {e}")
        sys.exit(3)


@click.group()
def main() -> None:
    """Export data from your Trakt account"""
    pass


@main.command(short_help="setup authentication")
@click.option(
    "--client-id",
    envvar="TRAKT_CLIENT_ID",
    required=True,
    help="Trakt Client ID",
    prompt=True,
    show_envvar=True,
)
@click.option(
    "--client-secret",
    envvar="TRAKT_CLIENT_SECRET",
    required=True,
    help="Trakt Client Secret",
    prompt=True,
    show_envvar=True,
    hide_input=True,
)
@click.argument("USERNAME")
def auth(client_id: str, client_secret: str, username: str) -> None:
    """Authenticate (or Re-authenticate) - only needs to be done once"""
    # https://pytrakt.readthedocs.io/en/latest/getstarted.html#oauth-auth
    # use OAuth and store credentials
    init(username, store=True, client_id=client_id, client_secret=client_secret)


@main.command(name="export", short_help="run an account export")
@click.argument("USERNAME")
def _export(username: str) -> None:
    """
    Runs a full account export - assumes authentication has already been setup

    Prints results to STDOUT
    """
    with handle_trakt_unavailable():
        click.echo(json.dumps(full_export(username)))


@main.command(name="partial_export", short_help="run a partial export")
@click.argument("USERNAME")
@click.option(
    "--pages",
    type=int,
    default=None,
    help="Only request these many pages of your history",
)
@click.option(
    "--days",
    type=int,
    default=None,
    help="Request history till this many days ago",
)
def _partial_export(username: str, pages: Optional[int], days: Optional[int]) -> None:
    """
    Run a partial history export - assumes authentication has already been setup

    This exports your movie/TV show history from Trakt without all the other
    attributes. You can specify --pages or --days to only request the
    first few pages so this doesn't take ages to run.

    The 'merge' command takes multiple partial exports (or full exports)
    and merges them all together into a complete history
    """
    with handle_trakt_unavailable():
        click.echo(json.dumps(partial_export(username, pages=pages, days=days)))


@main.command(name="inspect", short_help="read/interact with an export file")
@click.argument("EXPORT_FILE", type=click.Path(exists=True))
def _inspect(export_file: str) -> None:
    """
    Given an export JSON file, this parses the info into python objects
    """
    with open(export_file, "r") as f:
        data: TraktExport = parse_export(f)  # noqa
    click.secho("Use 'data' to interact with the parsed TraktExport object", fg="green")

    import IPython  # type: ignore[import]

    IPython.embed()


@main.command(name="merge", short_help="merge multiple exports")
@click.argument("EXPORT_FILES", type=click.Path(exists=True), nargs=-1, required=True)
def _merge(export_files: Sequence[str]) -> None:
    """
    Given multiple JSON export files, this combines the data into a parsed object
    """
    data: FullTraktExport = read_and_merge_exports(list(export_files))  # noqa
    click.secho("Use 'data' to interact with the parsed TraktExport object", fg="green")

    import IPython  # type: ignore[import]

    IPython.embed()


if __name__ == "__main__":
    main(prog_name="traktexport")
