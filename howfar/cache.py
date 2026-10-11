"""Where downloaded map pieces live, and how the tool identifies itself to the open data servers.
Everything cached here is public map data for the places you asked about; `howfar clear-cache` wipes it."""
import os

CACHE = os.environ.get("HOWFAR_CACHE") or os.path.join(os.path.expanduser("~"), ".cache", "howfar")
os.makedirs(CACHE, exist_ok=True)
UA = {"User-Agent": "howfar/0.1 (open-source agent skill; https://github.com/Mendypf/howfar)"}


def clear():
    n = 0
    for f in os.listdir(CACHE):
        p = os.path.join(CACHE, f)
        if os.path.isfile(p):
            os.remove(p); n += 1
    return n
