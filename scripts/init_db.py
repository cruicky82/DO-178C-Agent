#!/usr/bin/env python3
"""
init_db.py
Functionality: Initializes the DO-178C traceability SQLite database.
Inputs: --db-path (optional, default: docs/artefacts/traceability.db)
Outputs: A new SQLite database file with the required schema.
Data/Control Flow: Creates tables, views, and indexes for requirements traceability.
Timestamp: 2025-02-10 08:30 UTC
"""

import sqlite3
import argparse
import os
import sys
import re

SCHEMA_SQL = """
-- ============================================================
-- DO-178C Traceability Database Schema
-- Supports 1:N HLR → LLR decomposition with full trace matrix
-- ============================================================

-- System/User Requirements (top of hierarchy)
CREATE TABLE IF NOT EXISTS system_requirements (
    id          TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'User Prompt',
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- High-Level Requirements (1:N from system reqs)
-- HLRs describe SOFTWARE FUNCTIONS (behavioral capabilities), NOT source files.
-- A single HLR may be implemented across multiple files.
CREATE TABLE IF NOT EXISTS high_level_requirements (
    id           TEXT PRIMARY KEY,
    text         TEXT NOT NULL,
    source       TEXT NOT NULL,         -- 'SYS_xxx' ref or 'Derived'
    parent_sys   TEXT,                  -- FK to system_requirements.id (NULL for derived)
    allocated_to TEXT,                  -- Software function or component name (NOT filename)
    is_derived   INTEGER DEFAULT 0,    -- 1 if not traceable to a system requirement
    derivation_rationale TEXT,          -- WHY this derived HLR exists (required if is_derived=1)
    hlr_category TEXT CHECK(hlr_category IN (
        'functional', 'performance', 'interface', 'safety'
    )),
    created_at   TEXT DEFAULT (datetime('now')),
    updated_at   TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (parent_sys) REFERENCES system_requirements(id)
);

-- Low-Level Requirements (N:1 to HLR — MANY LLRs per ONE HLR)
CREATE TABLE IF NOT EXISTS low_level_requirements (
    id            TEXT PRIMARY KEY,
    text          TEXT NOT NULL,
    parent_hlr    TEXT NOT NULL,
    source        TEXT NOT NULL,
    logic_type    TEXT CHECK(logic_type IN (
        'branch', 'loop', 'error_handler', 'validation',
        'computation', 'state_transition', 'initialization', 'other'
    )),
    trace_to_code TEXT,
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (parent_hlr) REFERENCES high_level_requirements(id)
);

-- Architectural Decisions (linked to HLR)
CREATE TABLE IF NOT EXISTS architecture_decisions (
    id          TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    rationale   TEXT,
    parent_hlr  TEXT,
    category    TEXT CHECK(category IN (
        'partitioning', 'scheduling', 'interface', 'resource',
        'safety', 'data_flow', 'control_flow', 'other'
    )),
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (parent_hlr) REFERENCES high_level_requirements(id)
);

-- HLR Test Cases (EVERY HLR MUST have at least one)
CREATE TABLE IF NOT EXISTS hlr_test_cases (
    id              TEXT PRIMARY KEY,
    parent_hlr      TEXT NOT NULL,
    test_type       TEXT NOT NULL CHECK(test_type IN (
        'integration', 'system', 'acceptance', 'regression', 'safety'
    )),
    description     TEXT NOT NULL,
    procedure       TEXT NOT NULL,
    input_data      TEXT NOT NULL,
    expected_output TEXT NOT NULL,
    pass_criteria   TEXT NOT NULL,
    test_script_ref TEXT,
    pass_fail       TEXT DEFAULT 'NOT_RUN' CHECK(pass_fail IN ('PASS', 'FAIL', 'NOT_RUN')),
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (parent_hlr) REFERENCES high_level_requirements(id)
);

-- SDD Sections (full-text markdown with {{ref}} placeholders)
-- Stores the entire SDD document as ordered sections.
-- References like {{HLR.HLR_001.text}} are resolved at render time.
CREATE TABLE IF NOT EXISTS sdd_sections (
    id              TEXT PRIMARY KEY,   -- e.g., 'SDD_1', 'SDD_5_4'
    section_number  TEXT NOT NULL,      -- e.g., '1', '1.1', '5.4'
    title           TEXT NOT NULL,      -- e.g., 'Scope', 'Track Fuser'
    content         TEXT NOT NULL,      -- Full markdown with {{TABLE.ID.FIELD}} placeholders
    sort_order      INTEGER NOT NULL,   -- Display ordering
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- ============================================================
-- Source Inventory (populated by scan_codebase.py — Phase 1)
-- Catalogs every function/method in the codebase for tracking.
-- ============================================================
CREATE TABLE IF NOT EXISTS source_inventory (
    id            TEXT PRIMARY KEY,    -- 'file_path::function_name'
    file_path     TEXT NOT NULL,       -- Relative path from APP_ROOT
    function_name TEXT NOT NULL,       -- Function/method name
    start_line    INTEGER,            -- Starting line number
    end_line      INTEGER,            -- Ending line number
    line_count    INTEGER,            -- Number of lines
    has_llr       INTEGER DEFAULT 0,  -- 1 if LLRs have been derived for this function
    parent_hlr    TEXT,               -- Which HLR this function contributes to (set during LLR derivation)
    scanned_at    TEXT DEFAULT (datetime('now'))
);

-- ============================================================
-- Indexes for fast lookups
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_hlr_parent_sys  ON high_level_requirements(parent_sys);
CREATE INDEX IF NOT EXISTS idx_llr_parent_hlr  ON low_level_requirements(parent_hlr);
CREATE INDEX IF NOT EXISTS idx_htc_parent_hlr  ON hlr_test_cases(parent_hlr);
CREATE INDEX IF NOT EXISTS idx_arch_parent_hlr ON architecture_decisions(parent_hlr);
CREATE INDEX IF NOT EXISTS idx_inv_file_path   ON source_inventory(file_path);
CREATE INDEX IF NOT EXISTS idx_inv_has_llr     ON source_inventory(has_llr);

-- ============================================================
-- Full Trace Matrix View (HLR test cases only)
-- ============================================================
CREATE VIEW IF NOT EXISTS trace_matrix AS
SELECT
    sr.id            AS sys_req_id,
    sr.text          AS sys_req_text,
    hlr.id           AS hlr_id,
    hlr.text         AS hlr_text,
    htc.id           AS hlr_test_id,
    htc.pass_fail    AS hlr_test_result,
    htc.test_script_ref AS test_script,
    llr.id           AS llr_id,
    llr.text         AS llr_text,
    llr.logic_type   AS llr_type,
    llr.trace_to_code AS code_ref,
    hlr.allocated_to  AS allocated_file
FROM system_requirements sr
LEFT JOIN high_level_requirements hlr ON hlr.parent_sys  = sr.id
LEFT JOIN hlr_test_cases          htc ON htc.parent_hlr  = hlr.id
LEFT JOIN low_level_requirements  llr ON llr.parent_hlr  = hlr.id;

-- ============================================================
-- Validation Views (for integrity checks)
-- ============================================================

-- HLRs with fewer than 2 LLRs (decomposition incomplete)
CREATE VIEW IF NOT EXISTS v_incomplete_decomposition AS
SELECT hlr.id, hlr.text, COUNT(llr.id) AS llr_count
FROM high_level_requirements hlr
LEFT JOIN low_level_requirements llr ON llr.parent_hlr = hlr.id
GROUP BY hlr.id
HAVING llr_count < 2;

-- HLRs without test cases (MUST have at least one — FAIL condition)
CREATE VIEW IF NOT EXISTS v_untested_hlrs AS
SELECT hlr.id, hlr.text
FROM high_level_requirements hlr
LEFT JOIN hlr_test_cases htc ON htc.parent_hlr = hlr.id
WHERE htc.id IS NULL;

-- HLR test cases without generated test scripts
CREATE VIEW IF NOT EXISTS v_untested_scripts AS
SELECT htc.id, htc.parent_hlr, htc.description
FROM hlr_test_cases htc
WHERE htc.test_script_ref IS NULL;

-- Orphaned LLRs (no valid parent HLR)
CREATE VIEW IF NOT EXISTS v_orphaned_llrs AS
SELECT llr.id, llr.parent_hlr
FROM low_level_requirements llr
LEFT JOIN high_level_requirements hlr ON hlr.id = llr.parent_hlr
WHERE hlr.id IS NULL;

-- Orphaned HLRs (no valid parent system requirement)
CREATE VIEW IF NOT EXISTS v_orphaned_hlrs AS
SELECT hlr.id, hlr.parent_sys
FROM high_level_requirements hlr
LEFT JOIN system_requirements sr ON sr.id = hlr.parent_sys
WHERE (hlr.parent_sys IS NOT NULL AND sr.id IS NULL);

-- Untraced HLRs (parent_sys is NULL — breaks DO-178C traceability chain)
CREATE VIEW IF NOT EXISTS v_untraced_hlrs AS
SELECT hlr.id, hlr.text, hlr.is_derived
FROM high_level_requirements hlr
WHERE hlr.parent_sys IS NULL;
"""


