"""Engine map: which games share code (studio, SDK, engine) and the memory map of one game."""
import sqlite3
from collections import defaultdict

from . import config, difficulty, games


def memory_map(g) -> dict:
    """Every function of the main module as [addr, size, state]; state -1 = matched, else difficulty level."""
    rows = g.functions()
    port = games.portable(g)
    out = []
    for r in rows:
        lvl = -1 if r["done"] else difficulty.rate(dict(r), port)["level"]
        out.append([r["addr"], r["size"], lvl])
    return {"functions": out, "start": min((r[0] for r in out), default=0),
            "end": max((r[0] + r[1] for r in out), default=0)}


def cross_games() -> dict:
    """Pairs of indexed games with the number of identical functions, split into SDK (in 5+ games) and engine
    (in 2-4 games: code a studio reused)."""
    if not config.FPDB.exists():
        return {"games": [], "pairs": []}
    con = sqlite3.connect(config.FPDB)
    spread = dict(con.execute("SELECT strict, COUNT(DISTINCT game) FROM fn GROUP BY strict").fetchall())
    by_game = defaultdict(set)
    for game, strict in con.execute("SELECT game, strict FROM fn"):
        by_game[game].add(strict)
    con.close()
    inv = {v: k for k, v in games.FP_KEY.items()}
    keys = sorted(by_game)
    pairs = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            common = by_game[a] & by_game[b]
            if not common:
                continue
            sdk = sum(1 for s in common if spread[s] >= 5)
            pairs.append({"a": inv.get(a, a), "b": inv.get(b, b), "shared": len(common), "sdk": sdk,
                          "engine": len(common) - sdk})
    info = []
    for k in keys:
        gid = inv.get(k, k)
        mine = by_game[k]
        info.append({"id": gid, "key": k, "title": games.TITLES.get(gid, gid), "studio": games.STUDIOS.get(gid, ""),
                     "functions": len(mine), "unique": sum(1 for s in mine if spread[s] == 1),
                     "sdk": sum(1 for s in mine if spread[s] >= 5)})
    pairs.sort(key=lambda p: -p["engine"])
    return {"games": info, "pairs": pairs}


def studios() -> list[dict]:
    """Projects grouped by studio (same studio = often the same engine)."""
    groups = defaultdict(list)
    for g in games.all_games():
        groups[games.STUDIOS.get(g.id, "Inconnu")].append(g.id)
    return [{"studio": s, "games": sorted(v)} for s, v in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
