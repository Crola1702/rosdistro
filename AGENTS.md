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

# Per-distro overrides under an OS
libopencv-core:
  debian:
    bookworm: [libopencv-core406]
    trixie:   [libopencv-core410]
  ubuntu:
    '*':      [libopencv-core406t64]   # wildcard: applies to any unlisted distro
    jammy:    [libopencv-core4.5d]
    noble:    [libopencv-core406t64]   # explicit override wins over '*'
    resolute: [libopencv-core410]
```

### File: `rosdep/python.yaml`

Python packages follow a **different wildcard pattern**:

```yaml
python3-somelib:
  ubuntu:
    '*':   {pip: {packages: [somelib]}}  # pip fallback for old/unlisted distros
    jammy:   [python3-somelib]           # apt package for jammy
    noble:   [python3-somelib]           # apt package for noble
    resolute:[python3-somelib]           # apt package for resolute
```

> **Critical**: In `python.yaml` the outer `'*'` is a **pip fallback** for old
> distros that don't have the deb package. You **must not** replace
> `noble: [pkg]` with `'*': [pkg]` here — that would destroy the pip fallback
> for older distros. Instead, add explicit `resolute:` entries.

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

### When to use `'*'` vs explicit entries

| Situation | Approach |
|---|---|
| Package name is stable across many distros | Use `'*'` |
| Package name includes a version number (`libboost1.83.0`) | Use explicit per-distro entries |
| Package was renamed or doesn't exist in a new distro | Use explicit override or `null` |
| `python.yaml` with a pip fallback | **Never** replace noble with `'*'`; add explicit `resolute:` |

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

### pip fallback pattern (python.yaml)

```yaml
python3-somelib:
  ubuntu:
    '*':     {pip: {packages: [somelib]}}
    jammy:   [python3-somelib]
    noble:   [python3-somelib]
    resolute:[python3-somelib]
```

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

## Known Issues / Phase 2 Work Remaining

The following rosdep keys have a `'*'` wildcard that resolves to a package name
**not available on Ubuntu Resolute**. They need explicit `resolute:` overrides
once the correct package names are determined (requires access to a running
Ubuntu Resolute system or its package index):

- **`libboost-*` (15 runtime packages)** — current: `libboost-*1.83.0`; Resolute
  ships a newer Boost whose version number is unknown.
- **`libpcl-*` (21 runtime packages)** — current: `libpcl-*1.14`; PCL version
  on Resolute is unknown.
- **`protobuf`** — current: `libprotobuf32t64`; Resolute package name unknown.
- **`libceres`** — current: `libceres4t64`; Resolute package name unknown.
- **`libopenvdb`** — current: `libopenvdb10.0t64`; Resolute package name unknown.
- **`libpqxx`** — current: `libpqxx-7.8t64`; Resolute package name unknown.
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
