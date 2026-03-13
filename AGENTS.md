# AGENTS.md — rosdistro Codebase Guide

This file documents the structure, conventions, tooling, and gotchas of the
`rosdistro` repository for the benefit of automated agents (and humans) working
in this codebase.

---

## Repository Purpose

`rosdistro` is the **central metadata index** for the ROS ecosystem. It serves
three main audiences:

1. **Release managers** — submit new package versions via `bloom`.
2. **ROS Build Farm** — reads distribution files to know what to compile.
3. **End users** — `rosdep update` downloads this repo's metadata to resolve
   system dependencies (`apt install`, `pip install`, etc.).

---

## Top-Level Layout

```
rosdistro/
├── index.yaml / index-v4.yaml   # Entry point: lists all ROS distributions
├── <distro>/                    # Per-ROS-distro folders (humble/, jazzy/, etc.)
│   └── distribution.yaml        # Released packages, versions, repo URLs
├── rosdep/                      # OS dependency rules (the most-edited area)
│   ├── base.yaml                # Non-Python system packages (~1 300 rosdep keys)
│   ├── python.yaml              # Python packages (~1 000 rosdep keys)
│   ├── ruby.yaml                # Ruby packages
│   └── osx-homebrew.yaml        # macOS Homebrew packages
├── scripts/                     # Maintenance utilities
│   ├── check_rosdep.py          # Formatting validator (run after every edit)
│   ├── clean_rosdep_yaml.py     # PyYAML-based formatter (use with care, see caveats)
│   └── convert_resolute_wildcard.py  # Wildcard-conversion script (added 2025)
├── test/
│   └── rosdep_repo_check/       # CI tool: verifies packages exist in OS repos
│       └── config.yaml          # Supported OS versions and package sources
└── releases/                    # Legacy ROS 1 release files
```

---

## rosdep YAML Structure

### File: `rosdep/base.yaml`

Each top-level key is a **rosdep key** — a platform-agnostic dependency name
used in `package.xml` files. The value maps OS names to package names.

```yaml
# Simplest form: same package everywhere
cmake:
  ubuntu: [cmake]
  debian: [cmake]
  fedora: [cmake]

# Per-distro overrides: wildcard = newest, older different names are explicit
libopencv-core:
  debian:
    bookworm: [libopencv-core406]
    trixie:   [libopencv-core410]
  ubuntu:
    '*':   [libopencv-core410]    # resolute (newest) and future distros
    jammy: [libopencv-core4.5d]   # jammy differs — keep explicit
    noble: [libopencv-core406t64] # noble differs — keep explicit
```

### File: `rosdep/python.yaml`

Python packages follow Pattern B (see Wildcard section):

```yaml
python3-somelib:
  ubuntu:
    '*':   [python3-somelib]             # newest (resolute) → future inherits deb
    focal: {pip: {packages: [somelib]}}  # focal had no deb → explicit pip
    jammy: {pip: {packages: [somelib]}}  # jammy had no deb → explicit pip (if applicable)
```

> **Historical note**: Many older python.yaml entries still use the legacy
> Pattern A (`'*': pip, jammy: deb, noble: deb`). When editing these entries
> or adding new ones, convert to Pattern B so `'*'` = newest deb.

---

## Wildcard (`'*'`) Semantics

- `'*'` under an OS key is a **catch-all** applied to any distro not explicitly
  listed.
- Because explicit distro entries take precedence, adding `'*'` only affects
  distros that have no explicit entry.
- **Alphabetical ordering required**: `check_rosdep.py` enforces alphabetical
  key order. `'*'` (ASCII 42) sorts before any letter, so it must appear
  **first** in the distro map.
- The key must be **quoted** in YAML (`'*'`, not `*`) to avoid being parsed as
  an alias.

### Canonical wildcard convention (important)

> **`'*'` must always point to the newest/latest distro's value.**
> Explicit entries are only for *older* distros where the package name differs.

This is the agreed convention for forward compatibility. When the next Ubuntu
release comes out, it will automatically inherit the `'*'` value without any
change to rosdep.

