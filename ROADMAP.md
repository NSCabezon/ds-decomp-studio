# Roadmap : de la décomp au lanceur natif de tous les jeux

**But final** : un seul logiciel PC qui lance nativement (sans émulateur) chaque jeu DS décompilé, construit avec les
mêmes outils pour tous les jeux. **Premier jeu : Rayman Raving Rabbids** : pas d'overlays, C pur (moteur OpenSpace),
environ 42 % du module principal déjà matché.

Principe directeur : **tout ce qui est commun aux jeux DS doit être fait une seule fois**, dans le Studio ou dans le
runtime partagé, jamais dans un jeu. Les jeux DS partagent le NitroSDK, NitroSystem, la libc MSL et le même matériel :
un outil ou une couche faite pour Rayman doit servir tel quel au jeu suivant.

```
 ROM (fournie par l'utilisateur)
   │  étapes 1-2 : outils de décomp (Studio)        étape 3 : lisibilité      étape 4 : shiftable
   ▼
 src/ C qui recompile au bit près  ──────────────►  noms, types, headers  ──►  build modifiable
   │
   │  étape 5 : assets (extraits de la ROM de l'utilisateur, jamais distribués)
   ▼
 étape 6 : runtime "nitro-pc" commun  +  module natif par jeu (.dll)  +  lanceur unique
```

---

## Étape 1 : la ROM se reconstruit (base de tout)

| Outil | État | À faire |
|---|---|---|
| `dsd init` + `new_project.py` | ✅ | — |
| `reloc_fixes.py` (faux pointeurs de dsd) | ✅ | généraliser la détection automatique |
| `find_culprits.py` | ✅ | — |
| Réparer les 5 jeux KO (Spore, Club House, Tom & Jerry, Layton, SW Lethal Alliance) | 🔴 | outil de bissection : comparer module par module, puis section par section, pour isoler ce que dsd recompose mal |

**Critère de sortie** : `VERIFY PASSED` sur le jeu. Rayman : ✅.

## Étape 2 : 100 % des fonctions matchées

| Outil | État | À faire |
|---|---|---|
| `auto_match.py` (m2c + variantes) | ✅ main ARM | **étendre aux overlays et à l'ITCM/DTCM** ; mode Thumb (`-thumb`) |
| `donor_match.py` (autres décomps + nos autres jeux) | ✅ main ARM | idem overlays et Thumb ; indexer NitroSystem/MSL avec plus de profils de compilateur (1.2/sp3, 2.0/sp2…) pour couvrir les vieilles versions du SDK |
| Permuter, Qwen, Claude par blocs | ✅ | brief par bloc avec le contexte du moteur (types, fonctions voisines déjà matchées) |
| Fonctions asm (SDK, `mrs/msr/swp`) | ✅ | — |
| **Données** (`.data`, `.rodata`, `.bss`) | 🔴 | aujourd'hui seul `.text` compte : outil qui déclare les tables, chaînes et constantes en C (pour le natif, toute donnée doit exister dans le source) |
| ARM7 | ⚪ | **inutile pour le natif** : c'est le firmware son/wifi/tactile standard de Nintendo, remplacé par le runtime (étape 6) |

**Critère de sortie** : le module principal + ITCM/DTCM (+ overlays) à 100 % code et 100 % données, VERIFY PASSED.
Rayman : main 42 % → 100 %, puis ITCM/DTCM, puis les données.

Priorités Rayman :
1. Portable (Reprendre) sur tous les blocs L0.
2. Auto-match + permuter sur les near misses.
3. Qwen / Claude sur les niveaux Facile et Moyen, bloc par bloc.
4. La main sur les niveaux Expert et Légendaire, avec les headers OpenSpace (REFERENCES-rayman.md : ACP_Ray2, ray3).

## Étape 3 : code lisible (noms, types, fichiers)

Sans ça, le portage est impossible : il faudra modifier ce code, donc le comprendre.

