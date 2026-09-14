/* 灵犀测速 · 持续测速报告生成器（全局共享）：
   window.buildDocx(blocks) —— 把结构化 blocks（h1/h2/b/p/table）打包成 OOXML，输出 .docx Blob。
   排版与服务端 python-docx 写出的报告保持一致：
   居中微软雅黑大标题 / 加粗章节标题 / 正文 10.5pt 1.3 倍行距 / 全宽细边框表格（表头底纹加粗居中），
   中英文字体（ascii/hAnsi/eastAsia）逐 run 显式声明，Word/WPS 打开不发生字体回退。 */
function xmlEsc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function rPrXml(sz, bold) {
  return '<w:rPr><w:rFonts w:ascii="Microsoft YaHei" w:hAnsi="Microsoft YaHei" w:eastAsia="微软雅黑"/>' +
    (bold ? '<w:b/><w:bCs/>' : '') + '<w:sz w:val="' + sz + '"/><w:szCs w:val="' + sz + '"/></w:rPr>';
}
function pXml(text, o) {
  o = o || {};
  return '<w:p><w:pPr>' +
    (o.ind ? '<w:ind w:left="' + o.ind + '"/>' : '') +
    '<w:spacing w:before="' + (o.before || 0) + '" w:after="' + (o.after == null ? 120 : o.after) + '" w:line="312" w:lineRule="auto"/>' +
    (o.center ? '<w:jc w:val="center"/>' : '') +
    '</w:pPr><w:r>' + rPrXml(o.sz || 21, o.bold) + '<w:t xml:space="preserve">' + xmlEsc(text) + '</w:t></w:r></w:p>';
}
function tcXml(text, header) {
  return '<w:tc><w:tcPr><w:vAlign w:val="center"/>' + (header ? '<w:shd w:val="clear" w:color="auto" w:fill="E8EEF7"/>' : '') + '</w:tcPr>' +
    '<w:p><w:pPr><w:spacing w:before="30" w:after="30"/>' + (header ? '<w:jc w:val="center"/>' : '') + '</w:pPr>' +
    '<w:r>' + rPrXml(20, header) + '<w:t xml:space="preserve">' + xmlEsc(text) + '</w:t></w:r></w:p></w:tc>';
}
function crc32(buf) {
  if (!crc32.table) {
    crc32.table = new Uint32Array(256);
    for (var n = 0; n < 256; n++) {
      var c = n;
      for (var k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      crc32.table[n] = c >>> 0;
    }
  }
  var crc = 0xFFFFFFFF;
  for (var i = 0; i < buf.length; i++) crc = crc32.table[(crc ^ buf[i]) & 0xFF] ^ (crc >>> 8);
  return (crc ^ 0xFFFFFFFF) >>> 0;
}
function buildDocx(blocks) {
  var body = [];
  blocks.forEach(function (b) {
    if (b.t === 'h1') body.push(pXml(b.text, { sz: 40, bold: true, center: true, after: 160 }));
    else if (b.t === 'h2') body.push(pXml(b.text, { sz: 28, bold: true, before: 360, after: 140 }));
    else if (b.t === 'b') body.push(pXml('• ' + b.text, { ind: 420, after: 60 }));
    else if (b.t === 'p') body.push(pXml(b.text, { bold: b.bold, after: 120 }));
    else if (b.t === 'table') {
      var rows = b.rows || [];
      if (!rows.length) return;
      var tbl = ['<w:tbl><w:tblPr>',
        '<w:tblW w:w="5000" w:type="pct"/>',
        '<w:tblBorders>',
        '<w:top w:val="single" w:sz="4" w:color="9AA4AE"/>',
        '<w:left w:val="single" w:sz="4" w:color="9AA4AE"/>',
        '<w:bottom w:val="single" w:sz="4" w:color="9AA4AE"/>',
        '<w:right w:val="single" w:sz="4" w:color="9AA4AE"/>',
        '<w:insideH w:val="single" w:sz="4" w:color="9AA4AE"/>',
        '<w:insideV w:val="single" w:sz="4" w:color="9AA4AE"/>',
        '</w:tblBorders>',
        '<w:tblCellMar><w:top w:w="71" w:type="dxa"/><w:left w:w="141" w:type="dxa"/><w:bottom w:w="71" w:type="dxa"/><w:right w:w="141" w:type="dxa"/></w:tblCellMar>',
        '</w:tblPr>'];
      rows.forEach(function (row, i) {
        tbl.push('<w:tr>' + row.map(function (c) { return tcXml(c, i === 0); }).join('') + '</w:tr>');
      });
      tbl.push('</w:tbl><w:p><w:pPr><w:spacing w:after="80"/></w:pPr></w:p>');
      body.push(tbl.join(''));
    }
  });
  var documentXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' +
    body.join('') +
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>' +
    '</w:body></w:document>';
  var files = [
    ['[Content_Types].xml',
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
      '<Default Extension="xml" ContentType="application/xml"/>' +
      '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>' +
      '</Types>'],
    ['_rels/.rels',
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      '<Relationship Id="rpt1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>' +
      '</Relationships>'],
    ['word/_rels/document.xml.rels',
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'],
    ['word/document.xml', documentXml]
  ];
  var enc = new TextEncoder();
  var chunks = [], central = [], offset = 0;
  files.forEach(function (f) {
    var nameBytes = enc.encode(f[0]);
    var data = enc.encode(f[1]);
    var crc = crc32(data);
    var h = new DataView(new ArrayBuffer(30));
    h.setUint32(0, 0x04034b50, true);
    h.setUint16(4, 20, true);
    h.setUint16(6, 0x0800, true);          // UTF-8 文件名标志
    h.setUint16(8, 0, true);               // STORE 不压缩
    h.setUint32(14, crc, true);
    h.setUint32(18, data.length, true);
    h.setUint32(22, data.length, true);
    h.setUint16(26, nameBytes.length, true);
    chunks.push(new Uint8Array(h.buffer), nameBytes, data);
    central.push({ name: nameBytes, crc: crc, size: data.length, off: offset });
    offset += 30 + nameBytes.length + data.length;
  });
  var centralStart = offset;
  central.forEach(function (c) {
    var r = new DataView(new ArrayBuffer(46));
    r.setUint32(0, 0x02014b50, true);
    r.setUint16(4, 20, true);
    r.setUint16(6, 20, true);
    r.setUint16(8, 0x0800, true);
    r.setUint32(16, c.crc, true);
    r.setUint32(20, c.size, true);
    r.setUint32(24, c.size, true);
    r.setUint16(28, c.name.length, true);
    r.setUint32(42, c.off, true);
    chunks.push(new Uint8Array(r.buffer), c.name);
    offset += 46 + c.name.length;
  });
  var end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, central.length, true);
  end.setUint16(10, central.length, true);
  end.setUint32(12, offset - centralStart, true);
  end.setUint32(16, centralStart, true);
  chunks.push(new Uint8Array(end.buffer));
  return new Blob(chunks, { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
}
window.buildDocx = buildDocx;
