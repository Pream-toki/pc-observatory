"""Launcher used by the Desktop/Start Menu shortcuts.

It only forwards to main.main(); kept as a stable target for shortcuts.
"""
import main

if __name__ == "__main__":
    raise SystemExit(main.main())
