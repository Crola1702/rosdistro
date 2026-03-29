#!/bin/bash
set -e

echo "📦 Extracting resolute packages from base.yaml..."

# Use a quick python snippet to parse the yaml and grab all packages 
# designated for 'resolute' (or falling back to the '*' wildcard).
python3 -c "
import yaml
with open('base.yaml', 'r') as f:
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
        
    # Add only standard string packages (ignores nested dicts like pip configs)
    if isinstance(target, list):
        for p in target:
            if isinstance(p, str): 
                pkgs.add(p)

with open('resolute_pkgs.txt', 'w') as f:
    f.write('\n'.join(sorted(pkgs)))
"

TOTAL=$(wc -l < resolute_pkgs.txt)
echo "✅ Found $TOTAL packages. Starting Ubuntu Resolute Docker container..."

# Run a temporary docker container, mount the package list, and test each one
docker run --rm -v "$(pwd)/resolute_pkgs.txt:/tmp/pkgs.txt" ubuntu:resolute bash -c "
apt-get update -qq

echo '🔍 Simulating installation for each package...'
MISSING=0

while read -r pkg; do
    # We use 'apt-get install -s' (simulate) instead of apt-cache because 
    # it natively resolves 'virtual' packages and aliases without breaking.
    if ! apt-get install -s \"\$pkg\" > /dev/null 2>&1; then
        echo \"❌ MISSING: \$pkg\"
        MISSING=\$((MISSING + 1))
    fi
done < /tmp/pkgs.txt

echo \"---------------------------------------------------\"
if [ \$MISSING -eq 0 ]; then
    echo \"🎉 SUCCESS: All $TOTAL packages are available in Ubuntu Resolute!\"
else
    echo \"⚠️ WARNING: \$MISSING out of $TOTAL packages are missing in Ubuntu Resolute.\"
fi
"
