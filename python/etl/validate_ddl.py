#!/usr/bin/env python3
"""
Structural validator for the PARK It Up DDL.

WHY THIS EXISTS
    The development sandbox has no PostgreSQL server and no network access, so
    the DDL cannot be executed here. Rather than assume the schema is correct,
    this script parses it and checks the structural invariants that account for
    most real schema defects:

        1. Every table declares a PRIMARY KEY.
        2. Every FOREIGN KEY points at a table that exists.
        3. Every FOREIGN KEY points at a column that exists and is the target
           table's primary key or is UNIQUE.
        4. A referenced table is created before the table referencing it, so
           the files can be applied in filename order.
        5. No duplicate table definitions, no duplicate columns within a table.
        6. The teardown script drops every table that the schema creates.
        7. Composite-key FK arity matches.

    It does NOT validate SQL syntax, expression semantics, or type
    compatibility. Those require a real server: scripts/validate_schema.sh
    covers them. Passing this script means the schema is structurally coherent,
    not that PostgreSQL will accept it.

USAGE
    python3 python/etl/validate_ddl.py [--schema-dir database/schema]

EXIT CODES
    0 = all structural checks passed
    1 = at least one failure
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------

TABLE_LEVEL_KEYWORDS = (
    "CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "EXCLUDE", "LIKE",
)


def strip_sql_comments(sql: str) -> str:
    """Remove -- line comments and /* */ block comments, preserving string literals."""
    out, i, n = [], 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":                                  # single-quoted literal
            out.append(ch)
            i += 1
            while i < n:
                out.append(sql[i])
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":  # escaped ''
                        out.append(sql[i + 1])
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            while i < n and sql[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            i += 2
            while i + 1 < n and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def match_paren_block(sql: str, open_idx: int) -> int:
    """Given the index of '(', return the index of its matching ')'."""
    depth, i, n = 0, open_idx, len(sql)
    while i < n:
        c = sql[i]
        if c == "'":
            i += 1
            while i < n:
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        i += 2
                        continue
                    break
                i += 1
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced parentheses in DDL")


def split_top_level(body: str) -> list[str]:
    """Split a CREATE TABLE body on commas that sit at paren depth zero."""
    parts, depth, cur, i, n = [], 0, [], 0, len(body)
    while i < n:
        c = body[i]
        if c == "'":
            cur.append(c)
            i += 1
            while i < n:
                cur.append(body[i])
                if body[i] == "'":
                    if i + 1 < n and body[i + 1] == "'":
                        cur.append(body[i + 1])
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    if "".join(cur).strip():
        parts.append("".join(cur).strip())
    return [p for p in parts if p]


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------

@dataclass
class ForeignKey:
    columns: list[str]
    ref_table: str
    ref_columns: list[str]
    source_file: str


@dataclass
class Table:
    name: str
    source_file: str
    order_index: int
    columns: list[str] = field(default_factory=list)
    pk_columns: list[str] = field(default_factory=list)
    unique_sets: list[list[str]] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    check_count: int = 0


def parse_columns_list(raw: str) -> list[str]:
    return [c.strip().strip('"') for c in raw.split(",") if c.strip()]


def parse_schema(files: list[Path]) -> tuple[dict[str, Table], list[str]]:
    tables: dict[str, Table] = {}
    errors: list[str] = []
    order = 0

    create_re = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][\w.]*)\s*\(",
        re.IGNORECASE,
    )
    ref_re = re.compile(
        r"REFERENCES\s+([A-Za-z_][\w.]*)\s*(?:\(\s*([^)]*?)\s*\))?",
        re.IGNORECASE,
    )
    fk_re = re.compile(
        r"FOREIGN\s+KEY\s*\(([^)]*)\)\s*REFERENCES\s+([A-Za-z_][\w.]*)\s*\(([^)]*)\)",
        re.IGNORECASE,
    )
    pk_tbl_re = re.compile(r"PRIMARY\s+KEY\s*\(([^)]*)\)", re.IGNORECASE)
    uq_tbl_re = re.compile(r"UNIQUE\s*\(([^)]*)\)", re.IGNORECASE)

    for path in files:
        sql = strip_sql_comments(path.read_text(encoding="utf-8"))
        for m in create_re.finditer(sql):
            raw_name = m.group(1)
            name = raw_name.split(".")[-1].lower()
            open_idx = sql.index("(", m.end() - 1)
            close_idx = match_paren_block(sql, open_idx)
            body = sql[open_idx + 1: close_idx]

            if name in tables:
                errors.append(
                    f"duplicate table definition '{name}' in {path.name} "
                    f"(already defined in {tables[name].source_file})"
                )
                continue

            order += 1
            tbl = Table(name=name, source_file=path.name, order_index=order)

            for item in split_top_level(body):
                head = item.split(None, 1)[0].upper().rstrip("(")
                is_table_level = head in TABLE_LEVEL_KEYWORDS

                if "CHECK" in item.upper():
                    tbl.check_count += item.upper().count("CHECK")

                if is_table_level:
                    fkm = fk_re.search(item)
                    if fkm:
                        tbl.foreign_keys.append(ForeignKey(
                            columns=parse_columns_list(fkm.group(1)),
                            ref_table=fkm.group(2).split(".")[-1].lower(),
                            ref_columns=parse_columns_list(fkm.group(3)),
                            source_file=path.name,
                        ))
                    # PRIMARY KEY (...) but not inside a CHECK expression
                    if re.match(r"(CONSTRAINT\s+\w+\s+)?PRIMARY\s+KEY", item, re.IGNORECASE):
                        pkm = pk_tbl_re.search(item)
                        if pkm:
                            tbl.pk_columns = parse_columns_list(pkm.group(1))
                    if re.match(r"(CONSTRAINT\s+\w+\s+)?UNIQUE", item, re.IGNORECASE):
                        uqm = uq_tbl_re.search(item)
                        if uqm:
                            tbl.unique_sets.append(parse_columns_list(uqm.group(1)))
                    continue

                # --- column definition ---
                col = item.split(None, 1)[0].strip('"').lower()
                tbl.columns.append(col)
                upper = item.upper()
                if re.search(r"\bPRIMARY\s+KEY\b", upper):
                    tbl.pk_columns = [col]
                if re.search(r"\bUNIQUE\b", upper):
                    tbl.unique_sets.append([col])
                rm = ref_re.search(item)
                if rm:
                    ref_cols = parse_columns_list(rm.group(2)) if rm.group(2) else []
                    tbl.foreign_keys.append(ForeignKey(
                        columns=[col],
                        ref_table=rm.group(1).split(".")[-1].lower(),
                        ref_columns=ref_cols,
                        source_file=path.name,
                    ))

            tables[name] = tbl

    return tables, errors


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def run_checks(tables: dict[str, Table], drop_sql: str | None) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []

    for name, t in tables.items():
        # 1. primary key present
        if not t.pk_columns:
            failures.append(f"[PK] table '{name}' ({t.source_file}) declares no PRIMARY KEY")

        # 5. duplicate columns
        dupes = {c for c in t.columns if t.columns.count(c) > 1}
        if dupes:
            failures.append(f"[COL] table '{name}' has duplicate columns: {sorted(dupes)}")

        # primary key columns must exist. Generated identity columns are in
        # t.columns, so a missing name here is a genuine typo.
        for c in t.pk_columns:
            if c not in t.columns:
                failures.append(
                    f"[PK] table '{name}' primary key references unknown column '{c}'"
                )

        for fk in t.foreign_keys:
            # 2. target table exists
            if fk.ref_table not in tables:
                failures.append(
                    f"[FK] {name}.{','.join(fk.columns)} references unknown table "
                    f"'{fk.ref_table}' ({fk.source_file})"
                )
                continue
            target = tables[fk.ref_table]

            # implicit target = target's primary key
            ref_cols = fk.ref_columns or target.pk_columns
            if not ref_cols:
                failures.append(
                    f"[FK] {name}.{','.join(fk.columns)} -> {fk.ref_table} has no "
                    f"resolvable target column"
                )
                continue

            # 3a. target columns exist
            for rc in ref_cols:
                if rc not in target.columns:
                    failures.append(
                        f"[FK] {name}.{','.join(fk.columns)} references "
                        f"'{fk.ref_table}.{rc}', which does not exist"
                    )

            # 3b. target is PK or UNIQUE
            is_pk = sorted(ref_cols) == sorted(target.pk_columns)
            is_uq = any(sorted(ref_cols) == sorted(u) for u in target.unique_sets)
            if not (is_pk or is_uq):
                failures.append(
                    f"[FK] {name}.{','.join(fk.columns)} -> {fk.ref_table}"
                    f"({','.join(ref_cols)}) targets neither the primary key nor a "
                    f"UNIQUE constraint; PostgreSQL will reject this"
                )

            # 7. arity match
            if fk.ref_columns and len(fk.columns) != len(fk.ref_columns):
                failures.append(
                    f"[FK] {name} arity mismatch: {len(fk.columns)} local column(s) "
                    f"vs {len(fk.ref_columns)} referenced"
                )

            # 4. creation order (self-references are fine)
            if target.order_index > t.order_index and fk.ref_table != name:
                failures.append(
                    f"[ORDER] '{name}' ({t.source_file}) references '{fk.ref_table}' "
                    f"({target.source_file}), which is created later; applying files "
                    f"in filename order will fail"
                )

    # 6. teardown completeness
    if drop_sql is not None:
        dropped = {
            m.group(1).split(".")[-1].lower()
            for m in re.finditer(
                r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([A-Za-z_][\w.]*)",
                drop_sql, re.IGNORECASE)
        }
        missing = sorted(set(tables) - dropped)
        if missing:
            failures.append(
                f"[TEARDOWN] 99_drop_all.sql does not drop: {missing}"
            )
        orphan = sorted(dropped - set(tables))
        if orphan:
            warnings.append(
                f"[TEARDOWN] drops tables that are never created: {orphan}"
            )

    for name, t in tables.items():
        if not t.foreign_keys and name not in {
            "dim_city", "dim_date", "dim_funnel_stage",
            "dim_score_dimension", "owners", "segment_rule", "scoring_weight_set",
        }:
            warnings.append(f"[FK] '{name}' has no foreign keys - intended?")

    return failures, warnings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema-dir", default="database/schema")
    args = ap.parse_args()

    schema_dir = Path(args.schema_dir)
    if not schema_dir.is_dir():
        print(f"ERROR: schema directory not found: {schema_dir}", file=sys.stderr)
        return 1

    all_sql = sorted(schema_dir.glob("*.sql"))
    build_files = [p for p in all_sql if not p.name.startswith("99_")]
    drop_file = schema_dir / "99_drop_all.sql"
    drop_sql = drop_file.read_text(encoding="utf-8") if drop_file.exists() else None

    print("=" * 72)
    print("PARK It Up - DDL structural validation")
    print("=" * 72)
    print(f"schema directory : {schema_dir}")
    print(f"files parsed     : {', '.join(p.name for p in build_files)}")

    tables, parse_errors = parse_schema(build_files)
    failures, warnings = run_checks(tables, drop_sql)
    failures = parse_errors + failures

    total_cols = sum(len(t.columns) for t in tables.values())
    total_fks = sum(len(t.foreign_keys) for t in tables.values())
    total_checks = sum(t.check_count for t in tables.values())

    print(f"\ntables           : {len(tables)}")
    print(f"columns          : {total_cols}")
    print(f"foreign keys     : {total_fks}")
    print(f"CHECK expressions: {total_checks}")

    print("\n--- inventory " + "-" * 58)
    for t in sorted(tables.values(), key=lambda x: x.order_index):
        pk = ",".join(t.pk_columns) or "** NONE **"
        print(f"  {t.name:<26} cols={len(t.columns):<3} pk=({pk})  fks={len(t.foreign_keys)}")

    if warnings:
        print("\n--- warnings " + "-" * 59)
        for w in warnings:
            print(f"  WARN  {w}")

    print("\n--- result " + "-" * 61)
    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        print(f"\n{len(failures)} structural failure(s).")
        return 1

    print("  All structural checks PASSED.")
    print("  Note: syntax and expression semantics are NOT verified here.")
    print("  Run scripts/validate_schema.sh against a real PostgreSQL server.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
