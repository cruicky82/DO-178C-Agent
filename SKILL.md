---
name: do178c-dev
description: "Strict DO-178C Level D+ governance for safety-critical software. Enforces V-Model workflow with proper 1:N HLR→LLR decomposition, SQLite-backed traceability, and DI-IPSC-81435A SDD compliance. Supports both Forward and Reverse Engineering workflows."
---

# Safety-Critical Developer Protocols (DO-178C)

## 1. Activation Rules

**WHEN TO APPLY:**

1.  **New Code (Mode B - Forward Engineering):** Automatically apply when the user asks to generate **new** features, modules, or functions.
2.  **Existing Code (Mode A - Reverse Engineering):** Apply when the user asks to "reverse engineer requirements," "add compliance to existing code," "certify," or "refactor for safety."
3.  **Explicit Request:** Apply to any code the user explicitly requests "compliance," "certification," or "DO-178C" for.

**EXCEPTION:**
If the user asks for a quick script, debug snippet, or "scratchpad" code NOT part of the production codebase, you may bypass this skill _if and only if_ you state: _"Bypassing DO-178C protocols for this ad-hoc request."_

---

## 2. Mode Selection & Execution Rules (MANDATORY)

### 2.1 COMPLETENESS GATE (MANDATORY FIRST STEP)

Before any requirements analysis, you **MUST** perform a complete file discovery:

1.  **Enumerate ALL source files** in `${APP_ROOT}` and any supporting directories (shared libraries, backend services, etc.).
2.  **Record the file list** as a checklist. Every file with functional logic MUST be analyzed.
3.  In a **monorepo**, identify all directories the target app depends on (e.g., shared `kccore/`, `libs/`, service directories). Include ALL of them in scope.
4.  **DO NOT** limit yourself to the first few files you encounter. If a directory contains 20 files, you analyze all 20.

> **RULE: No file may be skipped.** Every source file in scope gets LLRs. HLRs are derived from **software functions** (behavioral capabilities), not from files — multiple files may contribute LLRs to a single HLR.

### 2.2 PIPELINE EXECUTION (MULTI-SESSION)

The DO-178C workflow executes as a **9-phase pipeline**. Each phase persists progress to the database. You may complete multiple phases in one session, but you **MUST NOT skip phases**. Large codebases may require multiple sessions — this is expected.

**Before starting**, run `check_progress.py --db <db>` to see current state.
**After each phase**, run `check_progress.py` to verify progress.

| Phase | Name             | Tool                                          | Description                                                                                                                                                                                                                                                                          |
| ----- | ---------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1     | **SCAN**         | `scan_codebase.py`                            | Catalog all source files and functions into `source_inventory`                                                                                                                                                                                                                       |
| 2A    | **LLR DERIVE**   | `derive_llrs.py`                              | Auto-generate draft LLRs from code structure (AST/regex). Deterministic.                                                                                                                                                                                                             |
| 2B    | **HLR CLUSTER**  | `cluster_hlrs.py`                             | Cluster functions into behavioral HLR candidates using domain-specific templates and function semantic analysis. Produces implementation-agnostic HLR text (no function names or file references). Auto-generates System Requirements per domain and sets `parent_sys` on every HLR. |
| 2C    | **REFINE**       | `refine_requirements.py`                      | Strip file extensions, enforce "The software shall" pattern, inject quantitative terms from LLR boundary analysis.                                                                                                                                                                   |
| 2D    | **ARCH EXTRACT** | `extract_architecture.py`                     | Infer architecture decisions from import graphs, component boundaries, data flow, and interface patterns.                                                                                                                                                                            |
| 3     | **REVIEW**       | Agent                                         | Review auto-generated HLRs/LLRs. Refine text, add quantitative tolerances.                                                                                                                                                                                                           |
| 4     | **TEST GEN**     | `gen_test_cases.py`                           | Auto-generate Normal Range + Robustness test case skeletons with boundary analysis per HLR. Use `--gen-scripts <dir>` to generate executable test files.                                                                                                                             |
| 5     | **SDD GEN**      | `populate_sdd.py` + `render_sdd.py`           | Generate SDD sections from populated DB                                                                                                                                                                                                                                              |
| 6     | **VALIDATE**     | `init_db.py --validate` + `check_progress.py` | Verify completeness, traceability chain, quantitative quality, and anti-patterns                                                                                                                                                                                                     |

**Key Rules:**

