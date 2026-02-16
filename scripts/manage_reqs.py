#!/usr/bin/env python3
"""
manage_reqs.py
Functionality: CLI helper for inserting, querying, and exporting requirements
               in the DO-178C traceability database.
Inputs: Subcommand (add-sys, add-hlr, add-llr, add-tc, add-arch, export, query)
        plus required arguments per subcommand.
Outputs: Database modifications or printed query results.
Data/Control Flow: Parses CLI args, connects to SQLite, executes operations.
Timestamp: 2025-02-10 08:30 UTC
"""

import sqlite3
import argparse
import csv
import os
import sys


def connect(db_path):
    """
    connect
    Functionality: Opens a connection to the traceability database with FK enforcement.
    Inputs: db_path (str) - Path to the SQLite database file.
    Outputs: sqlite3.Connection object.
    Data/Control Flow: Checks file exists, connects with foreign keys enabled.
    Timestamp: 2025-02-10 08:30 UTC
    """
    # Decision Logic: Verify database file exists before connecting.
    # Conditions: os.path.exists(db_path) must be True.
    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        print("  Run init_db.py first to create the database.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def add_system_req(conn, req_id, text, source="User Prompt"):
    """
    add_system_req
    Functionality: Inserts a new system-level requirement.
    Inputs: conn (Connection), req_id (str), text (str), source (str).
    Outputs: None (commits row to database).
    Data/Control Flow: INSERT OR REPLACE into system_requirements table.
    Timestamp: 2025-02-10 08:30 UTC
    """
    conn.execute(
        "INSERT OR REPLACE INTO system_requirements (id, text, source) VALUES (?, ?, ?)",
        (req_id, text, source)
    )
    conn.commit()
    print(f"[OK] System Requirement {req_id} added.")


def add_hlr(conn, hlr_id, text, source, parent_sys=None, allocated_to=None):
    """
    add_hlr
    Functionality: Inserts a new High-Level Requirement linked to a system requirement.
    Inputs: conn (Connection), hlr_id (str), text (str), source (str),
            parent_sys (str, optional), allocated_to (str, optional).
    Outputs: None (commits row to database).
    Data/Control Flow: INSERT OR REPLACE into high_level_requirements table.
    Timestamp: 2025-02-10 08:30 UTC
    """
    conn.execute(
        """INSERT OR REPLACE INTO high_level_requirements
           (id, text, source, parent_sys, allocated_to)
           VALUES (?, ?, ?, ?, ?)""",
        (hlr_id, text, source, parent_sys, allocated_to)
    )
    conn.commit()
    print(f"[OK] HLR {hlr_id} added (parent: {parent_sys}).")


def add_llr(conn, llr_id, text, parent_hlr, source=None, logic_type=None, trace_to_code=None):
    """
    add_llr
    Functionality: Inserts a new Low-Level Requirement linked to its parent HLR.
    Inputs: conn (Connection), llr_id (str), text (str), parent_hlr (str),
            source (str, optional), logic_type (str, optional), trace_to_code (str, optional).
    Outputs: None (commits row to database).
    Data/Control Flow: INSERT OR REPLACE into low_level_requirements table.
                       Defaults source to parent_hlr if not provided.
    Timestamp: 2025-02-10 08:30 UTC
    """
    # Decision Logic: Default source to parent_hlr if not explicitly set.
    # Conditions: source is None.
    if source is None:
        source = parent_hlr

    conn.execute(
        """INSERT OR REPLACE INTO low_level_requirements
           (id, text, parent_hlr, source, logic_type, trace_to_code)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (llr_id, text, parent_hlr, source, logic_type, trace_to_code)
    )
    conn.commit()
    print(f"[OK] LLR {llr_id} added (parent HLR: {parent_hlr}, type: {logic_type}).")


def add_test_case(conn, tc_id, parent_llr, test_type, input_data, expected_output):



def add_arch_decision(conn, arch_id, description, rationale=None, parent_hlr=None, category=None):
    """
    add_arch_decision
    Functionality: Inserts a new architectural decision.
    Inputs: conn (Connection), arch_id (str), description (str),
            rationale (str, optional), parent_hlr (str, optional), category (str, optional).
    Outputs: None (commits row to database).
    Data/Control Flow: INSERT OR REPLACE into architecture_decisions table.
    Timestamp: 2025-02-10 08:30 UTC
    """
    conn.execute(
        """INSERT OR REPLACE INTO architecture_decisions
           (id, description, rationale, parent_hlr, category)
           VALUES (?, ?, ?, ?, ?)""",
        (arch_id, description, rationale, parent_hlr, category)
    )
    conn.commit()
    print(f"[OK] Architecture Decision {arch_id} added (category: {category}).")


def add_hlr_test_case(conn, tc_id, parent_hlr, test_type, description, procedure, input_data, expected_output, pass_criteria=None):
    """
    add_hlr_test_case
    Functionality: Inserts a new HLR-level test case.
    Inputs: conn (Connection), tc_id (str), parent_hlr (str), test_type (str),
            description (str), procedure (str), input_data (str),
            expected_output (str), pass_criteria (str, optional).
    Outputs: None (commits row to database).
    Data/Control Flow: INSERT OR REPLACE into hlr_test_cases table.
    Timestamp: 2025-02-10 20:45 UTC
    """
    conn.execute(
        """INSERT OR REPLACE INTO hlr_test_cases
           (id, parent_hlr, test_type, description, procedure, input_data, expected_output, pass_criteria)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (tc_id, parent_hlr, test_type, description, procedure, input_data, expected_output, pass_criteria)
    )
    conn.commit()
    print(f"[OK] HLR Test Case {tc_id} added (parent HLR: {parent_hlr}, type: {test_type}).")


def add_sdd_section(conn, sdd_id, section_number, title, content, sort_order):
    """
    add_sdd_section
    Functionality: Inserts or updates an SDD section with full markdown content.
    Inputs: conn (Connection), sdd_id (str), section_number (str), title (str),
            content (str), sort_order (int).
    Outputs: None (commits row to database).
    Data/Control Flow: INSERT OR REPLACE into sdd_sections table.
    Timestamp: 2025-02-10 21:45 UTC
    """
    conn.execute(
        """INSERT OR REPLACE INTO sdd_sections
           (id, section_number, title, content, sort_order)
           VALUES (?, ?, ?, ?, ?)""",
        (sdd_id, section_number, title, content, sort_order)
    )
    conn.commit()
    print(f"[OK] SDD Section {sdd_id} ({section_number} {title}) added.")


def export_trace_matrix(conn, output_dir):
    """
    export_trace_matrix
    Functionality: Exports the full trace matrix and individual tables to CSV.
    Inputs: conn (Connection), output_dir (str) - Directory for CSV files.
    Outputs: CSV files written to output_dir.
    Data/Control Flow: Queries each table/view and writes to CSV.
    Timestamp: 2025-02-10 08:30 UTC
    """
    os.makedirs(output_dir, exist_ok=True)

    exports = {
        "TraceMatrix_export.csv": "SELECT * FROM trace_matrix ORDER BY sys_req_id, hlr_id, llr_id",
        "HLR_export.csv":        "SELECT * FROM high_level_requirements ORDER BY id",
        "HLR_TestCases_export.csv": "SELECT * FROM hlr_test_cases ORDER BY parent_hlr, id",
        "LLR_export.csv":        "SELECT * FROM low_level_requirements ORDER BY parent_hlr, id",
        "SDD_Sections_export.csv": "SELECT * FROM sdd_sections ORDER BY sort_order",
    }

    for filename, query in exports.items():
        filepath = os.path.join(output_dir, filename)
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        headers = [desc[0] for desc in cursor.description]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

        print(f"[OK] Exported {len(rows)} rows to {filepath}")


def query_table(conn, table_name):
    """
    query_table
    Functionality: Prints all rows from a specified table or view.
    Inputs: conn (Connection), table_name (str).
    Outputs: Prints formatted rows to stdout.
    Data/Control Flow: Executes SELECT * and prints results.
    Timestamp: 2025-02-10 08:30 UTC
    """
    try:
        cursor = conn.execute(f"SELECT * FROM {table_name}")
        headers = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        if not rows:
            print(f"[INFO] {table_name} is empty.")
            return

        # Print header
        print(" | ".join(headers))
        print("-" * (sum(len(h) for h in headers) + 3 * (len(headers) - 1)))

        # Print rows
        for row in rows:
            print(" | ".join(str(v) if v is not None else "" for v in row))

        print(f"\n({len(rows)} rows)")
    except sqlite3.OperationalError as e:
        print(f"[ERROR] {e}")


def main():
    """
    main
    Functionality: CLI entry point for managing the traceability database.
    Inputs: Command-line arguments.
    Outputs: Varies by subcommand.
    Data/Control Flow: Parses args, routes to appropriate function.
    Timestamp: 2025-02-10 08:30 UTC
    """
    parser = argparse.ArgumentParser(description="DO-178C Requirements Management CLI")
    parser.add_argument("--db-path", default="docs/artefacts/traceability.db",
                        help="Path to the SQLite database")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- add-sys ---
    p_sys = subparsers.add_parser("add-sys", help="Add a system requirement")
    p_sys.add_argument("id", help="Requirement ID (e.g., SYS_001)")
    p_sys.add_argument("text", help="Requirement text")
    p_sys.add_argument("--source", default="User Prompt", help="Source (default: User Prompt)")

    # --- add-hlr ---
    p_hlr = subparsers.add_parser("add-hlr", help="Add a high-level requirement")
    p_hlr.add_argument("id", help="HLR ID (e.g., HLR_001)")
    p_hlr.add_argument("text", help="Requirement text")
    p_hlr.add_argument("--source", required=True, help="Source (e.g., SYS_001 or Derived)")
    p_hlr.add_argument("--parent-sys", help="Parent system requirement ID")
    p_hlr.add_argument("--allocated-to", help="Allocated file/module")

    # --- add-llr ---
    p_llr = subparsers.add_parser("add-llr", help="Add a low-level requirement")
    p_llr.add_argument("id", help="LLR ID (e.g., LLR_001)")
    p_llr.add_argument("text", help="Requirement text")
    p_llr.add_argument("--parent-hlr", required=True, help="Parent HLR ID")
    p_llr.add_argument("--source", help="Source (defaults to parent HLR)")
    p_llr.add_argument("--logic-type", choices=[
        "branch", "loop", "error_handler", "validation",
        "computation", "state_transition", "initialization", "other"
    ], help="Type of logic this LLR represents")
    p_llr.add_argument("--trace-to-code", help="Code reference (e.g., module.c:20-25)")

    # --- add-tc (REMOVED: Use add-hlr-tc instead) ---
    # LLR test cases are no longer required by the simplified schema.

    # --- add-arch ---
    p_arch = subparsers.add_parser("add-arch", help="Add an architectural decision")
    p_arch.add_argument("id", help="Decision ID (e.g., ARCH_001)")
    p_arch.add_argument("description", help="Decision description")
    p_arch.add_argument("--rationale", help="Rationale for the decision")
    p_arch.add_argument("--parent-hlr", help="Related HLR ID")
    p_arch.add_argument("--category", choices=[
        "partitioning", "scheduling", "interface", "resource",
        "safety", "data_flow", "control_flow", "other"
    ], help="Category of the decision")

    # --- export ---
    p_export = subparsers.add_parser("export", help="Export tables to CSV")
    p_export.add_argument("--output-dir", default="docs/artefacts/exports",
                          help="Output directory for CSV files")

    # --- query ---
    p_query = subparsers.add_parser("query", help="Query a table or view")
    p_query.add_argument("table", help="Table or view name (e.g., trace_matrix, v_untested_hlrs)")

    # --- add-hlr-tc ---
    p_htc = subparsers.add_parser("add-hlr-tc", help="Add an HLR-level test case")
    p_htc.add_argument("id", help="Test Case ID (e.g., HTC_001)")
    p_htc.add_argument("--parent-hlr", required=True, help="Parent HLR ID")
    p_htc.add_argument("--test-type", required=True,
                       choices=["integration", "system", "acceptance", "regression", "safety"],
                       help="Type of test")
    p_htc.add_argument("--description", required=True, help="What this test verifies")
    p_htc.add_argument("--procedure", required=True, help="Step-by-step test procedure")
    p_htc.add_argument("--input", required=True, dest="input_data", help="Input data")
    p_htc.add_argument("--expected", required=True, help="Expected output")
    p_htc.add_argument("--pass-criteria", help="Quantitative pass/fail criteria")

    # --- add-sdd-section ---
    p_sdd = subparsers.add_parser("add-sdd-section", help="Add/update an SDD section")
    p_sdd.add_argument("id", help="Section ID (e.g., SDD_1, SDD_5_4)")
    p_sdd.add_argument("--number", required=True, dest="section_number", help="Section number (e.g., 1.1, 5.4)")
    p_sdd.add_argument("--title", required=True, help="Section title")
    p_sdd.add_argument("--content", required=True, help="Full markdown content (use {{TABLE.ID.FIELD}} for refs)")
    p_sdd.add_argument("--sort-order", required=True, type=int, help="Display ordering integer")

    args = parser.parse_args()

    # Decision Logic: Route to appropriate function based on subcommand.
    # Conditions: args.command matches one of the defined subcommands.
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    conn = connect(args.db_path)

    if args.command == "add-sys":
        add_system_req(conn, args.id, args.text, args.source)
    elif args.command == "add-hlr":
        add_hlr(conn, args.id, args.text, args.source, args.parent_sys, args.allocated_to)
    elif args.command == "add-llr":
        add_llr(conn, args.id, args.text, args.parent_hlr, args.source, args.logic_type, args.trace_to_code)
    elif args.command == "add-arch":
        add_arch_decision(conn, args.id, args.description, args.rationale, args.parent_hlr, args.category)
    elif args.command == "export":
        export_trace_matrix(conn, args.output_dir)
    elif args.command == "query":
        query_table(conn, args.table)
    elif args.command == "add-hlr-tc":
        add_hlr_test_case(conn, args.id, args.parent_hlr, args.test_type,
                          args.description, args.procedure, args.input_data,
                          args.expected, args.pass_criteria)
    elif args.command == "add-sdd-section":
        add_sdd_section(conn, args.id, args.section_number, args.title,
                        args.content, args.sort_order)

    conn.close()


if __name__ == "__main__":
    main()
