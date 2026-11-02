"""Converts DBML into tbls JSON for `liam erd build --format tbls`, preserving custom data types
(VARIANT, NUMBER(38,0), TIMESTAMP_NTZ, decimal(38,2), etc.).

Usage: python dbml_to_tbls.py <input.dbml> <output.tbls.json>
"""

import json
import sys
from pathlib import Path

from pydbml import PyDBML
from pydbml.classes import Column, Enum


class DbmlSyntaxError(ValueError):
    pass


def _note_text(obj) -> str:
    note = getattr(obj, "note", None)
    return (note.text if note else "") or ""


def _default_text(value) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "text", value))


def dbml_to_tbls(dbml_content: str, schema_name: str) -> dict:
    try:
        database = PyDBML(dbml_content)
    except Exception as exc:
        raise DbmlSyntaxError(str(exc)) from exc

    tables: dict[str, dict] = {}
    relations = []

    for table in database.tables:
        columns, constraints, indexes, pk_columns = [], [], [], []

        for field in table.columns:
            is_enum = isinstance(field.type, Enum)
            raw_type = field.type.name if is_enum else str(field.type or "varchar")
            if field.pk:
                pk_columns.append(field.name)

            comment = _note_text(field)
            if is_enum:
                enum_values = f"Enum values: {', '.join(item.name for item in field.type.items)}"
                comment = f"{comment} ({enum_values})" if comment else enum_values

            columns.append({
                "name": field.name,
                "type": raw_type,
                "nullable": not (field.not_null or field.pk),
                "default": _default_text(field.default),
                "comment": comment,
            })

            if field.unique and not field.pk:
                constraints.append({
                    "name": f"{table.name}_{field.name}_key",
                    "type": "UNIQUE",
                    "def": f"UNIQUE ({field.name})",
                    "table": table.name,
                    "columns": [field.name],
                })

        for idx in table.indexes:
            idx_cols = [s.name for s in idx.subjects if isinstance(s, Column)]
            if not idx_cols:
                continue
            if idx.pk:
                pk_columns.extend(c for c in idx_cols if c not in pk_columns)
                continue

            idx_name = idx.name or f"{table.name}_{'_'.join(idx_cols)}_idx"
            cols_sql = ", ".join(idx_cols)
            if idx.unique:
                constraints.append({
                    "name": idx_name,
                    "type": "UNIQUE",
                    "def": f"UNIQUE ({cols_sql})",
                    "table": table.name,
                    "columns": idx_cols,
                })
            unique_sql = "UNIQUE " if idx.unique else ""
            indexes.append({
                "name": idx_name,
                "def": f"CREATE {unique_sql}INDEX {idx_name} ON {table.name} ({cols_sql})",
                "table": table.name,
                "columns": idx_cols,
            })

        if pk_columns:
            constraints.insert(0, {
                "name": f"{table.name}_pkey",
                "type": "PRIMARY KEY",
                "def": f"PRIMARY KEY ({', '.join(pk_columns)})",
                "table": table.name,
                "columns": pk_columns,
            })

        tables[table.name] = {
            "name": table.name,
            "type": "TABLE",
            "comment": _note_text(table),
            "columns": columns,
            "indexes": indexes,
            "constraints": constraints,
        }

    for ref in database.refs:
        # "<" points from the parent (one) side to the child (many) side; ">", "-" and "<>" list the child first
        child_cols, parent_cols = (ref.col2, ref.col1) if ref.type == "<" else (ref.col1, ref.col2)
        if not child_cols or not parent_cols:
            continue
        child, parent = child_cols[0].table.name, parent_cols[0].table.name
        child_names = [c.name for c in child_cols]
        parent_names = [c.name for c in parent_cols]
        is_one_to_one = ref.type == "-"

        fk_name = ref.name or f"{parent}_{'_'.join(parent_names)}_to_{child}_{'_'.join(child_names)}"
        fk_def = f"FOREIGN KEY ({', '.join(child_names)}) REFERENCES {parent}({', '.join(parent_names)})"

        child_table = tables.get(child)
        if child_table:
            # Liam ERD only draws a FK as one-to-one when a UNIQUE constraint covers it (PRIMARY KEY is not enough)
            has_unique = any(
                c["type"] == "UNIQUE" and c["columns"] == child_names for c in child_table["constraints"]
            )
            if is_one_to_one and not has_unique:
                child_table["constraints"].append({
                    "name": f"{child}_{'_'.join(child_names)}_key",
                    "type": "UNIQUE",
                    "def": f"UNIQUE ({', '.join(child_names)})",
                    "table": child,
                    "columns": child_names,
                })
            child_table["constraints"].append({
                "name": fk_name,
                "type": "FOREIGN KEY",
                "def": fk_def,
                "table": child,
                "referenced_table": parent,
                "columns": child_names,
                "referenced_columns": parent_names,
            })

        relations.append({
            "table": child,
            "columns": child_names,
            "cardinality": "zero_or_one" if is_one_to_one else "zero_or_more",
            "parent_table": parent,
            "parent_columns": parent_names,
            "parent_cardinality": "exactly_one",
            "def": fk_def,
        })

    return {"name": schema_name, "tables": list(tables.values()), "relations": relations}


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("Usage: python dbml_to_tbls.py <input.dbml> <output.tbls.json>")
    input_path, output_path = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        tbls = dbml_to_tbls(input_path.read_text(encoding="utf-8"), input_path.stem)
    except DbmlSyntaxError as exc:
        sys.exit(f"DBML syntax error in {input_path}: {exc}")
    output_path.write_text(json.dumps(tbls, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
