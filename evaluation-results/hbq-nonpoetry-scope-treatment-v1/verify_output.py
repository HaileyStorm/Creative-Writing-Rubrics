"""Verify the frozen, provider-free S2 treatment package."""
from __future__ import annotations

import json

from study import validate_package


if __name__ == "__main__":
    print(json.dumps(validate_package(), sort_keys=True))
