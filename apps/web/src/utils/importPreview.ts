export interface ImportPreviewRow {
  sender_name?: string;
  text?: string;
  timestamp?: string;
  channel?: string;
}

export function detectSourceType(filename: string | undefined, content: string): "csv" | "json" | "text" {
  if (filename?.toLowerCase().endsWith(".csv")) return "csv";
  if (filename?.toLowerCase().endsWith(".json")) return "json";

  const trimmed = content.trim();
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) return "json";
  if (trimmed.includes(",") && trimmed.includes("\n")) return "csv";
  return "text";
}

export function previewRows(content: string, sourceType: "csv" | "json" | "text"): ImportPreviewRow[] {
  if (!content.trim()) return [];

  if (sourceType === "json") {
    try {
      const parsed = JSON.parse(content);
      const rows = Array.isArray(parsed) ? parsed : parsed.messages ?? parsed.items ?? [parsed];
      return rows.slice(0, 5).map((row: Record<string, unknown>) => ({
        sender_name: String(row.sender_name ?? row.sender ?? row.name ?? ""),
        text: String(row.text ?? row.content ?? row.message ?? ""),
        timestamp: String(row.timestamp ?? row.created_at ?? row.time ?? ""),
        channel: String(row.channel ?? "json")
      }));
    } catch {
      return [{ text: "JSON 格式暂未通过本地预览校验" }];
    }
  }

  if (sourceType === "csv") {
    const [headerLine, ...lines] = content.split(/\r?\n/).filter(Boolean);
    const headers = splitCsvLine(headerLine).map((item) => item.trim());
    return lines.slice(0, 5).map((line) => {
      const cells = splitCsvLine(line);
      const row = Object.fromEntries(headers.map((header, index) => [header, cells[index] ?? ""]));
      return {
        sender_name: row.sender_name ?? row.sender ?? row.name,
        text: row.text ?? row.content ?? row.message,
        timestamp: row.timestamp ?? row.time ?? row.created_at,
        channel: row.channel ?? "csv"
      };
    });
  }

  return content
    .split(/\r?\n/)
    .filter(Boolean)
    .slice(0, 5)
    .map((line) => ({ text: line, channel: "text" }));
}

function splitCsvLine(line: string) {
  const values: string[] = [];
  let current = "";
  let quoted = false;

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === "\"") {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      values.push(current.trim());
      current = "";
    } else {
      current += char;
    }
  }

  values.push(current.trim());
  return values;
}
