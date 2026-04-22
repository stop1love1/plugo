#!/usr/bin/env python3
"""
Plugo CLI management commands.

Admin credentials are configured via .env (USERNAME/PASSWORD) or config.json
— there's no DB-backed user store to manage.

Available subcommands:
    reindex <site_id>   Rebuild ChromaDB embeddings for every chunk on a site.
                        Use after changing `embedding.provider` or `embedding.model`
                        in config.json. Unlike the HTTP /api/knowledge/reindex
                        endpoint, the CLI has no request timeout so it's the
                        supported path for large sites (> 1000 chunks).
"""

import asyncio
import os
import sys


def _print_usage() -> None:
    print(__doc__.strip() if __doc__ else "Usage: manage.py <command> [args...]")


async def _cmd_reindex(site_id: str) -> int:
    # Delayed imports so `manage.py --help` doesn't spin up the DB/Chroma stack.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from repositories import create_repos
    from routers.knowledge import _reindex_site

    repos = await create_repos()
    try:
        site = await repos.sites.get_by_id(site_id)
        if not site:
            print(f"[error] site '{site_id}' not found", file=sys.stderr)
            return 2
        print(f"[reindex] site={site['name']!r} ({site_id})")

        def _progress(done: int, total: int) -> None:
            pct = (done / total * 100) if total else 100.0
            print(f"  {done}/{total} ({pct:.1f}%)", flush=True)

        result = await _reindex_site(site_id, repos, progress_cb=_progress)
        print(
            f"[done] reindexed {result['chunks_reindexed']} chunks in {result['elapsed_seconds']}s"
        )
        return 0
    finally:
        await repos.close()


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help", "help"}:
        _print_usage()
        # Print usage on no-args is not an error — lets the old no-args call still exit 0.
        return 0

    cmd = sys.argv[1]
    if cmd == "reindex":
        if len(sys.argv) < 3:
            print("usage: manage.py reindex <site_id>", file=sys.stderr)
            return 2
        return asyncio.run(_cmd_reindex(sys.argv[2]))

    print(f"unknown command: {cmd}", file=sys.stderr)
    _print_usage()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
