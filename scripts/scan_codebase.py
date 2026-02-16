#!/usr/bin/env python3
"""
scan_codebase.py — DO-178C Phase 1: Source Inventory Scanner

Scans all source files under a given root directory, identifies
functions/methods/classes using regex-based heuristics, and
populates the source_inventory table in the traceability database.

Usage:
    python scan_codebase.py --root <APP_ROOT> --db <traceability.db>
    python scan_codebase.py --root ./src --db docs/artefacts/traceability.db

Supported languages:
    .js, .jsx, .ts, .tsx  — JavaScript/TypeScript
    .go                   — Go
    .py                   — Python
    .rs                   — Rust

Timestamp: 2026-02-11 07:36 UTC
"""

import argparse
import os
import re
import sqlite3
import sys

# ============================================================
# Language-specific function extraction patterns
# ============================================================

# JavaScript/TypeScript keywords to exclude from method detection
JS_KEYWORDS = {
    'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'try', 'catch',
    'finally', 'throw', 'return', 'new', 'delete', 'typeof', 'instanceof',
    'void', 'with', 'debugger', 'yield', 'await', 'import', 'export',
    'default', 'break', 'continue', 'in', 'of',
}

# JavaScript/TypeScript patterns
JS_PATTERNS = [
    # Named function declarations: function foo(...) {
    re.compile(r'^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(', re.MULTILINE),
    # Arrow functions assigned to const/let/var: const foo = (...) =>
    re.compile(r'^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(?.*?\)?\s*=>', re.MULTILINE),
    # Method definitions in objects/classes: foo(...) {  or  async foo(...) {
    # NOTE: Post-filtered against JS_KEYWORDS to exclude if/for/while
    re.compile(r'^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{', re.MULTILINE),
    # Class declarations
    re.compile(r'^\s*(?:export\s+)?class\s+(\w+)', re.MULTILINE),
]

# Go patterns
GO_PATTERNS = [
    # func FuncName(...)
    re.compile(r'^func\s+(\w+)\s*\(', re.MULTILINE),
    # func (receiver) MethodName(...)
    re.compile(r'^func\s+\([^)]+\)\s+(\w+)\s*\(', re.MULTILINE),
    # type TypeName struct/interface
    re.compile(r'^type\s+(\w+)\s+(?:struct|interface)\s*\{', re.MULTILINE),
]

# Python patterns
PY_PATTERNS = [
    # def function_name(...)
    re.compile(r'^(?:\s*)def\s+(\w+)\s*\(', re.MULTILINE),
    # class ClassName(...)
    re.compile(r'^(?:\s*)class\s+(\w+)\s*[\(:]', re.MULTILINE),
]

# Rust patterns
RUST_PATTERNS = [
    # fn function_name(...)  — with optional pub/pub(crate)/async qualifiers
    re.compile(r'^\s*(?:pub(?:\(crate\))?\s+)?(?:async\s+)?fn\s+(\w+)\s*[<(]', re.MULTILINE),
    # impl TypeName — implementation blocks
    re.compile(r'^\s*impl(?:<[^>]+>)?\s+(\w+)', re.MULTILINE),
    # struct/enum/trait declarations
    re.compile(r'^\s*(?:pub(?:\(crate\))?\s+)?(?:struct|enum|trait)\s+(\w+)', re.MULTILINE),
]

# File extension to pattern mapping
LANG_MAP = {
    '.js': JS_PATTERNS,
    '.jsx': JS_PATTERNS,
    '.ts': JS_PATTERNS,
    '.tsx': JS_PATTERNS,
    '.go': GO_PATTERNS,
    '.py': PY_PATTERNS,
    '.rs': RUST_PATTERNS,
}

# Directories to always skip
SKIP_DIRS = {
    'node_modules', '.git', '__pycache__', 'dist', 'build',
    '.next', 'coverage', 'vendor', '.venv', 'venv',
}


def find_functions(content, patterns, lang_ext='.js'):
    """
    Find all function/class definitions in source content.

    Functionality: Scans content line-by-line for pattern matches
    Inputs: content (str) - file content, patterns (list) - regex patterns, lang_ext (str)
    Outputs: list of dicts with 'name' and 'line' keys
    Timestamp: 2026-02-11 07:36 UTC
    """
    results = []
    seen = set()
    lines = content.split('\n')
    is_js = lang_ext in ('.js', '.jsx', '.ts', '.tsx')

    for i, line in enumerate(lines, 1):
        for pattern in patterns:
            match = pattern.match(line)
            if match:
                name = match.group(1)
                # Filter out JS/TS keywords misidentified as method names
                if is_js and name in JS_KEYWORDS:
                    break
                key = f"{name}:{i}"
                if key not in seen:
                    seen.add(key)
                    results.append({'name': name, 'line': i})
                break

    return results


def estimate_end_line(content_lines, start_line, lang_ext):
    """
    Estimate the end line of a function using brace/indent matching.

    Functionality: Heuristic end-line detection for functions
    Inputs: content_lines (list), start_line (int, 1-indexed), lang_ext (str)
    Outputs: end_line (int, 1-indexed)
    Timestamp: 2026-02-11 07:36 UTC
    """
    total = len(content_lines)
    start_idx = start_line - 1

    if lang_ext == '.py':
        # Python: use indentation
        if start_idx >= total:
            return start_line

        # Get the indentation of the def/class line
        base_line = content_lines[start_idx]
        base_indent = len(base_line) - len(base_line.lstrip())

        end_idx = start_idx + 1
        while end_idx < total:
            line = content_lines[end_idx]
            stripped = line.strip()
            if stripped == '' or stripped.startswith('#'):
                end_idx += 1
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent:
                break
            end_idx += 1
        return end_idx  # 1-indexed (end_idx is already 0-indexed + 1 past end)

    else:
        # JS/TS/Go: use brace counting
        brace_count = 0
        started = False
        end_idx = start_idx

        while end_idx < total:
            line = content_lines[end_idx]
            brace_count += line.count('{') - line.count('}')
            if '{' in line:
                started = True
            if started and brace_count <= 0:
                return end_idx + 1  # 1-indexed
            end_idx += 1

        return total  # If no closing brace found, assume end of file


