import sys
from unittest.mock import MagicMock

# Mock the openai module if not installed
if "openai" not in sys.modules:
    sys.modules["openai"] = MagicMock()
