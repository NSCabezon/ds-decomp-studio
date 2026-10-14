"""Discovery of the DS projects and of their functions (matched or not, auto_match result, sharing)."""
import bisect
import json
import re
import sqlite3
import time
from pathlib import Path

from . import config

SYM_RE = re.compile(r"^(\S+)\s+kind:function\((arm|thumb)(?:,size=0x([0-9a-f]+))?.*addr:0x([0-9a-f]+)")
DELINK_RE = re.compile(r"^(src/\S+):\n\s+complete\n\s+\.text\s+start:0x([0-9a-f]+) end:0x([0-9a-f]+)", re.M)
HEALTH = config.DATA / "health.json"

# project dir -> key of the game in fpdb.sqlite (fingerprints were indexed from projets/_analyse)
FP_KEY = {"rayman-rr": "rrr", "heroes-of-mana": "hom", "dragon-ball-origins": "dbo", "eyeshield-21": "0301Eyeshield2",
          "club-house-games": "0595ClubHouseG", "powerpuff-girls-z": "1372GamedeDema", "farm-frenzy": "FarmFrenzyAnim",
          "mysims": "MySimsUSAEnFrE", "nintendogs-dachshund": "NintendogsDach", "fairy-tail-kardia": "OriginalStoryf",
          "resident-evil-deadly-silence": "ResidentEvilDe", "simanimals": "SimAnimalsEuro",
          "simcity-creator": "SimCityCreator", "simpsons-game": "SimpsonsGameTh", "spore-creatures": "SporeCreatures",
          "tom-and-jerry-tales": "TomandJerryTal", "fairy-tail-madoushi": "TVAnimeFairyTa"}
TITLES = {"rayman-rr": "Rayman Raving Rabbids", "heroes-of-mana": "Heroes of Mana", "dragon-ball-origins": "Dragon Ball Origins",
          "eyeshield-21": "Eyeshield 21", "club-house-games": "Club House Games", "powerpuff-girls-z": "Powerpuff Girls Z",
          "farm-frenzy": "Farm Frenzy", "mysims": "MySims", "nintendogs-dachshund": "Nintendogs Dachshund",
          "fairy-tail-kardia": "Fairy Tail: Kardia", "fairy-tail-madoushi": "Fairy Tail: Madoushi",
          "resident-evil-deadly-silence": "Resident Evil: Deadly Silence", "simanimals": "SimAnimals",
          "simcity-creator": "SimCity Creator", "simpsons-game": "The Simpsons Game", "spore-creatures": "Spore Creatures",
          "tom-and-jerry-tales": "Tom and Jerry Tales", "ultimate-spider-man": "Ultimate Spider-Man",
          "lego-star-wars-ii-the-original-trilogy": "LEGO Star Wars II", "harvest-moon-ds": "Harvest Moon DS",
          "spider-man-web-of-shadows": "Spider-Man: Web of Shadows", "blue-dragon-awakened-shadow": "Blue Dragon: Awakened Shadow",
          "code-lyoko": "Code Lyoko", "cooking-mama": "Cooking Mama", "livly-garden": "Livly Garden", "madagascar": "Madagascar",
          "professor-layton-and-the-spectre-s-call": "Professor Layton and the Spectre's Call",
          "spyro-shadow-legacy": "Spyro: Shadow Legacy", "star-wars-episode-iii-revenge-of-the-sit": "Star Wars Episode III",
          "star-wars-lethal-alliance": "Star Wars: Lethal Alliance", "penguins-of-madagascar-the": "The Penguins of Madagascar",
          "shrek-forever-after": "Shrek Forever After"}
