"""HTTP server of the studio (standard library only). Serves web/ and a JSON API on 127.0.0.1."""
import json
import mimetypes
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import blocks, brief, config, difficulty, engine, games, jobs, projects, toolsync, xp


def overview():
    gl = [{**g.info(), "tools_behind": toolsync.status(g)["behind"]} for g in games.all_games()]
    return {"games": gl, "settings": config.settings(), "levels": difficulty.LEVELS, "kinds": blocks.KINDS,
            "queue": blocks.queue_overview(), "archived": projects.archived(),
            "jobdefs": {k: {"label": v[0], "scope": v[1], "desc": v[3]} for k, v in jobs.DEFS.items()}}


def game_view(gid):
    g = games.get(gid)
    bl = blocks.view(g) if g.ready else []
    per_level = {}
    for b in bl:
        e = per_level.setdefault(b["level"], {"blocks": 0, "free": 0, "claimed": 0, "done": 0, "left": 0})
        e["blocks"] += 1
        e["left"] += b["left"]
        e["free" if b["state"] in ("free", "expired") else b["state"]] += 1
    return {"game": {**g.info(), "tools_behind": toolsync.status(g)["behind"]}, "blocks": bl, "per_level": per_level, "generation": blocks.load(g).get("generation", 0)}


KINDS_FILTER = {  # "what is left" split by what can work on it
    "auto": lambda r: r["auto_tools"],                                   # ARM, main module: automatic tools
    "thumb": lambda r: r["mode"] == "thumb",
    "overlay": lambda r: r["module"].startswith("ov"),
    "tcm": lambda r: r["module"] in ("itcm", "dtcm"),
    "manual": lambda r: not r["auto_tools"],                             # everything the tools do not handle
}


def function_list(gid, level, q, state, limit, kind=""):
    g = games.get(gid)
    rows = g.functions()
    if kind in KINDS_FILTER:
        rows = [r for r in rows if KINDS_FILTER[kind](r)]
    if state == "done":
        out = [dict(r) for r in rows if r["done"]]
    else:
        out = difficulty.rate_all(rows, games.portable(g))
        if level not in (None, ""):
            out = [r for r in out if r["level"] == int(level)]
    if q:
        out = [r for r in out if q.lower() in r["name"].lower()]
    out.sort(key=lambda r: (r.get("level", 0), r.get("score", 0)) if state != "done" else r["addr"])
    # block of each function
    owner = {f: b["id"] for b in blocks.load(g)["blocks"] for f in b["functions"]}
    for r in out:
        r["block"] = owner.get(r["name"], "")
    return {"total": len(out), "rows": out[:limit]}


def asm_of(gid, name):
    import re
    g = games.get(gid)
    for f in (g.path / "build").glob("*/asm/**/*.s"):
        t = f.read_text(encoding="utf-8", errors="replace")
        if name not in t:
            continue
        m = re.search(rf"^{re.escape(name)}: .*?^\s+(?:arm|thumb)_func_end {re.escape(name)}$", t, re.S | re.M)
        if m:
            return m.group(0)
    return "(assembleur introuvable : lancez la tache 'Desassembler' sur ce jeu)"


