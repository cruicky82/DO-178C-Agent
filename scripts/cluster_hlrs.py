#!/usr/bin/env python3
"""
cluster_hlrs.py — DO-178C Phase 2B: HLR Clustering Engine

Analyzes import/dependency relationships between source files and groups
related functions into behavioral HLR clusters. Auto-generates draft
High-Level Requirements for each cluster.

Usage:
    python cluster_hlrs.py --db <traceability.db>
    python cluster_hlrs.py --db docs/artefacts/traceability.db --dry-run
    python cluster_hlrs.py --db docs/artefacts/traceability.db --app-root ./

Timestamp: 2026-02-11 09:55 UTC
"""

import argparse
import os
import re
import sqlite3
import sys
from collections import defaultdict


# ============================================================
# Import/dependency extraction patterns by language
# ============================================================

IMPORT_PATTERNS = {
    '.js':  [
        # import ... from '...'
        re.compile(r'''(?:import|export)\s+.*?\s+from\s+['"](.+?)['"]'''),
        # require('...')
        re.compile(r'''require\s*\(\s*['"](.+?)['"]\s*\)'''),
    ],
    '.jsx': None,  # Same as .js — set below
    '.ts':  None,
    '.tsx': None,
    '.go':  [
        # import "package/path"
        re.compile(r'''^\s*"(.+?)"''', re.MULTILINE),
        # import alias "package/path"
        re.compile(r'''^\s*\w+\s+"(.+?)"''', re.MULTILINE),
    ],
    '.py':  [
        # import module / from module import ...
        re.compile(r'''^\s*(?:from\s+(\S+)\s+)?import\s+(\S+)''', re.MULTILINE),
    ],
    '.rs':  [
        # use crate::module::...
        re.compile(r'''^\s*use\s+(?:crate::)?(\S+?)(?:::\{|\s*;)''', re.MULTILINE),
        # mod module_name;
        re.compile(r'''^\s*(?:pub\s+)?mod\s+(\w+)\s*;''', re.MULTILINE),
    ],
}
# Aliases
IMPORT_PATTERNS['.jsx'] = IMPORT_PATTERNS['.js']
IMPORT_PATTERNS['.ts'] = IMPORT_PATTERNS['.js']
IMPORT_PATTERNS['.tsx'] = IMPORT_PATTERNS['.js']


def extract_imports(source, ext):
    """
    Extract import/dependency references from source code.

    Functionality: Find all import/require/use statements
    Inputs: source (str), ext (str) - file extension
    Outputs: set of imported module/file references
    Timestamp: 2026-02-11 09:55 UTC
    """
    patterns = IMPORT_PATTERNS.get(ext)
    if not patterns:
        return set()

    imports = set()
    for pat in patterns:
        for match in pat.finditer(source):
            # Take the first non-None group
            for g in match.groups():
                if g:
                    # Normalize: strip leading ./ and convert separators
                    ref = g.replace('\\', '/').lstrip('./')
                    imports.add(ref)
                    break
    return imports


def build_dependency_graph(app_root, file_paths):
    """
    Build a dependency graph between source files.

    Functionality: Read each file, extract imports, link to known files
    Inputs: app_root (str), file_paths (list of str)
    Outputs: dict mapping file_path -> set of file_paths it imports
    Timestamp: 2026-02-11 09:55 UTC
    """
    graph = defaultdict(set)
    path_index = {}

    # Build a lookup index: basename (no ext) → full path
    for fp in file_paths:
        basename = os.path.splitext(os.path.basename(fp))[0]
        path_index[basename] = fp
        # Also index by directory/basename for deeper matches
        parts = fp.replace('\\', '/').split('/')
        for i in range(len(parts)):
            key = '/'.join(parts[i:]).replace('/', '/')
            key_no_ext = os.path.splitext(key)[0]
            path_index[key_no_ext] = fp

    for fp in file_paths:
        full_path = os.path.join(app_root, fp)
        if not os.path.isfile(full_path):
            continue
        try:
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                source = f.read()
        except Exception:
            continue

        ext = os.path.splitext(fp)[1].lower()
        imports = extract_imports(source, ext)

        for imp in imports:
            # Try to match import to a known file
            imp_clean = imp.replace('\\', '/')
            imp_base = os.path.splitext(os.path.basename(imp_clean))[0]

            matched = path_index.get(imp_clean) or path_index.get(imp_base)
            if matched and matched != fp:
                graph[fp].add(matched)

    return graph