- **Phases 2A–2D are deterministic.** They auto-generate DRAFT-quality artifacts from code analysis. The agent reviews and refines in Phase 3.
- **Phase 2B auto-generates System Requirements** per behavioral domain (INGEST, FUSION, UI, SITL, SORA, TERRAIN, SAFETY, CORE, OTHER) and sets `parent_sys` on every HLR. No HLR may exist without a parent system requirement.
- **Phase 2B generates implementation-agnostic HLR text** by analyzing function name semantics (15 verb categories via camelCase/snake_case splitting), selecting from domain-specific behavioral templates (~55 templates across 9 domains), and adding LLR-profile structural qualifiers. HLR text must never contain function names, file names, or directory paths.
- **Phase 2C injects quantitative terms** by analyzing child LLR boundaries when the parent HLR lacks measurable tolerances.
- **Phase 2D extracts architecture decisions** from the import graph and component structure, populating the `architecture_decisions` table.
- **Phase 3 is the agent's primary value-add.** Review generated HLR text to be quantitative with tolerances. Add architecture decisions. Flag safety requirements.
- **Progress persists in the DB.** If a session ends mid-pipeline, the next session resumes from where it left off by running `check_progress.py`.
- **Each phase is idempotent.** Re-running a phase updates existing records without duplication.
- **Do not skip.** Phase 2B requires Phase 2A (clusters need LLRs). Phase 4 requires Phase 2B (tests are per-HLR).

### 2.3 Mode Selection

Ask the user which mode to use, or infer from context:

#### Mode A: Reverse Engineering (Code → Requirements)

**Flow:** `scan_codebase.py → derive_llrs.py → cluster_hlrs.py → refine_requirements.py → extract_architecture.py → Agent Review → gen_test_cases.py → SDD → Validate`

1.  **Step A0:** Perform Completeness Gate (§2.1). Run `scan_codebase.py --root <APP_ROOT> --db <db>`.
2.  **Step A1:** Run `derive_llrs.py --db <db> --app-root <APP_ROOT>` to auto-generate draft LLRs.
3.  **Step A2:** Run `cluster_hlrs.py --db <db> --app-root <APP_ROOT>` to cluster functions into behavioral HLR candidates grouped by domain. This also auto-generates system requirements per domain and sets `parent_sys` on every HLR.
4.  **Step A2C:** Run `refine_requirements.py --db <db> --apply` to strip file extensions, enforce standard phrasing, and inject quantitative terms from LLR boundary analysis.
5.  **Step A2D:** Run `extract_architecture.py --db <db> --app-root <APP_ROOT>` to infer and populate architecture decisions.
6.  **Step A3:** **Agent Review** — Refine auto-generated HLR text to be quantitative and implementation-agnostic. Add tolerances, apply the HLR Quality Gate (§3.1). Flag Derived HLRs (§3.5). Review and refine architecture decisions.
7.  **Step A4:** Run `gen_test_cases.py --db <db> --gen-scripts <APP_ROOT>/tests` to generate test case skeletons with boundary analysis and executable test scripts.
8.  **Step A5:** **Agent Review** — Refine test case procedures, input data, and pass criteria.
9.  **Step A6:** Run `check_progress.py --db <db>` to verify pipeline completeness.
10. **Step A7:** Populate SDD and run final validation.

#### Mode B: Forward Engineering (Requirements → Code)

**Use when:** Building new functionality from a user prompt or system requirement.
**Flow:** `User Prompt → HLRs → LLRs → Code → HLR Test Cases → Test Scripts → Establish Traceability`

1.  **Step B1:** Analyze the user's request and derive **High-Level Requirements (HLRs)** — the "what."
2.  **Step B2:** Decompose each HLR into multiple **Low-Level Requirements (LLRs)** — the "how."
3.  **Step B3:** Write source code that implements each LLR.
4.  **Step B4:** For **every** HLR, generate a detailed **HLR Test Case**.
5.  **Step B5:** Generate runnable **Test Scripts** from the HLR Test Cases (see §9).
6.  **Step B6:** Populate the traceability database and run validation.

---

## 3. Requirements Hierarchy (The 1:N Decomposition)

This is the core principle. Follow DO-178C's explicit hierarchy:

```
System Requirements (User Prompt)
    └──► High-Level Requirements (HLR) — Black Box: WHAT the software does
              └──► Software Architecture — HOW the structure is organized
                        └──► Low-Level Requirements (LLR) — White Box: HOW each piece works
                                  └──► Source Code — The implementation
```

### 3.1 High-Level Requirements (HLR) — Software Functions

