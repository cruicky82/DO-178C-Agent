#!/usr/bin/env python3
"""
gen_test_cases.py — DO-178C Phase 4: HLR Test Case Skeleton Generator

For each HLR in the database, generates draft Normal Range and Robustness
test case skeletons using LLR data to populate procedure, input, and
expected output fields.

Usage:
    python gen_test_cases.py --db <traceability.db>
    python gen_test_cases.py --db docs/artefacts/traceability.db --dry-run

Timestamp: 2026-02-11 09:55 UTC
"""

import argparse
import os
import re
import sqlite3
import sys
from collections import defaultdict


def get_hlrs_needing_tests(db_path):
    """
    Query HLRs that have no test cases yet.

    Functionality: Find HLRs missing test coverage
    Inputs: db_path (str)
    Outputs: list of dicts with HLR id, text, allocated_to, hlr_category
    Timestamp: 2026-02-11 09:55 UTC
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT hlr.id, hlr.text, hlr.allocated_to, hlr.hlr_category
        FROM high_level_requirements hlr
        LEFT JOIN hlr_test_cases htc ON htc.parent_hlr = hlr.id
        WHERE htc.id IS NULL
          AND hlr.id != 'HLR_UNCLUSTERED'
        ORDER BY hlr.id
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_llrs_for_hlr(db_path, hlr_id):
    """
    Get all LLRs under a given HLR.

    Functionality: Query LLRs for a specific parent HLR
    Inputs: db_path (str), hlr_id (str)
    Outputs: list of dicts with LLR id, text, logic_type, trace_to_code
    Timestamp: 2026-02-11 09:55 UTC
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT id, text, logic_type, trace_to_code
        FROM low_level_requirements
        WHERE parent_hlr = ?
        ORDER BY id
    """, (hlr_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def _extract_func_names(llrs):
    """Extract unique function names from LLR trace references."""
    funcs = set()
    for llr in llrs:
        text = llr.get('text', '')
        # Look for function names in patterns like "Function 'foo'"
        match = re.search(r"Function '(\w+)'", text)
        if match:
            funcs.add(match.group(1))
    return sorted(funcs)


def _extract_branch_conditions(llrs):
    """Extract branch conditions and boundary values from LLRs."""
    conditions = []
    boundaries = set()
    for llr in llrs:
        if llr.get('logic_type') in ['branch', 'validation']:
            text = llr['text']
            conditions.append(text[:80])
            # Look for numerical boundaries (e.g., "> 100", "<= 0.5")
            match = re.findall(r'([><]=?)\s*(-?\d+\.?\d*)', text)
            for op, val in match:
                boundaries.add(f"{op} {val}")
    return conditions[:5], sorted(list(boundaries))


def _extract_error_handlers(llrs):
    """Extract error handling descriptions from LLRs."""
    handlers = []
    for llr in llrs:
        if llr.get('logic_type') == 'error_handler':
            handlers.append(llr['text'][:80])
    return handlers[:5]


def generate_normal_test(hlr, llrs, tc_index):
    """
    Generate a Normal Range test case skeleton for an HLR.

    Functionality: Create an integration-type test exercising the happy path
    Inputs: hlr (dict), llrs (list), tc_index (int)
    Outputs: test case dict ready for DB insertion
    Timestamp: 2026-02-11 09:55 UTC
    """
    hlr_id = hlr['id']
    hlr_text = hlr['text']
    funcs = _extract_func_names(llrs)
    func_list = ', '.join(funcs) if funcs else 'functions under this HLR'
    _, boundaries = _extract_branch_conditions(llrs)

    # Build procedure from LLR data
    procedure_steps = [
        f"1. Initialize the test environment with default configuration.",
        f"2. Import/load the module(s) containing: {func_list}.",
    ]

    step = 3
    # Add steps for each initialization LLR
    init_llrs = [l for l in llrs if l.get('logic_type') == 'initialization']
    for llr in init_llrs[:3]:
        procedure_steps.append(f"{step}. Invoke {llr['text'][:60]}")
        step += 1

    procedure_steps.append(f"{step}. Provide valid input data as specified in input_data.")
    step += 1
    
    if boundaries:
        procedure_steps.append(f"{step}. Execute primary functions across valid ranges:")
        for b in boundaries:
            procedure_steps.append(f"   - Verify behavior within boundary constraint: {b}")
        step += 1
    else:
        procedure_steps.append(f"{step}. Execute the primary function(s) with normal-range inputs.")
        step += 1

    procedure_steps.append(f"{step}. Capture the return value(s) and/or side effects.")
    step += 1
    procedure_steps.append(f"{step}. Compare results against expected_output.")

    # Build input data
    input_items = []
    for func in funcs[:5]:
        input_items.append(f"- {func}: <provide valid test parameters>")
    if boundaries:
        input_items.append(f"- Boundary values to exercise: {', '.join(boundaries)}")

    # Build expected output
    expected_items = []
    comp_llrs = [l for l in llrs if l.get('logic_type') == 'computation']
    for llr in comp_llrs[:3]:
        expected_items.append(f"- {llr['text'][:80]}")
    if not expected_items:
        expected_items.append("- Functions execute without errors")
        expected_items.append("- Value output matches specification")

    tc_id = f"HTC_{hlr_id.replace('HLR_', '')}_NR_{tc_index:03d}"

    return {
        'id': tc_id,
        'parent_hlr': hlr_id,
        'test_type': 'integration',
        'description': f"Normal Range test for {hlr_id}: Verify {hlr_text[:100]}",
        'procedure': '\n'.join(procedure_steps),
        'input_data': '\n'.join(input_items),
        'expected_output': '\n'.join(expected_items),
        'pass_criteria': (
            f"All assertions pass. "
            f"Functions ({func_list}) return expected values. "
            f"Computational LLRs verified. No unhandled exceptions."
        ),
    }


def generate_robustness_test(hlr, llrs, tc_index):
    """
    Generate a Robustness test case skeleton for an HLR.

    Functionality: Create a regression-type test exercising error/boundary paths
    Inputs: hlr (dict), llrs (list), tc_index (int)
    Outputs: test case dict ready for DB insertion
    Timestamp: 2026-02-11 09:55 UTC
    """
    hlr_id = hlr['id']
    hlr_text = hlr['text']
    funcs = _extract_func_names(llrs)
    func_list = ', '.join(funcs) if funcs else 'functions under this HLR'
    branch_conditions, boundaries = _extract_branch_conditions(llrs)
    error_handlers = _extract_error_handlers(llrs)

    # Build procedure
    procedure_steps = [
        f"1. Initialize the test environment with default configuration.",
        f"2. Import/load the module(s) containing: {func_list}.",
    ]

    step = 3

    # Add boundary/error test steps
    if boundaries:
        procedure_steps.append(f"{step}. Test out-of-range boundary conditions:")
        for b in boundaries:
            procedure_steps.append(f"   - Inject values violating: {b}")
        step += 1

    if error_handlers:
        procedure_steps.append(f"{step}. Test error handling paths:")
        for handler in error_handlers:
            procedure_steps.append(f"   - Force condition: {handler}")
        step += 1

    procedure_steps.append(f"{step}. Provide invalid/malformed data (null, empty, type-mismatch).")
    step += 1
    procedure_steps.append(f"{step}. Verify robust error responses (no crashes, no unhandled exceptions).")
    step += 1
    procedure_steps.append(f"{step}. Verify system state remains consistent.")

    # Build input data
    input_items = [
        "- null/undefined/None inputs",
        "- Empty string / empty array",
        "- Boundary-violating values (e.g., NaN, Inf, Overflow)",
    ]
    if boundaries:
        input_items.append(f"- Specific boundary violation cases: {', '.join(boundaries)}")

    # Build expected output
    expected_items = [
        "- Appropriate error messages or codes returned",
        "- No unhandled exceptions or crashes",
        "- Critical system state is maintained",
    ]
    for handler in error_handlers[:3]:
        expected_items.append(f"- Handled path: {handler}")

    tc_id = f"HTC_{hlr_id.replace('HLR_', '')}_ROB_{tc_index:03d}"

    return {
        'id': tc_id,
        'parent_hlr': hlr_id,
        'test_type': 'regression',
        'description': f"Robustness test for {hlr_id}: Verify error handling for {hlr_text[:80]}",
        'procedure': '\n'.join(procedure_steps),
        'input_data': '\n'.join(input_items),
        'expected_output': '\n'.join(expected_items),
        'pass_criteria': (
            f"All error conditions handled per specification. "
            f"Zero unhandled exceptions. System state persists. "
            f"Error logic correctly detects and isolates invalid inputs."
        ),
    }


def populate_test_cases(db_path, test_cases, dry_run=False):
    """
    Write test case skeletons to the database.

    Functionality: UPSERT test cases into hlr_test_cases
    Inputs: db_path (str), test_cases (list), dry_run (bool)
    Outputs: count of inserted/updated test cases
    Timestamp: 2026-02-11 09:55 UTC
    """
    if dry_run:
        for tc in test_cases:
            print(f"  [DRY-RUN] {tc['id']} ({tc['test_type']})")
            print(f"            Parent: {tc['parent_hlr']}")
            print(f"            {tc['description'][:80]}")
            print()
        return len(test_cases)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    inserted = 0
    updated = 0

    for tc in test_cases:
        cursor.execute("SELECT id FROM hlr_test_cases WHERE id = ?", (tc['id'],))
        existing = cursor.fetchone()

        if existing:
            cursor.execute("""
                UPDATE hlr_test_cases
                SET description = ?, procedure = ?, input_data = ?,
                    expected_output = ?, pass_criteria = ?,
                    updated_at = datetime('now')
                WHERE id = ?
            """, (tc['description'], tc['procedure'], tc['input_data'],
                  tc['expected_output'], tc['pass_criteria'], tc['id']))
            updated += 1
        else:
            cursor.execute("""
                INSERT INTO hlr_test_cases
                    (id, parent_hlr, test_type, description, procedure,
                     input_data, expected_output, pass_criteria)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (tc['id'], tc['parent_hlr'], tc['test_type'],
                  tc['description'], tc['procedure'], tc['input_data'],
                  tc['expected_output'], tc['pass_criteria']))
            inserted += 1

    conn.commit()
    conn.close()
    print(f"\nDatabase updated: {inserted} test cases inserted, {updated} updated")
    return inserted + updated


