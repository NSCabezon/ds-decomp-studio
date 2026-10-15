# DS Decomp Studio

Logiciel pour organiser la décompilation (matching decomp) de jeux Nintendo DS à plusieurs, humains et IA.

*English summary: a local web app + CLI on top of [ds-decomp (dsd)](https://github.com/AetiasHax/ds-decomp),
mwccarm, m2c, objdiff and decomp-permuter. It lists your DS projects, rates every unmatched function by
difficulty, cuts them into blocks of 50, and runs a shared work queue (claims live in each game repo under
`.studio/`, so people and AIs coordinate through GitHub). See [AGENTS.md](AGENTS.md) for AI agents.*

## Avancement des jeux

<!-- games:start -->
32 jeux, 21 publiés · 36510/232419 fonctions matchées au total · mis à jour le 2026-10-15 (`python studio.py readme`)

| Jeu | Version | Studio | Code matché | Fonctions | ROM | Dépôt |
|---|---|---|---|---|---|---|
| Rayman Raving Rabbids | usa AR5E | Ubisoft Casablanca | `█████░░░░░` 45.95% | 2509/3607 | ✅ | [Rayman-RR-usa-decomp](https://github.com/liolu/Rayman-RR-usa-decomp) |
| Ultimate Spider-Man | fra AUSF | Vicarious Visions | `███░░░░░░░` 29.85% | 2292/4592 | ✅ | [ultimate-spider-man-decomp](https://github.com/liolu/ultimate-spider-man-decomp) |
| Nintendogs Dachshund | usa ADGE | Nintendo EAD | `██░░░░░░░░` 15.64% | 3117/8609 | ✅ | [nintendogs-dachshund-decomp](https://github.com/liolu/nintendogs-dachshund-decomp) |
| Dragon Ball Origins | eu CDZP | Game Republic | `██░░░░░░░░` 15.06% | 2704/5118 | ✅ | [dragon-ball-origins-decomp](https://github.com/liolu/dragon-ball-origins-decomp) |
| Farm Frenzy | usa BFZE | Alawar | `█░░░░░░░░░` 11.58% | 558/1208 | ✅ | [farm-frenzy-decomp](https://github.com/liolu/farm-frenzy-decomp) |
| Cooking Mama | usa ACCE | Office Create | `█░░░░░░░░░` 11.27% | 873/2551 | ✅ | [cooking-mama-decomp](https://github.com/liolu/cooking-mama-decomp) |
| LEGO Star Wars II | usa AL7E | Amaze Entertainment | `█░░░░░░░░░` 11.17% | 2079/4763 | ✅ | [lego-star-wars-ii-the-original-trilogy-decomp](https://github.com/liolu/lego-star-wars-ii-the-original-trilogy-decomp) |
| Resident Evil: Deadly Silence | usa ABHE | Capcom | `█░░░░░░░░░` 10.88% | 2064/5824 | ✅ | [resident-evil-deadly-silence-decomp](https://github.com/liolu/resident-evil-deadly-silence-decomp) |
| Blue Dragon: Awakened Shadow | ger YBUD | Brownie Brown | `█░░░░░░░░░` 8.81% | 3364/11800 | ✅ | [blue-dragon-awakened-shadow-decomp](https://github.com/liolu/blue-dragon-awakened-shadow-decomp) |
| Harvest Moon DS | usa ABCE | Marvelous | `█░░░░░░░░░` 8.71% | 2520/5133 | ✅ | [harvest-moon-ds-decomp](https://github.com/liolu/harvest-moon-ds-decomp) |
| MySims | usa AQIE | EA | `█░░░░░░░░░` 8.49% | 2225/6820 | ✅ | [mysims-decomp](https://github.com/liolu/mysims-decomp) |
| The Simpsons Game | usa YSZE | Amaze Entertainment | `█░░░░░░░░░` 7.52% | 2779/8968 | ✅ | [simpsons-game-decomp](https://github.com/liolu/simpsons-game-decomp) |
| Spider-Man: Web of Shadows | x CS5X | Amaze Entertainment | `█░░░░░░░░░` 7.40% | 2277/5846 | ✅ | [spider-man-web-of-shadows-decomp](https://github.com/liolu/spider-man-web-of-shadows-decomp) |
| Code Lyoko | usa AL5E | Game Machine Studios | `░░░░░░░░░░` 4.49% | 1509/7474 | ✅ | [code-lyoko-decomp](https://github.com/liolu/code-lyoko-decomp) |
| Heroes of Mana | eu AHEP | Brownie Brown | `░░░░░░░░░░` 4.44% | 959/9264 | ✅ | [heroes-of-mana-decomp](https://github.com/liolu/heroes-of-mana-decomp) |
| Livly Garden | jp BLIJ | Brownie Brown | `░░░░░░░░░░` 3.48% | 1024/9012 | ✅ | [livly-garden-decomp](https://github.com/liolu/livly-garden-decomp) |
| Eyeshield 21 | jp AE4J | Eighting | `░░░░░░░░░░` 2.17% | 1150/21940 | ✅ | [eyeshield-21-decomp](https://github.com/liolu/eyeshield-21-decomp) |
| Fairy Tail: Madoushi | jp BH6J | Konami | `░░░░░░░░░░` 1.86% | 1162/11096 | ✅ | [fairy-tail-madoushi-decomp](https://github.com/liolu/fairy-tail-madoushi-decomp) |
| Fairy Tail: Kardia | jp TFTJ | Konami | `░░░░░░░░░░` 1.51% | 1254/12899 | ✅ | [fairy-tail-kardia-decomp](https://github.com/liolu/fairy-tail-kardia-decomp) |
| Powerpuff Girls Z | jp YPPJ | Bandai Namco | `░░░░░░░░░░` 0.43% | 41/2359 | ✅ | [powerpuff-girls-z-decomp](https://github.com/liolu/powerpuff-girls-z-decomp) |
| Spyro: Shadow Legacy | usa ASSE | Amaze Entertainment | `░░░░░░░░░░` 0.21% | 50/3697 | ✅ | [spyro-shadow-legacy-decomp](https://github.com/liolu/spyro-shadow-legacy-decomp) |
| Club House Games | usa ATDE | Agenda | `░░░░░░░░░░` 0.00% | 0/8314 | ✅ | local (pas encore de match) |
| Madagascar | eu AMGP | Vicarious Visions | `░░░░░░░░░░` 0.00% | 0/3444 | ✅ | local (pas encore de match) |
| Professor Layton and the Spectre's Call | eu BLFP | Level-5 | `░░░░░░░░░░` 0.00% | 0/8430 | ✅ | local (pas encore de match) |
| Shrek Forever After | eu VSKV | Griptonite Games | `░░░░░░░░░░` 0.00% | 0/12253 | ✅ | local (pas encore de match) |
| SimAnimals | eu CM3P | EA | `░░░░░░░░░░` 0.00% | 0/2923 | ✅ | local (pas encore de match) |
| SimCity Creator | eu YC2P | EA | `░░░░░░░░░░` 0.00% | 0/6580 | ✅ | local (pas encore de match) |
| Spore Creatures | usa YSPE | Amaze Entertainment | `░░░░░░░░░░` 0.00% | 0/12008 | ✅ | local (pas encore de match) |
| Star Wars Episode III | eu ASTP | Ubisoft | `░░░░░░░░░░` 0.00% | 0/6518 | ✅ | local (pas encore de match) |
| Star Wars: Lethal Alliance | eu AWUP | Ubisoft | `░░░░░░░░░░` 0.00% | 0/8569 | ✅ | local (pas encore de match) |
| The Penguins of Madagascar | eu VPEV | Griptonite Games | `░░░░░░░░░░` 0.00% | 0/8879 | ✅ | local (pas encore de match) |
| Tom and Jerry Tales | eu AJTP | Sensory Sweep | `░░░░░░░░░░` 0.00% | 0/1921 | ✅ | local (pas encore de match) |

*Code matché : part du code des fonctions (ARM9, ITCM, DTCM, overlays) qui recompile à l'octet près. ROM ✅ : la ROM se reconstruit identique à l'originale.*
<!-- games:end -->

## Lancer

Double-clic sur `Studio.cmd` (ou `python studio.py`). L'app s'ouvre sur http://127.0.0.1:8765.

## Ce que fait l'app

| Onglet | Rôle |
|---|---|
| **Jeux** | Tous les projets : % de code matché, état de la ROM, GitHub. **Ajouter** un jeu depuis une ROM de `roms/`, **retirer** un jeu (rangé dans `projets/_archive`, rien n'est supprimé), **cloner** un jeu publié par quelqu'un d'autre. |
| **Travailler** | Le jeu choisi : 6 niveaux de difficulté, les **blocs de 50 fonctions**, la liste des fonctions triées par difficulté, la **carte mémoire**, et les boutons des tâches machine (moulinette, auto-match, verify, ninja, permuter, publier). |
| **Queue** | Qui travaille sur quel bloc (tous les jeux), et la file des tâches machine avec leurs logs. |
| **Engine map** | Les jeux regroupés par studio, et le code moteur partagé entre deux jeux (base d'empreintes `fpdb.sqlite`). |
| **Progression** | XP, niveaux, butin, succès (repris de l'ancien dashboard). |
| **Réglages** | Ton nom, nombre de tâches en parallèle, modèle Qwen, publication des prises sur GitHub. |

### Difficulté

| Niveau | Règle |
|---|---|
| Portable | le même code machine est déjà matché dans un autre jeu : copier sa source |
| Facile → Légendaire | taille de la fonction (≤ 32, 96, 256, 640 octets, plus), un niveau plus facile si auto_match l'a trouvée *presque* bonne (near), un niveau plus dur si le brouillon m2c ne compile pas |

### Blocs et queue

- Les fonctions restantes sont découpées en blocs de 50 de même niveau, dans l'ordre des adresses (les fonctions
  voisines viennent souvent du même fichier source).
- Prendre un bloc écrit `.studio/claims/<bloc>.json` dans le repo du jeu, commit **seulement `.studio/`**, et
  pousse sur GitHub si le jeu a un remote. Deux personnes ne peuvent pas prendre le même bloc.
- Un bloc non touché depuis 48 h retourne dans la queue.
- "Recalculer les blocs" refait les blocs libres avec ce qui reste ; les blocs pris ne bougent pas.
- Bouton **Qwen** : Qwen (Ollama, sur ton PC) prend le bloc et essaie chaque fonction ; un match n'est gardé
  que si `match.py verify` passe.
- Bouton **Voir / brief** : fiche de travail du bloc, à copier-coller à Claude ou à une autre IA.

### Tâches machine

Une seule tâche à la fois par jeu, et au plus N en même temps (Réglages). Elles tournent dans Git Bash après
`env.sh`. Les logs complets sont dans `data/logs/`.

## En ligne de commande (pour les IA et les scripts)

```
python studio.py games
python studio.py blocks <jeu> --free
python studio.py claim <jeu> next --level 1 --who NOM --kind claude
python studio.py brief <jeu> <bloc>
python studio.py touch <jeu> <bloc> --note "func_x: manque le type de la structure"
python studio.py done <jeu> <bloc>
python studio.py release <jeu> <bloc>
python studio.py queue
python studio.py publish <jeu>
```

## Outils partagés (`gametools/`)

Les outils de matching (`auto_match.py`, `match.py`, `probe_compiler.py`, `draft.py`, `permute.py`,
`find_culprits.py`…) ont **une seule version**, dans `gametools/`. Ils lisent ce qui est propre au jeu (version
`usa`/`eu`/`jp`, nom de la ROM, zone `.text`) dans le projet via `tools/project.py` : les fichiers sont donc
identiques dans tous les jeux. Chaque jeu en garde une copie dans son repo (un clone d'un seul jeu fonctionne), et
le bouton « Mettre à jour les outils » (ou `python studio.py sync-tools`) recopie `gametools/` partout.
Pour améliorer un outil : modifier `gametools/`, puis synchroniser. `tools/configure.py` reste propre à chaque jeu.

### Quand la ROM ne se reconstruit plus (`find_culprits.py`)

Une fonction peut être à 100 % dans objdiff et casser quand même la ROM (literal pool dans un autre ordre, fonction
`static`, fichier qui décale tout). `python tools/find_culprits.py` compare chaque module reconstruit avec
l'original, octet par octet, et désigne le fichier fautif en **une seule compilation**. `--fix` retire les fichiers
fautifs non commités (rangés dans `build/culprits/`) et recommence jusqu'à ce que la ROM soit identique.
auto_match l'utilise tout seul : un lot dont le verify échoue n'est plus annulé en entier.

## Installation sur un autre PC

L'app attend ce dossier à côté de la boîte à outils DS :

```
decomp ds/
  studio/        ce repo
  projets/       un dossier par jeu (repos <jeu>-decomp)
  roms/          tes ROMs (jamais publiées)
  tools/         dsd, mwccarm, m2c, decomp-permuter, fingerprint.py, new_project.py
  env.sh         met les outils dans le PATH
  fpdb.sqlite    base d'empreintes (optionnelle)
```

Ou bien `DSSTUDIO_ROOT=<dossier>`. Python 3.10+ seulement (bibliothèque standard ; `psutil` conseillé pour
arrêter les tâches). Git Bash est nécessaire pour lancer les tâches sous Windows.

## Règles

- Jamais de ROM, d'assets ou de binaires du jeu sur GitHub : la publication refuse un repo qui suit des fichiers
  `.nds`, `.bin`, `extract/`, `build/`… ou des fichiers de plus de 20 Mo.
- Ne jamais utiliser de code source fuité. Salle blanche : le binaire et les projets publics seulement.
- Aucun commit sans `VERIFY PASSED`. Formater avec `pre-commit run clang-format` avant (le CI des jeux le vérifie, `.studio/` est exclu).

Licence : CC0-1.0.
