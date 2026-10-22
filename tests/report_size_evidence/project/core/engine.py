from util.helpers import normalise
from core import registry


def run(value):
    return registry.lookup(normalise(value))


def shared_tool(value):
    return value
