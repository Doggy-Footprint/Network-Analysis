from core.engine import run, shared_tool
from web.views import render


def main():
    shared_tool(1)
    return render(run(1))