HLRs are the **direct output of the Software Requirements Process** (DO-178C §5.1). They describe the software's **functional, performance, interface, and safety requirements** as derived from system requirements.

**CRITICAL RULE: FUNCTIONS, NOT FILES**

HLRs describe **what the software does** as behavioral capabilities, NOT what a specific source file contains. A single HLR may be implemented across multiple files. Multiple HLRs may share code in the same file.

- **FORBIDDEN:** "The Utils module shall provide coordinate conversion functions." (This describes a file, not a function)
- **REQUIRED:** "The software shall convert geographic coordinates (lat/lon) to local East/North offsets relative to a user-defined origin with accuracy ≤1m at ranges up to 100km." (This is a quantitative, verifiable software function)

**HLR Derivation Process:**

1. Identify system requirements allocated to software (from `system_requirements` table).
2. Analyze for ambiguities, inconsistencies, and undefined conditions.
3. Decompose each system requirement into one or more **software functions** — the behavioral capabilities the software provides.
4. State each function as a quantitative, verifiable HLR.
5. Identify **Derived HLRs** (§3.5) — software functions needed for implementation that have no parent system requirement.

**HLR Quality Gate (DO-178C §5.1.2 items a–j):**

Every HLR MUST pass ALL of these checks before acceptance:

| #   | Check                                                                    | Example                                                           |
| --- | ------------------------------------------------------------------------ | ----------------------------------------------------------------- |
| a   | System requirement allocated to software has been analyzed for ambiguity | "alert" clarified to "WARNING/CAUTION/ADVISORY"                   |
| b   | Inadequate/incorrect inputs reported back to source                      | Missing tolerance flagged to system team                          |
| c   | Each system requirement is reflected in at least one HLR                 | Traceability verified via `parent_sys`                            |
| d   | Safety-related system requirements produce safety HLRs                   | Proximity alert thresholds explicitly stated                      |
| e   | Conforms to standards; verifiable and consistent                         | Can be tested with specific inputs/outputs                        |
| f   | **Quantitative with tolerances** where applicable                        | "±0.5 knots", "≤30s latency", "≤1m accuracy"                      |
| g   | **No design or verification detail** (unless justified constraint)       | No mention of specific algorithms, data structures, or file names |
| h   | Derived HLRs are identified with rationale                               | `is_derived=1`, `derivation_rationale` populated                  |
| i   | Derived HLRs provided to system safety process                           | Documented in SDD §3                                              |
| j   | Parameter data items described with structure/attributes                 | Config data formats specified                                     |

**Format:** `"The software shall [verb] [what] given [conditions/inputs] to [purpose/outcome] within [tolerance]."`

**Examples:**

> HLR_PROX_001: "The software shall compute proximity alert severity (WARNING, CAUTION, ADVISORY) based on horizontal distance ≤radius_km and vertical separation thresholds (≤500ft, ≤1500ft, >1500ft) relative to a reference altitude."
>
> HLR_INGEST_001: "The software shall ingest aircraft track data via WebSocket (binary Protobuf) and maintain a real-time track cache, pruning entries older than 30 seconds."
>
> HLR_GEO_001: "The software shall render aircraft positions, heading-oriented icons, trail history, and alert-level visual differentiation on a Leaflet map with ≤1s update latency."

**HLR Categories:** Each HLR must be classified as one of:

- `functional` — What the software does (most common)
- `performance` — Timing, throughput, accuracy constraints
- `interface` — External connections (WebSocket, REST API, hardware)
- `safety` — Requirements that prevent system hazards

### 3.2 Software Architecture (Structural Decisions)

Architecture defines the **structure** that organizes software components. It is developed during the Software Design Process and serves as the bridge between HLRs (what) and LLRs (how).

**Architecture Derivation Steps:**

1. **Data Flow:** Define how data moves between components (e.g., WebSocket → Decoder → Cache → Alert Engine → UI).
2. **Control Flow:** Define scheduling, event handling, and processing sequence.
3. **Partitioning:** Define component boundaries and isolation (e.g., audio subsystem vs. map subsystem).
4. **Resource Constraints:** Document memory limits, timing requirements, and concurrency model.
5. **Interfaces:** Define internal interfaces between components AND external interfaces to hardware/systems.
6. **Safety Compatibility:** Verify that the architecture supports all safety-related HLRs (e.g., alert processing path has no single point of failure).

**Rules:**