**Correct pattern** (wildcard = newest):
```yaml
libboost-atomic:
  ubuntu:
    '*':  [libboost-atomic1.83.0]  # resolute (newest) → future distros inherit this
    focal: [libboost-atomic1.71.0]  # older — different package name
    jammy: [libboost-atomic1.74.0]  # older — different package name
    # noble is NOT listed → it also gets 1.83.0 via wildcard
```

**Wrong pattern** (wildcard points to old value, newest listed explicitly):
```yaml
libboost-atomic:
  ubuntu:
    '*':  [libboost-atomic1.74.0]  # ← BAD: wildcard points to old jammy-era name
    noble:    [libboost-atomic1.83.0]
    resolute: [libboost-atomic1.83.0]  # ← BAD: explicit entry for newest distro
```

**Corollary — no redundant explicit entries**: Once `'*'` is set to a value,
remove all explicit distro entries that have the *same* value as `'*'`. They
are noise and will cause confusion.

### When to use `'*'` vs explicit entries

| Situation | Approach |
|---|---|
| Package name is stable across distros | `'*': [pkg]`, remove any older entries that match |
| Package name includes a version number (`libboost1.83.0`) | Explicit per-distro entries; `'*'` = newest version |
| Package was renamed or doesn't exist in a new distro | Explicit override or `null` for the *older* distro |
| Newest distro uses the same package as a prior distro | `'*': [pkg]`, no `resolute:` or `noble:` entry needed |

### python.yaml wildcard: two distinct patterns

`python.yaml` has two different wildcard uses — **do not confuse them**:

**Pattern A — pip fallback for old distros (legacy pattern)**:
```yaml
python3-somelib:
  ubuntu:
    '*':   {pip: {packages: [somelib]}}  # WRONG for new entries: '*' = old/pip
    jammy: [python3-somelib]
    noble: [python3-somelib]
```
This was the old convention. The `'*'` points to pip (for bionic/focal which
never had the deb). The newest distros are listed explicitly. **Avoid creating
new entries with this pattern.**

**Pattern B — deb for newest, pip for old (correct convention)**:
```yaml
python3-somelib:
  ubuntu:
    '*':   [python3-somelib]             # newest (resolute) → future inherits deb
    focal: {pip: {packages: [somelib]}}  # focal had no deb → use pip
    jammy: {pip: {packages: [somelib]}}  # jammy had no deb → use pip (if applicable)
```
Pattern B follows the canonical wildcard convention. When adding a new python
package that first appeared in noble or resolute, use Pattern B.

**Pattern C — aspirational/future deb not yet on current Ubuntu**:
```yaml
python3-future-pkg:
  ubuntu:
    '*':   [python3-future-pkg]   # future Ubuntu will ship this deb
    focal: null                   # not available on focal
    jammy: null                   # not available on jammy
    noble: null                   # not available on noble
    resolute: null                # not available on resolute
```
Used when a package exists on some non-Ubuntu platform or is expected in a
future Ubuntu release. All current distros get explicit `null` overrides.
`resolute: null` is a legitimate explicit entry here — it IS the newest, but
the package genuinely doesn't exist on it, so the explicit override is needed.

---

## Validation — Always Run After Edits

```bash
python3 scripts/check_rosdep.py rosdep/base.yaml
python3 scripts/check_rosdep.py rosdep/python.yaml
```

`check_rosdep.py` enforces:
- No trailing whitespace
- No blank lines
- Correct indentation (2-space, block style)
- **No block-style lists** — packages must use bracket notation `[pkg]`, not
  `- pkg` bullet lists
- **Alphabetical key ordering** at every level

### Running the full repo check (requires internet)

```bash
PYTHONPATH=test python3 -m rosdep_repo_check
```

This fetches the actual package indices from Ubuntu, Debian, Fedora, etc. and
verifies every mapped package name actually exists in those repos. Configured
in `test/rosdep_repo_check/config.yaml`.

To test locally with your own `rosdep` installation against the modified rules:

```bash
# Point rosdep at local files instead of GitHub
sudo rm /etc/ros/rosdep/sources.list.d/20-default.list
echo "yaml file:///path/to/rosdistro/rosdep/base.yaml" | \
  sudo tee /etc/ros/rosdep/sources.list.d/50-local.list
rosdep update
rosdep resolve libopencv-core --os=ubuntu:resolute
```

---

## Scripting / Programmatic Edits

### Preferred tool: `ruamel.yaml` (round-trip)