def _detect_test_framework(db_path):
    """Detect the dominant language from source_inventory to pick test framework."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("""
        SELECT
            SUM(CASE WHEN file_path LIKE '%.js' OR file_path LIKE '%.ts'
                      OR file_path LIKE '%.jsx' OR file_path LIKE '%.tsx' THEN 1 ELSE 0 END) as js_count,
            SUM(CASE WHEN file_path LIKE '%.go' THEN 1 ELSE 0 END) as go_count,
            SUM(CASE WHEN file_path LIKE '%.py' THEN 1 ELSE 0 END) as py_count,
            SUM(CASE WHEN file_path LIKE '%.rs' THEN 1 ELSE 0 END) as rs_count
        FROM source_inventory
    """)
    row = cursor.fetchone()
    conn.close()

    counts = {'jest': row[0] or 0, 'go': row[1] or 0, 'pytest': row[2] or 0, 'rust': row[3] or 0}
    return max(counts, key=counts.get)


def _build_assertions_js(llrs, hlr_id, tc):
    """Build Jest assertion code from LLR data."""
    lines = []
    funcs = _extract_func_names(llrs)
    _, boundaries = _extract_branch_conditions(llrs)
    errors = _extract_error_handlers(llrs)

    tc_type = tc.get('test_type', 'integration')

    if tc_type in ('integration', 'system', 'acceptance'):
        # Normal range assertions
        for func in funcs[:5]:
            lines.append(f"    // Verify {func} executes correctly")
            lines.append(f"    const result_{func} = {func}(/* valid input */);")
            lines.append(f"    expect(result_{func}).toBeDefined();")
            lines.append(f"    expect(result_{func}).not.toBeNull();")
            lines.append("")

        for b in boundaries[:3]:
            lines.append(f"    // Boundary: verify behavior at {b}")
            lines.append(f"    // TODO: Add specific boundary assertion for {b}")
            lines.append("")

        if not funcs and not boundaries:
            lines.append(f"    // TODO: Import module under test and verify {hlr_id} behavior")
            lines.append(f"    // const result = moduleUnderTest(validInput);")
            lines.append(f"    // expect(result).toEqual(expectedOutput);")
    else:
        # Robustness assertions
        for func in funcs[:3]:
            lines.append(f"    // Verify {func} handles invalid input")
            lines.append(f"    expect(() => {func}(null)).not.toThrow();")
            lines.append(f"    expect(() => {func}(undefined)).not.toThrow();")
            lines.append("")

        for handler in errors[:3]:
            lines.append(f"    // Error path: {handler[:60]}")
            lines.append(f"    // TODO: Force error condition and verify handling")
            lines.append("")

        if not funcs:
            lines.append(f"    // TODO: Verify error handling for {hlr_id}")
            lines.append(f"    // expect(() => moduleUnderTest(invalidInput)).toThrow();")

    return '\n'.join(lines) if lines else f"    // TODO: Implement assertions for {hlr_id}"


def _build_assertions_py(llrs, hlr_id, tc):
    """Build pytest assertion code from LLR data."""
    lines = []
    funcs = _extract_func_names(llrs)
    _, boundaries = _extract_branch_conditions(llrs)
    errors = _extract_error_handlers(llrs)

    tc_type = tc.get('test_type', 'integration')

    if tc_type in ('integration', 'system', 'acceptance'):
        for func in funcs[:5]:
            lines.append(f"    # Verify {func} executes correctly")
            lines.append(f"    result = {func}(  # valid input  )")
            lines.append(f"    assert result is not None")
            lines.append("")
        for b in boundaries[:3]:
            lines.append(f"    # Boundary: verify behavior at {b}")
            lines.append(f"    # TODO: Add specific boundary assertion for {b}")
            lines.append("")
        if not funcs:
            lines.append(f"    # TODO: Import module under test and verify {hlr_id}")
            lines.append(f"    # result = module_under_test(valid_input)")
            lines.append(f"    # assert result == expected_output")
    else:
        for func in funcs[:3]:
            lines.append(f"    # Verify {func} handles invalid input")
            lines.append(f"    import pytest")
            lines.append(f"    # pytest.raises(ValueError, {func}, None)")
            lines.append("")
        if not funcs:
            lines.append(f"    # TODO: Verify error handling for {hlr_id}")

    return '\n'.join(lines) if lines else f"    # TODO: Implement assertions for {hlr_id}"


def generate_test_scripts(db_path, tests_dir, dry_run=False):
    """
    Generate framework-specific test script files from hlr_test_cases.

    Functionality: Create runnable test files with real assertion patterns
    Inputs: db_path (str), tests_dir (str), dry_run (bool)
    Outputs: count of generated scripts
    Timestamp: 2026-02-11 18:36 UTC
    """
    framework = _detect_test_framework(db_path)
    print(f"\nDetected test framework: {framework}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get all test cases grouped by parent HLR
    tc_rows = conn.execute("""
        SELECT tc.*, hlr.text as hlr_text
        FROM hlr_test_cases tc
        JOIN high_level_requirements hlr ON hlr.id = tc.parent_hlr
        ORDER BY tc.parent_hlr, tc.id
    """).fetchall()

    # Group by HLR
    by_hlr = defaultdict(list)
    for row in tc_rows:
        by_hlr[row['parent_hlr']].append(dict(row))

    if not os.path.isdir(tests_dir) and not dry_run:
        os.makedirs(tests_dir, exist_ok=True)

    count = 0
    script_refs = {}  # tc_id -> relative_path

    for hlr_id, tcs in sorted(by_hlr.items()):
        # Get LLRs for assertion generation
        llrs_rows = conn.execute(
            "SELECT id, text, logic_type, trace_to_code FROM low_level_requirements WHERE parent_hlr = ?",
            (hlr_id,)
        ).fetchall()
        llrs = [dict(r) for r in llrs_rows]

        # Generate filename
        clean_id = hlr_id.lower().replace('hlr_', '')

        if framework == 'jest':
            filename = f"test_hlr_{clean_id}.test.js"
            content = _gen_jest_file(hlr_id, tcs, llrs)
        elif framework == 'pytest':
            filename = f"test_hlr_{clean_id}.py"
            content = _gen_pytest_file(hlr_id, tcs, llrs)
        elif framework == 'go':
            filename = f"hlr_{clean_id}_test.go"
            content = _gen_go_file(hlr_id, tcs, llrs)
        else:
            filename = f"test_hlr_{clean_id}.test.js"
            content = _gen_jest_file(hlr_id, tcs, llrs)

        filepath = os.path.join(tests_dir, filename)
        rel_path = f"tests/{filename}"

        if dry_run:
            print(f"  [DRY-RUN] Would write: {filepath}")
        else:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  Generated: {filename}")

        for tc in tcs:
            script_refs[tc['id']] = rel_path
        count += 1

    # Update test_script_ref in DB
    if not dry_run and script_refs:
        cursor = conn.cursor()
        for tc_id, ref in script_refs.items():
            cursor.execute(
                "UPDATE hlr_test_cases SET test_script_ref = ? WHERE id = ?",
                (ref, tc_id)
            )
        conn.commit()

    conn.close()
    return count


def _gen_jest_file(hlr_id, tcs, llrs):
    """Generate a Jest test file for an HLR."""
    lines = [
        f"/**",
        f" * DO-178C Test Script — {hlr_id}",
        f" * Auto-generated by gen_test_cases.py",
        f" *",
        f" * HLR: {tcs[0].get('hlr_text', '')[:80]}",
        f" */",
        f"",
        f"// TODO: Update import paths to match actual module locations",
        f"// const {{ functionName }} = require('../src/module');",
        f"",
    ]

    for tc in tcs:
        tc_id = tc['id']
        desc = tc.get('description', '').replace("'", "\\'")
        procedure = tc.get('procedure', '')
        assertions = _build_assertions_js(llrs, hlr_id, tc)

        lines.append(f"describe('{hlr_id}', () => {{")
        lines.append(f"  test('{tc_id}: {desc[:60]}', () => {{")
        lines.append(f"    /*")
        lines.append(f"     * Procedure:")
        for pline in procedure.split('\n')[:8]:
            lines.append(f"     * {pline.strip()}")
        lines.append(f"     */")
        lines.append(f"")
        lines.append(assertions)
        lines.append(f"  }});")
        lines.append(f"}});")
        lines.append(f"")

    return '\n'.join(lines)


def _gen_pytest_file(hlr_id, tcs, llrs):
    """Generate a pytest test file for an HLR."""
    lines = [
        f'"""',
        f"DO-178C Test Script — {hlr_id}",
        f"Auto-generated by gen_test_cases.py",
        f"",
        f"HLR: {tcs[0].get('hlr_text', '')[:80]}",
        f'"""',
        f"",
        f"# TODO: Update import paths to match actual module locations",
        f"# from src.module import function_name",
        f"",
    ]

    for tc in tcs:
        tc_id = tc['id']
        desc = tc.get('description', '')
        procedure = tc.get('procedure', '')
        assertions = _build_assertions_py(llrs, hlr_id, tc)

        func_name = tc_id.lower().replace('-', '_')
        lines.append(f"def test_{func_name}():")
        lines.append(f'    """{desc[:80]}"""')
        lines.append(f"    # Procedure:")
        for pline in procedure.split('\n')[:8]:
            lines.append(f"    # {pline.strip()}")
        lines.append(f"")
        lines.append(assertions)
        lines.append(f"")
        lines.append(f"")

    return '\n'.join(lines)