# ============================================================
# Behavioral Domain Rules
# ============================================================

DOMAIN_RULES = {
    'INGEST':   re.compile(r'ingest|feed|poll|stream|listener|dump1090|adsb|opensky|ozrwy', re.I),
    'FUSION':   re.compile(r'fusion|associate|filter|align|smooth|projector|tracker|kctrack', re.I),
    'UI':       re.compile(r'ui|component|view|indicator|hud|indicator|panel|display|frontend', re.I),
    'SITL':     re.compile(r'sitl|simulation|mock|replay', re.I),
    'SORA':     re.compile(r'sora|risk|volume|legend|overlap', re.I),
    'TERRAIN':  re.compile(r'terrain|tile|geotiff|elevation|clipping', re.I),
    'SAFETY':   re.compile(r'alert|safe|threshold|warning|critical|emergency|guard', re.I),
    'CORE':     re.compile(r'core|internal|lib|utils|config|metric|bus|nats|ws|gateway|server|api', re.I),
}

def identify_domain(path):
    """Identify the behavioral domain of a file based on its path."""
    path_lower = path.lower()
    for domain, pattern in DOMAIN_RULES.items():
        if pattern.search(path_lower):
            return domain
    return 'OTHER'

def cluster_files(file_paths, graph):
    """
    Cluster files by behavioral domain and directory proximity.

    Functionality: Group files into behavioral clusters using functional
                   domains as primary signal and directory as secondary.
    Inputs: file_paths (list), graph (dict) - dependency graph
    Outputs: list of clusters, each a dict with 'name' and 'files'
    Timestamp: 2026-02-11 05:45 UTC
    """
    # Group by domain + directory
    domain_groups = defaultdict(lambda: defaultdict(list))
    for fp in file_paths:
        domain = identify_domain(fp)
        normalized = fp.replace('\\', '/')
        directory = os.path.dirname(normalized) or '.'
        domain_groups[domain][directory].append(fp)

    clusters = []
    for domain, dirs in sorted(domain_groups.items()):
        for directory, files in sorted(dirs.items()):
            # If a directory has many files in one domain, sub-cluster by imports
            if len(files) > 10:
                sub_clusters = _sub_cluster_by_imports(files, graph)
                for i, sub_files in enumerate(sub_clusters):
                    cluster_name = f"{domain}_{_generate_cluster_name(directory, i + 1)}"
                    clusters.append({
                        'name': cluster_name,
                        'directory': directory,
                        'domain': domain,
                        'files': sub_files,
                    })
            else:
                cluster_name = f"{domain}_{_generate_cluster_name(directory)}"
                clusters.append({
                    'name': cluster_name,
                    'directory': directory,
                    'domain': domain,
                    'files': files,
                })

    return clusters


def _sub_cluster_by_imports(files, graph):
    """
    Sub-cluster files within a directory by mutual import relationships.

    Uses a simple union-find approach: files that import each other
    are placed in the same sub-cluster.
    """
    parent = {f: f for f in files}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    file_set = set(files)
    for f in files:
        for dep in graph.get(f, set()):
            if dep in file_set:
                union(f, dep)

    groups = defaultdict(list)
    for f in files:
        groups[find(f)].append(f)

    return list(groups.values())