**Do not use plain PyYAML (`yaml.dump`)** for writing rosdep YAML. PyYAML
reformats the entire file, breaking two known patterns:

1. **Float keys** — YAML keys like `15.2` (macOS/openSUSE versions) are parsed
   as Python `float`. On output they become unquoted, causing `check_order` to
   raise `TypeError: '<' not supported between instances of float and str`.
2. **Nested brackets in strings** — `gentoo: [www-servers/apache[apache2_mpms_prefork]]`
   is a string containing `[...]` inside a flow sequence. PyYAML drops the quotes
   on output, making the file un-parseable.

Use `ruamel.yaml` in round-trip mode to preserve original formatting:

```python
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

yaml = YAML()
yaml.width = 4096          # prevent line wrapping
yaml.preserve_quotes = True

with open('rosdep/base.yaml', 'r') as f:
    data = yaml.load(f)

# Use flow-style lists to match the bracket notation required by check_rosdep.py
def flow_list(items):
    seq = CommentedSeq(items)
    seq.fa.set_flow_style()
    return seq

# Sort a CommentedMap alphabetically (required after adding '*' keys)
def sort_commentedmap(cm):
    keys = sorted(cm.keys(), key=lambda k: str(k))
    new_cm = CommentedMap()
    for k in keys:
        new_cm[k] = cm[k]
    return new_cm

# Example: add resolute entry
ubuntu = data['some-package']['ubuntu']
ubuntu['resolute'] = flow_list(['some-package-name'])
data['some-package']['ubuntu'] = sort_commentedmap(ubuntu)

with open('rosdep/base.yaml', 'w') as f:
    yaml.dump(data, f)
```

> **Key ordering gotcha**: When you add a new key (like `'*'`) to a
> `CommentedMap`, ruamel.yaml appends it at the end. `check_rosdep.py` then
> fails because `'*'` must come first. Always call `sort_commentedmap()` after
> modifying distro maps.

### `scripts/convert_resolute_wildcard.py`

A ready-made script that converts explicit per-distro entries to `'*'`
wildcards where safe. Rules it applies:

1. **noble == resolute**: replaces both with `'*': <value>` (removes noble and
   resolute).
2. **resolute-only** (no noble, resolute value matches the most recent explicit
   distro before it): replaces resolute with `'*': <value>`.

Usage:
```bash
python3 scripts/convert_resolute_wildcard.py rosdep/base.yaml
```

---

## Ubuntu Distribution Key Names

| Ubuntu release | rosdep key |
|---|---|
| 18.04 Bionic | `bionic` |
| 20.04 Focal | `focal` |
| 22.04 Jammy | `jammy` |
| 24.04 Noble | `noble` |
| 26.04 Resolute | `resolute` |

Distros use the release **codename** (lowercase), not the version number.

### Package naming patterns per Ubuntu release

Some library packages encode the Ubuntu version in their name:

| Library | Jammy | Noble | Resolute |
|---|---|---|---|
| Boost runtime | `libboost-*1.74.0` | `libboost-*1.83.0` | TBD |
| PCL runtime | `libpcl-*1.12` | `libpcl-*1.14` | TBD |
| OpenCV runtime | `libopencv-*4.5d` | `libopencv-*406t64` | `libopencv-*410` |
| protobuf | `libprotobuf23` | `libprotobuf32t64` | TBD |
| Ceres Solver | `libceres2` | `libceres4t64` | TBD |
| OpenVDB | `libopenvdb9.0` | `libopenvdb10.0t64` | TBD |
| libpqxx | `libpqxx-6.4` | `libpqxx-7.8t64` | TBD |

The `t64` suffix indicates a 64-bit time_t rebuild introduced in Ubuntu 24.04.
Resolute uses OpenCV 4.10 (`410` suffix, no `t64`).

---

## Common rosdep Key Patterns

### `null` value

A `null` value means "this package does not exist / is not needed on this OS":

```yaml
some-package:
  ubuntu:
    noble: null   # package not available on noble
```

`rosdep` treats `null` as "no package to install" — it won't error.

### pip fallback pattern (python.yaml) — Pattern B (current convention)

