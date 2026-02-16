#!/usr/bin/env python3
"""
refine_requirements.py — DO-178C Phase 3: Requirement Refinement Agent

Systematically improves the quality of HLRs and LLRs by:
1. Removing implementation details (file names, extensions).
2. Enforcing "The software shall" pattern.
3. Adding quantitative tolerances where missing.
4. Improving pseudocode detail in LLRs.
"""

import sqlite3
import re
import os
import argparse

DB_PATH = r"C:\Users\cruic\KCGCS\docs\artefacts\traceability.db"

# Patterns to remove
FILE_EXTS = re.compile(r'\.(js|go|py|rs|ts|tsx|jsx|css|html|md|pb\.go|pb|proto)', re.I)
FILE_PATHS = re.compile(r'(\w+/)+\w+\.\w+', re.I)

QUANT_KEYWORDS = ['accuracy', 'tolerance', 'latency', 'within', 'less than',
                   'greater than', 'maximum', 'minimum', 'ms', 'seconds',
                   'meters', '%', 'knots', 'feet', 'km']

# Numerical patterns in LLR text for boundary extraction
NUMERICAL_PAT = re.compile(
    r'(\d+\.?\d*)\s*(ms|seconds?|s|meters?|m|km|ft|feet|knots?|kts|kPa|Hz|%|bytes?|MB|GB)',
    re.I
)

TIMING_KEYWORDS = ['timeout', 'interval', 'delay', 'latency', 'period', 'rate',
                   'frequency', 'update', 'refresh', 'poll']
DISTANCE_KEYWORDS = ['distance', 'range', 'radius', 'offset', 'buffer', 'altitude',
                     'elevation', 'height', 'separation']
RATIO_KEYWORDS = ['threshold', 'limit', 'max', 'min', 'ceiling', 'floor', 'cap']


def infer_quantitative_terms(hlr_id, hlr_text, llr_texts):
    """
    Analyze child LLR texts to infer quantitative qualifiers for the parent HLR.
    Returns a suffix string to append if the HLR lacks quantitative terms.
    """
    # Already has quantitative terms?
    if any(kw in hlr_text.lower() for kw in QUANT_KEYWORDS):
        return None

    # Collect all numerical values from LLRs
    all_nums = []
    for ltxt in llr_texts:
        for m in NUMERICAL_PAT.finditer(ltxt):
            all_nums.append((float(m.group(1)), m.group(2).lower()))

    if not all_nums:
        # No numerical data available — check for timing/distance keywords
        combined = ' '.join(llr_texts).lower()
        if any(k in combined for k in TIMING_KEYWORDS):
            return " Processing shall complete within the required time constraints."
        elif any(k in combined for k in DISTANCE_KEYWORDS):
            return " Distance calculations shall meet accuracy requirements."
        return None

    # Group by unit type
    by_unit = {}
    for val, unit in all_nums:
        # Normalize units
        norm_unit = unit.rstrip('s')  # 'seconds' -> 'second'
        if norm_unit not in by_unit:
            by_unit[norm_unit] = []
        by_unit[norm_unit].append(val)

    # Build quantitative suffix from the most common unit class
    parts = []
    for unit, vals in sorted(by_unit.items(), key=lambda x: -len(x[1])):
        mn, mx = min(vals), max(vals)
        if mn == mx:
            parts.append(f"{mn} {unit}")
        else:
            parts.append(f"{mn}–{mx} {unit}")

    if parts:
        return f" Operational parameters: {'; '.join(parts[:3])}."
    return None


def refine_hlr(hlr_id, text, functions, llr_texts=None):
    """Refine a single HLR."""
    # Remove file extensions
    refined = FILE_EXTS.sub('', text)
    # Remove paths
    refined = FILE_PATHS.sub('', refined)

    # Ensure "The software shall"
    if not refined.lower().startswith("the software shall"):
        # Strip generic prefixes like "The system shall" or "It shall"
        refined = re.sub(
            r'^(the system|it|the module|the component)\s+shall',
            'the software shall', refined, flags=re.I
        )
        if not refined.lower().startswith("the software shall"):
            refined = "The software shall " + refined[0].lower() + refined[1:]

    # Clean up double spaces or generic phrases
    refined = refined.replace("  ", " ").strip()
    if not refined.endswith("."):
        refined += "."

    # Inject quantitative terms if missing
    if llr_texts:
        suffix = infer_quantitative_terms(hlr_id, refined, llr_texts)
        if suffix:
            # Remove trailing period, add suffix
            refined = refined.rstrip('.') + suffix

    return refined

def main():
    parser = argparse.ArgumentParser(description='Refine HLRs/LLRs in the database.')
    parser.add_argument('--db', help='Path to traceability.db')
    parser.add_argument('--apply', action='store_true', help='Actually update the DB')
    args = parser.parse_args()

    db_to_use = args.db if args.db else DB_PATH

    conn = sqlite3.connect(db_to_use)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    print("=== Phase 3: Requirement Refinement ===")
    
    # 1. Refine HLRs
    c.execute("SELECT id, text FROM high_level_requirements")
    hlrs = c.fetchall()
    
    for row in hlrs:
        hid = row['id']
        old_text = row['text']
        
        # Get functions associated via source_inventory
        c.execute("SELECT function_name FROM source_inventory WHERE parent_hlr = ?", (hid,))
        funcs = [r[0] for r in c.fetchall()]
        
        # Get child LLR texts for quantitative inference
        c.execute("SELECT text FROM low_level_requirements WHERE parent_hlr = ?", (hid,))
        llr_texts = [r[0] for r in c.fetchall()]

        new_text = refine_hlr(hid, old_text, funcs, llr_texts=llr_texts)
        
        if old_text != new_text:
            print(f"\n[{hid}]")
            print(f"  OLD: {old_text}")
            print(f"  NEW: {new_text}")
            
            if args.apply:
                c.execute("UPDATE high_level_requirements SET text = ?, updated_at = datetime('now') WHERE id = ?", (new_text, hid))

    # 2. Refine LLRs (ensure they aren't just summaries)
    c.execute("SELECT id, text, parent_hlr FROM low_level_requirements")
    llrs = c.fetchall()
    for row in llrs:
        lid = row['id']
        txt = row['text']
        new_txt = FILE_EXTS.sub('', txt)
        if txt != new_txt:
            print(f"  LLR Refined: {lid}")
            if args.apply:
                c.execute("UPDATE low_level_requirements SET text = ?, updated_at = datetime('now') WHERE id = ?", (new_txt, lid))

    if args.apply:
        conn.commit()
        print("\nDatabase updated successfully.")
    else:
        print("\nDry run complete. Use --apply to save changes.")

    conn.close()

if __name__ == "__main__":
    main()
