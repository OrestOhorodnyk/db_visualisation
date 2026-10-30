"""Export dbt models as tbls JSON schemas for the Liam ERD server (`liam erd build --format tbls`).

Reads target/manifest.json and target/catalog.json (run `dbt docs generate` first) and writes one
schemas/<name>.tbls.json per export:
  - one table per selected model, with column types from the catalog and descriptions from the YAML docs
  - PRIMARY KEY from the first column that has both `unique` and `not_null` tests
  - UNIQUE constraints and nullability from `unique` / `not_null` tests
  - FOREIGN KEY constraints and relations from `relationships` tests between the selected models.
    Cardinality: a FK column that is also unique (or the PK) is one-to-one, otherwise one-to-many;
    a `not_null` FK means every child row has exactly one parent, a nullable FK means zero or one.

Usage:
  uv run python scripts/export_tbls.py                                   # all DEFAULT_EXPORTS
  uv run python scripts/export_tbls.py --layer silver --folder eshop --name silver_eshop
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = PROJECT_DIR.parent / "schemas"
# (layer, sub-folder or None for the whole layer, output schema name)
DEFAULT_EXPORTS = [
    ("gold", None, "gold_marts"),
    ("silver", "eshop", "silver_eshop"),
    ("silver", "warehouse", "silver_warehouse"),
]
REF_RE = re.compile(r"ref\(\s*['\"]([^'\"]+)['\"]\s*\)")
TABLE_TYPES = {"view": "VIEW", "materialized_view": "MATERIALIZED VIEW"}


def clean_text(text: str) -> str:
    return " ".join((text or "").split())


def load_artifacts(target_dir: Path) -> tuple[dict, dict]:
    manifest_path, catalog_path = target_dir / "manifest.json", target_dir / "catalog.json"
    for path in (manifest_path, catalog_path):
        if not path.exists():
            raise SystemExit(f"{path} not found. Run `uv run dbt docs generate --profiles-dir .` first.")
    return json.loads(manifest_path.read_text()), json.loads(catalog_path.read_text())


def collect_tests(manifest: dict, model_ids: set[str]) -> tuple[dict, list]:
    """Returns ({model_id: {column: {test names}}}, [(child_id, child_col, parent_name, parent_col)])."""
    column_tests: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    relationships = []
    for node in manifest["nodes"].values():
        if node["resource_type"] != "test" or not node.get("test_metadata"):
            continue
        model_id, column = node.get("attached_node"), node.get("column_name")
        if model_id not in model_ids or not column:
            continue
        test_name = node["test_metadata"]["name"]
        column_tests[model_id][column].add(test_name)
        if test_name == "relationships":
            kwargs = node["test_metadata"].get("kwargs", {})
            match = REF_RE.search(str(kwargs.get("to", "")))
            if match and kwargs.get("field"):
                relationships.append((model_id, column, match.group(1), kwargs["field"]))
    return column_tests, relationships


def build_tbls(manifest: dict, catalog: dict, layer: str, folder: str | None, schema_name: str) -> dict:
    prefix = [layer, folder] if folder else [layer]
    models = {
        uid: node
        for uid, node in manifest["nodes"].items()
        if node["resource_type"] == "model" and node["fqn"][1 : 1 + len(prefix)] == prefix
    }
    if not models:
        raise SystemExit(f"No models found in models/{'/'.join(prefix)}.")

    column_tests, relationships = collect_tests(manifest, set(models))
    tables: dict[str, dict] = {}
    pk_by_table: dict[str, list[str]] = {}

    for uid in sorted(models, key=lambda u: models[u]["name"]):
        node = models[uid]
        catalog_node = catalog["nodes"].get(uid)
        if not catalog_node:
            raise SystemExit(f"{node['name']} is missing from catalog.json; build it before exporting.")

        name = node["name"]
        tests = column_tests.get(uid, {})
        pk_columns = [c for c, t in tests.items() if {"unique", "not_null"} <= t][:1]
        doc_columns = {col_name.lower(): col for col_name, col in node.get("columns", {}).items()}

        columns, constraints = [], []
        if pk_columns:
            constraints.append({
                "name": f"{name}_pkey",
                "type": "PRIMARY KEY",
                "def": f"PRIMARY KEY ({', '.join(pk_columns)})",
                "table": name,
                "columns": pk_columns,
            })

        for col in sorted(catalog_node["columns"].values(), key=lambda c: c["index"]):
            col_name = col["name"]
            col_tests = tests.get(col_name, set())
            columns.append({
                "name": col_name,
                "type": col["type"].lower(),
                "nullable": col_name not in pk_columns and "not_null" not in col_tests,
                "default": None,
                "comment": clean_text(doc_columns.get(col_name.lower(), {}).get("description", "")),
            })
            if "unique" in col_tests and col_name not in pk_columns:
                constraints.append({
                    "name": f"{name}_{col_name}_key",
                    "type": "UNIQUE",
                    "def": f"UNIQUE ({col_name})",
                    "table": name,
                    "columns": [col_name],
                })

        materialized = node["config"].get("materialized", "")
        pk_by_table[name] = pk_columns
        tables[name] = {
            "name": name,
            "type": TABLE_TYPES.get(materialized, "TABLE"),
            "comment": clean_text(f"{node['description']} (dbt model {node['schema']}.{name}, {materialized})"),
            "columns": columns,
            "indexes": [],
            "constraints": constraints,
        }

    relations = []
    for child_id, child_col, parent, parent_col in sorted(
        set(relationships), key=lambda r: (models[r[0]]["name"], r[1])
    ):
        child = models[child_id]["name"]
        if parent not in tables:
            continue
        child_tests = column_tests[child_id][child_col]
        child_is_pk = child_col in pk_by_table[child]
        is_one_to_one = child_is_pk or "unique" in child_tests
        is_mandatory = child_is_pk or "not_null" in child_tests

        # Liam ERD only treats a FK as one-to-one when a UNIQUE constraint covers it (PRIMARY KEY is not enough)
        unique_name = f"{child}_{child_col}_key"
        if child_is_pk and not any(c["name"] == unique_name for c in tables[child]["constraints"]):
            tables[child]["constraints"].append({
                "name": unique_name,
                "type": "UNIQUE",
                "def": f"UNIQUE ({child_col})",
                "table": child,
                "columns": [child_col],
            })

        fk_def = f"FOREIGN KEY ({child_col}) REFERENCES {parent}({parent_col})"
        tables[child]["constraints"].append({
            "name": f"{parent}_{parent_col}_to_{child}_{child_col}",
            "type": "FOREIGN KEY",
            "def": fk_def,
            "table": child,
            "referenced_table": parent,
            "columns": [child_col],
            "referenced_columns": [parent_col],
        })
        relations.append({
            "table": child,
            "columns": [child_col],
            "cardinality": "zero_or_one" if is_one_to_one else "zero_or_more",
            "parent_table": parent,
            "parent_columns": [parent_col],
            "parent_cardinality": "exactly_one" if is_mandatory else "zero_or_one",
            "def": fk_def,
        })

    return {"name": schema_name, "tables": list(tables.values()), "relations": relations}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--layer", help="Top-level models/ folder to export, e.g. gold (default: all DEFAULT_EXPORTS)")
    parser.add_argument("--folder", help="Optional sub-folder of the layer, e.g. eshop")
    parser.add_argument("--name", help="Output schema name (default: <layer>_<folder> or <layer>)")
    parser.add_argument("--target-dir", type=Path, default=PROJECT_DIR / "target")
    parser.add_argument("--schemas-dir", type=Path, default=SCHEMAS_DIR)
    args = parser.parse_args()

    if args.layer:
        name = args.name or "_".join(p for p in (args.layer, args.folder) if p)
        exports = [(args.layer, args.folder, name)]
    else:
        exports = DEFAULT_EXPORTS

    manifest, catalog = load_artifacts(args.target_dir)
    for layer, folder, name in exports:
        tbls = build_tbls(manifest, catalog, layer, folder, name)
        output = args.schemas_dir / f"{name}.tbls.json"
        output.write_text(json.dumps(tbls, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {output} ({len(tbls['tables'])} tables, {len(tbls['relations'])} relations)")


if __name__ == "__main__":
    main()