def _gen_go_file(hlr_id, tcs, llrs):
    """Generate a Go test file for an HLR."""
    lines = [
        f"// DO-178C Test Script — {hlr_id}",
        f"// Auto-generated by gen_test_cases.py",
        f"",
        f"package main",
        f"",
        f'import "testing"',
        f"",
    ]

    for tc in tcs:
        tc_id = tc['id']
        desc = tc.get('description', '')
        func_name = ''.join(word.capitalize() for word in tc_id.replace('-', '_').split('_'))

        lines.append(f"func Test{func_name}(t *testing.T) {{")
        lines.append(f'\t// {desc[:80]}')
        lines.append(f"\t// TODO: Implement test logic")
        lines.append(f'\tt.Log("Testing {hlr_id}")')
        lines.append(f"}}")
        lines.append(f"")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='DO-178C Phase 4: Generate HLR test case skeletons'
    )
    parser.add_argument('--db', required=True,
                        help='Path to traceability.db')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print test cases without writing to DB')
    parser.add_argument('--gen-scripts', metavar='TESTS_DIR',
                        help='Generate executable test script files into TESTS_DIR')

    args = parser.parse_args()

    db = os.path.abspath(args.db)
    if not os.path.isfile(db):
        print(f"ERROR: Database not found: {db}")
        sys.exit(1)

    # Get HLRs without test cases
    hlrs = get_hlrs_needing_tests(db)
    if not hlrs:
        print("All HLRs already have test cases.")
        # Still allow --gen-scripts on existing test cases
        if args.gen_scripts:
            count = generate_test_scripts(db, args.gen_scripts, dry_run=args.dry_run)
            print(f"\nGenerated {count} test scripts.")
        sys.exit(0)

    print(f"=== DO-178C Phase 4: Test Case Generation ===")
    print(f"DB:   {db}")
    print(f"HLRs needing tests: {len(hlrs)}")
    print()

    all_test_cases = []
    tc_index = 1

    for hlr in hlrs:
        llrs = get_llrs_for_hlr(db, hlr['id'])
        print(f"  {hlr['id']}: {len(llrs)} LLRs -> generating 2 test cases")

        # Normal Range test
        nr_test = generate_normal_test(hlr, llrs, tc_index)
        all_test_cases.append(nr_test)
        tc_index += 1

        # Robustness test
        rob_test = generate_robustness_test(hlr, llrs, tc_index)
        all_test_cases.append(rob_test)
        tc_index += 1

    print(f"\nTotal: {len(all_test_cases)} test cases for {len(hlrs)} HLRs")

    if args.dry_run:
        print("\n--- DRY RUN (no DB writes) ---\n")
    populate_test_cases(db, all_test_cases, dry_run=args.dry_run)

    # Generate test scripts if requested
    if args.gen_scripts:
        count = generate_test_scripts(db, args.gen_scripts, dry_run=args.dry_run)
        print(f"\nGenerated {count} test scripts.")

    print("\nPhase 4 complete.")


if __name__ == '__main__':
    main()

