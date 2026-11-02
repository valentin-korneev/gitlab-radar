function xmlEscape(value) {
  return String(value)
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function excelColumnName(index) {
  let name = '';
  for (let current = index + 1; current; current = Math.floor((current - 1) / 26)) {
    name = String.fromCharCode(65 + ((current - 1) % 26)) + name;
  }
  return name;
}

function crc32(bytes) {
  let crc = 0xffffffff;
  bytes.forEach((byte) => {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  });
  return (crc ^ 0xffffffff) >>> 0;
}

function uint16(value) {
  return new Uint8Array([value & 0xff, (value >>> 8) & 0xff]);
}

function uint32(value) {
  return new Uint8Array([
    value & 0xff,
    (value >>> 8) & 0xff,
    (value >>> 16) & 0xff,
    (value >>> 24) & 0xff,
  ]);
}

function joinBytes(parts) {
  const result = new Uint8Array(parts.reduce((size, part) => size + part.length, 0));
  let offset = 0;
  parts.forEach((part) => {
    result.set(part, offset);
    offset += part.length;
  });
  return result;
}

function zipFiles(files) {
  const encoder = new TextEncoder();
  const localParts = [];
  const centralParts = [];
  let offset = 0;
  Object.entries(files).forEach(([path, content]) => {
    const name = encoder.encode(path);
    const data = encoder.encode(content);
    const checksum = crc32(data);
    const localHeader = joinBytes([
      uint32(0x04034b50), uint16(20), uint16(0x0800), uint16(0), uint16(0), uint16(0),
      uint32(checksum), uint32(data.length), uint32(data.length), uint16(name.length), uint16(0), name,
    ]);
    localParts.push(localHeader, data);
    centralParts.push(joinBytes([
      uint32(0x02014b50), uint16(20), uint16(20), uint16(0x0800), uint16(0), uint16(0), uint16(0),
      uint32(checksum), uint32(data.length), uint32(data.length), uint16(name.length), uint16(0), uint16(0),
      uint16(0), uint16(0), uint32(0), uint32(offset), name,
    ]));
    offset += localHeader.length + data.length;
  });
  const centralDirectory = joinBytes(centralParts);
  const end = joinBytes([
    uint32(0x06054b50), uint16(0), uint16(0), uint16(centralParts.length), uint16(centralParts.length),
    uint32(centralDirectory.length), uint32(offset), uint16(0),
  ]);
  return joinBytes([...localParts, centralDirectory, end]);
}

function downloadXlsx(filename, columns, rows, sheetName = 'Проекты') {
  const allRows = [columns.map((column) => column.title), ...rows];
  const sheetRows = allRows.map((row, rowIndex) => {
    const cells = row.map((value, columnIndex) => {
      const reference = `${excelColumnName(columnIndex)}${rowIndex + 1}`;
      if (typeof value === 'number') return `<c r="${reference}" s="${rowIndex ? 2 : 1}"><v>${value}</v></c>`;
      return `<c r="${reference}" s="${rowIndex ? 2 : 1}" t="inlineStr"><is><t xml:space="preserve">${xmlEscape(value ?? '')}</t></is></c>`;
    }).join('');
    return `<row r="${rowIndex + 1}">${cells}</row>`;
  }).join('');
  const columnWidths = columns.map((column, index) => (
    `<col min="${index + 1}" max="${index + 1}" width="${column.width || 16}" customWidth="1"/>`
  )).join('');
  const files = {
    '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
    '_rels/.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
    'xl/workbook.xml': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="${xmlEscape(sheetName)}" sheetId="1" r:id="rId1"/></sheets></workbook>`,
    'xl/_rels/workbook.xml.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
    'xl/styles.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/><color rgb="FFFFFFFF"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFEF3124"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
    'xl/worksheets/sheet1.xml': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>${columnWidths}</cols><sheetData>${sheetRows}</sheetData><autoFilter ref="A1:${excelColumnName(columns.length - 1)}${allRows.length}"/></worksheet>`,
  };
  const blob = new Blob([zipFiles(files)], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
