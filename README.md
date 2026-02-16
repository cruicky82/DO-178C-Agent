# DO-178C Agent

A deterministic, code-driven pipeline for **DO-178C software compliance** — automating the derivation of requirements, traceability, test cases, and design documentation for safety-critical systems.

> **Design Principle:** _"The script does the MECHANICAL work (enumeration, extraction, classification). The agent does the JUDGMENT work (HLR naming, architecture rationale, review). The DB enforces COMPLETENESS (every function must have an LLR)."_

---

## Overview

Traditional DO-178C compliance relies heavily on manual effort or AI agents operating with unconstrained context. This toolkit inverts that model by providing a **9-phase deterministic pipeline** that:

- **Auto-generates ~80%** of compliance artifacts from static analysis (AST/regex)
- **Persists progress** in a SQLite traceability database — enabling multi-session execution
- **Enforces completeness** — scripts won't finish until every function has coverage
- **Reduces the agent's role** to genuine judgment: requirement naming, architecture rationale, and quality review

The pipeline implements the full DO-178C V-Model hierarchy:

```
System Requirements
  └── High-Level Requirements (HLR) — WHAT the software does
        └── Software Architecture — HOW the structure is organized
              └── Low-Level Requirements (LLR) — HOW each piece works
                    └── Source Code — The implementation
```

---

## Pipeline Phases

| Phase                 | Script                                        | Description                                                                           |
| --------------------- | --------------------------------------------- | ------------------------------------------------------------------------------------- |
| **1 — Scan**          | `scan_codebase.py`                            | Catalog all source files and functions into `source_inventory`                        |
| **2A — LLR Derive**   | `derive_llrs.py`                              | Auto-generate draft LLRs from code structure (AST/regex)                              |
| **2B — HLR Cluster**  | `cluster_hlrs.py`                             | Cluster functions into behavioral HLR candidates using domain-specific templates      |
| **2C — Refine**       | `refine_requirements.py`                      | Enforce standard phrasing, inject quantitative terms from LLR boundary analysis       |
| **2D — Arch Extract** | `extract_architecture.py`                     | Infer architecture decisions from import graphs and component boundaries              |
| **3 — Review**        | _Agent_                                       | Review and refine auto-generated HLRs/LLRs; add tolerances and architecture decisions |
| **4 — Test Gen**      | `gen_test_cases.py`                           | Generate Normal Range + Robustness test case skeletons with boundary analysis         |
| **5 — SDD Gen**       | `populate_sdd.py` + `render_sdd.py`           | Generate Software Design Description per DI-IPSC-81435A                               |
| **6 — Validate**      | `init_db.py --validate` + `check_progress.py` | Verify completeness, traceability chain, and quality gates                            |

---

## Language Support

The pipeline supports multi-language codebases:

| Language   | Extensions    | Scanner                                         |
| ---------- | ------------- | ----------------------------------------------- |
| JavaScript | `.js`, `.jsx` | Regex-based function detection                  |
| TypeScript | `.ts`, `.tsx` | Regex-based function detection                  |
| Go         | `.go`         | Regex-based function detection                  |
| Python     | `.py`         | AST + regex analysis                            |
| Rust       | `.rs`         | Regex-based (`fn`, `impl`, `struct/enum/trait`) |

---

## Quick Start

### Prerequisites

- **Python 3.10+**
- No external dependencies — the pipeline uses only the Python standard library

### Usage

```bash
# 1. Initialize the traceability database
python scripts/init_db.py --db docs/artefacts/traceability.db

# 2. Scan the codebase
python scripts/scan_codebase.py --root <APP_ROOT> --db docs/artefacts/traceability.db

# 3. Derive Low-Level Requirements
python scripts/derive_llrs.py --db docs/artefacts/traceability.db --app-root <APP_ROOT>

# 4. Cluster into High-Level Requirements
python scripts/cluster_hlrs.py --db docs/artefacts/traceability.db --app-root <APP_ROOT>

# 5. Refine requirement text
python scripts/refine_requirements.py --db docs/artefacts/traceability.db --apply

# 6. Extract architecture decisions
python scripts/extract_architecture.py --db docs/artefacts/traceability.db --app-root <APP_ROOT>

# 7. Generate test cases and scripts
python scripts/gen_test_cases.py --db docs/artefacts/traceability.db --gen-scripts <APP_ROOT>/tests

# 8. Generate SDD document
python scripts/render_sdd.py --db-path docs/artefacts/traceability.db --output docs/artefacts/SDD.md

# Check progress at any time
python scripts/check_progress.py --db docs/artefacts/traceability.db
```