| Outil | État / à faire |
|---|---|
| **Nommage automatique** | ✅ `gametools/names.py` (job Studio « Nommer ») : empreinte de chaque fonction (matchée ou non) cherchée dans donors.sqlite, vote pondéré (ntrtwl > dossiers de libs > rien pour le code d'autres jeux), les relocations des donneurs nomment aussi les fonctions appelées et les données, et départagent les petites fonctions. Renomme `symbols.txt`, sources, noms de fichiers, `.studio/blocks.json`, puis rebuild ninja ; les noms fautifs sont rendus (incrémental). Rayman : ~740 noms trouvés ; Heroes of Mana : 855 noms, 539 fichiers → 372 vrais fichiers, VERIFY PASSED. À faire : propager les noms faits à la main d'un jeu à l'autre (fpdb) ; overlays |
| **Headers SDK partagés** | un seul `include/nitro/` (repris de ntrtwl) pour tous les jeux, à la place des `M2C_UNK` et des prototypes devinés |
| **Regroupement en fichiers** | 🟡 `gametools/regroup.py` (job « Regrouper ») : fichiers voisins venant du même fichier d'origine SDK/MSL (trouvé par le nom dans donors.sqlite) fusionnés en `src/nitro/os/os_thread.c`, `src/nnsys/snd/main.c`, `src/msl/printf.c`… ; chaque fusion est compilée et comparée à la ROM avant d'être écrite. À faire : code du jeu (les noms d'assert ne couvrent que 19 fonctions dans Rayman : il faudra les bornes des fichiers déduites des données `.data`/`.rodata` par fichier) |
| **Nettoyage m2c** | 🟡 `gametools/cleanup.py` (job « Nettoyer ») : notes de m2c, lignes vides, clang-format, ROM reconstruite. À faire (passe vérifiée fichier par fichier avec `regroup.compile_check`) : vrais prototypes du SDK à la place des `M2C_UNK`, `p->field` à la place de `M2C_FIELD` une fois les structures connues |
| **Types du moteur** | headers par moteur (OpenSpace pour Rayman), partagés par les jeux du même moteur (voir Engine map du Studio) |

Piège connu : le linker identifie les objets par leur **nom de fichier seul, sans dossier ni casse** (`OS_UnLockCartridge.c` et `OS_UnlockCartridge.c` = même objet) : tout nom de fichier doit être unique dans le jeu.

**Critère de sortie** : 0 fichier `src/auto/` restant, aucun `M2C_UNK` dans les fonctions du jeu, structures principales
nommées.

## Étape 4 : build « shiftable » (le code peut bouger)

Aujourd'hui le build ne marche que si chaque octet reste à sa place. Pour modifier ou porter, il faut que les adresses
soient recalculées par le linker.

| Outil | À faire |
|---|---|
| Relocations complètes | toute adresse dans le code et les données passe par un symbole (aucun nombre `0x02xxxxxx` en dur) ; détecteur qui liste les adresses littérales restantes |
| **Test de décalage** | job Studio « shift test » : insère N octets au début du module, rebuild, lance la ROM dans melonDS en headless et compare des captures d'écran avec la ROM d'origine |
| Linker script généré | LCF construit à partir des sources, plus de positions figées |

**Critère de sortie** : la ROM décalée démarre et joue comme l'originale (Rayman : écran titre + premier mini-jeu).
C'est aussi l'étape qui ouvre le **modding**.

## Étape 5 : assets

Les assets ne sont **jamais distribués** : le lanceur les extrait de la ROM de l'utilisateur au premier lancement.

| Outil | À faire |
|---|---|
| Formats Nitro communs | extracteurs/convertisseurs partagés : NARC, NCGR/NCLR/NSCR/NCER/NANR (2D), NSBMD/NSBTX/NSBCA (3D), SDAT/SSEQ/SBNK/SWAR (son), BMG/texte |
| Formats par moteur | un module par moteur (OpenSpace pour Rayman ; voir raymap, qui lit déjà `rrr_ds`) |
| Inventaire | job Studio qui liste les fichiers de la ROM, leur format reconnu ou non, et le % d'assets compris par jeu |

**Critère de sortie** : tous les fichiers de la ROM de Rayman identifiés et lisibles par le runtime.

## Étape 6 : runtime natif commun + lanceur unique

### Architecture

- **`nitro-pc` (commun à tous les jeux)** : réimplémentation PC du NitroSDK et de NitroSystem. C'est la pièce
  centrale : comme tous les jeux appellent les mêmes fonctions du SDK, les réécrire une fois sert à tous.
  - `OS` : threads (fibres ou threads hôtes), alarmes, IRQ simulées (VBlank à 60 Hz), arènes mémoire ;
  - `FS` : fichiers lus depuis l'extraction de la ROM de l'utilisateur ; les overlays sont chargés comme des modules ;
  - `GX/G2/G3` : rendu des deux moteurs 2D et du moteur 3D DS sur GPU (OpenGL/Vulkan), avec une option haute
    résolution ;
  - `SND` (NitroSystem) : séquenceur SDAT sur la sortie audio du PC ;
  - `PAD/TP` : clavier, manette, souris pour le stylet ; `CARD` : sauvegardes en fichiers ; `RTC` : horloge du PC.
- **Couche registres** : le code de jeu écrit parfois directement dans le matériel (`*(vu32 *)0x04000000`). Ces accès
  passent par une table de registres émulés que le renderer lit, comme un émulateur, mais seulement pour ces accès.
- **Module natif par jeu** : le C de la décomp compilé par clang/MSVC en `.dll` 32 bits (pointeurs 32 bits comme sur
  DS, pour ne pas tout réécrire au début), lié au runtime. Les fonctions du SDK de la décomp sont remplacées par celles
  de `nitro-pc`.
- **Lanceur** : liste les jeux, demande la ROM une fois (vérifiée par SHA-1), extrait les assets, gère les manettes,
  la résolution et les sauvegardes, puis charge le module du jeu.

### Outils à créer pour y arriver

| Outil | Rôle |
|---|---|
| `compat.h` (mwcc → clang/MSVC) | `__declspec`, `asm` inline, pragmas, `#pragma thumb`, alignements, `-enum int`, `char` signé |
| Convertisseur des fonctions `asm` | réécrire en C les fonctions asm du jeu (`swp`, `mrs`/`msr`… deviennent des intrinsèques ou des appels runtime) |
| « Native build » dans le Studio | compile chaque jeu en `.dll` avec la même config ; rapport des erreurs par fichier = la nouvelle liste « à faire » |
| Tests de comparaison | lancer la même séquence d'entrées dans melonDS et dans le natif, puis comparer les images (régressions du renderer) |

### Ordre pour Rayman

1. Lancer la logique seule : compiler le jeu en natif avec un runtime vide (stubs) et atteindre la boucle principale.
2. Fichiers + mémoire (FS, arènes).
3. 2D (menus, écran tactile), puis entrées.
4. 3D (le moteur OpenSpace utilise G3), puis son.
5. Jouable du début à la fin ; comparaison image par image avec melonDS.

**Critère de sortie** : Rayman se lance depuis le lanceur, jouable, sans émulateur.
Le jeu suivant ne devrait demander que **son module** et ses formats d'assets propres.

---

## Ordre de travail recommandé

| Phase | Rayman | Outils communs (Studio) |
|---|---|---|
| **A** (maintenant) | finir le module principal (étape 2) | auto/donor sur overlays + Thumb ; outil « données » |
| **B** | ITCM/DTCM + données à 100 % | nommage automatique SDK ; headers `include/nitro/` partagés |
| **C** | code lisible (étape 3), structures OpenSpace | fusion des `src/auto` en vrais fichiers ; nettoyage m2c |
| **D** | shiftable (étape 4) | job « shift test » avec melonDS headless |
| **E** | assets Rayman (étape 5) | extracteurs Nitro communs |
| **F** | portage natif de Rayman | `nitro-pc`, `compat.h`, native build, lanceur |
| **G** | jeu 2, 3… | seulement les modules propres à chaque jeu |

Les phases A à C peuvent avancer en parallèle sur les autres jeux avec les mêmes outils. Le runtime (F) peut commencer
dès que Rayman est à 100 % sur l'étape 2, sans attendre la fin du nettoyage.

## Points de vigilance

- **Légal** : aucun asset ni ROM distribués ; le lanceur ne fonctionne qu'avec la ROM de l'utilisateur. Le code
  vient de la décomp (clean-room, jamais de source leaké) ; respecter les licences des décomps externes
  (`decomps-externes/sources.tsv`).
- **Timing** : certains jeux dépendent du rythme exact du matériel (VBlank, DMA) ; le runtime simule ces signaux, il
  ne les ignore pas.
- **Mémoire** : les jeux supposent 4 Mo de RAM à des adresses fixes ; le runtime réserve une arène équivalente.
- **Taille** : un portage natif représente beaucoup de travail ; le gain vient de la réutilisation (SDK, moteurs).
  Chaque outil doit donc être écrit pour tous les jeux dès le départ.