- Architecture describes **data flow and control flow** between components.
- It defines **partitioning**, scheduling, and resource constraints (memory, timing).
- It defines **interfaces** between components and to external hardware.
- Architecture must be **compatible with HLRs**, especially safety-related functions.
- Architectural decisions are recorded in the `architecture_decisions` table and the SDD (Section 4).
- Architecture gives visibility to **derived requirements** that emerge from structural decisions.

### 3.3 Low-Level Requirements (LLR) — The Logic (Pseudocode)

LLRs are the **Software Design Output**. They must be detailed enough that a developer could write the code **without thinking** or making design decisions.

**CRITICAL RULE: PSEUDOCODE ONLY**

- **FORBIDDEN:** "Calculate distance between user and aircraft." (Too abstract/functional)
- **REQUIRED:** "Iterate through `state.trackCache`. For each track, compute Great Circle distance using the haversine formula between `user.lat`/`user.lon` and `track.lat`/`track.lon`."

**Decomposition Rules:**

1.  **Variable Specificity:** You MUST reference specific variable names, struct fields, and function arguments where known.
2.  **Explicit Logic:** DO NOT summarize logic. Write it out step-by-step.
    - _Bad:_ "Validate input range."
    - _Good:_ "If `input_val` < 0 or `input_val` > 100, return `ERR_OUT_OF_RANGE`."
3.  **One Branch = One LLR:** Every `if`, `else`, `case`, and `catch` block requires its own LLR.
4.  **Math & Algorithms:** Cite the specific formula or algorithm (e.g., "Haversine", "Alpha-Beta filter", "CRC-32").

**Format:**
`"At [Line/Block], [Action/Assignment] using [Variables/Logic]."`

**Example (decomposing HLR_001 "Calculate Airspeed"):**

> LLR_001: "If `raw_pitot` > 150.0 (kPa), set `error_flags` bit `PITOT_RANGE_ERR`."
> LLR_002: "If `raw_static` > 110.0 (kPa), set `error_flags` bit `STATIC_RANGE_ERR`."
> LLR_003: "Compute `q_c` (impact pressure) = `raw_pitot` - `raw_static`."
> LLR_004: "Calculate `CAS` = `sqrt(2 * q_c / CONST_RHO_SL)` where `CONST_RHO_SL` = 1.225."
> LLR_005: "If `CAS` > `V_ne` (Never Exceed Speed), set `warning_status` to `OVERSPEED`."

### 3.4 Derived Requirements

Derived requirements are HLRs or LLRs that arise during the design process but are **not directly traceable** to a system requirement. They exist because the software needs them to function, even though no system-level requirement explicitly asked for them.

**Examples of Derived Requirements:**

- System initialization sequences (no system requirement says "initialize the audio context")
- Internal data caching strategies (the system says "real-time display" but doesn’t specify caching)
- Error handling for internal conditions (e.g., WebSocket reconnection logic)
- Configuration persistence (localStorage management)

**Process:**

1. When deriving requirements (either Mode A or Mode B), identify any HLR/LLR that has no explicit parent system requirement.
2. Set `is_derived = 1` in the database record.
3. Populate `derivation_rationale` explaining WHY this requirement exists.
4. For Derived HLRs: `cluster_hlrs.py` auto-generates a domain-level system requirement (e.g., `SYS_CORE_001`) and sets `parent_sys` to it. **Every HLR MUST have a non-NULL `parent_sys`** — this is enforced by the `v_untraced_hlrs` validation view. Set `source = 'Derived'`.
5. For Derived LLRs: set `source = 'Derived'` (parent_hlr still links to the functional HLR).
6. Document all derived requirements in **SDD §3** (CSCI-Wide Design Decisions) so they are visible to the system safety assessment process.

> **TRACEABILITY INVARIANT:** The complete chain `System Requirement → HLR → LLR → Code` must be unbroken. No HLR may have `parent_sys = NULL`. The validation gate (`init_db.py --validate`) will FAIL if any HLR lacks a parent system requirement.

### 3.5 Single-Level Exception

Per DO-178C §5.2.1: If source code is generated directly from HLRs (e.g., auto-coding tools, very simple systems), the HLRs are also treated as LLRs, and all LLR guidance applies. You must explicitly note this in the traceability database.

---

## 4. Monorepo Context & File Organization

### 4.1 Context Detection

Identify the specific application or module being modified. This directory is the **${APP_ROOT}**.

> [!CAUTION]
> **In a monorepo, `${APP_ROOT}` is the specific app directory (e.g., `revcop/`, `revnav/`), NOT the repository root.** All artifacts (`traceability.db`, `SDD.md`, test scripts) MUST be created under `${APP_ROOT}/docs/artefacts/`. Creating them at the repo root is a CRITICAL ERROR that breaks project isolation. When running pipeline scripts, always pass the app directory as `--app-root`, never the repo root.

