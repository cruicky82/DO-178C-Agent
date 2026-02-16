#!/usr/bin/env python3
"""
render_sdd.py
Functionality: Renders the SDD document from database sections, resolving dynamic references.
Inputs: --db-path (required), --output (optional, default: docs/artefacts/SDD.md)
Outputs: Rendered SDD.md file with all {{ref}} placeholders resolved.
Data/Control Flow: Reads sdd_sections ordered by sort_order, resolves {{TABLE.ID.FIELD}}
                   and {{LIST_LLRS:HLR_ID}} placeholders, writes final markdown.
Timestamp: 2025-02-10 21:45 UTC
"""

import sqlite3
import argparse
import re
import os
import sys

# Mapping of placeholder table names to actual DB table names
TABLE_MAP = {
    "HLR":  "high_level_requirements",
    "LLR":  "low_level_requirements",
    "HTC":  "hlr_test_cases",
    "SYS":  "system_requirements",
    "ARCH": "architecture_decisions",
}


def get_db_connection(db_path):
    """
    get_db_connection
    Functionality: Opens a read-only connection to the traceability database.
    Inputs: db_path (str) - Path to the SQLite database.
    Outputs: sqlite3.Connection with row_factory set.
    Data/Control Flow: Checks file existence, connects, returns connection.
    Timestamp: 2025-02-10 21:45 UTC
    """
    # Decision Logic: Check if DB file exists.
    # Conditions: os.path.exists(db_path) is True.
    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def resolve_field_ref(conn, table_key, record_id, field_name):
    """
    resolve_field_ref
    Functionality: Resolves a single {{TABLE.ID.FIELD}} reference to its current DB value.
    Inputs: conn (Connection), table_key (str), record_id (str), field_name (str).
    Outputs: Resolved string value, or an error marker if not found.
    Data/Control Flow: Maps table_key to real table, queries for record, extracts field.
    Timestamp: 2025-02-10 21:45 UTC
    """
    # Decision Logic: Check if table_key is valid.
    # Conditions: table_key is in TABLE_MAP.
    if table_key not in TABLE_MAP:
        return f"[UNRESOLVED: unknown table '{table_key}']"

    real_table = TABLE_MAP[table_key]

    try:
        row = conn.execute(
            f"SELECT * FROM {real_table} WHERE id = ?", (record_id,)
        ).fetchone()
    except sqlite3.OperationalError as e:
        return f"[UNRESOLVED: DB error '{e}']"

    # Decision Logic: Check if record was found.
    # Conditions: row is not None.
    if row is None:
        return f"[UNRESOLVED: {table_key}.{record_id} not found]"

    # Decision Logic: Check if requested field exists.
    # Conditions: field_name is in row keys.
    if field_name not in row.keys():
        return f"[UNRESOLVED: {table_key}.{record_id} has no field '{field_name}']"

    value = row[field_name]
    # Decision Logic: Handle None values.
    # Conditions: value is None.
    if value is None:
        return "(empty)"

    return str(value)


def resolve_list_llrs(conn, hlr_id):
    """
    resolve_list_llrs
    Functionality: Generates a bullet list of all LLRs under a given HLR.
    Inputs: conn (Connection), hlr_id (str).
    Outputs: Markdown bullet list string.
    Data/Control Flow: Queries low_level_requirements filtered by parent_hlr.
    Timestamp: 2025-02-10 21:45 UTC
    """
    rows = conn.execute(
        "SELECT id, text, logic_type, trace_to_code FROM low_level_requirements WHERE parent_hlr = ? ORDER BY id",
        (hlr_id,)
    ).fetchall()

    # Decision Logic: Check if any LLRs exist for this HLR.
    # Conditions: len(rows) > 0.
    if not rows:
        return f"*(No LLRs found for {hlr_id})*"

    lines = []
    for r in rows:
        code_ref = f" → `{r['trace_to_code']}`" if r['trace_to_code'] else ""
        lines.append(f"- **{r['id']}** [{r['logic_type'] or 'other'}]: {r['text']}{code_ref}")

    return "\n".join(lines)


def resolve_list_htcs(conn, hlr_id):
    """
    resolve_list_htcs
    Functionality: Generates a bullet list of all test cases under a given HLR.
    Inputs: conn (Connection), hlr_id (str).
    Outputs: Markdown bullet list string.
    Data/Control Flow: Queries hlr_test_cases filtered by parent_hlr.
    Timestamp: 2025-02-10 21:45 UTC
    """
    rows = conn.execute(
        "SELECT id, test_type, description, pass_fail FROM hlr_test_cases WHERE parent_hlr = ? ORDER BY id",
        (hlr_id,)
    ).fetchall()

    # Decision Logic: Check if any test cases exist for this HLR.
    # Conditions: len(rows) > 0.
    if not rows:
        return f"*(No test cases found for {hlr_id})*"

    lines = []
    for r in rows:
        status = f" [{r['pass_fail']}]" if r['pass_fail'] != 'NOT_RUN' else ""
        lines.append(f"- **{r['id']}** ({r['test_type']}): {r['description']}{status}")

    return "\n".join(lines)


