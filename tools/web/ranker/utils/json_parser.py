import json
import re
from typing import Any, Optional


def parse_json_from_text(s: str) -> Optional[Any]:
    """Parse JSON from an LLM response string.

    Attempts direct parsing first, then searches for the first balanced
    JSON object or array in the string and parses that. Returns the parsed
    Python object on success or `None` on failure.
    """
    if not s:
        return None

    try:
        return json.loads(s)
    except Exception:
        pass

    start_candidates = [i for i in (s.find('{'), s.find('[')) if i >= 0]
    for start in sorted(start_candidates):
        stack = []
        pairs = {'{': '}', '[': ']'}
        for i in range(start, len(s)):
            ch = s[i]
            if ch in pairs:
                stack.append(pairs[ch])
            elif stack and ch == stack[-1]:
                stack.pop()
                if not stack:
                    candidate = s[start:i+1]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        break

    m = re.search(r"(\{.*\}|\[.*\])", s, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            return None

    return None