In a **monorepo**, the analysis scope includes (but artifacts are stored under `${APP_ROOT}`):

- The app's own source directory (e.g., `revcop/src/`)
- Any shared backend services (e.g., `kccore/go/`, `kccore/services/`)
- The app's main entry point (e.g., `electron-main.js`)
- Configuration files that affect behavior (e.g., `package.json` scripts)

**You MUST analyze ALL of these, not just the app's `src/` folder.**

### 4.2 Directory Structure (Strict)

```text
${APP_ROOT}/
├── README.md
├── CHANGELOG.md
├── src/                          (Source code)
├── tests/                        (Generated test scripts from HLR Test Cases)
│   ├── test_hlr_001.js
│   ├── test_hlr_002.test.js
│   └── ...
└── docs/
    └── artefacts/
        ├── traceability.db       (SQLite database — single source of truth)
        ├── SDD.md                (Software Design Description per DI-IPSC-81435A)
        └── exports/              (Optional CSV exports for review)
            ├── HLR_export.csv
            ├── LLR_export.csv
            ├── HLR_TestCases_export.csv
            └── TraceMatrix_export.csv
```

---

## 5. Traceability Database (SQLite)

**Replace CSV files** with a single SQLite database for robust relational traceability. Initialize using the `init_db.py` script in this skill's `scripts/` directory.

### 5.1 Database Schema

```sql
-- System/User Requirements (top of hierarchy)
CREATE TABLE system_requirements (
    id          TEXT PRIMARY KEY,  -- e.g., 'SYS_001'
    text        TEXT NOT NULL,
    source      TEXT NOT NULL      -- 'User Prompt', 'System Spec', 'Derived'
);

-- High-Level Requirements (1:N from system reqs)
-- HLRs describe SOFTWARE FUNCTIONS, NOT source files.
CREATE TABLE high_level_requirements (
    id          TEXT PRIMARY KEY,  -- e.g., 'HLR_PROX_001'
    text        TEXT NOT NULL,
    source      TEXT NOT NULL,     -- 'SYS_001' or 'Derived'
    parent_sys  TEXT NOT NULL,     -- FK to system_requirements.id (ALWAYS required, even for derived)
    allocated_to TEXT,             -- Software function name (NOT filename)
    is_derived  INTEGER DEFAULT 0, -- 1 if not traceable to system req
    derivation_rationale TEXT,     -- WHY derived HLR exists (required if is_derived=1)
    hlr_category TEXT,             -- 'functional', 'performance', 'interface', 'safety'
    FOREIGN KEY (parent_sys) REFERENCES system_requirements(id)
);

-- Low-Level Requirements (N:1 to HLR)
CREATE TABLE low_level_requirements (
    id           TEXT PRIMARY KEY,  -- e.g., 'LLR_001'
    text         TEXT NOT NULL,
    parent_hlr   TEXT NOT NULL,     -- FK to high_level_requirements.id
    source       TEXT NOT NULL,     -- 'HLR_001' or 'Derived'
    logic_type   TEXT,              -- 'branch', 'loop', 'error_handler', etc.
    trace_to_code TEXT,             -- e.g., 'module.c:45-52'
    FOREIGN KEY (parent_hlr) REFERENCES high_level_requirements(id)
);

-- HLR Test Cases (EVERY HLR MUST have at least one)
CREATE TABLE hlr_test_cases (
    id              TEXT PRIMARY KEY,  -- e.g., 'HTC_001'
    parent_hlr      TEXT NOT NULL,     -- FK to high_level_requirements.id
    test_type       TEXT NOT NULL,     -- 'integration', 'system', 'acceptance', 'regression', 'safety'
    description     TEXT NOT NULL,     -- What this test verifies
    procedure       TEXT NOT NULL,     -- Step-by-step numbered test procedure
    input_data      TEXT NOT NULL,     -- Specific inputs to provide
    expected_output TEXT NOT NULL,     -- Exact expected outcomes
    pass_criteria   TEXT NOT NULL,     -- Quantitative pass/fail criteria
    test_script_ref TEXT,              -- Path to generated test script
    pass_fail       TEXT DEFAULT 'NOT_RUN',
    FOREIGN KEY (parent_hlr) REFERENCES high_level_requirements(id)
);

-- SDD Sections (full-text markdown with dynamic references)
-- The entire SDD document is stored as ordered sections.
-- Use {{TABLE.ID.FIELD}} placeholders for dynamic references.
CREATE TABLE sdd_sections (
    id              TEXT PRIMARY KEY,   -- e.g., 'SDD_1', 'SDD_5_4'
    section_number  TEXT NOT NULL,      -- e.g., '1', '1.1', '5.4'
    title           TEXT NOT NULL,      -- e.g., 'Scope', 'Track Fuser'
    content         TEXT NOT NULL,      -- Full markdown with {{ref}} placeholders
    sort_order      INTEGER NOT NULL    -- Display ordering
);

-- Architectural decisions (linked to HLR)
CREATE TABLE architecture_decisions (
    id          TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    rationale   TEXT,
    parent_hlr  TEXT,
    category    TEXT,
    FOREIGN KEY (parent_hlr) REFERENCES high_level_requirements(id)
);

-- Full trace matrix view
CREATE VIEW trace_matrix AS
SELECT
    sr.id   AS sys_req_id,
    hlr.id  AS hlr_id,
    htc.id  AS hlr_test_id,
    htc.pass_fail AS hlr_test_result,
    llr.id  AS llr_id,
    llr.trace_to_code AS code_ref,
    hlr.allocated_to  AS allocated_file
FROM system_requirements sr
LEFT JOIN high_level_requirements hlr ON hlr.parent_sys = sr.id
LEFT JOIN hlr_test_cases          htc ON htc.parent_hlr = hlr.id
LEFT JOIN low_level_requirements  llr ON llr.parent_hlr = hlr.id;

-- Untraced HLRs (parent_sys is NULL — breaks DO-178C traceability chain)
CREATE VIEW IF NOT EXISTS v_untraced_hlrs AS
SELECT hlr.id, hlr.text, hlr.is_derived
FROM high_level_requirements hlr
WHERE hlr.parent_sys IS NULL;
```