def _generate_cluster_name(directory, sub_idx=None):
    """Generate a human-readable cluster name from a directory path."""
    # Take last 2 path segments for the name
    parts = directory.replace('\\', '/').strip('/').split('/')
    name_parts = parts[-2:] if len(parts) >= 2 else parts
    name = '_'.join(name_parts).upper()
    # Sanitize
    name = re.sub(r'[^A-Z0-9_]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    if not name:
        name = 'ROOT'
    if sub_idx:
        name = f"{name}_{sub_idx}"
    return name


# ============================================================
# Function semantic analysis — extract behavioral verbs
# ============================================================

# Maps function-name patterns to behavioral descriptions
SEMANTIC_PATTERNS = [
    (re.compile(r'(calculate|compute|estimate|derive|measure)', re.I),
     'compute', 'calculate {what} values'),
    (re.compile(r'(validate|check|verify|assert|ensure|guard)', re.I),
     'validate', 'validate {what} constraints'),
    (re.compile(r'(parse|decode|deserialize|extract|read)', re.I),
     'parse', 'parse and decode {what} data'),
    (re.compile(r'(render|display|draw|paint|show|present)', re.I),
     'render', 'render {what} visualizations'),
    (re.compile(r'(send|transmit|emit|publish|broadcast|write)', re.I),
     'transmit', 'transmit {what} data'),
    (re.compile(r'(receive|listen|accept|subscribe|poll|fetch)', re.I),
     'receive', 'receive and process {what} inputs'),
    (re.compile(r'(handle|process|manage|dispatch|route)', re.I),
     'process', 'process {what} events'),
    (re.compile(r'(init|setup|configure|create|start|boot|connect)', re.I),
     'initialize', 'initialize and configure {what} resources'),
    (re.compile(r'(update|set|modify|change|transform|convert)', re.I),
     'update', 'update {what} state'),
    (re.compile(r'(search|find|filter|query|lookup|match|select)', re.I),
     'search', 'search and filter {what} records'),
    (re.compile(r'(log|record|audit|trace|monitor|track)', re.I),
     'monitor', 'monitor and record {what} activity'),
    (re.compile(r'(store|save|persist|cache|buffer)', re.I),
     'store', 'store {what} data'),
    (re.compile(r'(delete|remove|clean|purge|clear|destroy)', re.I),
     'cleanup', 'manage lifecycle of {what} resources'),
    (re.compile(r'(load|import|ingest|consume|open)', re.I),
     'ingest', 'ingest {what} data from external sources'),
    (re.compile(r'(error|fail|abort|rollback|recover|retry)', re.I),
     'recover', 'detect and recover from {what} error conditions'),
]

# Domain-specific "what" placeholders
DOMAIN_SUBJECTS = {
    'INGEST':  'sensor feed',
    'FUSION':  'multi-source tracking',
    'UI':      'operator interface',
    'SITL':    'simulation',
    'SORA':    'SORA risk assessment',
    'TERRAIN': 'terrain elevation',
    'SAFETY':  'safety threshold',
    'CORE':    'system infrastructure',
    'OTHER':   'application',
}


def _split_name(name):
    """Split camelCase, PascalCase, and snake_case into word tokens."""
    # Insert underscores before uppercase runs: handleMissionAck -> handle_Mission_Ack
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', s)
    return [w.lower() for w in re.split(r'[_\-]+', s) if len(w) > 1]


def _classify_function_behaviors(functions):
    """
    Analyze function names to extract dominant behavioral patterns.

    Splits compound names (camelCase/snake_case) and matches EACH word
    against semantic patterns. This ensures 'calculateBearing' is counted
    as 'compute' and 'fetchTerrainElevation' as 'receive', rather than
    everything falling into the generic 'process' bucket.

    Returns a list of (behavior_category, count) sorted by frequency.
    """
    behavior_counts = defaultdict(int)
    for func in functions:
        words = _split_name(func)
        categories_found = set()
        for word in words:
            for pattern, category, _ in SEMANTIC_PATTERNS:
                if pattern.search(word):
                    categories_found.add(category)
                    break
        if categories_found:
            for cat in categories_found:
                behavior_counts[cat] += 1
        else:
            behavior_counts['process'] += 1  # default fallback

    return sorted(behavior_counts.items(), key=lambda x: -x[1])


def _get_llr_profile(db_path, file_paths):
    """
    Query LLR logic type distribution for files in a cluster.
    Returns dict of logic_type -> count.
    """
    conn = sqlite3.connect(db_path)
    profile = defaultdict(int)
    for fp in file_paths:
        cursor = conn.execute("""
            SELECT logic_type, COUNT(*) as cnt
            FROM low_level_requirements
            WHERE trace_to_code LIKE ? || '%'
            GROUP BY logic_type
        """, (fp,))
        for row in cursor:
            profile[row[0]] += row[1]
    conn.close()
    return dict(profile)


def generate_hlr_text(cluster_name, domain, files, functions, db_path=None):
    """
    Generate draft HLR text using behavioral synthesis.

    Synthesizes a DO-178C-compliant behavioral requirement by:
    1. Analyzing function name semantics to extract dominant behaviors
    2. Reading LLR logic type distributions to understand structural patterns
    3. Using domain-specific behavioral templates for meaningful descriptions
    4. Composing implementation-agnostic requirement text

    Functionality: Create behavioral HLR text from cluster analysis
    Inputs: cluster_name (str), domain (str), files (list), functions (list),
            db_path (str, optional) - for LLR profile queries
    Outputs: HLR text string (implementation-agnostic)
    Timestamp: 2026-02-11 19:30 UTC
    """
    # Step 1: Classify function behaviors
    behaviors = _classify_function_behaviors(functions)
    if not behaviors:
        behaviors = [('process', len(functions))]
    behavior_set = {cat for cat, _ in behaviors}
    top_category = behaviors[0][0] if behaviors else 'process'

    # Step 2: Get LLR structural profile if DB available
    llr_profile = {}
    if db_path:
        llr_profile = _get_llr_profile(db_path, files)

    # Step 3: Domain-specific behavioral templates
    # Each domain maps behavior categories to specific, meaningful descriptions.
    # Falls through to a sensible domain-level default if no specific match.
    DOMAIN_BEHAVIORS = {
        'INGEST': {
            'parse':      'receive and decode incoming telemetry streams',
            'receive':    'receive and buffer incoming sensor data feeds',
            'validate':   'validate incoming sensor data integrity and format compliance',
            'process':    'acquire, normalize, and forward sensor data for downstream processing',
            'initialize': 'establish and manage connections to external data sources',
            '_default':   'ingest external data feeds and normalize them into internal representations',
        },
        'FUSION': {
            'compute':    'correlate multi-source tracks and compute fused state estimates',
            'search':     'associate and match detections across sensor sources',
            'validate':   'validate track consistency and flag measurement anomalies',
            'process':    'filter and integrate multi-source measurements into unified tracks',
            '_default':   'fuse multi-source tracking data into correlated track records',
        },
        'UI': {
            'render':     'render geographic, telemetry, and mission data on the operator display',
            'update':     'update the operator display in response to state changes and user actions',
            'validate':   'validate user inputs before committing mission plan changes',
            'initialize': 'initialize map layers, UI panels, and interactive controls',
            'process':    'manage user interactions and coordinate display updates',
            'parse':      'parse and format data for operator display presentation',
            'search':     'search, filter, and select mission elements on the display',
            '_default':   'present geographic and mission data to the operator and manage user interactions',
        },
        'SITL': {
            'initialize': 'initialize and configure software-in-the-loop simulation instances',
            'process':    'manage SITL process lifecycle including startup, monitoring, and teardown',
            'transmit':   'relay simulated telemetry data between the simulation engine and display',
            'validate':   'verify simulation parameter constraints before launch',
            'parse':      'decode simulated MAVLink telemetry from SITL processes',
            '_default':   'manage the lifecycle and data flow of software-in-the-loop simulation processes',
        },
        'SORA': {
            'compute':    'compute SORA ground risk buffers, flight geography, and contingency volumes',
            'validate':   'validate SORA volume geometries against operational constraints',
            'search':     'evaluate population density across SORA risk assessment areas',
            'process':    'determine operational risk classification using SORA methodology',
            '_default':   'calculate SORA risk assessment volumes and classify operational risk levels',
        },
        'TERRAIN': {
            'compute':    'calculate terrain elevation profiles and collision clearances along flight paths',
            'parse':      'parse and decode terrain elevation tile data from geospatial sources',
            'receive':    'fetch terrain elevation tiles from local or remote sources',
            'validate':   'validate terrain clearance margins against minimum safe altitude thresholds',
            'process':    'process terrain data to determine elevation values and obstruction clearances',
            'search':     'query and clip terrain elevation data within specified geographic boundaries',
            '_default':   'process terrain elevation data and assess flight path clearance margins',
        },
        'SAFETY': {
            'validate':   'evaluate safety thresholds and trigger alerting when limits are exceeded',
            'monitor':    'continuously monitor safety-critical parameters against defined limits',
            'compute':    'calculate safety margins and proximity to operational boundaries',
            'process':    'detect safety-critical conditions and initiate appropriate responses',
            '_default':   'monitor safety-critical thresholds and issue alerts when limits are approached',
        },
        'CORE': {
            'parse':      'parse and decode communications protocol messages for internal processing',
            'initialize': 'initialize system services and establish inter-component communication channels',
            'compute':    'perform core mathematical and geospatial utility calculations',
            'process':    'provide shared computational services used across system components',
            'receive':    'receive and route messages between system components',
            '_default':   'provide core infrastructure services including communications, utilities, and configuration',
        },
        'OTHER': {
            'validate':   'validate operational parameters against configured constraints',
            'compute':    'perform domain-specific calculations and data transformations',
            'process':    'coordinate processing workflows across system components',
            'initialize': 'initialize and configure system components and runtime environment',
            'ingest':     'load and process external data files and configuration resources',
            '_default':   'coordinate application workflows and manage cross-cutting processing concerns',
        },
    }

    domain_templates = DOMAIN_BEHAVIORS.get(domain, DOMAIN_BEHAVIORS['OTHER'])

    # Select the best template: prefer the top behavior category, then try others
    primary_text = None
    for cat, _ in behaviors:
        if cat in domain_templates:
            primary_text = domain_templates[cat]
            break
    if not primary_text:
        primary_text = domain_templates.get('_default',
                                            f'manage {DOMAIN_SUBJECTS.get(domain, "application")} operations')

    # Step 4: Build structural qualifier from LLR profile
    structural_qualifier = ''
    if llr_profile:
        total_llrs = sum(llr_profile.values())
        branch_pct = llr_profile.get('branch', 0) * 100 // max(total_llrs, 1)
        error_pct = llr_profile.get('error_handler', 0) * 100 // max(total_llrs, 1)
        validation_pct = llr_profile.get('validation', 0) * 100 // max(total_llrs, 1)

        qualifiers = []
        if branch_pct > 20:
            qualifiers.append('conditional logic paths')
        if error_pct > 10:
            qualifiers.append('error detection and recovery')
        if validation_pct > 10:
            qualifiers.append('input validation')
        if llr_profile.get('computation', 0) > 3:
            qualifiers.append('numerical computations')
        if llr_profile.get('loop', 0) > 3:
            qualifiers.append('iterative data processing')

        if qualifiers:
            structural_qualifier = f', incorporating {" and ".join(qualifiers[:2])}'

    # Step 5: Add secondary behavior as a supplementary clause
    secondary_text = ''
    if len(behaviors) > 1:
        # Find a DIFFERENT domain template for the second behavior category
        for cat, _ in behaviors[1:]:
            if cat in domain_templates and domain_templates[cat] != primary_text:
                secondary_text = f' The software shall also {domain_templates[cat]}.'
                break

    # Step 6: Compose final HLR text
    hlr = f"The software shall {primary_text}{structural_qualifier}.{secondary_text}"

    return hlr


def populate_hlrs(db_path, clusters, dry_run=False):
    """
    Write HLR drafts to the database with full traceability.

    Functionality: Auto-generate System Requirements per domain,
                   UPSERT HLRs with parent_sys set, re-parent LLRs
    Inputs: db_path (str), clusters (list), dry_run (bool)
    Outputs: count of HLRs created
    Timestamp: 2026-02-11 06:00 UTC
    """
    # Collect unique domains from clusters
    domains = sorted(set(c.get('domain', 'OTHER') for c in clusters))

    # Domain descriptions for system requirements
    DOMAIN_DESCRIPTIONS = {
        'INGEST':  'The system shall provide data ingestion capabilities for external sensor feeds.',
        'FUSION':  'The system shall correlate and filter multi-source tracking data.',
        'UI':      'The system shall render operator displays and controls.',
        'SITL':    'The system shall support simulation and replay of operations.',
        'SORA':    'The system shall compute SORA risk assessments and airspace volumes.',
        'TERRAIN': 'The system shall process and display terrain elevation data.',
        'SAFETY':  'The system shall monitor safety thresholds and issue alerts.',
        'CORE':    'The system shall provide core infrastructure services.',
        'OTHER':   'The system shall provide auxiliary software services.',
    }

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    # Phase 1: Auto-generate system requirements per domain
    sys_req_map = {}  # domain -> sys_req_id
    for domain in domains:
        sys_id = f"SYS_{domain}_001"
        sys_text = DOMAIN_DESCRIPTIONS.get(domain,
            f"The system shall provide {domain.lower()} capabilities.")

        if dry_run:
            print(f"  [DRY-RUN] System Req: {sys_id}")
            print(f"            {sys_text}")
        else:
            cursor.execute("""
                INSERT INTO system_requirements (id, text, source)
                VALUES (?, ?, 'Derived from behavioral domain analysis')
                ON CONFLICT(id) DO UPDATE SET
                    text = excluded.text,
                    updated_at = datetime('now')
            """, (sys_id, sys_text))

        sys_req_map[domain] = sys_id

    if not dry_run:
        print(f"  {len(sys_req_map)} system requirements created/updated")

    # Phase 2: UPSERT HLRs with parent_sys set
    hlr_count = 0
    for cluster in clusters:
        hlr_id = f"HLR_{cluster['name']}"
        hlr_text = cluster['hlr_text']
        files = cluster['files']
        domain = cluster.get('domain', 'OTHER')
        parent_sys = sys_req_map.get(domain, sys_req_map.get('OTHER'))

        if dry_run:
            print(f"  [DRY-RUN] {hlr_id} -> {parent_sys}")
            print(f"            {hlr_text[:100]}")
            print(f"            Files: {', '.join(files)}")
            print()
            continue

        # UPSERT the HLR with parent_sys
        cursor.execute("""
            INSERT INTO high_level_requirements
                (id, text, source, parent_sys, is_derived, derivation_rationale,
                 hlr_category, allocated_to)
            VALUES (?, ?, ?, ?, 1,
                    'Auto-generated by cluster_hlrs.py from behavioral domain analysis',
                    'functional', ?)
            ON CONFLICT(id) DO UPDATE SET
                text = excluded.text,
                parent_sys = excluded.parent_sys,
                allocated_to = excluded.allocated_to,
                updated_at = datetime('now')
        """, (hlr_id, hlr_text, parent_sys, parent_sys, cluster['directory']))
        hlr_count += 1

        # Re-parent LLRs: find LLRs that trace to files in this cluster
        for file_path in files:
            cursor.execute("""
                UPDATE low_level_requirements
                SET parent_hlr = ?, source = ?, updated_at = datetime('now')
                WHERE parent_hlr = 'HLR_UNCLUSTERED'
                  AND trace_to_code LIKE ? || '%'
            """, (hlr_id, hlr_id, file_path))

        # Update source_inventory.parent_hlr
        for file_path in files:
            cursor.execute("""
                UPDATE source_inventory
                SET parent_hlr = ?
                WHERE file_path = ?
            """, (hlr_id, file_path))

    if not dry_run:
        # Check if HLR_UNCLUSTERED has any remaining LLRs
        cursor.execute("""
            SELECT COUNT(*) FROM low_level_requirements
            WHERE parent_hlr = 'HLR_UNCLUSTERED'
        """)
        remaining = cursor.fetchone()[0]
        if remaining == 0:
            cursor.execute("DELETE FROM high_level_requirements WHERE id = 'HLR_UNCLUSTERED'")
            print(f"  Removed HLR_UNCLUSTERED placeholder (all LLRs re-parented)")
        else:
            print(f"  WARNING: {remaining} LLRs still under HLR_UNCLUSTERED")

        conn.commit()

    conn.close()
    return hlr_count


def main():
    parser = argparse.ArgumentParser(
        description='DO-178C Phase 2B: Cluster functions into HLR candidates'
    )
    parser.add_argument('--db', required=True,
                        help='Path to traceability.db')
    parser.add_argument('--app-root', default=None,
                        help='Root directory of the application source')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print clusters without writing to DB')

    args = parser.parse_args()

    db = os.path.abspath(args.db)
    if not os.path.isfile(db):
        print(f"ERROR: Database not found: {db}")
        sys.exit(1)

    # Get all unique file paths from source_inventory
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT DISTINCT file_path FROM source_inventory ORDER BY file_path
    """)
    file_paths = [row['file_path'] for row in cursor.fetchall()]

    # Get function names per file
    func_by_file = defaultdict(list)
    cursor = conn.execute("""
        SELECT file_path, function_name FROM source_inventory
        ORDER BY file_path, start_line
    """)
    for row in cursor:
        func_by_file[row['file_path']].append(row['function_name'])
    conn.close()

    if not file_paths:
        print("No files in source_inventory. Run scan_codebase.py first.")
        sys.exit(0)

    # Determine app root
    app_root = args.app_root
    if not app_root:
        db_dir = os.path.dirname(db)
        if db_dir.endswith(os.sep + os.path.join('docs', 'artefacts')):
            app_root = os.path.dirname(os.path.dirname(db_dir))
        else:
            app_root = os.path.dirname(db)
    app_root = os.path.abspath(app_root)

    print(f"=== DO-178C Phase 2B: HLR Clustering ===")
    print(f"DB:       {db}")
    print(f"App Root: {app_root}")
    print(f"Files:    {len(file_paths)}")
    print()

    # Build dependency graph
    print("Building dependency graph...")
    graph = build_dependency_graph(app_root, file_paths)
    edge_count = sum(len(deps) for deps in graph.values())
    print(f"  {len(graph)} files with imports, {edge_count} dependency edges\n")

    # Cluster files
    clusters = cluster_files(file_paths, graph)
    print(f"Identified {len(clusters)} clusters:\n")

    for cluster in clusters:
        # Look up function names for this cluster
        funcs = []
        for fp in cluster['files']:
            funcs.extend(func_by_file.get(fp, []))

        cluster['hlr_text'] = generate_hlr_text(
            cluster['name'], cluster['domain'], cluster['files'], funcs,
            db_path=db
        )
        cluster['functions'] = funcs

        print(f"  [{cluster['name']}]")
        print(f"    Domain:    {cluster['domain']}")
        print(f"    Directory: {cluster['directory']}")
        print(f"    Files: {len(cluster['files'])}, Functions: {len(funcs)}")

    print()

    # Populate database
    if args.dry_run:
        print("--- DRY RUN (no DB writes) ---\n")
    count = populate_hlrs(db, clusters, dry_run=args.dry_run)
    if not args.dry_run:
        print(f"\n{count} HLRs written to database")

    print("\nPhase 2B complete.")


if __name__ == '__main__':
    main()
