"""Difficulty of an unmatched function, from what the tools already know about it.

Level 0 "Portable": the same machine code is already matched in another project, copy its source.
Levels 1-5: size of the function, corrected by the last auto_match result:
  near    (m2c draft compiles to the right size, a few instructions differ) -> one level easier
  size    (compiles, wrong length)                                             -> unchanged
  compile / m2c (the draft does not even compile / m2c failed)                 -> one level harder
"""

LEVELS = [
    {"n": 0, "key": "portable", "label": "Portable", "hint": "deja matchee dans un autre jeu : copier la source"},
    {"n": 1, "key": "facile", "label": "Facile", "hint": "petite fonction ou brouillon presque bon"},
    {"n": 2, "key": "moyen", "label": "Moyen", "hint": "quelques branches, brouillon m2c a corriger"},
    {"n": 3, "key": "difficile", "label": "Difficile", "hint": "boucles, structures a deviner"},
    {"n": 4, "key": "expert", "label": "Expert", "hint": "grosse fonction, types du moteur necessaires"},
    {"n": 5, "key": "legendaire", "label": "Legendaire", "hint": "tres grosse fonction, a decouper mentalement"},
]
AUTO_LABEL = {"near": "presque (near)", "size": "taille differente", "compile": "ne compile pas", "m2c": "m2c a echoue",
              "": "jamais essaye"}


def size_level(size: int) -> int:
    for lvl, limit in ((1, 32), (2, 96), (3, 256), (4, 640)):
        if size <= limit:
            return lvl
    return 5


def rate(fn: dict, portable: dict) -> dict:
    """Adds level / score to an unmatched function row (see games.Game.functions)."""
    if fn["addr"] in portable:
        g, other, src = portable[fn["addr"]]
        fn.update(level=0, score=fn["size"] / 1000, port={"game": g, "name": other, "file": src})
        return fn
    lvl = size_level(fn["size"])
    auto = fn.get("auto", "")
    if auto == "near":
        lvl -= 1
    elif auto in ("compile", "m2c"):
        lvl += 1
    lvl = max(1, min(5, lvl))
    # score: continuous value for sorting inside a level (bytes, weighted by the auto_match result)
    w = {"near": 0.6, "size": 1.0, "": 1.1, "compile": 1.3, "m2c": 1.5}.get(auto, 1.0)
    fn.update(level=lvl, score=round(fn["size"] * w, 1))
    return fn


def rate_all(rows: list[dict], portable: dict) -> list[dict]:
    return [rate(dict(r), portable) for r in rows if not r["done"]]