### 5.2 Standard Queries for the Agent

**Check for untested HLRs (EVERY HLR MUST have a test case — FAIL if any missing):**

```sql
SELECT hlr.id, hlr.text
FROM high_level_requirements hlr
LEFT JOIN hlr_test_cases htc ON htc.parent_hlr = hlr.id
WHERE htc.id IS NULL;
```

**Verify 1:N decomposition (every HLR must have ≥2 LLRs):**

```sql
SELECT hlr.id, COUNT(llr.id) AS llr_count
FROM high_level_requirements hlr
LEFT JOIN low_level_requirements llr ON llr.parent_hlr = hlr.id
GROUP BY hlr.id
HAVING llr_count < 2;
```

**Check for untraced HLRs (traceability chain break — FAIL if any):**

```sql
SELECT id, text FROM high_level_requirements WHERE parent_sys IS NULL;
```

**HLR Quality Gates (run by `init_db.py --validate`):**

```sql
-- HLRs referencing file extensions (DO-178C violation)
SELECT id, text FROM high_level_requirements
WHERE text REGEXP '\.(js|go|py|rs|ts|tsx|jsx|css|html|md)';

-- Quantitative term coverage (should be >50%)
SELECT id, text FROM high_level_requirements
WHERE LOWER(text) NOT LIKE '%accuracy%'
  AND LOWER(text) NOT LIKE '%tolerance%'
  AND LOWER(text) NOT LIKE '%latency%'
  AND LOWER(text) NOT LIKE '%within%';
```

**Export full trace matrix:**

```sql
SELECT * FROM trace_matrix ORDER BY sys_req_id, hlr_id, llr_id;
```

### 5.3 HLR Test Case Format (STRICT)

Every HLR test case MUST follow this detailed format:

**`description`**: A one-line summary of what the test verifies, referencing the specific HLR function.

**`procedure`**: Numbered step-by-step instructions that a tester can follow without interpretation:

```text
1. Launch the application with [specific configuration]
2. Call function [FunctionName] with input parameters: [specific values]
3. Observe [specific variable/output/UI element]
4. Verify [specific condition] equals [specific expected value]
5. Repeat with [boundary/error input]
6. Verify [error handling behavior]
```

**`input_data`**: The exact inputs to provide (values, not descriptions).

**`expected_output`**: The exact outcomes to check (values, not descriptions).

**`pass_criteria`**: Quantitative pass/fail threshold. E.g., "Function returns within 100ms," "Distance error < 0.01 NM," "All 5 alerts generated."

**Example HLR Test Case:**