```yaml
python3-somelib:
  ubuntu:
    '*':   [python3-somelib]             # newest (resolute) → future distros inherit
    focal: {pip: {packages: [somelib]}}  # focal has no deb → pip fallback
    # jammy: {pip: ...} if jammy also had no deb package
```

Old entries in the file may still use the legacy Pattern A (`'*': pip, newer-distros: deb`).
When modifying such an entry, migrate it to Pattern B.

### Empty value (legacy)

Some entries use an empty value (no package) equivalent to `null`:

```yaml
somepackage:
  ubuntu:
    focal:   # empty — not available on focal
    jammy: [somepackage]
```

### YAML anchors and aliases

`python.yaml` uses YAML anchors (`&id`) and aliases (`*id`) for entries that
map to the same value. `ruamel.yaml` handles these correctly in round-trip
mode — assigning to one aliased object updates all aliases automatically.

---

## Known Issues / Remaining Work

The following rosdep keys have a `'*'` wildcard that resolves to a package name
**not confirmed available on Ubuntu Resolute**. They need explicit `resolute:`
overrides once the correct package names are determined (requires access to a
running Ubuntu Resolute system or its package index):

- **`libboost-*` (15 runtime packages)** — current `'*'`: `libboost-*1.83.0`;
  Resolute ships a newer Boost whose version number is unknown.
- **`libpcl-*` (21 runtime packages)** — current `'*'`: `libpcl-*1.14`;
  PCL version on Resolute is unknown.
- **`protobuf`** — current `'*'`: `libprotobuf32t64`; Resolute package name unknown.
- **`libceres`** — current `'*'`: `libceres4t64`; Resolute package name unknown.
- **`libopenvdb`** — current `'*'`: `libopenvdb10.0t64`; Resolute package name unknown.
- **`libpqxx`** — current `'*'`: `libpqxx-7.8t64`; Resolute package name unknown.
- **`ignition-*` / `libignition-*` (63 entries)** — old Ignition Robotics packages
  (pre-Gazebo-rebranding); likely not available on Resolute; may need
  `resolute: null`.
- **`gz-*` / `gazebo*` older versions (36 entries)** — older Gazebo versions;
  availability on Resolute depends on OSRF's package repos.

To validate which packages are broken for a given OS version:
```bash
PYTHONPATH=test python3 -m rosdep_repo_check  # requires internet
```

---

## Testing

Unit tests for rosdep formatting live in `test/rosdep_formatting_test.py` but
require the `rosdistro` Python package to be installed. Run the formatting
checker directly instead:

```bash
python3 scripts/check_rosdep.py rosdep/base.yaml
python3 scripts/check_rosdep.py rosdep/python.yaml
```

---

## Commit Conventions

- Commits to `rosdep/` typically describe the rosdep key(s) changed and why.
- Keep changes surgical — the files are large and merge conflicts are painful.
- Always validate with `check_rosdep.py` before committing.

---

## Wildcard Design Principles (from reviewer consensus)

These principles were established during the Ubuntu Resolute rosdep update and
should guide all future rosdep changes:

1. **`'*'` always equals the newest distro's value.**  Adding support for a
   new Ubuntu release means adding `'*': [newest-pkg]` and keeping older
   distros' explicit entries only where the package name changed.

2. **No explicit entry for the newest distro.**  If the newest Ubuntu release
   uses the same package name as what you'd put in `'*'`, there must be no
   explicit entry for it — it inherits via wildcard.

3. **Remove redundant explicit entries.**  After setting `'*'`, delete any
   older distro entries whose value equals the wildcard. They are noise.

4. **The wildcard enables forward compatibility.**  Future Ubuntu releases will
   automatically get the `'*'` value without any file changes. Discrepancies
   (renamed or missing packages) are fixed only when they actually occur.

5. **Exception — "not yet available" packages.**  For packages that exist on
   some platform but not yet on current Ubuntu distros, `'*': [pkg]` represents
   the future deb that will eventually ship. Current distros (including
   resolute) need explicit `null` overrides, even if resolute is newest. This
   is the only valid reason for an explicit `resolute:` entry.

6. **python.yaml pip entries follow the same rule.**  `'*'` should be the deb
   package (newest), and older distros without the deb get explicit pip entries.
   Do **not** put pip in `'*'` and list deb packages explicitly — that is the
   legacy Pattern A and should be migrated away from.
