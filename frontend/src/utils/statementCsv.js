// Parse locally. No raw file, unselected columns or unselected rows leave here.
export function parseStatementCsv(text, delimiter = ',') {
  if (![',', ';', '\t'].includes(delimiter)) throw new Error('invalid');
  if (text.length > 2 * 1024 * 1024) throw new Error('fileLimit');
  const rows = [];
  let row = [],
    cell = '',
    quoted = false,
    closed = false;
  const pushCell = () => {
    if (cell.length > 4096) throw new Error('fileLimit');
    row.push(cell);
    cell = '';
    closed = false;
    if (row.length > 100) throw new Error('fileLimit');
  };
  const pushRow = () => {
    pushCell();
    if (row.some(v => v.trim())) rows.push(row);
    row = [];
    if (rows.length > 10000) throw new Error('fileLimit');
  };
  text = text.replace(/^\uFEFF/, '');
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i++;
        } else {
          quoted = false;
          closed = true;
        }
      } else cell += c;
    } else if (c === delimiter) pushCell();else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      pushRow();
    } else if (c === '"' && !cell && !closed) quoted = true;else {
      if (closed || c === '"') throw new Error('invalid');
      cell += c;
    }
  }
  if (quoted) throw new Error('invalid');
  if (cell || row.length || closed) pushRow();
  if (rows.length < 2 || rows.some(r => r.length !== rows[0].length)) throw new Error('invalid');
  return {
    columns: rows[0],
    rows: rows.slice(1).map((cells, i) => ({
      row_number: i + 2,
      cells
    }))
  };
}
export function cents(value, decimal = '.') {
  const text = String(value).trim();
  const pattern = decimal === ',' ? /^-?\d{1,8}(,\d{1,2})?$/ : /^-?\d{1,8}(\.\d{1,2})?$/;
  if (!pattern.test(text)) throw new Error('invalid');
  const [whole, fraction = ''] = text.replace(',', '.').replace('-', '').split('.');
  return (BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'))) * (text.startsWith('-') ? -1n : 1n);
}
export function money(value) {
  const sign = value < 0n ? '-' : '';
  const absolute = value < 0n ? -value : value;
  return `${sign}${absolute / 100n}.${String(absolute % 100n).padStart(2, '0')}`;
}
function day(value, format) {
  const parts = value.trim().split(format === 'iso' ? '-' : '/');
  if (parts.length !== 3 || parts.some(p => !/^\d+$/.test(p))) throw new Error('invalid');
  const [y, m, d] = format === 'iso' ? parts : format === 'dmy' ? [parts[2], parts[1], parts[0]] : [parts[2], parts[0], parts[1]];
  const result = `${y.padStart(4, '0')}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`;
  const parsed = new Date(result + 'T12:00:00Z');
  if (Number(y) < 1900 || Number(y) > 2100 || Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== result) throw new Error('invalid');
  return result;
}
export function normalizeStatement(parsed, selected, mapping, settings) {
  if (!selected.size || selected.size > 2000) throw new Error('fileLimit');
  for (const key of ['date', 'amount', 'currency']) if (mapping[key] === '') throw new Error('mappingRequired');
  return parsed.rows.filter(r => selected.has(r.row_number)).map(row => {
    const get = key => row.cells[Number(mapping[key])]?.trim() || '';
    const amount = cents(get('amount'), settings.decimal) * (settings.sign === 'bank' ? -1n : 1n);
    const currency = get('currency').toUpperCase();
    const vendor = mapping.vendor === '' ? '' : get('vendor');
    if (!amount || !/^[A-Z]{3}$/.test(currency) || vendor.length > 120 || Array.from(vendor).some(c => c.charCodeAt(0) < 32)) throw new Error('invalid');
    return {
      row_number: row.row_number,
      date: day(get('date'), settings.dateFormat),
      amount: money(amount),
      currency,
      vendor
    };
  });
}
export async function statementFingerprint(bytes) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
}
