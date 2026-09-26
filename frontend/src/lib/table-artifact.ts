/** Parse workspace table-form text into the backend `table.*` payload shape. */

export type TableCell = number | string;

export type TablePayload = {
  columns: string[];
  rows: Record<string, TableCell>[];
  title?: string;
};

/** Whole-number tokens stay ints; everything else is forwarded as an exact string. */
export function parseCellToken(text: string): TableCell {
  const token = text.trim();
  return /^-?\d+$/.test(token) ? Number.parseInt(token, 10) : token;
}

export function parseColumnList(text: string): string[] {
  return text
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

/**
 * Split a textarea of CSV-ish rows. Empty lines drop. A row whose cell count
 * does not match `columns` is invalid — return null so Run stays disabled.
 */
export function parseTableRows(
  columns: string[],
  text: string,
): Record<string, TableCell>[] | null {
  if (columns.length === 0) return null;
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const rows: Record<string, TableCell>[] = [];
  for (const line of lines) {
    const cells = line.split(",").map((cell) => cell.trim());
    if (cells.length !== columns.length) return null;
    if (cells.some((cell) => cell.length === 0)) return null;
    const row: Record<string, TableCell> = {};
    for (let i = 0; i < columns.length; i += 1) {
      row[columns[i]] = parseCellToken(cells[i]);
    }
    rows.push(row);
  }
  return rows;
}

export function buildTablePayload(
  columnsText: string,
  rowsText: string,
  titleText: string,
): TablePayload | null {
  const columns = parseColumnList(columnsText);
  if (columns.length === 0) return null;
  const rows = parseTableRows(columns, rowsText);
  if (rows === null) return null;
  const title = titleText.trim();
  return title ? { columns, rows, title } : { columns, rows };
}
