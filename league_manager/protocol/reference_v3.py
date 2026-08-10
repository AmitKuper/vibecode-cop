"""Alias of the canonical cop_worker implementation.

This copy had drifted (stale hard-coded scent lock, terms, and identity while the
canonical derives them from config/game.json); it is now a module alias so there is
a single source of truth and the two packages cannot drift. Import via either
package path — both resolve to the same module object (monkeypatches included).
"""

import sys

from cop_worker.protocol.reference_v3 import *  # noqa: F401,F403
from cop_worker.protocol.reference_v3 import __name__ as _canonical_name  # noqa: F401

sys.modules[__name__] = sys.modules["cop_worker.protocol.reference_v3"]
