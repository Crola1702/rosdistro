#!/usr/bin/env python3
"""
Convert explicit per-distro ubuntu entries to wildcard '*' where possible.

Rules:
1. If noble == resolute (both explicitly listed):
   Replace both with '*': <value>

2. If resolute exists but noble doesn't, and resolute value matches the most
   recently listed explicit distro before it (jammy, focal, bionic):
   Replace resolute with '*': <value>

This allows future Ubuntu distributions to automatically inherit the latest
rosdep rules without requiring explicit entries.

Usage:
    python3 scripts/convert_resolute_wildcard.py rosdep/base.yaml
    python3 scripts/convert_resolute_wildcard.py rosdep/python.yaml
"""

import argparse
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

# Ordered list of Ubuntu distros (oldest to newest, excluding resolute)
DISTROS_BEFORE_RESOLUTE = ['bionic', 'focal', 'jammy', 'noble']


def sort_commentedmap(cm):
    """Return a new CommentedMap with keys sorted alphabetically."""
    new_cm = CommentedMap()
    for k in sorted(str(key) for key in cm.keys()):
        for orig_key in cm.keys():
            if str(orig_key) == k:
                new_cm[orig_key] = cm[orig_key]
                break
    return new_cm


def convert_file(infile, outfile, dry_run=False):
    ry = YAML()
    ry.preserve_quotes = True
    ry.width = 4096

    with open(infile) as f:
        data = ry.load(f)

    counts = {'noble_resolute': 0, 'resolute_only': 0}

    for pkg in sorted(data.keys()):
        rules = data[pkg]
        if not isinstance(rules, dict):
            continue
        ubuntu = rules.get('ubuntu')
        if not isinstance(ubuntu, dict):
            continue
        if 'resolute' not in ubuntu:
            continue

        resolute_val = ubuntu['resolute']
        changed = False

        # Case 1: noble == resolute -> use '*'
        if 'noble' in ubuntu and ubuntu['noble'] == resolute_val:
            if dry_run:
                print("  [noble_resolute] %s" % pkg)
            else:
                ubuntu['*'] = resolute_val
                del ubuntu['noble']
                del ubuntu['resolute']
            counts['noble_resolute'] += 1
            changed = True

        # Case 2: resolute only (no noble), resolute == last explicitly listed distro
        elif 'noble' not in ubuntu:
            prev_val = None
            for d in DISTROS_BEFORE_RESOLUTE:
                if d in ubuntu:
                    prev_val = ubuntu[d]
            if prev_val is not None and prev_val == resolute_val:
                if dry_run:
                    print("  [resolute_only] %s" % pkg)
                else:
                    ubuntu['*'] = resolute_val
                    del ubuntu['resolute']
                counts['resolute_only'] += 1
                changed = True

        if changed and not dry_run:
            # Sort the ubuntu section so '*' comes first (alphabetically)
            rules['ubuntu'] = sort_commentedmap(ubuntu)

    print("Summary:")
    print("  noble==resolute -> '*': %d" % counts['noble_resolute'])
    print("  resolute-only   -> '*': %d" % counts['resolute_only'])

    if not dry_run:
        with open(outfile, 'w') as f:
            ry.dump(data, f)
        print("Written to: %s" % outfile)


def main():
    parser = argparse.ArgumentParser(
        description='Convert explicit noble/resolute rosdep entries to wildcard *')
    parser.add_argument('infile', help='Input rosdep YAML file')
    parser.add_argument(
        'outfile', nargs='?',
        help='Output YAML file (default: overwrite infile)')
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Print changes without writing output')
    args = parser.parse_args()

    outfile = args.outfile if args.outfile else args.infile

    convert_file(args.infile, outfile, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
