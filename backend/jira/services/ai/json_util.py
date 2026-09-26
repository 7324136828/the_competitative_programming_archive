import json
import re


def parse_json_object(text: str):
    if not text or not isinstance(text, str):
        raise ValueError('Empty AI response')
    t = text.strip()
    fence = re.match(r'^```(?:json)?\s*([\s\S]*?)\s*```$', t, re.IGNORECASE)
    if fence:
        t = fence.group(1).strip()
    try:
        return json.loads(t)
    except (json.JSONDecodeError, ValueError):
        start = t.find('{')
        end = t.rfind('}')
        if start != -1 and end > start:
            return json.loads(t[start:end + 1])
        raise ValueError('AI response was not valid JSON')
