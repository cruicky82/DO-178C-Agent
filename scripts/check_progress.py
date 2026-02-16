#!/usr/bin/env python3
"""
check_progress.py — DO-178C Pipeline Progress Dashboard

Shows the current state of all 6 pipeline phases, identifies
gaps, and suggests where to resume work.

Usage:
    python check_progress.py --db <traceability.db>
    python check_progress.py --db docs/artefacts/traceability.db

Timestamp: 2026-02-11 07:36 UTC
"""

import argparse
import os
import sqlite3
import sys


def check_table_exists(cursor, table_name):
    """Check if a table exists in the database."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def phase1_scan(cursor):
    """Phase 1: Source Inventory scan status."""
    print("Phase 1: SCAN (Source Inventory)")
    print("-" * 50)

    if not check_table_exists(cursor, 'source_inventory'):
        print("  Status: NOT STARTED — source_inventory table missing")
        print("  Action: Run init_db.py to create schema, then scan_codebase.py")
        return

    cursor.execute("SELECT COUNT(*) FROM source_inventory")
    total = cursor.fetchone()[0]

    if total == 0:
        print("  Status: NOT STARTED — table exists but empty")
        print("  Action: Run scan_codebase.py --root <src_dir> --db <db>")
        return

    cursor.execute("SELECT COUNT(DISTINCT file_path) FROM source_inventory")
    files = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM source_inventory WHERE has_llr = 1")
    covered = cursor.fetchone()[0]

    pct = (covered / total * 100) if total > 0 else 0
    status = "COMPLETE" if covered == total else "IN PROGRESS"

    print(f"  Status: {status}")
    print(f"  Files scanned:     {files}")
    print(f"  Functions found:   {total}")
    print(f"  Functions with LLR: {covered}/{total} ({pct:.0f}%)")

    if covered < total:
        # Show files with uncovered functions
        cursor.execute("""
            SELECT file_path, COUNT(*) as uncovered
            FROM source_inventory WHERE has_llr = 0
            GROUP BY file_path ORDER BY uncovered DESC LIMIT 10
        """)
        remaining = cursor.fetchall()
        if remaining:
            print(f"\n  Remaining files (top 10):")
            for fp, cnt in remaining:
                print(f"    {fp}: {cnt} functions need LLRs")


def phase2_hlrs(cursor):
    """Phase 2: HLR derivation status."""
    print("\nPhase 2: HLR DERIVE")
    print("-" * 50)

    cursor.execute("SELECT COUNT(*) FROM high_level_requirements")
    hlr_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM system_requirements")
    sys_count = cursor.fetchone()[0]

    if hlr_count == 0:
        print("  Status: NOT STARTED")
        print(f"  System requirements: {sys_count}")
        return

    # Check for derived HLRs
    has_derived_col = False
    cursor.execute("PRAGMA table_info(high_level_requirements)")
    for col in cursor.fetchall():
        if col[1] == 'is_derived':
            has_derived_col = True
            break

    derived = 0
    if has_derived_col:
        cursor.execute("SELECT COUNT(*) FROM high_level_requirements WHERE is_derived = 1")
        derived = cursor.fetchone()[0]

    # Check category distribution
    has_category = False
    cursor.execute("PRAGMA table_info(high_level_requirements)")
    for col in cursor.fetchall():
        if col[1] == 'hlr_category':
            has_category = True
            break

    print(f"  Status: {hlr_count} HLRs defined")
    print(f"  System requirements: {sys_count}")
    if has_derived_col:
        print(f"  Derived HLRs: {derived}")
    if has_category:
        cursor.execute("""
            SELECT COALESCE(hlr_category, 'uncategorized'), COUNT(*)
            FROM high_level_requirements GROUP BY hlr_category
        """)
        for cat, cnt in cursor.fetchall():
            print(f"    {cat}: {cnt}")

    # List all HLRs
    cursor.execute("SELECT id, substr(text, 1, 70) FROM high_level_requirements")
    for hid, txt in cursor.fetchall():
        print(f"    {hid}: {txt}...")


def phase3_llrs(cursor):
    """Phase 3: LLR derivation status."""
    print("\nPhase 3: LLR DERIVE")
    print("-" * 50)

    cursor.execute("SELECT COUNT(*) FROM low_level_requirements")
    llr_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM high_level_requirements")
    hlr_count = cursor.fetchone()[0]

    if llr_count == 0:
        print("  Status: NOT STARTED")
        return

    # LLRs per HLR
    cursor.execute("""
        SELECT parent_hlr, COUNT(*) as cnt
        FROM low_level_requirements
        GROUP BY parent_hlr ORDER BY parent_hlr
    """)
    per_hlr = cursor.fetchall()

    avg = llr_count / hlr_count if hlr_count > 0 else 0
    print(f"  Status: {llr_count} LLRs (avg {avg:.1f}/HLR)")

    for hlr_id, cnt in per_hlr:
        marker = " ⚠" if cnt < 2 else ""
        print(f"    {hlr_id}: {cnt} LLRs{marker}")

    # HLRs with no LLRs
    cursor.execute("""
        SELECT h.id FROM high_level_requirements h
        LEFT JOIN low_level_requirements l ON l.parent_hlr = h.id
        WHERE l.id IS NULL
    """)
    orphaned = [r[0] for r in cursor.fetchall()]
    if orphaned:
        print(f"\n  ⚠ HLRs with ZERO LLRs: {', '.join(orphaned)}")


def phase4_tests(cursor):
    """Phase 4: Test case generation status."""
    print("\nPhase 4: TEST GEN")
    print("-" * 50)

    cursor.execute("SELECT COUNT(*) FROM hlr_test_cases")
    tc_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM high_level_requirements")
    hlr_count = cursor.fetchone()[0]

    if tc_count == 0:
        print("  Status: NOT STARTED")
        return

    # Test cases per HLR
    cursor.execute("""
        SELECT parent_hlr, COUNT(*) FROM hlr_test_cases
        GROUP BY parent_hlr ORDER BY parent_hlr
    """)
    per_hlr = cursor.fetchall()
    tested_hlrs = len(per_hlr)

    print(f"  Status: {tc_count} test cases for {tested_hlrs}/{hlr_count} HLRs")

    # Pass/fail distribution
    cursor.execute("""
        SELECT pass_fail, COUNT(*) FROM hlr_test_cases GROUP BY pass_fail
    """)
    for status, cnt in cursor.fetchall():
        print(f"    {status}: {cnt}")

    # HLRs with no tests
    cursor.execute("""
        SELECT h.id FROM high_level_requirements h
        LEFT JOIN hlr_test_cases t ON t.parent_hlr = h.id
        WHERE t.id IS NULL
    """)
    untested = [r[0] for r in cursor.fetchall()]
    if untested:
        print(f"\n  ⚠ HLRs with ZERO test cases: {', '.join(untested)}")

    # Test scripts
    cursor.execute("SELECT COUNT(*) FROM hlr_test_cases WHERE test_script_ref IS NOT NULL")
    scripted = cursor.fetchone()[0]
    print(f"\n  Test scripts: {scripted}/{tc_count}")


def phase5_sdd(cursor):
    """Phase 5: SDD generation status."""
    print("\nPhase 5: SDD GEN")
    print("-" * 50)

    cursor.execute("SELECT COUNT(*) FROM sdd_sections")
    sec_count = cursor.fetchone()[0]

    if sec_count == 0:
        print("  Status: NOT STARTED")
        return

    print(f"  Status: {sec_count} sections")

    cursor.execute("""
        SELECT section_number, title, length(content)
        FROM sdd_sections ORDER BY sort_order
    """)
    for num, title, content_len in cursor.fetchall():
        print(f"    §{num} {title} ({content_len} chars)")

    # Architecture decisions
    cursor.execute("SELECT COUNT(*) FROM architecture_decisions")
    arch = cursor.fetchone()[0]
    print(f"\n  Architecture decisions: {arch}")


def phase6_validate(cursor, db_path):
    """Phase 6: Validation summary."""
    print("\nPhase 6: VALIDATE")
    print("-" * 50)

    issues = []

    # HLRs with no LLRs
    cursor.execute("""
        SELECT COUNT(*) FROM high_level_requirements h
        LEFT JOIN low_level_requirements l ON l.parent_hlr = h.id
        WHERE l.id IS NULL
    """)
    orphaned_hlrs = cursor.fetchone()[0]
    if orphaned_hlrs > 0:
        issues.append(f"  FAIL: {orphaned_hlrs} HLRs have no LLRs")

    # HLRs with <2 LLRs
    cursor.execute("""
        SELECT COUNT(*) FROM (
            SELECT h.id, COUNT(l.id) as cnt FROM high_level_requirements h
            LEFT JOIN low_level_requirements l ON l.parent_hlr = h.id
            GROUP BY h.id HAVING cnt > 0 AND cnt < 2
        )
    """)
    thin_hlrs = cursor.fetchone()[0]
    if thin_hlrs > 0:
        issues.append(f"  WARN: {thin_hlrs} HLRs have only 1 LLR (expect ≥2)")

    # HLRs with no tests
    cursor.execute("""
        SELECT COUNT(*) FROM high_level_requirements h
        LEFT JOIN hlr_test_cases t ON t.parent_hlr = h.id
        WHERE t.id IS NULL
    """)
    untested = cursor.fetchone()[0]
    if untested > 0:
        issues.append(f"  FAIL: {untested} HLRs have no test cases")

    # Test cases without scripts
    cursor.execute("""
        SELECT COUNT(*) FROM hlr_test_cases WHERE test_script_ref IS NULL
    """)
    unscripted = cursor.fetchone()[0]
    if unscripted > 0:
        issues.append(f"  WARN: {unscripted} test cases have no script reference")

    # TRACEABILITY CHAIN: HLRs with NULL parent_sys
    cursor.execute("""
        SELECT COUNT(*) FROM high_level_requirements WHERE parent_sys IS NULL
    """)
    untraced = cursor.fetchone()[0]
    if untraced > 0:
        issues.append(f"  FAIL: {untraced} HLRs have NULL parent_sys (traceability break)")

    # ARCHITECTURE DECISIONS: empty table
    cursor.execute("SELECT COUNT(*) FROM architecture_decisions")
    arch = cursor.fetchone()[0]
    if arch == 0:
        issues.append(f"  WARN: No architecture decisions recorded (run extract_architecture.py)")

    # QUANTITATIVE QUALITY: HLRs lacking measurable terms
    import re
    QUANT_KW = ['accuracy', 'tolerance', 'latency', 'within', 'less than',
                'greater than', 'maximum', 'minimum', 'ms', 'seconds',
                'meters', '%', 'knots', 'feet', 'km']
    cursor.execute("SELECT id, text FROM high_level_requirements")
    hlrs = cursor.fetchall()
    total = len(hlrs)
    quant = sum(1 for _, t in hlrs if any(k in t.lower() for k in QUANT_KW))
    pct = (quant * 100 // total) if total > 0 else 0
    if pct < 50:
        issues.append(f"  WARN: Only {quant}/{total} HLRs ({pct}%) have quantitative terms (target >=50%)")

    # HLRs with file extensions (implementation detail leak)
    ext_pat = re.compile(r'\.(js|go|py|rs|ts|tsx|jsx|css|html|md)', re.I)
    file_refs = sum(1 for _, t in hlrs if ext_pat.search(t))
    if file_refs > 0:
        issues.append(f"  FAIL: {file_refs} HLRs reference file extensions (DO-178C violation)")

    # ANTI-PATTERN: ad-hoc SQL files in artefacts directory
    db_dir = os.path.dirname(db_path)
    if db_dir:
        adhoc_files = []
        try:
            for f in os.listdir(db_dir):
                if f.endswith('.sql') or (f.endswith('.py') and f.startswith('apply_')):
                    adhoc_files.append(f)
        except OSError:
            pass
        if adhoc_files:
            issues.append(
                f"  WARN: Ad-hoc refinement files found in artefacts/ "
                f"(should use pipeline scripts instead): {', '.join(adhoc_files)}"
            )

    if issues:
        print("  Issues found:")
        for issue in issues:
            print(issue)
    else:
        print("  OK: All validation checks passed")


def main():
    parser = argparse.ArgumentParser(
        description='DO-178C Pipeline Progress Dashboard'
    )
    parser.add_argument('--db', required=True, help='Path to traceability.db')

    args = parser.parse_args()
    db = os.path.abspath(args.db)

    if not os.path.isfile(db):
        print(f"ERROR: Database not found: {db}")
        sys.exit(1)

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    print("=" * 60)
    print("  DO-178C Pipeline Progress Dashboard")
    print(f"  DB: {db}")
    print("=" * 60)

    phase1_scan(cursor)
    phase2_hlrs(cursor)
    phase3_llrs(cursor)
    phase4_tests(cursor)
    phase5_sdd(cursor)
    phase6_validate(cursor, db)

    print("\n" + "=" * 60)
    conn.close()


if __name__ == '__main__':
    main()
