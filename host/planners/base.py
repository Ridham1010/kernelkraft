"""Planner interfaces."""


class Planner:
    def plan(self, request, state):
        raise NotImplementedError