STUDIOS = {  # who made the game: games of one studio often share an engine
    "livly-garden": "Brownie Brown", "heroes-of-mana": "Brownie Brown", "blue-dragon-awakened-shadow": "Brownie Brown",
    "professor-layton-and-the-spectre-s-call": "Level-5", "star-wars-episode-iii-revenge-of-the-sit": "Ubisoft",
    "rayman-rr": "Ubisoft Casablanca", "madagascar": "Vicarious Visions", "ultimate-spider-man": "Vicarious Visions",
    "spyro-shadow-legacy": "Amaze Entertainment", "lego-star-wars-ii-the-original-trilogy": "Amaze Entertainment",
    "simpsons-game": "Amaze Entertainment", "spore-creatures": "Amaze Entertainment",
    "spider-man-web-of-shadows": "Amaze Entertainment", "shrek-forever-after": "Griptonite Games",
    "penguins-of-madagascar-the": "Griptonite Games", "mysims": "EA", "simanimals": "EA", "simcity-creator": "EA",
    "nintendogs-dachshund": "Nintendo EAD", "club-house-games": "Agenda", "cooking-mama": "Office Create",
    "harvest-moon-ds": "Marvelous", "dragon-ball-origins": "Game Republic", "code-lyoko": "Game Machine Studios",
    "resident-evil-deadly-silence": "Capcom", "eyeshield-21": "Eighting", "fairy-tail-kardia": "Konami",
    "fairy-tail-madoushi": "Konami", "tom-and-jerry-tales": "Sensory Sweep", "farm-frenzy": "Alawar",
    "powerpuff-girls-z": "Bandai Namco", "star-wars-lethal-alliance": "Ubisoft",
}
# ROM rebuild state seen during onboarding; `verify` jobs update data/health.json, which wins
KNOWN_BROKEN = {"spore-creatures": "ROM reconstruit different", "club-house-games": "delink impossible (dsd)",
                "tom-and-jerry-tales": "ROM reconstruit plus grand", "star-wars-lethal-alliance": "ninja echoue",
                "professor-layton-and-the-spectre-s-call": "ninja echoue"}

_cache: dict = {}


def _cached(key, path_or_mtime, fn):
    m = path_or_mtime.stat().st_mtime if isinstance(path_or_mtime, Path) else path_or_mtime
    k = (key, m)
    if k not in _cache:
        _cache[k] = fn()
    return _cache[k]