def resolve_trace_matrix(conn):
    """
    resolve_trace_matrix
    Functionality: Generates a full trace matrix as a markdown table.
    Inputs: conn (Connection).
    Outputs: Markdown table string.
    Data/Control Flow: Queries trace_matrix view and formats as markdown table.
    Timestamp: 2025-02-10 21:45 UTC
    """
    rows = conn.execute("SELECT * FROM trace_matrix ORDER BY sys_req_id, hlr_id, llr_id").fetchall()

    # Decision Logic: Check if trace matrix has any rows.
    # Conditions: len(rows) > 0.
    if not rows:
        return "*(Trace matrix is empty)*"

    headers = rows[0].keys()
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for r in rows:
        lines.append("| " + " | ".join(str(r[h]) if r[h] is not None else "" for h in headers) + " |")

    return "\n".join(lines)


def resolve_all_references(conn, content):
    """
    resolve_all_references
    Functionality: Scans markdown content for all {{...}} placeholders and resolves them.
    Inputs: conn (Connection), content (str) - markdown with placeholders.
    Outputs: Fully resolved markdown string.
    Data/Control Flow: Uses regex to find placeholders, dispatches to appropriate resolver.
    Timestamp: 2025-02-10 21:45 UTC
    """
    # Resolve {{TABLE.ID.FIELD}} references
    # Decision Logic: Find all {{X.Y.Z}} patterns.
    # Conditions: Pattern matches 3-part dot-separated reference.
    def replace_field_ref(match):
        table_key = match.group(1)
        record_id = match.group(2)
        field_name = match.group(3)
        return resolve_field_ref(conn, table_key, record_id, field_name)

    content = re.sub(
        r'\{\{(\w+)\.(\w+)\.(\w+)\}\}',
        replace_field_ref,
        content
    )

    # Resolve {{LIST_LLRS:HLR_ID}} references
    # Decision Logic: Find all LIST_LLRS patterns.
    # Conditions: Pattern matches LIST_LLRS:<id> format.
    def replace_list_llrs(match):
        hlr_id = match.group(1)
        return resolve_list_llrs(conn, hlr_id)

    content = re.sub(
        r'\{\{LIST_LLRS:(\w+)\}\}',
        replace_list_llrs,
        content
    )

    # Resolve {{LIST_HTCS:HLR_ID}} references
    # Decision Logic: Find all LIST_HTCS patterns.
    # Conditions: Pattern matches LIST_HTCS:<id> format.
    def replace_list_htcs(match):
        hlr_id = match.group(1)
        return resolve_list_htcs(conn, hlr_id)

    content = re.sub(
        r'\{\{LIST_HTCS:(\w+)\}\}',
        replace_list_htcs,
        content
    )

    # Resolve {{TRACE_MATRIX}} reference
    # Decision Logic: Find TRACE_MATRIX placeholder.
    # Conditions: Exact match of {{TRACE_MATRIX}}.
    if "{{TRACE_MATRIX}}" in content:
        content = content.replace("{{TRACE_MATRIX}}", resolve_trace_matrix(conn))

    return content


def render_sdd(db_path, output_path):
    """
    render_sdd
    Functionality: Reads all SDD sections from DB, resolves references, writes SDD.md.
    Inputs: db_path (str), output_path (str).
    Outputs: Rendered SDD.md file on disk.
    Data/Control Flow: Query → Resolve → Write.
    Timestamp: 2025-02-10 21:45 UTC
    """
    conn = get_db_connection(db_path)

    sections = conn.execute(
        "SELECT section_number, title, content FROM sdd_sections ORDER BY sort_order"
    ).fetchall()

    # Decision Logic: Check if any sections exist.
    # Conditions: len(sections) > 0.
    if not sections:
        print("[WARN] No SDD sections found in database. Nothing to render.")
        conn.close()
        return

    output_lines = []

    for sec in sections:
        resolved_content = resolve_all_references(conn, sec['content'])
        output_lines.append(resolved_content)
        output_lines.append("")  # blank line between sections

    conn.close()

    # Write output
    # Decision Logic: Ensure output directory exists.
    # Conditions: os.path.dirname(output_path) is non-empty.
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"[OK] SDD rendered to {output_path} ({len(sections)} sections)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render SDD from traceability database")
    parser.add_argument("--db-path", required=True, help="Path to the traceability database")
    parser.add_argument("--output", default="docs/artefacts/SDD.md",
                        help="Output path for rendered SDD.md (default: docs/artefacts/SDD.md)")
    args = parser.parse_args()

    render_sdd(args.db_path, args.output)
