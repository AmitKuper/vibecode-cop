"""Alias of the canonical cop_worker implementation.

This module was a byte-identical copy; it is now a module alias so there is a
single source of truth and the two packages cannot drift. Import via either
package path — both resolve to the same module object (monkeypatches included).
"""

import sys

from cop_worker.protocol.dsl import *  # noqa: F401,F403
from cop_worker.protocol.dsl import __name__ as _canonical_name  # noqa: F401

sys.modules[__name__] = sys.modules["cop_worker.protocol.dsl"]
