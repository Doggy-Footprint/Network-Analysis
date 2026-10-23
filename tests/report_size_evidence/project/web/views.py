from core.engine import shared_tool
from util.helpers import normalise


def render(value):
    shared_tool(value)
    return normalise(value)