def init_database(db_path):
    """
    init_database
    Functionality: Creates the SQLite database and applies the full schema.
    Inputs: db_path (str) - Path to the database file.
    Outputs: None (creates file on disk).
    Data/Control Flow: Ensures parent directory exists, connects, executes schema.
    Timestamp: 2025-02-10 08:30 UTC
    """
    # Decision Logic: Check if parent directory exists, create if not.
    # Conditions: os.path.dirname(db_path) is not empty string.
    parent_dir = os.path.dirname(db_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    print(f"[DO-178C] Traceability database initialized at: {db_path}")


def validate_database(db_path):
    """
    validate_database
    Functionality: Runs integrity checks on an existing traceability database.
    Inputs: db_path (str) - Path to the database file.
    Outputs: Prints validation results to stdout.
    Data/Control Flow: Queries validation views and reports findings.
    Timestamp: 2025-02-10 08:30 UTC
    """
    # Decision Logic: Check if DB file exists.
    # Conditions: os.path.exists(db_path) is True.
    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")

    print("\n=== DO-178C Traceability Validation ===\n")

    # Check incomplete decomposition
    rows = conn.execute("SELECT * FROM v_incomplete_decomposition").fetchall()
    if rows:
        print(f"[WARN] {len(rows)} HLR(s) have fewer than 2 LLRs:")
        for r in rows:
            print(f"       {r[0]}: {r[2]} LLR(s) — \"{r[1][:60]}...\"")
    else:
        print("[PASS] All HLRs have ≥2 LLRs (1:N decomposition satisfied)")

    # Check untested HLRs
    rows = conn.execute("SELECT * FROM v_untested_hlrs").fetchall()
    if rows:
        print(f"[FAIL] {len(rows)} HLR(s) have NO test cases:")
        for r in rows:
            print(f"       {r[0]}: \"{r[1][:60]}...\"")
    else:
        print("[PASS] All HLRs have at least one HLR-level test case")

    # Check orphaned LLRs
    rows = conn.execute("SELECT * FROM v_orphaned_llrs").fetchall()
    if rows:
        print(f"[FAIL] {len(rows)} orphaned LLR(s) (no valid parent HLR):")
        for r in rows:
            print(f"       {r[0]} → parent: {r[1]}")
    else:
        print("[PASS] No orphaned LLRs")

    # Check orphaned HLRs
    rows = conn.execute("SELECT * FROM v_orphaned_hlrs").fetchall()
    if rows:
        print(f"[WARN] {len(rows)} HLR(s) reference non-existent system requirements:")
        for r in rows:
            print(f"       {r[0]} → parent_sys: {r[1]}")
    else:
        print("[PASS] No orphaned HLRs")

    # Check for untraced HLRs (NULL parent_sys — traceability break)
    try:
        rows = conn.execute("SELECT * FROM v_untraced_hlrs").fetchall()
        if rows:
            print(f"[FAIL] {len(rows)} HLR(s) have no parent system requirement (traceability break):")
            for r in rows[:5]:
                print(f"       {r[0]}: \"{r[1][:50]}...\"")
            if len(rows) > 5:
                print(f"       ... and {len(rows)-5} more")
        else:
            print("[PASS] All HLRs trace to a system requirement")
    except sqlite3.OperationalError:
        pass  # View may not exist in older schema

    # Check for test cases without generated scripts
    try:
        rows = conn.execute("SELECT * FROM v_untested_scripts").fetchall()
        if rows:
            print(f"[WARN] {len(rows)} HLR test case(s) have no generated test script:")
            for r in rows:
                print(f"       {r[0]} (HLR: {r[1]})")
        else:
            print("[PASS] All HLR test cases have generated test scripts")
    except sqlite3.OperationalError:
        pass  # View may not exist in older schema

    # --- HLR Quality Spot-Checks ---
    print("\n--- HLR Quality Gates ---")
    
    # 1. File Extension Check
    all_hlrs = conn.execute("SELECT id, text FROM high_level_requirements").fetchall()
    file_ref_hlrs = []
    ext_pattern = re.compile(r'\.(js|go|py|rs|ts|tsx|jsx|css|html|md|pb\.go|pb|proto)', re.I)
    
    for row in all_hlrs:
        if ext_pattern.search(row[1]):
            file_ref_hlrs.append(row[0])
            
    if file_ref_hlrs:
        print(f"[FAIL] {len(file_ref_hlrs)} HLR(s) reference file extensions (DO-178C violation):")
        for hid in file_ref_hlrs[:5]:
            print(f"       {hid}")
        if len(file_ref_hlrs) > 5:
            print(f"       ... and {len(file_ref_hlrs)-5} more")
    else:
        print("[PASS] No HLRs reference specific file extensions")

    # 2. Quantitative Terms Check
    quant_keywords = ['accuracy', 'tolerance', 'latency', 'within', 'less than', 'greater than', 'maximum', 'minimum', 'ms', 'seconds', 'meters', '%', 'knots', 'feet', 'km']
    hlrs_with_quant = 0
    for row in all_hlrs:
        txt = row[1].lower()
        if any(kw in txt for kw in quant_keywords):
            hlrs_with_quant += 1
            
    coverage = (hlrs_with_quant / len(all_hlrs) * 100) if all_hlrs else 0
    if coverage < 50:
        print(f"[WARN] Low quantitative coverage: {coverage:.1f}% ({hlrs_with_quant}/{len(all_hlrs)})")
        print("       HLRs should specify tolerances, units, or performance constraints.")
    else:
        print(f"[PASS] Good quantitative coverage: {coverage:.1f}% ({hlrs_with_quant}/{len(all_hlrs)})")

    # Summary stats
    hlrs = conn.execute("SELECT COUNT(*) FROM high_level_requirements").fetchone()[0]
    llrs = conn.execute("SELECT COUNT(*) FROM low_level_requirements").fetchone()[0]
    hlr_tcs = conn.execute("SELECT COUNT(*) FROM hlr_test_cases").fetchone()[0]
    sdd_count = conn.execute("SELECT COUNT(*) FROM sdd_sections").fetchone()[0]
    ratio = f"{llrs/hlrs:.1f}" if hlrs > 0 else "N/A"
    print(f"\n--- Summary ---")
    print(f"  System Reqs:     {conn.execute('SELECT COUNT(*) FROM system_requirements').fetchone()[0]}")
    print(f"  HLRs:            {hlrs}")
    print(f"  HLR Test Cases:  {hlr_tcs}")
    print(f"  LLRs:            {llrs}  (avg {ratio} per HLR)")
    print(f"  SDD Sections:    {sdd_count}")
    print(f"  Arch Decisions:  {conn.execute('SELECT COUNT(*) FROM architecture_decisions').fetchone()[0]}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DO-178C Traceability Database Manager")
    parser.add_argument("--db-path", default="docs/artefacts/traceability.db",
                        help="Path to the SQLite database (default: docs/artefacts/traceability.db)")
    parser.add_argument("--validate", action="store_true",
                        help="Validate an existing database instead of creating one")
    args = parser.parse_args()

    # Decision Logic: Route to init or validate based on --validate flag.
    # Conditions: args.validate is True or False.
    if args.validate:
        validate_database(args.db_path)
    else:
        init_database(args.db_path)
