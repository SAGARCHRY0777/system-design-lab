"""Put each implementation directory on sys.path.

Implementations are standalone teaching artefacts, not a package: a reader
should be able to copy one folder out and run it. That means `from rate_limiter
import TokenBucket` has to work without an installed package or a src layout.
"""

import sys
from pathlib import Path

for child in sorted(Path(__file__).parent.iterdir()):
    if child.is_dir() and not child.name.startswith((".", "_")):
        sys.path.insert(0, str(child))
