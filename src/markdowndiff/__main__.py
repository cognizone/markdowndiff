"""`python3 -m markdowndiff` shim — defers to `markdowndiff.cli.main`."""

from .cli import main

raise SystemExit(main())
