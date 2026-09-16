"""Allow ``python -m composio_ops`` to reach the root CLI."""

from .cli.main import main

if __name__ == "__main__":
    main()