def warm_up():
    """Computes in the background what the first page views need (functions, cross-game twins, tool state of every
    game): the first click on a game is then as fast as the next ones."""
    for g in games.all_games():
        try:
            if g.ready:
                g.functions()
                games.portable(g)
                toolsync.status(g)
        except Exception:
            traceback.print_exc()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, obj, code=200, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith(("text", "application/j")) else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if not u.path.startswith("/api/"):
                name = u.path.strip("/") or "index.html"
                f = (config.WEB / name).resolve()
                if config.WEB.resolve() in f.parents and f.is_file():
                    return self.send(f.read_bytes(), ctype=mimetypes.guess_type(f.name)[0] or "text/plain")
                return self.send({"error": "not found"}, 404)
            p = u.path[5:]
            if p == "overview":
                return self.send(overview())
            if p == "game":
                return self.send(game_view(q["id"]))
            if p == "functions":
                return self.send(function_list(q["game"], q.get("level"), q.get("q", ""), q.get("state", "todo"),
                                               int(q.get("limit", 300)), q.get("kind", "")))
            if p == "block":
                g = games.get(q["game"])
                return self.send({"functions": blocks.functions_of(g, q["id"]), "brief": brief.brief(g, q["id"])})
            if p == "asm":
                return self.send({"asm": asm_of(q["game"], q["name"])})
            if p == "map":
                return self.send(engine.memory_map(games.get(q["game"])))
            if p == "engine":
                return self.send({**engine.cross_games(), "studios": engine.studios()})
            if p == "jobs":
                return self.send({"jobs": jobs.view()})
            if p == "log":
                return self.send({"log": jobs.full_log(int(q["n"]))})
            if p == "xp":
                done = sum(len(blocks.finished(g)) for g in games.all_games() if g.ready)
                return self.send(xp.update(done))
            if p == "roms":
                return self.send({"roms": projects.roms_without_project()})
            if p == "github":
                return self.send({"repos": projects.published_on_github()})
        except KeyError as e:
            return self.send({"error": str(e)}, 400)
        except Exception as e:
            traceback.print_exc()
            return self.send({"error": repr(e)}, 500)
        self.send({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0) or 0)) or b"{}")
            p = u.path[5:]
            s = config.settings()
            if p == "claim":
                return self.send(blocks.claim(games.get(d["game"]), d.get("block"), d.get("who") or s["who"],
                                              d.get("kind", "human"), d.get("level"), d.get("note", "")))
            if p == "qwen_swarm":
                # Qwen agents on several blocks at once: claims them for Qwen, then one job (N agents) for all
                g = games.get(d["game"])
                ids = d.get("blocks") or []
                if not ids:
                    lvl = d.get("level")
                    ids = [b["id"] for b in blocks.view(g) if b["state"] in ("free", "expired")
                           and (lvl is None or b["level"] == int(lvl))][:int(d.get("count") or 1)]
                if not ids:
                    return self.send({"error": "aucun bloc libre a donner a Qwen"})
                taken = []
                for bid in ids:
                    r = blocks.claim(g, bid, f"qwen-{s['who']}", "qwen")
                    if r.get("ok"):
                        taken.append(bid)
                if not taken:
                    return self.send({"error": "aucun bloc n'a pu etre pris"})
                params = {k: d[k] for k in ("agents", "minutes", "max", "model", "batch") if d.get(k) not in (None, "")}
                params["blocks"] = taken
                return self.send({**jobs.submit("qwen", g.id, params, s["who"]), "blocks": taken})
            if p == "release":
                return self.send(blocks.release(games.get(d["game"]), d["block"], None, bool(d.get("finished"))))
            if p == "touch":
                return self.send(blocks.touch(games.get(d["game"]), d["block"], note=d.get("note")))
            if p == "rebuild":
                data = blocks.rebuild(games.get(d["game"]))
                return self.send({"ok": True, "blocks": len(data["blocks"])})
            if p == "run":
                return self.send(jobs.submit(d["id"], d.get("game"), d.get("params") or {}, s["who"]))
            if p == "cancel":
                return self.send({"ok": jobs.cancel(int(d["n"]))})
            if p == "qwen_stop":
                g = games.get(d["game"])
                (g.path / "build" / "qwen_auto").mkdir(parents=True, exist_ok=True)
                (g.path / "build" / "qwen_auto" / "STOP").write_text("stop")
                return self.send({"ok": True})
            if p == "settings":
                return self.send(config.save_settings(d))
            if p == "archive":
                return self.send(projects.archive(d["game"]))
            if p == "restore":
                return self.send(projects.restore(d["name"]))
            if p == "clone":
                return self.send(projects.clone(d["url"]))
        except KeyError as e:
            return self.send({"error": str(e)}, 400)
        except Exception as e:
            traceback.print_exc()
            return self.send({"error": repr(e)}, 500)
        self.send({"error": "bad request"}, 400)


class Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second server bind the same port and steal half of the requests
    allow_reuse_address = False
    daemon_threads = True


def serve(open_browser=True):
    url = f"http://127.0.0.1:{config.PORT}"
    try:
        srv = Server(("127.0.0.1", config.PORT), H)
    except OSError:
        print(f"Le port {config.PORT} est deja pris : le studio (ou l'ancien dashboard) tourne deja. Ouverture de {url}")
        if open_browser:
            webbrowser.open(url)
        return
    jobs.start_scheduler()
    threading.Thread(target=warm_up, daemon=True).start()
    print(f"DS Decomp Studio sur {url}  (Ctrl+C pour arreter)")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