def health() -> dict:
    try:
        return json.loads(HEALTH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def set_health(game: str, ok: bool, note: str = ""):
    h = health()
    h[game] = {"ok": ok, "note": note, "t": time.time()}
    HEALTH.write_text(json.dumps(h, indent=1), encoding="utf-8")


class Game:
    def __init__(self, path: Path):
        self.path = path
        self.id = path.name
        vers = sorted(p.name for p in (path / "config").iterdir() if (p / "arm9" / "symbols.txt").exists()) \
            if (path / "config").exists() else []
        self.version = vers[0] if vers else None
        self.ready = self.version is not None and (path / ".git").exists()

    # ---- metadata ----
    @property
    def cfg(self) -> Path:
        return self.path / "config" / (self.version or "?") / "arm9"

    @property
    def title(self) -> str:
        if self.id in TITLES:
            return TITLES[self.id]
        r = self.path / "README.md"
        if r.exists():
            m = re.match(r"#\s*(.+?) decompilation", r.read_text(encoding="utf-8", errors="replace"))
            if m:
                return m.group(1)
        return self.id.replace("-", " ").title()

    @property
    def code(self) -> str:
        r = self.path / "extract" / "README.md"
        if r.exists():
            m = re.search(r"Game code `(\w{4})`", r.read_text(encoding="utf-8", errors="replace"))
            if m:
                return m.group(1)
        return "AR5E" if self.id == "rayman-rr" else ""

    def remote(self) -> str:
        cfg = self.path / ".git" / "config"
        if not cfg.exists():
            return ""
        m = re.search(r'\[remote "origin"\][^\[]*?url = (\S+)', cfg.read_text(encoding="utf-8", errors="replace"))
        return m.group(1) if m else ""

    def rom_state(self) -> dict:
        if not self.ready:
            return {"ok": False, "note": "projet incomplet (dsd init a echoue)"}
        h = health().get(self.id)
        if h:
            return h
        if self.id in KNOWN_BROKEN:
            return {"ok": False, "note": KNOWN_BROKEN[self.id]}
        return {"ok": True, "note": ""}

    # ---- functions ----
    def symbols(self):
        p = self.cfg / "symbols.txt"
        if not p.exists():
            return []

        def parse():
            out = []
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                m = SYM_RE.match(line)
                if m and m.group(3):
                    out.append((m.group(1), int(m.group(4), 16), int(m.group(3), 16), m.group(2)))
            return out
        return _cached(("sym", str(p)), p, parse)

    def done_ranges(self):
        p = self.cfg / "delinks.txt"
        if not p.exists():
            return []
        return _cached(("dl", str(p)), p, lambda: sorted(
            (int(a, 16), int(b, 16), f) for f, a, b in DELINK_RE.findall(p.read_text(encoding="utf-8", errors="replace"))))

    def auto_status(self) -> dict:
        """{name: 'near'|'size'|'compile'|'m2c'} from the last auto_match pass (build/auto/status.json)."""
        p = self.path / "build" / "auto" / "status.json"
        if not p.exists():
            return {}
        try:
            return _cached(("st", str(p)), p, lambda: {r[0]: r[3] for r in json.loads(p.read_text())})
        except Exception:
            return {}

    def functions(self) -> list[dict]:
        """Every function of the main ARM9 module with its state. The tools (auto_match, verify) work on that module."""
        syms, ranges, st = self.symbols(), self.done_ranges(), self.auto_status()
        dl = self.cfg / "delinks.txt"
        key = ("fns", self.id, dl.stat().st_mtime if dl.exists() else 0, len(syms), id(st))
        if key in _cache:
            return _cache[key]
        starts = [r[0] for r in ranges]
        shared = shared_counts(FP_KEY.get(self.id))
        rows = []
        for name, addr, size, mode in syms:
            i = bisect.bisect_right(starts, addr) - 1
            f = ranges[i][2] if i >= 0 and ranges[i][0] <= addr < ranges[i][1] else None
            rows.append({"name": name, "addr": addr, "size": size, "mode": mode, "done": f is not None, "file": f,
                         "auto": st.get(name, ""), "shared": shared.get(addr, 0)})
        _cache[key] = rows
        return rows

    def summary(self) -> dict:
        rows = self.functions() if self.ready else []
        tot, got = len(rows), sum(r["done"] for r in rows)
        tb, gb = sum(r["size"] for r in rows), sum(r["size"] for r in rows if r["done"])
        return {"functions": tot, "matched": got, "bytes": tb, "matched_bytes": gb,
                "pct_fn": round(100 * got / tot, 2) if tot else 0, "pct_code": round(100 * gb / tb, 2) if tb else 0}

    def info(self) -> dict:
        return {"id": self.id, "title": self.title, "version": self.version, "code": self.code, "ready": self.ready,
                "studio": STUDIOS.get(self.id, ""), "remote": self.remote(), "rom": self.rom_state(),
                "auto_done": (self.path / ".auto_done").exists(), **self.summary()}


def all_games(include_broken=True) -> list[Game]:
    out = []
    if not config.PROJETS.exists():
        return out
    for d in sorted(config.PROJETS.iterdir()):
        if d.is_dir() and not d.name.startswith(("_", ".")) and (d / "config").exists():
            g = Game(d)
            if include_broken or g.ready:
                out.append(g)
    return out


def get(game_id: str) -> Game:
    d = config.PROJETS / game_id
    if not game_id or "/" in game_id or "\\" in game_id or ".." in game_id or not d.is_dir():
        raise KeyError(f"jeu inconnu : {game_id}")
    return Game(d)


# ---- cross-game sharing (fingerprint DB) ----
def _db():
    return sqlite3.connect(config.FPDB) if config.FPDB.exists() else None


def shared_counts(key) -> dict:
    """{addr: number of OTHER games containing the same function (strict hash)}."""
    if not key or not config.FPDB.exists():
        return {}

    def q():
        con = _db()
        rows = con.execute("""SELECT x.addr, COUNT(DISTINCT y.game) FROM fn x JOIN fn y
                              ON x.strict=y.strict AND y.game<>x.game WHERE x.game=? GROUP BY x.addr""", (key,)).fetchall()
        con.close()
        return dict(rows)
    return _cached(("shared", key), config.FPDB, q)


def portable(game: Game) -> dict:
    """{addr: (other game id, its function name, its source file)} for unmatched functions whose exact twin is
    already matched in another project: the source can be copied from there."""
    key = FP_KEY.get(game.id)
    if not key or not config.FPDB.exists():
        return {}
    others = {FP_KEY[g.id]: g for g in all_games() if g.id in FP_KEY and g.id != game.id and g.ready}
    stamp = (config.FPDB.stat().st_mtime,) + tuple(
        (g.cfg / "delinks.txt").stat().st_mtime for g in others.values() if (g.cfg / "delinks.txt").exists())

    def q():
        con = _db()
        rows = con.execute("""SELECT x.addr, y.game, y.addr, y.name FROM fn x JOIN fn y
                              ON x.strict=y.strict AND y.game<>x.game WHERE x.game=?""", (key,)).fetchall()
        con.close()
        out = {}
        for addr, ogame, oaddr, oname in rows:
            g = others.get(ogame)
            if g is None or addr in out:
                continue
            rng = g.done_ranges()
            i = bisect.bisect_right([r[0] for r in rng], oaddr) - 1
            if i >= 0 and rng[i][0] <= oaddr < rng[i][1]:
                out[addr] = (g.id, oname, rng[i][2])
        return out
    return _cached(("portable", game.id), hash(stamp), q)
