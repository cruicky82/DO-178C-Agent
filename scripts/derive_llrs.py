#!/usr/bin/env python3
"""
derive_llrs.py — DO-178C Phase 2A: Deterministic LLR Auto-Generation Engine

Parses source files from the source_inventory table, extracts structural
elements (branches, loops, error handlers, computations), and auto-generates
draft Low-Level Requirements (LLRs) for each element.

Usage:
    python derive_llrs.py --db <traceability.db>
    python derive_llrs.py --db docs/artefacts/traceability.db --dry-run

Supported languages:
    .py         — Full AST parsing via Python's ast module
    .js, .jsx, .ts, .tsx — Regex/heuristic branch detection
    .go         — Regex/heuristic branch detection (Go-specific)
    .rs         — Regex/heuristic branch detection (Rust-specific)

Timestamp: 2026-02-11 09:55 UTC
"""

import argparse
import ast
import os
import re
import sqlite3
import sys
from collections import defaultdict


# ============================================================
# Language-agnostic structural element types
# Maps to logic_type in low_level_requirements schema:
#   branch, loop, error_handler, validation,
#   computation, state_transition, initialization, other
# ============================================================


def _make_llr_id(file_path, func_name, idx):
    """
    Generate a deterministic LLR ID from file, function, and index.

    Functionality: Creates unique LLR identifiers
    Inputs: file_path (str), func_name (str), idx (int)
    Outputs: LLR ID string like 'LLR_utils_py__calc_dist__001'
    Timestamp: 2026-02-11 09:55 UTC
    """
    # Sanitize path: replace non-alphanumeric with _
    safe_path = re.sub(r'[^a-zA-Z0-9]', '_', file_path)
    # Collapse consecutive underscores and trim
    safe_path = re.sub(r'_+', '_', safe_path).strip('_')
    # Limit length to keep IDs manageable
    if len(safe_path) > 40:
        safe_path = safe_path[:40]
    return f"LLR_{safe_path}__{func_name}__{idx:03d}"


# ============================================================
# Python AST-based extraction (highest quality)
# ============================================================

class PythonLLRExtractor(ast.NodeVisitor):
    """
    PythonLLRExtractor
    Functionality: Walks the Python AST to extract structural elements
                   and generate draft LLR text for each.
    Inputs: source (str) - Python source code, file_path (str)
    Outputs: list of LLR draft dicts
    Timestamp: 2026-02-11 09:55 UTC
    """

    def __init__(self, source, file_path, func_name, start_line):
        self.source = source
        self.file_path = file_path
        self.func_name = func_name
        self.start_line = start_line
        self.llrs = []
        self.idx = 0

    def _add_llr(self, logic_type, text, line):
        """Add an LLR draft to the collection."""
        self.idx += 1
        self.llrs.append({
            'id': _make_llr_id(self.file_path, self.func_name, self.idx),
            'text': text,
            'logic_type': logic_type,
            'trace_to_code': f"{self.file_path}:{self.start_line + line - 1}",
        })

    def visit_FunctionDef(self, node):
        """Extract function initialization LLR."""
        args = [a.arg for a in node.args.args]
        returns = ''
        if node.returns:
            returns = f" -> {ast.dump(node.returns)}"
        self._add_llr(
            'initialization',
            f"Function '{node.name}' shall be defined with parameters ({', '.join(args)}){returns}. "
            f"Entry point at line {self.start_line + node.lineno - 1}.",
            node.lineno
        )
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_If(self, node):
        """Extract branch LLR for each if/elif/else."""
        try:
            condition = ast.unparse(node.test)
        except Exception:
            condition = "<complex condition>"

        self._add_llr(
            'branch',
            f"If {condition}, then execute the if-body "
            f"({len(node.body)} statement(s)). "
            f"Else execute the else-body ({len(node.orelse)} statement(s)).",
            node.lineno
        )
        self.generic_visit(node)

    def visit_For(self, node):
        """Extract loop LLR."""
        try:
            target = ast.unparse(node.target)
            iter_expr = ast.unparse(node.iter)
        except Exception:
            target = "<target>"
            iter_expr = "<iterable>"

        self._add_llr(
            'loop',
            f"Iterate '{target}' over {iter_expr}. "
            f"Loop body contains {len(node.body)} statement(s).",
            node.lineno
        )
        self.generic_visit(node)

    def visit_While(self, node):
        """Extract loop LLR for while."""
        try:
            condition = ast.unparse(node.test)
        except Exception:
            condition = "<condition>"

        self._add_llr(
            'loop',
            f"While {condition}, execute loop body "
            f"({len(node.body)} statement(s)). "
            f"Terminate when condition is false.",
            node.lineno
        )
        self.generic_visit(node)

    def visit_Try(self, node):
        """Extract error_handler LLR for try/except."""
        handler_types = []
        for handler in node.handlers:
            if handler.type:
                try:
                    handler_types.append(ast.unparse(handler.type))
                except Exception:
                    handler_types.append("<Exception>")
            else:
                handler_types.append("Exception (bare)")

        self._add_llr(
            'error_handler',
            f"Try block with {len(node.body)} statement(s). "
            f"Handles exceptions: [{', '.join(handler_types)}]. "
            f"Finally block: {'yes' if node.finalbody else 'no'}.",
            node.lineno
        )
        self.generic_visit(node)

    def visit_Return(self, node):
        """Extract computation LLR for return statements with values."""
        if node.value:
            try:
                val = ast.unparse(node.value)
            except Exception:
                val = "<expression>"
            # Only add for non-trivial returns
            if val not in ('None', 'True', 'False'):
                self._add_llr(
                    'computation',
                    f"Return {val}.",
                    node.lineno
                )


