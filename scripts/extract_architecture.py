#!/usr/bin/env python3
"""
extract_architecture.py — DO-178C Phase 2D: Architecture Decision Extraction

Analyzes the source_inventory and HLR clustering to automatically infer
architecture decisions:
  1. Component Boundaries — directories that form distinct modules.
  2. Data Flow — import/dependency edges between components.
  3. Interface Patterns — API controllers, service layers, shared libs.
  4. Partitioning — frontend/backend/shared separation.

Usage:
    python extract_architecture.py --db <traceability.db> --app-root <dir>
    python extract_architecture.py --db docs/artefacts/traceability.db --app-root . --dry-run

Timestamp: 2026-02-11 18:36 UTC
"""

import argparse
import os
import re
import sqlite3
import sys
from collections import defaultdict


# ──────────────────────────────────────────────────────────────
# Import extraction patterns per language
# ──────────────────────────────────────────────────────────────

IMPORT_PATTERNS = {
    '.js':  [
        re.compile(r'''(?:import|require)\s*\(?['"]([^'"]+)['"]\)?'''),
        re.compile(r'''from\s+['"]([^'"]+)['"]'''),
    ],
    '.jsx': None,   # reuse .js
    '.ts':  None,   # reuse .js
    '.tsx': None,   # reuse .js
    '.go':  [
        re.compile(r'"([^"]+)"'),  # inside import blocks
    ],
    '.py':  [
        re.compile(r'^(?:from|import)\s+([\w.]+)', re.MULTILINE),
    ],
    '.rs':  [
        re.compile(r'(?:use|mod)\s+([\w:]+)', re.MULTILINE),
    ],
}


def _get_patterns(ext):
    """Get import patterns, falling back to .js for JSX/TS/TSX."""
    p = IMPORT_PATTERNS.get(ext)
    if p is None and ext in ('.jsx', '.ts', '.tsx'):
        return IMPORT_PATTERNS['.js']
    return p or []


def extract_imports(file_path, ext):
    """Extract import targets from a source file."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except (OSError, IOError):
        return []

    patterns = _get_patterns(ext)
    imports = set()
    for pat in patterns:
        for m in pat.finditer(content):
            target = m.group(1)
            # Skip stdlib / npm / external crate references
            if target.startswith(('.', '/', '..', '@')):
                imports.add(target)
            elif ext == '.py' and '.' in target:
                imports.add(target)
            elif ext == '.rs' and '::' in target:
                imports.add(target)
            elif ext == '.go' and '/' in target:
                imports.add(target)
    return list(imports)


def build_component_map(cursor, app_root):
    """
    Build a map of components from the source_inventory.
    A 'component' is defined as a top-level directory under app_root
    that contains source files.
    """
    cursor.execute("SELECT DISTINCT file_path FROM source_inventory")
    files = [row[0] for row in cursor.fetchall()]

    component_map = defaultdict(list)   # component_name -> [file_paths]
    for fp in files:
        # Normalize separators
        norm = fp.replace('\\', '/')
        parts = norm.split('/')
        if len(parts) >= 2:
            # Component = first two directory levels (e.g., src/backend)
            comp = '/'.join(parts[:2])
        else:
            comp = parts[0] if parts else 'root'
        component_map[comp].append(fp)

    return component_map


def classify_component(comp_name, files):
    """Classify a component's architectural role."""
    name_lower = comp_name.lower()

    if any(k in name_lower for k in ['controller', 'api', 'route']):
        return 'API Layer'
    elif any(k in name_lower for k in ['service', 'lib', 'core', 'util']):
        return 'Service / Shared Library'
    elif any(k in name_lower for k in ['frontend', 'ui', 'component', 'view', 'page']):
        return 'UI / Frontend'
    elif any(k in name_lower for k in ['backend', 'server']):
        return 'Backend'
    elif any(k in name_lower for k in ['test', 'spec', 'fixture']):
        return 'Testing'
    elif any(k in name_lower for k in ['config', 'setting']):
        return 'Configuration'
    else:
        return 'Module'


def infer_data_flow(component_map, app_root):
    """
    Analyze imports across components to build a data-flow graph.
    Returns a list of (source_component, target_component, edge_count) tuples.
    """
    edges = defaultdict(int)  # (src_comp, dst_comp) -> count

    for comp, files in component_map.items():
        for fp in files:
            ext = os.path.splitext(fp)[1]
            full_path = os.path.join(app_root, fp)
            if not os.path.isfile(full_path):
                continue

            imports = extract_imports(full_path, ext)
            for imp in imports:
                # Resolve import to component
                imp_norm = imp.lstrip('./').replace('\\', '/')
                for other_comp in component_map:
                    if other_comp != comp and imp_norm.startswith(other_comp.split('/')[-1]):
                        edges[(comp, other_comp)] += 1
                        break

    return [(s, t, c) for (s, t), c in sorted(edges.items(), key=lambda x: -x[1])]