def scan_file(file_path, rel_path, lang_ext):
    """
    Scan a single source file for function definitions.

    Functionality: Read file, extract functions, estimate line ranges
    Inputs: file_path (str), rel_path (str), lang_ext (str)
    Outputs: list of dicts with id, file_path, function_name, start/end/count
    Timestamp: 2026-02-11 07:36 UTC
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        print(f"  WARN: Cannot read {rel_path}: {e}")
        return []

    patterns = LANG_MAP.get(lang_ext, [])
    if not patterns:
        return []

    functions = find_functions(content, patterns, lang_ext)
    if not functions:
        return []

    content_lines = content.split('\n')
    results = []
    seen_ids = set()

    # Sort by line number to enable proper end-line estimation
    functions.sort(key=lambda f: f['line'])

    for i, func in enumerate(functions):
        name = func['name']
        start = func['line']

        # Estimate end: either next function's start - 1, or brace/indent match
        if i + 1 < len(functions):
            next_start = functions[i + 1]['line']
            end = min(
                estimate_end_line(content_lines, start, lang_ext),
                next_start - 1
            )
        else:
            end = estimate_end_line(content_lines, start, lang_ext)

        # Normalize path separators
        normalized_path = rel_path.replace('\\', '/')

        # Make ID unique by including line number for duplicate names
        inv_id = f"{normalized_path}::{name}:L{start}"
        if inv_id in seen_ids:
            continue  # Skip true duplicates
        seen_ids.add(inv_id)

        results.append({
            'id': inv_id,
            'file_path': normalized_path,
            'function_name': name,
            'start_line': start,
            'end_line': end,
            'line_count': end - start + 1,
        })

    return results


def scan_directory(root_dir):
    """
    Recursively scan all source files under root_dir.

    Functionality: Walk directory tree, skip excluded dirs, scan each file
    Inputs: root_dir (str) - absolute path to scan
    Outputs: list of inventory records
    Timestamp: 2026-02-11 07:36 UTC
    """
    all_records = []
    file_count = 0

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Skip excluded directories
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for filename in sorted(filenames):
            ext = os.path.splitext(filename)[1].lower()
            if ext not in LANG_MAP:
                continue

            file_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(file_path, root_dir)
            file_count += 1

            records = scan_file(file_path, rel_path, ext)
            if records:
                print(f"  {rel_path}: {len(records)} functions")
                all_records.extend(records)

    print(f"\nScanned {file_count} files, found {len(all_records)} functions")
    return all_records


def populate_inventory(db_path, records):
    """
    Insert/update source inventory records in the database.

    Functionality: UPSERT records into source_inventory (idempotent)
    Inputs: db_path (str), records (list of dicts)
    Outputs: count of inserted/updated records
    Timestamp: 2026-02-11 07:36 UTC
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    inserted = 0
    updated = 0

    for rec in records:
        # Check if exists
        cursor.execute("SELECT has_llr FROM source_inventory WHERE id = ?", (rec['id'],))
        existing = cursor.fetchone()

        if existing:
            # Update line info but preserve has_llr status
            cursor.execute("""
                UPDATE source_inventory
                SET start_line = ?, end_line = ?, line_count = ?, scanned_at = datetime('now')
                WHERE id = ?
            """, (rec['start_line'], rec['end_line'], rec['line_count'], rec['id']))
            updated += 1
        else:
            cursor.execute("""
                INSERT INTO source_inventory (id, file_path, function_name, start_line, end_line, line_count)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (rec['id'], rec['file_path'], rec['function_name'],
                  rec['start_line'], rec['end_line'], rec['line_count']))
            inserted += 1

    conn.commit()
    conn.close()
    print(f"\nDatabase updated: {inserted} inserted, {updated} updated")
    return inserted + updated


def main():
    parser = argparse.ArgumentParser(
        description='DO-178C Phase 1: Scan codebase and populate source_inventory'
    )
    parser.add_argument('--root', required=True,
                        help='Root directory to scan (e.g., ./src or ../kccore/go)')
    parser.add_argument('--db', required=True,
                        help='Path to traceability.db')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print what would be inserted without writing to DB')

    args = parser.parse_args()

    root = os.path.abspath(args.root)
    db = os.path.abspath(args.db)

    if not os.path.isdir(root):
        print(f"ERROR: Root directory not found: {root}")
        sys.exit(1)

    if not os.path.isfile(db):
        print(f"ERROR: Database not found: {db}")
        print("Run init_db.py first to create the database.")
        sys.exit(1)

    print(f"=== DO-178C Phase 1: Source Inventory Scan ===")
    print(f"Root: {root}")
    print(f"DB:   {db}")
    print()

    records = scan_directory(root)

    if args.dry_run:
        print("\n--- DRY RUN (no DB writes) ---")
        for rec in records:
            print(f"  {rec['id']}  L{rec['start_line']}-{rec['end_line']} ({rec['line_count']} lines)")
    else:
        populate_inventory(db, records)

    print("\nPhase 1 complete.")


if __name__ == '__main__':
    main()