def extract_python_llrs(source, file_path, func_name, start_line):
    """
    Extract LLRs from Python source using AST.

    Functionality: Parse and walk AST to identify structural elements
    Inputs: source (str), file_path (str), func_name (str), start_line (int)
    Outputs: list of LLR draft dicts
    Timestamp: 2026-02-11 09:55 UTC
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    extractor = PythonLLRExtractor(source, file_path, func_name, start_line)
    extractor.visit(tree)
    return extractor.llrs


# ============================================================
# Regex-based extraction for JS/TS, Go, Rust
# ============================================================

# Common branch/loop/error patterns
REGEX_PATTERNS = {
    'js': {
        'branch': [
            re.compile(r'^\s*(?:} )?(?:else )?if\s*\((.+?)\)\s*\{', re.MULTILINE),
            re.compile(r'^\s*} else\s*\{', re.MULTILINE),
            re.compile(r'^\s*switch\s*\((.+?)\)\s*\{', re.MULTILINE),
            re.compile(r'^\s*case\s+(.+?):', re.MULTILINE),
            re.compile(r'^\s*default\s*:', re.MULTILINE),
        ],
        'loop': [
            re.compile(r'^\s*for\s*\((.+?)\)\s*\{', re.MULTILINE),
            re.compile(r'^\s*while\s*\((.+?)\)\s*\{', re.MULTILINE),
            re.compile(r'^\s*do\s*\{', re.MULTILINE),
            re.compile(r'^\s*for\s*\(\s*(?:const|let|var)\s+\w+\s+(?:of|in)\s+.+?\)\s*\{', re.MULTILINE),
        ],
        'error_handler': [
            re.compile(r'^\s*try\s*\{', re.MULTILINE),
            re.compile(r'^\s*}\s*catch\s*\((.+?)\)\s*\{', re.MULTILINE),
            re.compile(r'^\s*}\s*finally\s*\{', re.MULTILINE),
        ],
        'validation': [
            re.compile(r'^\s*if\s*\(\s*!?\w+\s*(?:===?|!==?)\s*(?:null|undefined|NaN)\s*\)', re.MULTILINE),
            re.compile(r'^\s*if\s*\(\s*typeof\s+\w+\s*===?\s*[\'"]', re.MULTILINE),
        ],
    },
    'go': {
        'branch': [
            re.compile(r'^\s*if\s+(.+?)\s*\{', re.MULTILINE),
            re.compile(r'^\s*}\s*else\s*\{', re.MULTILINE),
            re.compile(r'^\s*}\s*else if\s+(.+?)\s*\{', re.MULTILINE),
            re.compile(r'^\s*switch\s*(.*?)\s*\{', re.MULTILINE),
            re.compile(r'^\s*case\s+(.+?):', re.MULTILINE),
            re.compile(r'^\s*default\s*:', re.MULTILINE),
        ],
        'loop': [
            re.compile(r'^\s*for\s+(.*?)\s*\{', re.MULTILINE),
        ],
        'error_handler': [
            re.compile(r'^\s*if\s+err\s*!=\s*nil\s*\{', re.MULTILINE),
            re.compile(r'^\s*defer\s+', re.MULTILINE),
        ],
    },
    'rust': {
        'branch': [
            re.compile(r'^\s*if\s+(.+?)\s*\{', re.MULTILINE),
            re.compile(r'^\s*}\s*else\s+if\s+(.+?)\s*\{', re.MULTILINE),
            re.compile(r'^\s*}\s*else\s*\{', re.MULTILINE),
            re.compile(r'^\s*match\s+(.+?)\s*\{', re.MULTILINE),
        ],
        'loop': [
            re.compile(r'^\s*for\s+(\w+)\s+in\s+(.+?)\s*\{', re.MULTILINE),
            re.compile(r'^\s*while\s+(.+?)\s*\{', re.MULTILINE),
            re.compile(r'^\s*loop\s*\{', re.MULTILINE),
        ],
        'error_handler': [
            re.compile(r'^\s*(?:\.unwrap\(\)|\.expect\()', re.MULTILINE),
            re.compile(r'^\s*(?:Ok|Err)\s*\(', re.MULTILINE),
            re.compile(r'\?\s*;', re.MULTILINE),
        ],
    },
}

# Map match arm patterns for Rust
RUST_MATCH_ARM = re.compile(r'^\s+(\S.*?)\s*=>', re.MULTILINE)


def _get_lang_key(ext):
    """Map file extension to language key for regex patterns."""
    if ext in ('.js', '.jsx', '.ts', '.tsx'):
        return 'js'
    if ext == '.go':
        return 'go'
    if ext == '.rs':
        return 'rust'
    return None


def extract_regex_llrs(source, file_path, func_name, start_line, lang_ext):
    """
    Extract LLRs from source using regex heuristics (JS/TS/Go/Rust).

    Functionality: Scans source line-by-line for structural patterns
    Inputs: source (str), file_path (str), func_name (str),
            start_line (int), lang_ext (str)
    Outputs: list of LLR draft dicts
    Timestamp: 2026-02-11 09:55 UTC
    """
    lang_key = _get_lang_key(lang_ext)
    if lang_key is None:
        return []

    patterns = REGEX_PATTERNS.get(lang_key, {})
    llrs = []
    idx = 0
    lines = source.split('\n')

    # Always generate an initialization LLR for the function itself
    idx += 1
    llrs.append({
        'id': _make_llr_id(file_path, func_name, idx),
        'text': f"Function '{func_name}' entry point. "
                f"Defined at {file_path}:{start_line}.",
        'logic_type': 'initialization',
        'trace_to_code': f"{file_path}:{start_line}",
    })

    for line_num, line in enumerate(lines, 1):
        abs_line = start_line + line_num - 1

        for logic_type, type_patterns in patterns.items():
            for pat in type_patterns:
                match = pat.match(line)
                if match:
                    groups = match.groups()
                    condition = groups[0] if groups else ''

                    # Build descriptive text based on type
                    if logic_type == 'branch':
                        if 'switch' in line.lower() or 'match' in line.lower():
                            text = f"Switch/match on '{condition.strip()}'. Evaluate each arm/case."
                        elif 'else if' in line.lower() or 'elif' in line.lower():
                            text = f"Else-if branch: when {condition.strip()}, execute the corresponding block."
                        elif 'else' in line.lower() and not condition:
                            text = f"Else branch: execute default/fallthrough block."
                        elif 'case' in line.lower():
                            text = f"Case '{condition.strip()}': execute case-specific logic."
                        elif 'default' in line.lower():
                            text = f"Default case: execute fallback logic."
                        else:
                            text = f"If {condition.strip()}, execute conditional block."

                    elif logic_type == 'loop':
                        if 'while' in line.lower():
                            text = f"While {condition.strip()}, repeat loop body."
                        elif 'loop' in line.lower() and not condition:
                            text = f"Infinite loop (requires explicit break for termination)."
                        else:
                            text = f"Iterate: {condition.strip() if condition else 'loop'}."

                    elif logic_type == 'error_handler':
                        if 'catch' in line.lower():
                            text = f"Catch handler for '{condition.strip()}'. Process error."
                        elif 'defer' in line.lower():
                            text = f"Deferred cleanup: {line.strip()}."
                        elif 'err != nil' in line:
                            text = f"Error check: if err != nil, handle error condition."
                        elif '?' in line:
                            text = f"Propagate error via ? operator."
                        elif 'unwrap' in line or 'expect' in line:
                            text = f"Unwrap/expect: panic on None/Err. {line.strip()}"
                        else:
                            text = f"Error handling: {line.strip()}"

                    elif logic_type == 'validation':
                        text = f"Input validation: {condition.strip() if condition else line.strip()}."

                    else:
                        text = f"{logic_type}: {line.strip()}"

                    idx += 1
                    llrs.append({
                        'id': _make_llr_id(file_path, func_name, idx),
                        'text': text,
                        'logic_type': logic_type,
                        'trace_to_code': f"{file_path}:{abs_line}",
                    })
                    break  # Only match first pattern per line

        # Rust: detect match arms as additional branch LLRs
        if lang_key == 'rust':
            arm_match = RUST_MATCH_ARM.match(line)
            if arm_match:
                arm_text = arm_match.group(1).strip()
                # Skip generic catch-all _ unless it's meaningful
                if arm_text != '_':
                    idx += 1
                    llrs.append({
                        'id': _make_llr_id(file_path, func_name, idx),
                        'text': f"Match arm '{arm_text}': execute arm-specific logic.",
                        'logic_type': 'branch',
                        'trace_to_code': f"{file_path}:{abs_line}",
                    })

    return llrs


# ============================================================
# Main orchestration
# ============================================================

def get_source_inventory(db_path):
    """
    Read all functions from source_inventory that need LLR derivation.

    Functionality: Query source_inventory for uncovered functions
    Inputs: db_path (str)
    Outputs: list of dicts with id, file_path, function_name, start_line, end_line
    Timestamp: 2026-02-11 09:55 UTC
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT id, file_path, function_name, start_line, end_line
        FROM source_inventory
        WHERE has_llr = 0
        ORDER BY file_path, start_line
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def read_function_source(app_root, file_path, start_line, end_line):
    """
    Read the source code of a specific function from disk.

    Functionality: Extract function body from file using line ranges
    Inputs: app_root (str), file_path (str), start_line (int), end_line (int)
    Outputs: source code string, or None on error
    Timestamp: 2026-02-11 09:55 UTC
    """
    full_path = os.path.join(app_root, file_path)
    if not os.path.isfile(full_path):
        return None
    try:
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()

        # Extract the function's line range (1-indexed → 0-indexed)
        start_idx = max(0, start_line - 1)
        end_idx = min(len(all_lines), end_line)
        return ''.join(all_lines[start_idx:end_idx])
    except Exception as e:
        print(f"  WARN: Cannot read {full_path}: {e}")
        return None


