import sys
import re

# Chronological list of Ubuntu releases to determine the "latest" available
UBUNTU_RELEASES = [
    'lucid', 'maverick', 'natty', 'oneiric', 'precise', 'quantal', 'raring', 'saucy',
    'trusty', 'utopic', 'vivid', 'wily', 'xenial', 'yakkety', 'zesty', 'artful',
    'bionic', 'cosmic', 'disco', 'eoan', 'focal', 'groovy', 'hirsute', 'impish',
    'jammy', 'kinetic', 'lunar', 'mantic', 'noble', 'oracular', 'resolute'
]

def patch_rosdep_yaml(file_path):
    with open(file_path, 'r') as f:
        lines = f.readlines()

    out_lines = []
    i = 0
    modified_count = 0

    while i < len(lines):
        line = lines[i]
        
        # Detect the exact start of a multiline '  ubuntu:' dictionary
        # Ignores flat lists like '  ubuntu: [package]'
        if re.match(r'^  ubuntu:\s*(#.*)?$', line.rstrip('\r\n')):
            out_lines.append(line)
            i += 1
            
            block_lines = []
            # Collect all lines belonging to the ubuntu block
            while i < len(lines):
                next_line = lines[i]
                # Safely append completely empty lines inside the block
                if next_line.strip() == '':
                    block_lines.append(next_line)
                    i += 1
                    continue
                
                indent = len(next_line) - len(next_line.lstrip())
                # If indent is <= 2, we have exited the 'ubuntu' dictionary
                if indent <= 2:
                    break
                    
                block_lines.append(next_line)
                i += 1
            
            # Group the collected lines by their OS release keys
            releases = {}
            current_rel = None
            base_indent = -1
            
            for idx, bline in enumerate(block_lines):
                if bline.strip() == '':
                    if current_rel:
                        releases[current_rel]['lines'].append(bline)
                    continue
                    
                indent = len(bline) - len(bline.lstrip())
                if base_indent == -1:
                    base_indent = indent
                    
                if indent == base_indent:
                    # Match standard keys: "    focal: [foo]" or "    '*': null"
                    match = re.match(r'^(\s+)([\'"]?)([a-zA-Z0-9*-]+)\2\s*:', bline)
                    if match:
                        rel_name = match.group(3)
                        current_rel = rel_name
                        releases[current_rel] = {'lines': [bline]}
                    else:
                        current_rel = None
                elif indent > base_indent and current_rel is not None:
                    releases[current_rel]['lines'].append(bline)
                    
            has_wildcard = '*' in releases
            has_resolute = 'resolute' in releases
            
            # If it's a valid dict without a wildcard or existing 'resolute' key
            if base_indent != -1 and len(releases) > 0:
                if not has_wildcard and not has_resolute:
                    # Find the most recent release
                    latest_rel = None
                    latest_idx = -1
                    for rel in releases.keys():
                        if rel in UBUNTU_RELEASES:
                            rel_idx = UBUNTU_RELEASES.index(rel)
                            if rel_idx > latest_idx:
                                latest_idx = rel_idx
                                latest_rel = rel
                                
                    if latest_rel:
                        # Copy the exact lines defining the latest release
                        target_lines = releases[latest_rel]['lines']
                        first_line = target_lines[0]
                        
                        # Replace the release name on the first line while preserving spacing/quotes
                        new_first_line = re.sub(
                            r'^(\s+)([\'"]?)' + re.escape(latest_rel) + r'(\2\s*:)',
                            r'\g<1>\g<2>resolute\3',
                            first_line
                        )
                        
                        # Ensure the preceding line has a newline safely (for EOF edge cases)
                        if len(block_lines) > 0 and not block_lines[-1].endswith('\n'):
                            block_lines[-1] += '\n'
                            
                        # Append the newly cloned setup to the bottom of the ubuntu block
                        new_target_lines = [new_first_line] + target_lines[1:]
                        block_lines.extend(new_target_lines)
                        modified_count += 1

            out_lines.extend(block_lines)
            continue
            
        else:
            out_lines.append(line)
            i += 1

    # Write identical bytes out, except for the strictly added resolute blocks
    if modified_count > 0:
        with open(file_path, 'w') as f:
            f.writelines(out_lines)
        print(f"Successfully patched {modified_count} packages with 'resolute'.")
    else:
        print("No packages needed patching.")

if __name__ == '__main__':
    target_file = 'base.yaml'
    patch_rosdep_yaml(target_file)