---

## Repository Structure

```
DO-178C-Agent/
├── SKILL.md                        # AI agent orchestration guide (DO-178C skill definition)
├── README.md
├── scripts/
│   ├── init_db.py                  # Database schema initialization & validation
│   ├── scan_codebase.py            # Phase 1: Source file & function scanner
│   ├── derive_llrs.py              # Phase 2A: Deterministic LLR generation
│   ├── cluster_hlrs.py             # Phase 2B: Behavioral HLR clustering
│   ├── refine_requirements.py      # Phase 2C: Requirement text refinement
│   ├── extract_architecture.py     # Phase 2D: Architecture decision extraction
│   ├── gen_test_cases.py           # Phase 4: Test case & script generation
│   ├── render_sdd.py               # Phase 5: SDD markdown renderer
│   ├── check_progress.py           # Phase 6: Progress dashboard
│   ├── audit_coverage.py           # Coverage audit (LLR + test script completeness)
│   ├── manage_reqs.py              # Manual requirement management utilities
│   └── repair_traceability.py      # Database repair & consistency tools
└── tests/
    └── fixture/                    # Multi-language test fixtures
        ├── traceability.db         # Sample populated database
        └── src/
            ├── sample_module.py    # Python fixture
            ├── sensor.rs           # Rust fixture
            ├── tracker.go          # Go fixture
            └── utils.js            # JavaScript fixture
```

---

## Traceability Database

All compliance artifacts are stored in a single **SQLite database** (`traceability.db`), providing relational traceability across the full V-Model:

| Table                     | Purpose                                                   |
| ------------------------- | --------------------------------------------------------- |
| `system_requirements`     | Top-level system/user requirements                        |
| `high_level_requirements` | Behavioral software functions (HLRs)                      |
| `low_level_requirements`  | Implementation-level pseudocode (LLRs)                    |
| `hlr_test_cases`          | Test cases with procedures, inputs, and pass criteria     |
| `source_inventory`        | Catalog of all scanned source files and functions         |
| `architecture_decisions`  | Structural design decisions with rationale                |
| `sdd_sections`            | SDD document sections with dynamic `{{ref}}` placeholders |
| `trace_matrix` (view)     | Full traceability: System Req → HLR → LLR → Code          |

---

## AI Agent Integration

This repository is designed as a **skill** for AI coding agents. The `SKILL.md` file provides:

- **Activation rules** — when to apply DO-178C protocols
- **Mode selection** — Forward Engineering (requirements → code) or Reverse Engineering (code → requirements)
- **Pipeline orchestration** — step-by-step execution guide with validation gates
- **Quality gates** — DO-178C §5.1.2 compliance checks for every HLR
- **Coding standards** — DO-178C §11.8 constraints (nesting depth, no recursion, comment headers)

To use as an agent skill, copy the `SKILL.md` and `scripts/` directory into your agent's skill path.

---

## Key Concepts

### HLR Quality Gate (DO-178C §5.1.2)

Every High-Level Requirement must pass these checks:

- ✅ Traceable to a parent system requirement (`parent_sys` is non-NULL)
- ✅ **Implementation-agnostic** — no function names, file names, or directory paths
- ✅ **Quantitative with tolerances** — accuracy, latency, thresholds specified
- ✅ Verifiable with specific inputs and expected outputs
- ✅ Derived requirements identified with rationale

### Behavioral Domains

HLRs are clustered into domain-specific groups:

`INGEST` · `FUSION` · `UI` · `SITL` · `SORA` · `TERRAIN` · `SAFETY` · `CORE` · `OTHER`

---

## License

This project is proprietary. All rights reserved.