def derive_llrs_for_function(app_root, func_record):
    """
    Derive draft LLRs for a single function from source_inventory.

    Functionality: Read source, dispatch to appropriate extractor
    Inputs: app_root (str), func_record (dict)
    Outputs: list of LLR draft dicts
    Timestamp: 2026-02-11 09:55 UTC
    """
    file_path = func_record['file_path']
    func_name = func_record['function_name']
    start_line = func_record['start_line'] or 1
    end_line = func_record['end_line'] or start_line + 50

    source = read_function_source(app_root, file_path, start_line, end_line)
    if not source:
        return []

    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.py':
        llrs = extract_python_llrs(source, file_path, func_name, start_line)
    else:
        llrs = extract_regex_llrs(source, file_path, func_name, start_line, ext)

    # Ensure at least one LLR per function
    if not llrs:
        llrs.append({
            'id': _make_llr_id(file_path, func_name, 1),
            'text': f"Function '{func_name}' at {file_path}:{start_line}-{end_line}. "
                    f"Requires manual LLR derivation.",
            'logic_type': 'other',
            'trace_to_code': f"{file_path}:{start_line}-{end_line}",
        })

    return llrs


def populate_llrs(db_path, all_llrs, inventory_ids):
    """
    Write LLR drafts to the database and update source_inventory.

    Functionality: UPSERT LLRs and set has_llr = 1 for processed functions
    Inputs: db_path (str), all_llrs (list), inventory_ids (list)
    Outputs: count of inserted/updated LLRs
    Timestamp: 2026-02-11 09:55 UTC
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF;")  # Temporarily disable for draft inserts
    cursor = conn.cursor()

    inserted = 0
    updated = 0

    # Ensure the placeholder HLR exists for unclustered LLRs
    cursor.execute("""
        INSERT OR IGNORE INTO high_level_requirements
            (id, text, source, is_derived, derivation_rationale, hlr_category)
        VALUES
            ('HLR_UNCLUSTERED', 'Unclustered draft LLRs awaiting HLR assignment',
             'Derived', 1, 'Auto-generated placeholder for LLRs pending cluster_hlrs.py',
             'functional')
    """)

    for llr in all_llrs:
        cursor.execute("SELECT id FROM low_level_requirements WHERE id = ?", (llr['id'],))
        existing = cursor.fetchone()

        if existing:
            cursor.execute("""
                UPDATE low_level_requirements
                SET text = ?, logic_type = ?, trace_to_code = ?,
                    updated_at = datetime('now')
                WHERE id = ?
            """, (llr['text'], llr['logic_type'], llr['trace_to_code'], llr['id']))
            updated += 1
        else:
            cursor.execute("""
                INSERT INTO low_level_requirements
                    (id, text, parent_hlr, source, logic_type, trace_to_code)
                VALUES (?, ?, 'HLR_UNCLUSTERED', 'Derived', ?, ?)
            """, (llr['id'], llr['text'], llr['logic_type'], llr['trace_to_code']))
            inserted += 1

    # Mark all processed functions as having LLRs
    for inv_id in inventory_ids:
        cursor.execute("""
            UPDATE source_inventory SET has_llr = 1 WHERE id = ?
        """, (inv_id,))

    conn.commit()
    conn.close()
    print(f"\nDatabase updated: {inserted} LLRs inserted, {updated} updated")
    print(f"Source inventory: {len(inventory_ids)} functions marked as covered")
    return inserted + updated


def main():
    parser = argparse.ArgumentParser(
        description='DO-178C Phase 2A: Auto-derive draft LLRs from source code'
    )
    parser.add_argument('--db', required=True,
                        help='Path to traceability.db')
    parser.add_argument('--app-root', default=None,
                        help='Root directory of the application source '
                             '(default: inferred from source_inventory paths)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print generated LLRs without writing to DB')

    args = parser.parse_args()

    db = os.path.abspath(args.db)
    if not os.path.isfile(db):
        print(f"ERROR: Database not found: {db}")
        print("Run init_db.py first, then scan_codebase.py.")
        sys.exit(1)

    # Get uncovered functions
    functions = get_source_inventory(db)
    if not functions:
        print("All functions in source_inventory already have LLRs.")
        print("Run scan_codebase.py to add new functions, or reset has_llr flags.")
        sys.exit(0)

    # Determine app root
    app_root = args.app_root
    if not app_root:
        # Infer from DB path: typically <app_root>/docs/artefacts/traceability.db
        db_dir = os.path.dirname(db)
        if db_dir.endswith(os.sep + os.path.join('docs', 'artefacts')):
            app_root = os.path.dirname(os.path.dirname(db_dir))
        else:
            app_root = os.path.dirname(db)
    app_root = os.path.abspath(app_root)

    print(f"=== DO-178C Phase 2A: LLR Auto-Derivation ===")
    print(f"DB:       {db}")
    print(f"App Root: {app_root}")
    print(f"Functions to process: {len(functions)}")
    print()

    all_llrs = []
    inventory_ids = []

    # Group by file for efficient processing
    by_file = defaultdict(list)
    for func in functions:
        by_file[func['file_path']].append(func)

    for file_path, file_funcs in sorted(by_file.items()):
        print(f"  {file_path}:")
        for func in file_funcs:
            llrs = derive_llrs_for_function(app_root, func)
            if llrs:
                print(f"    {func['function_name']}: {len(llrs)} LLRs")
                all_llrs.extend(llrs)
                inventory_ids.append(func['id'])
            else:
                print(f"    {func['function_name']}: WARNING — no LLRs extracted")

    print(f"\nTotal: {len(all_llrs)} LLRs derived from {len(inventory_ids)} functions")

    if args.dry_run:
        print("\n--- DRY RUN (no DB writes) ---")
        for llr in all_llrs:
            print(f"  [{llr['logic_type']:15s}] {llr['id']}")
            print(f"                    {llr['text'][:100]}")
            print(f"                    -> {llr['trace_to_code']}")
    else:
        populate_llrs(db, all_llrs, inventory_ids)

    print("\nPhase 2A complete.")


if __name__ == '__main__':
    main()
