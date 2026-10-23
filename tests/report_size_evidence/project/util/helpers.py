import requests_unknown_lib
from core.engine import shared_tool


def normalise(value):
    shared_tool(value)
    return str(value).strip()