> **HTC_FUSE_001** (parent: HLR_FUSE_001, type: integration)
> **Description:** Verify Track Fusion applies Alpha-Beta filter to smooth position updates.
> **Procedure:**
>
> 1. Initialize FilterState with RefLat=-27.5, RefLon=153.0
> 2. Send 3 sequential track updates at 1-second intervals: (lat=-27.501, lon=153.001), (lat=-27.502, lon=153.002), (lat=-27.503, lon=153.003)
> 3. After each update, read state.X, state.Y, state.Vx, state.Vy
> 4. Verify position converges toward measurement (residual decreases each step)
> 5. Verify velocity estimates are non-zero after 2nd update
> 6. Send an invalid track (lat=0, lon=0). Verify cleanser rejects it and state is unchanged.
>    **Input Data:** 3 valid track positions + 1 invalid track
>    **Expected Output:** Smoothed positions converging, velocity estimates increasing, invalid track filtered
>    **Pass Criteria:** Position residual after 3rd update < 50m; velocity estimate after 2nd update > 0.1 m/s; invalid track produces no state change

---

## 6. Coding Standards (DO-178C §11.8)

### 6.1 Constraints

- **Nesting Depth:** Maximum 4 levels of control structure nesting.
- **Recursion:** **STRICTLY FORBIDDEN** (bounded execution requirement).
- **Coupling:** Minimize global variables. All interfaces must be explicitly defined.
- **Function Length:** Maximum 50 lines of logic per function (excluding comments).

### 6.2 Comment Standards (Strict Enforcement)

**Function/Method Header:**

```c
/*
 * [Function Name]
 * Functionality: [Define the functionality]
 * Inputs: [Identify all inputs with types]
 * Outputs: [Identify all outputs with types]
 * Data/Control Flow: [Describe data sources and control passing]
 * LLR Trace: [List LLR IDs implemented by this function]
 * Timestamp: [YYYY-MM-DD HH:MM UTC]
 */
```

**Decision Point (if/switch/loop):**

```c
/*
 * Decision Logic: [Explain the logic flow]
 * Conditions: [Describe all conditions being evaluated]
 * LLR Trace: [LLR ID for this specific branch]
 * Timestamp: [YYYY-MM-DD HH:MM UTC]
 */
if (condition) { ... }
```

---

## 7. SDD Storage & Dynamic References

The SDD is stored **entirely in the database** as ordered markdown sections. Each section's `content` field contains full prose with dynamic reference placeholders that are resolved at render time.

### 7.1 Storage Model

Each SDD section (Scope, Architecture, Unit 5.x, etc.) is one row in `sdd_sections`:

- `section_number` — e.g., "1", "1.1", "5.4"
- `title` — e.g., "Scope", "Track Fuser"
- `content` — Full markdown prose, including headings, code blocks, and `{{ref}}` placeholders
- `sort_order` — Integer for display ordering

### 7.2 Dynamic Reference Syntax

Within `content`, use these placeholders. They resolve to current DB values at render time:

| Placeholder                     | Resolves To                                                |
| ------------------------------- | ---------------------------------------------------------- |
| `{{HLR.HLR_001.text}}`          | Current HLR requirement text                               |
| `{{LLR.LLR_001.text}}`          | Current LLR text                                           |
| `{{LLR.LLR_001.trace_to_code}}` | Code file reference for LLR                                |
| `{{HTC.HTC_001.description}}`   | Test case description                                      |
| `{{HTC.HTC_001.pass_criteria}}` | Test case pass criteria                                    |
| `{{ARCH.ARCH_001.description}}` | Architecture decision text                                 |
| `{{LIST_LLRS:HLR_001}}`         | Auto-generated bullet list of all LLRs under HLR_001       |
| `{{LIST_HTCS:HLR_001}}`         | Auto-generated bullet list of all test cases under HLR_001 |
| `{{TRACE_MATRIX}}`              | Full rendered trace matrix as a markdown table             |

### 7.3 Rendering

Run `render_sdd.py` from the skill's `scripts/` directory to generate the final `SDD.md`:

```bash
python render_sdd.py --db-path docs/artefacts/traceability.db --output docs/artefacts/SDD.md
```

This resolves all `{{ref}}` placeholders to current database values and writes the output.

**Rule:** After any change to HLRs, LLRs, test cases, or architecture decisions, re-run `render_sdd.py` to keep `SDD.md` synchronized.

### 7.4 Section Content Guidelines (DI-IPSC-81435A)

Each section must still follow DI-IPSC-81435A structure:

- **Section 1:** Scope (identification, system overview, document overview)
- **Section 2:** Referenced Documents
- **Section 3:** CSCI-Wide Design Decisions
- **Section 4:** CSCI Architectural Design (components, execution, interfaces)
- **Section 5.x:** Per-unit detailed design (use `{{LIST_LLRS:HLR_xxx}}` for traceability)
- **Section 6:** Requirements Traceability (use `{{TRACE_MATRIX}}`)
- **Section 7:** Notes, acronyms, glossary

### 7.5 Example: Storing Section 5.4 with Dynamic References

```markdown
### 5.4 Track Fuser (kccore/track-fuser)

**Traceability:**
{{LIST_LLRS:HLR_FUSE_001}}

**Detailed Design (Alpha-Beta Filter):**
The unit implements the following algorithm for each track:

1. **Initialize:** If `!IsInitialized`, set `RefLat/Lon` = `track.Lat/Lon`.
2. **Measure:** Convert `track.Lat/Lon` to ENU meters.
3. **Predict:** `predX` = `state.X` + `state.Vx` \* dt
4. **Update:** `state.X` = `predX` + alpha \* residual

**Test Coverage:**
{{LIST_HTCS:HLR_FUSE_001}}
```

When rendered, the `{{LIST_LLRS:...}}` and `{{LIST_HTCS:...}}` placeholders expand into bullet lists of current LLR and test case content from the database.

---

## 8. Documentation Updates (Phase C)

After every code change:

1.  **`${APP_ROOT}/CHANGELOG.md`** — Structured per commit:

    ```markdown
    ## [Commit Hash/ID] - [Date]

    ### Added

    - [New features / requirements]

    ### Changed

    - [Modified logic / refactored code]

    ### Verified

    - [Test Case IDs verified]
    ```

2.  **`${APP_ROOT}/README.md`** — Update feature lists, artefact listings, file structure.

3.  **`${APP_ROOT}/docs/artefacts/SDD.md`** — Update affected unit sections (5.x).

4.  **`${APP_ROOT}/docs/artefacts/traceability.db`** — Update all affected rows and verify integrity using the validation queries in §5.2.

---

## 9. Test Script Generation (MANDATORY)

After populating HLR Test Cases in the database, you **MUST** generate a runnable test script for each HLR test case.

### 9.1 Rules

1.  **One test file per HLR** in `${APP_ROOT}/tests/`. Name: `test_hlr_<id>.{ext}`
2.  **Framework selection:** Use the project's existing test framework. Defaults:
    - JavaScript/Node.js → Jest
    - Go → `testing` package
    - Python → pytest
3.  **Test body** must implement the exact `procedure` from the HLR Test Case record.
4.  **Assertions** must verify the exact `expected_output` and `pass_criteria`.
5.  **Update the database:** Set `hlr_test_cases.test_script_ref` to the script path.

### 9.2 Example (Jest)

```javascript
/**
 * Test Script for HTC_FUSE_001
 * HLR: HLR_FUSE_001 — Track Fusion Alpha-Beta Filter
 * Generated from DO-178C traceability database
 */
const { applyFilter } = require("../src/track-fuser");

describe("HLR_FUSE_001: Track Fusion Smoothing", () => {
  test("HTC_FUSE_001: Alpha-Beta filter converges on valid input", () => {
    const state = initFilterState(-27.5, 153.0);
    const tracks = [
      { lat: -27.501, lon: 153.001, time: 1.0 },
      { lat: -27.502, lon: 153.002, time: 2.0 },
      { lat: -27.503, lon: 153.003, time: 3.0 },
    ];
    let prevResidual = Infinity;
    for (const track of tracks) {
      applyFilter(state, track);
      const residual = Math.sqrt(state.residualX ** 2 + state.residualY ** 2);
      expect(residual).toBeLessThan(prevResidual);
      prevResidual = residual;
    }
    // Pass criteria: residual < 50m after 3rd update
    expect(prevResidual).toBeLessThan(50);
    // Velocity > 0.1 m/s after 2nd update
    expect(Math.abs(state.Vx) + Math.abs(state.Vy)).toBeGreaterThan(0.1);
  });

  test("HTC_FUSE_001: Invalid track is rejected", () => {
    const state = initFilterState(-27.5, 153.0);
    const stateBefore = { ...state };
    applyFilter(state, { lat: 0, lon: 0, time: 4.0 });
    expect(state.X).toBe(stateBefore.X);
  });
});
```

### 9.3 Coverage Audit

After script generation, run `audit_coverage.py` (see `scripts/`) to verify every source file has LLR coverage and every HLR has a test script.
