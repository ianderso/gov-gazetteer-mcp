"""Entry point: ``python -m gov_gazetteer_mcp`` / the ``gov-gazetteer-mcp`` script."""

from __future__ import annotations

from .server import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
