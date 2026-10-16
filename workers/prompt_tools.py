"""What the AI agents are told about a try: only the part that differs, hints read from the difference, a finer
score, a different angle for each version, and the exact prototypes of the functions called.

Rows are (target line, candidate line) of the side-by-side disassembly (objdump text: "mnemonic operands")."""
import difflib
import re

ADDR = re.compile(r"0x[0-9a-f]{6,}")
REG = re.compile(r"\b(r\d+|ip|lr|sp|pc|fp|sl|sb)\b")
COND = "eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al"
INVERSE = {"eq": "ne", "ne": "eq", "ge": "lt", "lt": "ge", "gt": "le", "le": "gt", "hi": "ls", "ls": "hi",
           "cs": "cc", "cc": "cs", "hs": "lo", "lo": "hs", "mi": "pl", "pl": "mi"}


def norm(line: str) -> str:
    """Absolute addresses (branch targets, pool addresses) differ between candidate and target for no reason."""
    return ADDR.sub("X", line.strip())


def mnem(line: str) -> str:
    return line.split(None, 1)[0] if line.strip() else ""


def mnemonic_list(lines: list[str]) -> list[str]:
    return [mnem(l) or "?" for l in lines]


def edit_distance(target: list[str], cand: list[str]) -> int:
    """Instructions to add, remove or change to go from the candidate to the target (normalized lines). Moves when
    the number of differing instructions does not: a try can be closer without fixing a whole instruction."""
    t, c = [norm(x) for x in target], [norm(x) for x in cand]
    same = sum(b.size for b in difflib.SequenceMatcher(None, t, c, autojunk=False).get_matching_blocks())
    return len(t) + len(c) - 2 * same


def compact_diff(target: list[str], cand: list[str], context: int = 5, limit: int = 60) -> str:
    """Side-by-side lines, only around the differences (± context lines), '...' for the rest."""
    n = max(len(target), len(cand))
    rows = [(target[i] if i < len(target) else "", cand[i] if i < len(cand) else "") for i in range(n)]
    bad = [i for i, (a, b) in enumerate(rows) if norm(a) != norm(b)]
    if not bad:
        return "(identical)"
    keep = sorted({j for i in bad for j in range(max(0, i - context), min(n, i + context + 1))})
    out, last = [f"     {'TARGET':38} | CANDIDATE"], -1
    for j in keep:
        if j != last + 1:
            out.append("     ...")
        a, b = rows[j]
        out.append(f"{j:3} {'*' if j in bad else ' '} {a:38} | {b}")
        last = j
    if last < n - 1:
        out.append("     ...")
    if len(out) > limit:
        out = out[:limit] + [f"     ... ({len(bad)} differing lines in all)"]
    return "\n".join(out)


def _cond(m: str) -> tuple[str, str]:
    """('b', 'ne') from 'bne'; ('ldrh', '') from 'ldrh'."""
    mm = re.fullmatch(rf"(b|bl|bx)({COND})", m)
    return (mm.group(1), mm.group(2)) if mm else (m, "")