def generate_decisions(component_map, data_flow_edges, cursor):
    """Generate architecture_decisions rows."""
    decisions = []
    arch_idx = 1

    # 1. Partitioning decisions — one per component
    for comp, files in sorted(component_map.items()):
        role = classify_component(comp, files)

        # Find associated HLRs
        cursor.execute("""
            SELECT DISTINCT h.id FROM high_level_requirements h
            JOIN source_inventory si ON si.parent_hlr = h.id
            WHERE si.file_path LIKE ?
        """, (f"{comp}%",))
        associated_hlrs = [r[0] for r in cursor.fetchall()]
        parent_hlr = associated_hlrs[0] if associated_hlrs else None

        # Get function count
        cursor.execute(
            "SELECT COUNT(*) FROM source_inventory WHERE file_path LIKE ?",
            (f"{comp}%",)
        )
        func_count = cursor.fetchone()[0]

        arch_id = f"ARCH_{arch_idx:03d}"
        decisions.append({
            'id': arch_id,
            'description': (
                f"Component '{comp}' ({role}): Contains {len(files)} files "
                f"with {func_count} functions. Architectural role: {role}."
            ),
            'rationale': (
                f"Partitioning decision — isolates {role.lower()} concerns "
                f"within the '{comp}' directory boundary."
            ),
            'parent_hlr': parent_hlr,
            'category': 'partitioning',
        })
        arch_idx += 1

    # 2. Data flow decisions — one per significant import edge
    for src, dst, count in data_flow_edges:
        if count < 1:
            continue
        arch_id = f"ARCH_{arch_idx:03d}"
        decisions.append({
            'id': arch_id,
            'description': (
                f"Data flow: '{src}' depends on '{dst}' "
                f"({count} import reference(s))."
            ),
            'rationale': (
                f"Component coupling — '{src}' consumes services or types "
                f"from '{dst}'. This dependency must be maintained for "
                f"correct operation."
            ),
            'parent_hlr': None,
            'category': 'data_flow',
        })
        arch_idx += 1

    # 3. Interface detection — look for common patterns
    cursor.execute("""
        SELECT DISTINCT file_path FROM source_inventory
        WHERE LOWER(function_name) LIKE '%handler%'
           OR LOWER(function_name) LIKE '%controller%'
           OR LOWER(function_name) LIKE '%route%'
           OR LOWER(function_name) LIKE '%endpoint%'
           OR LOWER(function_name) LIKE '%api%'
    """)
    api_files = [r[0] for r in cursor.fetchall()]
    if api_files:
        arch_id = f"ARCH_{arch_idx:03d}"
        unique_dirs = set(os.path.dirname(f).replace('\\', '/') for f in api_files)
        decisions.append({
            'id': arch_id,
            'description': (
                f"External Interface Layer: {len(api_files)} files define "
                f"API handlers/controllers/routes in directories: "
                f"{', '.join(sorted(unique_dirs))}."
            ),
            'rationale': (
                "Interface isolation — external-facing endpoints are "
                "separated into dedicated handler/controller files, "
                "allowing independent testing and modification."
            ),
            'parent_hlr': None,
            'category': 'interface',
        })
        arch_idx += 1

    return decisions


def populate_decisions(db_path, decisions, dry_run=False):
    """Write architecture decisions to the database."""
    if dry_run:
        print(f"\n[DRY RUN] Would insert {len(decisions)} architecture decisions:")
        for d in decisions:
            print(f"  {d['id']}: {d['description'][:80]}...")
        return len(decisions)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    count = 0
    for d in decisions:
        c.execute("""
            INSERT INTO architecture_decisions (id, description, rationale, parent_hlr, category)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                description = excluded.description,
                rationale = excluded.rationale,
                parent_hlr = excluded.parent_hlr,
                category = excluded.category
        """, (d['id'], d['description'], d['rationale'], d['parent_hlr'], d['category']))
        count += 1

    conn.commit()
    conn.close()
    return count


def main():
    parser = argparse.ArgumentParser(
        description='DO-178C Phase 2D: Extract Architecture Decisions'
    )
    parser.add_argument('--db', required=True, help='Path to traceability.db')
    parser.add_argument('--app-root', required=True, help='Path to application root')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without writing')
    args = parser.parse_args()

    db = os.path.abspath(args.db)
    app_root = os.path.abspath(args.app_root)

    if not os.path.isfile(db):
        print(f"ERROR: Database not found: {db}")
        sys.exit(1)

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    print("=" * 60)
    print("  DO-178C Architecture Decision Extractor")
    print(f"  DB: {db}")
    print(f"  Root: {app_root}")
    print("=" * 60)

    # Step 1: Build component map
    component_map = build_component_map(cursor, app_root)
    print(f"\nDiscovered {len(component_map)} components:")
    for comp, files in sorted(component_map.items()):
        role = classify_component(comp, files)
        print(f"  {comp} ({len(files)} files) — {role}")

    # Step 2: Analyze data flow
    data_flow = infer_data_flow(component_map, app_root)
    if data_flow:
        print(f"\nData flow edges ({len(data_flow)}):")
        for src, dst, count in data_flow:
            print(f"  {src} → {dst} ({count} imports)")
    else:
        print("\nNo inter-component data flow detected.")

    # Step 3: Generate decisions
    decisions = generate_decisions(component_map, data_flow, cursor)
    conn.close()

    # Step 4: Populate
    count = populate_decisions(db, decisions, dry_run=args.dry_run)
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Wrote {count} architecture decisions.")


if __name__ == '__main__':
    main()
