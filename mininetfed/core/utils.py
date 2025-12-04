import base64
from typing import TypeAlias, Union

import numpy as np

JSONSerializableType: TypeAlias = Union[
    None, bool, int, float, str,
    list["JSONSerializableType"],
    dict[str, "JSONSerializableType"],
]

def ndarray_to_base64(arr: np.ndarray) -> dict:
    """Convert one ndarray to a base64 JSON-safe dict."""
    return {
        "dtype": str(arr.dtype),
        "shape": arr.shape,
        "data_b64": base64.b64encode(arr.tobytes()).decode("ascii"),
    }

def base64_to_ndarray(entry: dict) -> np.ndarray:
    """Decode one base64 JSON-encoded ndarray."""
    data = base64.b64decode(entry["data_b64"])
    arr = np.frombuffer(data, dtype=np.dtype(entry["dtype"]))
    return arr.reshape(entry["shape"])

class Color:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD_START = '\033[1m'
    BOLD_END = '\033[0m'
    RESET = "\x1B[0m"