def hints(target: list[str], cand: list[str]) -> list[tuple[str, str]]:
    """[(strategy key, advice)] read from the difference, most useful first."""
    out = []

    def add(key, text):
        if all(t != text for _k, t in out):
            out.append((key, text))
    if len(cand) != len(target):
        diff = len(cand) - len(target)
        tm, cm = [mnem(x) for x in target], [mnem(x) for x in cand]
        extra = [m for m in set(cm) if cm.count(m) > tm.count(m)]
        missing = [m for m in set(tm) if tm.count(m) > cm.count(m)]
        add("ops", f"the candidate has {abs(diff)} instruction(s) {'too many' if diff > 0 else 'too few'}: "
                   f"{'remove an operation' if diff > 0 else 'an operation is missing'}"
                   + (f" (extra: {', '.join(sorted(extra)[:4])})" if extra else "")
                   + (f" (missing: {', '.join(sorted(missing)[:4])})" if missing else ""))
        joined = "\n".join(cand)
        if diff > 0 and re.search(r"^lsl\b.*#(16|24)\n(?:.*\n)?asr\b.*#\1$", joined, re.M):
            add("types", "the candidate sign-extends a value (lsl+asr): a cast or an s8/s16 variable that the target "
                         "does not have")
        if diff > 0 and re.search(r"^lsl\b.*#16\n(?:.*\n)?lsr\b.*#16$|^and\w* [^,]+, [^,]+, #255$", joined, re.M):
            add("types", "the candidate zero-extends a value (u8/u16 cast or variable): use s32/u32 there")
    calls_t = sum(1 for x in target if re.match(r"blx?\s", x))
    calls_c = sum(1 for x in cand if re.match(r"blx?\s", x))
    if calls_c > calls_t:
        add("expr", f"the candidate makes {calls_c - calls_t} call(s) more than the original: the original has that "
                    "code inlined (write the operation out instead of calling the function, or use a macro-like "
                    "expression)")
    elif calls_t > calls_c:
        add("expr", f"the original makes {calls_t - calls_c} call(s) more: where the candidate computes something "
                    "itself, the original calls a function")
    # compare instructions that correspond (aligned like a diff: an inserted line does not shift the rest)
    sm = difflib.SequenceMatcher(None, [norm(x) for x in target], [norm(x) for x in cand], autojunk=False)
    pairs = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "replace":
            pairs += list(zip(target[i1:i2], cand[j1:j2]))
    differing = [(a, b) for a, b in pairs if norm(a) != norm(b)]
    if differing and len(target) == len(cand) and all("[pc" in a and "[pc" in b and mnem(a) == mnem(b)
                                                      for a, b in differing):
        add("order", "only literal pool loads differ (ldr ..., [pc, #...]): the C is right, the constants and "
                     "addresses are used in another order. Use them in the order of the target (reorder the "
                     "statements, or the first use of each global/constant)")
    for a, b in pairs:
        if norm(a) == norm(b):
            continue
        ma, mb = mnem(a), mnem(b)
        if {ma, mb} in ({"ldrsh", "ldrh"}, {"ldrsb", "ldrb"}):
            want = {"ldrsh": "s16", "ldrh": "u16", "ldrsb": "s8", "ldrb": "u8"}[ma]
            add("types", f"the target loads with {ma}: the value is {want} (the candidate uses {mb})")
        elif {ma, mb} == {"ldr", "ldrh"} or {ma, mb} == {"ldr", "ldrb"} or {ma, mb} == {"str", "strh"} \
                or {ma, mb} == {"str", "strb"}:
            add("types", f"the target uses {ma} where the candidate uses {mb}: change the width of that field/variable")
        elif ma == mb and REG.sub("R", a) == REG.sub("R", b):
            add("order", "only registers differ: change the order of the declarations or of the statements, or "
                         "use/remove a temporary variable")
        else:
            (ba, ca), (bb, cb) = _cond(ma), _cond(mb)
            if ba == bb == "b" and ca and cb and INVERSE.get(ca) == cb:
                add("control", f"the branch is inverted (target {ma}, candidate {mb}): invert the if condition and "
                               "swap its branches")
            elif ma.startswith("cmp") and mb.startswith("cmp"):
                add("control", "the comparison differs: check the constant (< vs <=, off by one) and the signedness "
                               "of the compared values")
            elif {ma, mb} & {"mul", "mla"} and {ma, mb} & {"lsl", "add", "mov"}:
                add("expr", "multiplication written differently (x * k vs shifts/additions)")
            elif ma.startswith(("push", "stmdb", "pop", "ldmia")) or mb.startswith(("push", "stmdb", "pop", "ldmia")):
                add("vars", "saved registers differ: the function uses more/fewer variables living across calls")
    return out


STRATEGIES = {
    "types": "change ONLY the types (signed/unsigned, s8/s16/s32, pointer types, casts)",
    "order": "change ONLY the order of declarations and independent statements",
    "control": "change ONLY the control flow (if/else order, inverted conditions, early return, goto vs loop)",
    "loop": "change ONLY the loop form (for/while/do-while, index vs pointer increment)",
    "expr": "change ONLY how expressions are written (temporaries, split or merge expressions)",
    "vars": "change ONLY the variables (add or remove temporaries, reuse one variable)",
    "ops": "add or remove the operation the hint points at, keep the rest",
    "free": "any change you think is right",
}
ROTATION = ["types", "order", "control", "loop", "expr", "vars", "free"]


def pick_strategies(hint_list: list[tuple[str, str]], rnd: int, n: int) -> list[str]:
    """n different angles for one request: the ones the hints point at first, then the rotation (shifted at every
    round so the same angles do not come back each time)."""
    keys = list(dict.fromkeys(k for k, _t in hint_list))
    start = (rnd * n) % len(ROTATION)
    for k in ROTATION[start:] + ROTATION[:start]:
        if k not in keys:
            keys.append(k)
    return [STRATEGIES[k] for k in keys[:n]]


# Fake matches (asm, preprocessor tricks...): gametools/fakematch.py, loaded by file path (studio/gametools must not
# go on sys.path here: auto_match/project would resolve to the studio copies instead of the game's)
def _load_fakematch():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "studio_fakematch", Path(__file__).resolve().parent.parent / "gametools" / "fakematch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.fake_match


fake_match = _load_fakematch()


def prototypes(asm: str, protos_text: str, self_name: str) -> list[str]:
    """Prototypes of the functions the assembly calls, from m2c_protos.h / engine.h text."""
    called = list(dict.fromkeys(re.findall(r"^\s+bl?x?(?:%s)?\s+(\w+)\s*$" % COND, asm or "", re.M)))
    called = [c for c in called if not REG.fullmatch(c) and c != self_name]
    out = []
    for c in called:
        m = re.search(rf"^[^#/\n][^\n;]*\b{re.escape(c)}\s*\([^;]*\);", protos_text, re.M)
        if m:
            out.append(m.group(0).strip())
    return out
