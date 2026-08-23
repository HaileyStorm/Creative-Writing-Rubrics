"""CLI verifier for the frozen source package."""
from __future__ import annotations

import json

from study import verify_package


if __name__ == "__main__":
    print(json.dumps(verify_package(), sort_keys=True))
