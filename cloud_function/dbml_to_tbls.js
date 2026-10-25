#!/usr/bin/env node
/**
 * Converts a .dbml file directly into tbls JSON format (schema.tbls.json)
 * for `liam erd build --format tbls`, preserving all Snowflake / custom data types
 * (VARIANT, OBJECT, ARRAY, NUMBER(38,0), TIMESTAMP_NTZ, VARCHAR(n), etc.).
 */
const fs = require('node:fs');
const path = require('node:path');

// Resolve @dbml/core from global node_modules
const globalModules = process.env.NODE_PATH || '/usr/local/lib/node_modules';
let Parser;
try {
  ({ Parser } = require('@dbml/core'));
} catch {
  try {
    ({ Parser } = require(path.join(globalModules, '@dbml/core')));
  } catch {
    ({ Parser } = require(path.join(globalModules, '@dbml/cli/node_modules/@dbml/core')));
  }
}

const [, , inputDbmlPath, outputTblsJsonPath] = process.argv;
if (!inputDbmlPath || !outputTblsJsonPath) {
  console.error('Usage: node dbml_to_tbls.js <input.dbml> <output.tbls.json>');
  process.exit(1);
}

try {
  const dbmlContent = fs.readFileSync(inputDbmlPath, 'utf8');
  const database = Parser.parse(dbmlContent, 'dbmlv2');

  const tablesMap = new Map();
  const enumsMap = new Map();
  const relations = [];

  for (const schema of database.schemas || []) {
    for (const enm of schema.enums || []) {
      const vals = (enm.values || []).map((v) => v.name);
      enumsMap.set(enm.name, vals);
    }

    for (const table of schema.tables || []) {
      const columns = [];
      const constraints = [];
      const indexes = [];
      const pkColumns = [];

      for (const field of table.fields || []) {
        const rawType =
          (field.type && (field.type.type_name || field.type.name)) || 'varchar';
        const isPk = Boolean(field.pk);
        const isNotNull = Boolean(field.not_null || isPk);

        if (isPk) {
          pkColumns.push(field.name);
        }

        let defaultVal = null;
        if (field.dbdefault !== undefined && field.dbdefault !== null) {
          defaultVal = String(field.dbdefault.value ?? field.dbdefault);
        }

        let comment = field.note || '';
        if (enumsMap.has(rawType)) {
          const enumValuesStr = `Enum values: ${enumsMap.get(rawType).join(', ')}`;
          comment = comment ? `${comment} (${enumValuesStr})` : enumValuesStr;
        }

        columns.push({
          name: field.name,
          type: String(rawType),
          nullable: !isNotNull,
          default: defaultVal,
          comment: comment || '',
        });

        if (field.unique && !isPk) {
          const uqName = `${table.name}_${field.name}_key`;
          constraints.push({
            name: uqName,
            type: 'UNIQUE',
            def: `UNIQUE (${field.name})`,
            table: table.name,
            columns: [field.name],
          });
        }
      }

      for (const idx of table.indexes || []) {
        const idxCols = (idx.columns || []).map((c) => c.value).filter(Boolean);
        if (idxCols.length === 0) continue;

        if (idx.pk) {
          for (const col of idxCols) {
            if (!pkColumns.includes(col)) pkColumns.push(col);
          }
          continue;
        }

        const idxName = idx.name || `${table.name}_${idxCols.join('_')}_idx`;
        const isUnique = Boolean(idx.unique);

        if (isUnique) {
          constraints.push({
            name: idxName,
            type: 'UNIQUE',
            def: `UNIQUE (${idxCols.join(', ')})`,
            table: table.name,
            columns: idxCols,
          });
        }

        indexes.push({
          name: idxName,
          def: isUnique
            ? `CREATE UNIQUE INDEX ${idxName} ON ${table.name} (${idxCols.join(', ')})`
            : `CREATE INDEX ${idxName} ON ${table.name} (${idxCols.join(', ')})`,
          table: table.name,
          columns: idxCols,
        });
      }

      if (pkColumns.length > 0) {
        constraints.unshift({
          name: `${table.name}_pkey`,
          type: 'PRIMARY KEY',
          def: `PRIMARY KEY (${pkColumns.join(', ')})`,
          table: table.name,
          columns: pkColumns,
        });
      }

      tablesMap.set(table.name, {
        name: table.name,
        type: 'TABLE',
        comment: table.note || '',
        columns,
        indexes,
        constraints,
      });
    }

    for (const ref of schema.refs || []) {
      const endpoints = ref.endpoints || [];
      if (endpoints.length !== 2) continue;

      const [ep0, ep1] = endpoints;
      let childEp = ep0;
      let parentEp = ep1;

      if (ep0.relation === '1' && ep1.relation !== '1') {
        childEp = ep1;
        parentEp = ep0;
      }

      const childTable = childEp.tableName;
      const parentTable = parentEp.tableName;
      const childCols = childEp.fieldNames || [];
      const parentCols = parentEp.fieldNames || [];

      if (!childTable || !parentTable || childCols.length === 0 || parentCols.length === 0) {
        continue;
      }

      const fkName =
        ref.name ||
        `${parentTable}_${parentCols.join('_')}_to_${childTable}_${childCols.join('_')}`;
      const fkDef = `FOREIGN KEY (${childCols.join(', ')}) REFERENCES ${parentTable}(${parentCols.join(', ')})`;

      const childTableObj = tablesMap.get(childTable);
      if (childTableObj) {
        childTableObj.constraints.push({
          name: fkName,
          type: 'FOREIGN KEY',
          def: fkDef,
          table: childTable,
          referenced_table: parentTable,
          columns: childCols,
          referenced_columns: parentCols,
        });
      }

      const isOneToOne = ep0.relation === '1' && ep1.relation === '1';
      relations.push({
        table: childTable,
        columns: childCols,
        cardinality: isOneToOne ? 'zero_or_one' : 'zero_or_more',
        parent_table: parentTable,
        parent_columns: parentCols,
        parent_cardinality: 'exactly_one',
        def: fkDef,
      });
    }
  }

  const tblsOutput = {
    name: path.basename(inputDbmlPath, '.dbml'),
    tables: Array.from(tablesMap.values()),
    relations,
  };

  fs.writeFileSync(outputTblsJsonPath, JSON.stringify(tblsOutput, null, 2), 'utf8');
} catch (err) {
  const errMsg = err && err.diags
    ? err.diags.map((d) => `Line ${d.location?.start?.line || '?'}: ${d.message}`).join('\n')
    : err.message || String(err);
  console.error(errMsg);
  process.exit(1);
}

