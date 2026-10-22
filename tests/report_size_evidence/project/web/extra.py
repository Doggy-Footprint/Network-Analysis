from core.engine import shared_tool
from core.registry import lookup


def extra(value):
    return lookup(shared_tool(value))
