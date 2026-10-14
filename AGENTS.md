# Instructions for AI agents

DS Decomp Studio coordinates people and AIs working on Nintendo DS matching decompilations. Work is split into
**blocks of 50 functions** of similar difficulty. Always take a block before working, so nobody duplicates effort.

## Workflow

```shell
python studio/studio.py games                                  # projects and progress
python studio/studio.py blocks <game> --free                   # free blocks, easiest first
python studio/studio.py claim <game> next --who <agent-name> --kind claude [--level N]
python studio/studio.py brief <game> <block>                   # your work sheet: functions, commands, rules
# ... match functions in projets/<game>/ ...
python studio/studio.py touch <game> <block> --note "..."      # still working / what blocks you
python studio/studio.py done <game> <block>                    # or `release` to give it back unfinished
```

## Rules

1. Work only inside `projets/<game>/`. Run `source env.sh` (Git Bash) first.
2. Never commit unless `python tools/match.py verify` prints `VERIFY PASSED`. Commit only the files you changed
   (`src/`, `include/`, `config/`), never `git add -A`.
3. ASCII-only sources, comments in English. `asm` functions only for instructions the compiler never emits.
4. Never use leaked source code. Never commit ROMs, extracted assets or build outputs.
5. `.studio/` is written by the studio only (through the commands above).
6. Level "Portable" functions have an identical twin already matched in another game: the brief names the source
   file to copy.

## Layout

- `dsstudio/games.py`: project discovery, functions, matched state (`delinks.txt`), cross-game twins (`fpdb.sqlite`).
- `dsstudio/difficulty.py`: levels. `dsstudio/blocks.py`: blocks and claims. `dsstudio/jobs.py`: machine task queue.
- `dsstudio/server.py` + `web/`: the web app. `workers/qwen_block.py`: local Qwen agents on blocks.
- `gametools/`: the ONLY source of the matching tools copied into every game's `tools/` (`studio.py sync-tools`).
  They read game-specific values from `tools/project.py`. Change tools here, never in a game's copy.
  `gametools/find_culprits.py` finds the files that break the ROM from one build (byte comparison).
