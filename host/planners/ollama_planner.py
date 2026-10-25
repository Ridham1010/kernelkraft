"""Optional Ollama planner; never emits shell text."""

import json

try:
    from .base import Planner
except ImportError:
    from base import Planner


class OllamaPlanner(Planner):
    def __init__(self, endpoint="http://localhost:11434/api/chat", model="llama3"):
        self.endpoint = endpoint
        self.model = model

    def plan(self, request, state):
        import requests

        schema = {
            "type": "object",
            "required": ["tool", "args"],
            "properties": {"tool": {"type": "string"}, "args": {"type": "object"}},
        }
        response = requests.post(
            self.endpoint,
            json={
                "model": self.model,
                "stream": False,
                "format": schema,
                "messages": [{"role": "user", "content": request}],
            },
            timeout=30,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        action = json.loads(content)
        if not isinstance(action, dict) or set(action) != {"tool", "args"}:
            raise ValueError("planner returned an invalid action")
        return action
