"""skillsync — entry script.

Run: source venv/bin/activate && python skillsync.py [flags]
"""

from src.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
