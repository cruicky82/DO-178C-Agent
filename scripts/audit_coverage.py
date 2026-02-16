#!/usr/bin/env python3
"""
audit_coverage.py
Functionality: Audits source code files for LLR coverage and HLR test script existence.
Inputs: --app-root (required), --db-path (optional), --extensions (optional)
Outputs: Coverage report (PASS/FAIL/PARTIAL) per file and overall statistics.
Data/Control Flow: Scans file system, queries DB, matches files to LLRs and HLRs to Scripts.
Timestamp: 2025-02-10 21:00 UTC
"""

import os
import sqlite3
import argparse
import sys

def get_db_connection(db_path):
    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def find_source_files(app_root, extensions):
    source_files = []
    # Directories to potentially exclude or be careful with could be added here
    exclude_dirs = {'.git', 'node_modules', 'dist', 'build', 'coverage', '.idea', '.vscode', 'docs'}
    
    for root, dirs, files in os.walk(app_root):
        # Modify dirs in-place to skip excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                full_path = os.path.join(root, file)
                # Store relative path for cleaner reporting matches
                rel_path = os.path.relpath(full_path, app_root)
                source_files.append(rel_path)
    return sorted(source_files)

def audit_coverage(app_root, db_path, extensions):
    print(f"--- DO-178C Coverage Audit ---")
    print(f"Root: {app_root}")
    print(f"DB:   {db_path}")
    
    conn = get_db_connection(db_path)
    
    # 1. Get all LLR allocations (normalized)
    # We query all LLRs and their trace_to_code to see which files are touched
    # trace_to_code format is typically "filename:lines" or just "filename"
    cursor = conn.execute("SELECT trace_to_code, id FROM low_level_requirements")
    covered_files = {}
    for row in cursor:
        trace = row['trace_to_code']
        if trace:
            # simple extraction: take part before ':' if present
            fname = trace.split(':')[0].strip()
            # Normalize to forward slashes for comparison
            fname = fname.replace('\\', '/')
            if fname not in covered_files:
                covered_files[fname] = []
            covered_files[fname].append(row['id'])

    # 2. Get all HLRs and check for test scripts
    cursor = conn.execute("SELECT id, allocated_to FROM high_level_requirements")
    hlr_map = {row['id']: row['allocated_to'] for row in cursor}
    
    cursor = conn.execute("SELECT id, parent_hlr, test_script_ref FROM hlr_test_cases")
    hlr_tests = {}
    for row in cursor:
        hlr_id = row['parent_hlr']
        if hlr_id not in hlr_tests:
            hlr_tests[hlr_id] = []
        hlr_tests[hlr_id].append({
            'test_id': row['id'],
            'script': row['test_script_ref']
        })

    # 3. Audit Source Files against LLRs
    source_files = find_source_files(app_root, extensions)
    print(f"\n[Source File Coverage]")
    
    missing_coverage = 0
    total_files = len(source_files)
    
    for rel_path in source_files:
        # Normalize relative path to forward slashes
        norm_path = rel_path.replace('\\', '/')
        basename = os.path.basename(norm_path)
        
        # Check for coverage by full rel path OR just basename (to be forgiving of different recording styles)
        llrs = covered_files.get(norm_path) or covered_files.get(basename)
        
        if llrs:
            print(f"  [PASS] {rel_path} ({len(llrs)} LLRs)")
        else:
            print(f"  [FAIL] {rel_path} (No LLRs linked)")
            missing_coverage += 1

    # 4. Audit HLR Test Scripts
    print(f"\n[HLR Test Script Coverage]")
    missing_scripts = 0
    total_hlrs = len(hlr_map)
    
    for hlr_id, allocated_file in hlr_map.items():
        tests = hlr_tests.get(hlr_id, [])
        if not tests:
            print(f"  [FAIL] {hlr_id} (Allocated to {allocated_file}) - NO TEST CASE defined")
            missing_scripts += 1
            continue
            
        # Check if at least one test has a script ref
        has_script = False
        for t in tests:
            if t['script']:
                # Verify script exists
                script_path = os.path.join(app_root, t['script'])
                if os.path.exists(script_path):
                    has_script = True
                else:
                    print(f"  [WARN] {hlr_id} - Script referenced but not found: {t['script']}")
        
        if has_script:
            print(f"  [PASS] {hlr_id} - Scripts: {[t['script'] for t in tests if t['script']]}")
        else:
            print(f"  [FAIL] {hlr_id} - Test cases exist but NO RUNNABLE SCRIPT generated")
            missing_scripts += 1

    conn.close()
    
    print("-" * 60)
    print(f"Source Files audited: {total_files}")
    print(f"Files w/o LLRs:       {missing_coverage}")
    print(f"Total HLRs:           {total_hlrs}")
    print(f"HLRs w/o Scripts:     {missing_scripts}")
    
    if missing_coverage == 0 and missing_scripts == 0 and total_files > 0:
        print("\nOVERALL STATUS: PASS")
        sys.exit(0)
    else:
        print("\nOVERALL STATUS: FAIL")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit DO-178C Coverage")
    parser.add_argument("--app-root", required=True, help="Root directory of the application")
    parser.add_argument("--db-path", default="docs/artefacts/traceability.db", help="Path to DB")
    parser.add_argument("--extensions", nargs="+", default=[".py", ".js", ".ts", ".go", ".c", ".cpp", ".h"], help="File extensions to scan")
    
    args = parser.parse_args()
    audit_coverage(args.app_root, args.db_path, args.extensions)
