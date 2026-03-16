#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "📦 Extracting resolute packages from base.yaml..."

python3 -c "
import yaml
with open('$SCRIPT_DIR/base.yaml', 'r') as f:
    data = yaml.safe_load(f)

pkgs = set()
for rosdep, os_map in data.items():
    if not os_map or 'ubuntu' not in os_map: 
        continue
        
    u = os_map['ubuntu']
    target = []
    
    if isinstance(u, list): 
        target = u
    elif isinstance(u, dict):
        target = u.get('resolute', u.get('*', []))
        
    if isinstance(target, list):
        for p in target:
            if isinstance(p, str): 
                pkgs.add(p)

with open('$SCRIPT_DIR/resolute_pkgs.txt', 'w') as f:
    f.write('\n'.join(sorted(pkgs)) + '\n')
"

TOTAL=$(wc -l < "$SCRIPT_DIR/resolute_pkgs.txt")
echo "✅ Found $TOTAL packages. Starting Ubuntu Resolute Docker container..."

docker run --rm -v "$SCRIPT_DIR/resolute_pkgs.txt:/tmp/pkgs.txt" ubuntu:resolute bash -c "
apt-get update -qq

echo '🔍 Checking packages and finding alternatives for missing ones...'
MISSING=0

while read -r pkg; do
    if ! apt-get install -s \"\$pkg\" > /dev/null 2>&1; then
        echo -e \"\\n❌ MISSING: \$pkg\"
        MISSING=\$((MISSING + 1))
        
        # Regex to strip trailing version bumps, dots, and ABI suffixes 
        # e.g., libpcl-apps1.14 -> libpcl-apps
        # e.g., libopencv-core406t64 -> libopencv-core
        base_name=\$(echo \"\$pkg\" | sed -E 's/[-]*[0-9][0-9.a-z]*(-dev)?$//')
        
        if [ -n \"\$base_name\" ] && [ \"\$base_name\" != \"\$pkg\" ]; then
            echo \"   ↳ Searching for new versions of '\$base_name'...\"
            # Search apt-cache for packages starting with the base name
            apt-cache search --names-only \"^\$base_name\" | awk '{print \"      - \" \$1}' | head -n 5
        else
            # If the package doesn't have a standard version suffix, do a broader search
            search_term=\$(echo \"\$pkg\" | sed -E 's/[0-9]+//g')
            echo \"   ↳ Searching for names containing '\$search_term'...\"
            apt-cache search --names-only \"\$search_term\" | awk '{print \"      - \" \$1}' | head -n 5
        fi
    fi
done < /tmp/pkgs.txt

echo -e \"\\n---------------------------------------------------\"
echo \"Done. Found \$MISSING missing packages out of $TOTAL.\"
"
