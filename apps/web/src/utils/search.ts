export function matchesSearch<T extends Record<string, unknown>>(row: T, query: string, fields: string[]) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return fields.some((field) => stringifyValue(readPath(row, field)).toLowerCase().includes(normalized));
}

export function filterBySearch<T extends Record<string, unknown>>(rows: T[], query: string, fields: string[]) {
  return rows.filter((row) => matchesSearch(row, query, fields));
}

function readPath(value: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((current, key) => {
    if (current === null || current === undefined) return undefined;
    if (Array.isArray(current)) return current.map((item) => readPath(item, key));
    if (typeof current === "object") return (current as Record<string, unknown>)[key];
    return undefined;
  }, value);
}

function stringifyValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.map(stringifyValue).join(" ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
