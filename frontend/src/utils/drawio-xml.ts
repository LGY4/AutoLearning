/**
 * Draw.io XML utility functions.
 * Ported from DayuanJiang/next-ai-draw-io (Apache-2.0).
 * Adapted for React + TypeScript (no Next.js dependencies).
 */

// ============================================================================
// Constants
// ============================================================================

const MIN_REAL_DIAGRAM_LENGTH = 300;
const MAX_XML_SIZE = 1_000_000;
const MAX_DROP_ITERATIONS = 10;

const STRUCTURAL_ATTRS = [
  "edge", "parent", "source", "target", "vertex", "connectable",
];

const VALID_DRAWIO_TAGS = new Set([
  "mxfile", "diagram", "mxGraphModel", "root",
  "mxCell", "mxGeometry", "mxPoint", "Array", "Object", "mxRectangle",
]);

// ============================================================================
// Public API
// ============================================================================

export function isRealDiagram(xml: string | undefined | null): boolean {
  return !!xml && xml.length > MIN_REAL_DIAGRAM_LENGTH;
}

export function isMxCellXmlComplete(xml: string | undefined | null): boolean {
  const trimmed = xml?.trim() || "";
  if (!trimmed) return false;
  const lastSelfClose = trimmed.lastIndexOf("/>");
  const lastMxCellClose = trimmed.lastIndexOf("</mxCell>");
  const lastValidEnd = Math.max(lastSelfClose, lastMxCellClose);
  if (lastValidEnd === -1) return false;
  const endOffset = lastMxCellClose > lastSelfClose ? 9 : 2;
  const suffix = trimmed.slice(lastValidEnd + endOffset);
  return /^(\s*<\/[^>]+>)*\s*$/.test(suffix);
}

export function extractCompleteMxCells(xml: string | undefined | null): string {
  if (!xml) return "";
  const completeCells: Array<{ index: number; text: string }> = [];
  const selfClosingPattern = /<mxCell\s+[^>]*\/>/g;
  const nestedPattern = /<mxCell\s+[^>]*>[\s\S]*?<\/mxCell>/g;
  let match: RegExpExecArray | null;
  while ((match = selfClosingPattern.exec(xml)) !== null) {
    completeCells.push({ index: match.index, text: match[0] });
  }
  while ((match = nestedPattern.exec(xml)) !== null) {
    completeCells.push({ index: match.index, text: match[0] });
  }
  completeCells.sort((a, b) => a.index - b.index);
  const seen = new Set<number>();
  return completeCells
    .filter((c) => { if (seen.has(c.index)) return false; seen.add(c.index); return true; })
    .map((c) => c.text)
    .join("\n");
}

export function wrapWithMxFile(xml: string): string {
  const ROOT_CELLS = '<mxCell id="0"/><mxCell id="1" parent="0"/>';
  if (!xml || !xml.trim()) {
    return `<mxfile><diagram name="Page-1" id="page-1"><mxGraphModel><root>${ROOT_CELLS}</root></mxGraphModel></diagram></mxfile>`;
  }
  if (xml.includes("<mxfile")) return xml;
  if (xml.includes("<mxGraphModel")) {
    return `<mxfile><diagram name="Page-1" id="page-1">${xml}</diagram></mxfile>`;
  }
  let content = xml;
  if (xml.includes("<root>")) {
    content = xml.replace(/<\/?root>/g, "").trim();
  }
  // Strip trailing LLM wrapper tags
  const lastSelfClose = content.lastIndexOf("/>");
  const lastMxCellClose = content.lastIndexOf("</mxCell>");
  const lastValidEnd = Math.max(lastSelfClose, lastMxCellClose);
  if (lastValidEnd !== -1) {
    const endOffset = lastMxCellClose > lastSelfClose ? 9 : 2;
    const suffix = content.slice(lastValidEnd + endOffset);
    if (/^(\s*<\/[^>]+>)*\s*$/.test(suffix)) {
      content = content.slice(0, lastValidEnd + endOffset);
    }
  }
  // Remove any root cells the LLM might have included
  content = content
    .replace(/<mxCell[^>]*\bid=["']0["'][^>]*(?:\/>|><\/mxCell>)/g, "")
    .replace(/<mxCell[^>]*\bid=["']1["'][^>]*(?:\/>|><\/mxCell>)/g, "")
    .trim();
  return `<mxfile><diagram name="Page-1" id="page-1"><mxGraphModel><root>${ROOT_CELLS}${content}</root></mxGraphModel></diagram></mxfile>`;
}

export function validateAndFixXml(xml: string): {
  valid: boolean;
  error: string | null;
  fixed: string | null;
  fixes: string[];
} {
  const { fixed, fixes } = autoFixXml(xml);
  // Basic structural validation
  if (!fixed.includes("<mxCell")) {
    return { valid: false, error: "XML 中没有 mxCell 元素", fixed, fixes };
  }
  // Try DOMParser validation
  if (typeof DOMParser !== "undefined") {
    const parser = new DOMParser();
    const doc = parser.parseFromString(fixed, "text/xml");
    const parseError = doc.querySelector("parsererror");
    if (parseError) {
      return {
        valid: false,
        error: parseError.textContent?.slice(0, 200) || "XML 解析错误",
        fixed,
        fixes,
      };
    }
  }
  return { valid: true, error: null, fixed, fixes };
}

// ============================================================================
// Internal helpers
// ============================================================================

interface ParsedTag {
  tag: string;
  tagName: string;
  isClosing: boolean;
  isSelfClosing: boolean;
  startIndex: number;
  endIndex: number;
}

function parseXmlTags(xml: string): ParsedTag[] {
  const tags: ParsedTag[] = [];
  let i = 0;
  while (i < xml.length) {
    const tagStart = xml.indexOf("<", i);
    if (tagStart === -1) break;
    let tagEnd = tagStart + 1;
    let inQuote = false;
    let quoteChar = "";
    while (tagEnd < xml.length) {
      const c = xml[tagEnd];
      if (inQuote) {
        if (c === quoteChar) inQuote = false;
      } else {
        if (c === '"' || c === "'") { inQuote = true; quoteChar = c; }
        else if (c === ">") break;
      }
      tagEnd++;
    }
    if (tagEnd >= xml.length) break;
    const tag = xml.substring(tagStart, tagEnd + 1);
    i = tagEnd + 1;
    const tagMatch = /^<(\/?)([a-zA-Z][a-zA-Z0-9:_-]*)/.exec(tag);
    if (!tagMatch) continue;
    tags.push({
      tag,
      tagName: tagMatch[2],
      isClosing: tagMatch[1] === "/",
      isSelfClosing: tag.endsWith("/>"),
      startIndex: tagStart,
      endIndex: tagEnd,
    });
  }
  return tags;
}

function isInsideQuotes(str: string, pos: number): boolean {
  let inQuote = false;
  let quoteChar = "";
  for (let i = 0; i < pos && i < str.length; i++) {
    const c = str[i];
    if (inQuote) {
      if (c === quoteChar) inQuote = false;
    } else if (c === '"' || c === "'") {
      let j = i - 1;
      while (j >= 0 && /\s/.test(str[j])) j--;
      if (j >= 0 && str[j] === "=") { inQuote = true; quoteChar = c; }
    }
  }
  return inQuote;
}

export function autoFixXml(xml: string): { fixed: string; fixes: string[] } {
  if (!xml || xml.length > MAX_XML_SIZE) {
    return { fixed: xml, fixes: [] };
  }

  let fixed = xml;
  const fixes: string[] = [];

  // 0. Fix JSON-escaped XML
  if (/=\\"/.test(fixed)) {
    fixed = fixed.replace(/\\"/g, '"');
    fixed = fixed.replace(/\\n/g, "\n");
    fixes.push("Fixed JSON-escaped XML");
  }

  // 1. Remove CDATA wrapper
  if (/^\s*<!\[CDATA\[/.test(fixed)) {
    fixed = fixed.replace(/^\s*<!\[CDATA\[/, "").replace(/\]\]>\s*$/, "");
    fixes.push("Removed CDATA wrapper");
  }

  // 1b. Strip trailing LLM wrapper tags
  const lastSelfClose = fixed.lastIndexOf("/>");
  const lastMxCellClose = fixed.lastIndexOf("</mxCell>");
  const lastValidEnd = Math.max(lastSelfClose, lastMxCellClose);
  if (lastValidEnd !== -1) {
    const endOffset = lastMxCellClose > lastSelfClose ? 9 : 2;
    const suffix = fixed.slice(lastValidEnd + endOffset);
    if (/^(\s*<\/[^>]+>)+\s*$/.test(suffix)) {
      fixed = fixed.slice(0, lastValidEnd + endOffset);
      fixes.push("Stripped trailing LLM wrapper tags");
    }
  }

  // 2. Remove text before XML root
  const xmlStart = fixed.search(/<(\?xml|mxGraphModel|mxfile)/i);
  if (xmlStart > 0 && !/^<[a-zA-Z]/.test(fixed.trim())) {
    fixed = fixed.substring(xmlStart);
    fixes.push("Removed text before XML root");
  }

  // 2b. Fix duplicate structural attributes
  let dupAttrFixed = false;
  fixed = fixed.replace(/<[^>]+>/g, (tag) => {
    let newTag = tag;
    for (const attr of STRUCTURAL_ATTRS) {
      const attrRegex = new RegExp(`\\s${attr}\\s*=\\s*["'][^"']*["']`, "gi");
      const matches = tag.match(attrRegex);
      if (matches && matches.length > 1) {
        let firstKept = false;
        newTag = newTag.replace(attrRegex, (m) => {
          if (!firstKept) { firstKept = true; return m; }
          dupAttrFixed = true;
          return "";
        });
      }
    }
    return newTag;
  });
  if (dupAttrFixed) fixes.push("Removed duplicate structural attributes");

  // 3. Fix unescaped & characters
  const ampersandPattern = /&(?!(?:lt|gt|amp|quot|apos|#[0-9]+|#x[0-9a-fA-F]+);)/g;
  if (ampersandPattern.test(fixed)) {
    fixed = fixed.replace(ampersandPattern, "&amp;");
    fixes.push("Escaped unescaped & characters");
  }

  // 3b. Fix double-escaped entities
  const invalidEntities = [
    { pattern: /&ampquot;/g, replacement: "&quot;" },
    { pattern: /&amplt;/g, replacement: "&lt;" },
    { pattern: /&ampgt;/g, replacement: "&gt;" },
    { pattern: /&ampapos;/g, replacement: "&apos;" },
    { pattern: /&ampamp;/g, replacement: "&amp;" },
  ];
  for (const { pattern, replacement } of invalidEntities) {
    if (pattern.test(fixed)) {
      fixed = fixed.replace(pattern, replacement);
      fixes.push(`Fixed double-escaped entity`);
    }
  }

  // 3c. Fix malformed attribute quotes
  if (/(\s[a-zA-Z][a-zA-Z0-9_:-]*)=&quot;/.test(fixed)) {
    fixed = fixed.replace(/(\s[a-zA-Z][a-zA-Z0-9_:-]*)=&quot;([^&]*?)&quot;/g, '$1="$2"');
    fixes.push("Fixed malformed attribute quotes");
  }

  // 3d. Fix malformed closing tags
  if (/<\/([a-zA-Z][a-zA-Z0-9]*)\s*\/>/g.test(fixed)) {
    fixed = fixed.replace(/<\/([a-zA-Z][a-zA-Z0-9]*)\s*\/>/g, "</$1>");
    fixes.push("Fixed malformed closing tags");
  }

  // 3e. Fix missing space between attributes
  if (/("[^"]*")([a-zA-Z][a-zA-Z0-9_:-]*=)/g.test(fixed)) {
    fixed = fixed.replace(/("[^"]*")([a-zA-Z][a-zA-Z0-9_:-]*=)/g, "$1 $2");
    fixes.push("Added missing space between attributes");
  }

  // 3f. Remove quotes around color values in style
  if (/;([a-zA-Z]*[Cc]olor)="#/.test(fixed)) {
    fixed = fixed.replace(/;([a-zA-Z]*[Cc]olor)="#/g, ";$1=#");
    fixes.push("Removed quotes around color values in style");
  }

  // 4. Fix unescaped < > in attribute values
  const attrPattern = /(=\s*")([^"]*?)(<)([^"]*?)(")/g;
  let attrMatch;
  let hasUnescapedLt = false;
  while ((attrMatch = attrPattern.exec(fixed)) !== null) {
    if (!attrMatch[3].startsWith("&lt;")) { hasUnescapedLt = true; break; }
  }
  if (hasUnescapedLt) {
    fixed = fixed.replace(/=\s*"([^"]*)"/g, (_match, value) => {
      const escaped = value.replace(/</g, "&lt;").replace(/>/g, "&gt;");
      return `="${escaped}"`;
    });
    fixes.push("Escaped <> in attribute values");
  }

  // 5-6. Fix invalid character references
  fixed = fixed.replace(/&#x([^;]*);/g, (match, hex) => {
    return /^[0-9a-fA-F]+$/.test(hex) && hex.length > 0 ? match : "";
  });
  fixed = fixed.replace(/&#([^x][^;]*);/g, (match, dec) => {
    return /^[0-9]+$/.test(dec) && dec.length > 0 ? match : "";
  });

  // 7. Fix invalid comment syntax
  fixed = fixed.replace(/<!--([\s\S]*?)-->/g, (match, content) => {
    if (/--/.test(content)) {
      let fixedContent = content;
      while (/--/.test(fixedContent)) fixedContent = fixedContent.replace(/--/g, "-");
      fixes.push("Fixed invalid comment syntax");
      return `<!--${fixedContent}-->`;
    }
    return match;
  });

  // 8. Fix <Cell> → <mxCell>
  if (/<\/?Cell[\s>]/i.test(fixed)) {
    fixed = fixed.replace(/<Cell(\s)/gi, "<mxCell$1");
    fixed = fixed.replace(/<Cell>/gi, "<mxCell>");
    fixed = fixed.replace(/<\/Cell>/gi, "</mxCell>");
    fixes.push("Fixed <Cell> to <mxCell>");
  }

  // 8b. Fix closing tag typos
  const tagTypos = [
    { wrong: /<\/mxElement>/gi, right: "</mxCell>" },
    { wrong: /<\/mxcell>/g, right: "</mxCell>" },
    { wrong: /<\/mxgeometry>/g, right: "</mxGeometry>" },
    { wrong: /<\/mxpoint>/g, right: "</mxPoint>" },
    { wrong: /<\/mxgraphmodel>/gi, right: "</mxGraphModel>" },
  ];
  for (const { wrong, right } of tagTypos) {
    const before = fixed;
    fixed = fixed.replace(wrong, right);
    if (fixed !== before) fixes.push(`Fixed typo to ${right}`);
  }

  // 8c. Remove non-draw.io tags (not inside quotes)
  const foreignTagPattern = /<\/?([a-zA-Z][a-zA-Z0-9_]*)[^>]*>/g;
  let foreignMatch;
  const foreignTags = new Set<string>();
  const foreignPositions: Array<{ start: number; end: number }> = [];
  while ((foreignMatch = foreignTagPattern.exec(fixed)) !== null) {
    const tagName = foreignMatch[1];
    if (VALID_DRAWIO_TAGS.has(tagName)) continue;
    if (isInsideQuotes(fixed, foreignMatch.index)) continue;
    foreignTags.add(tagName);
    foreignPositions.push({ start: foreignMatch.index, end: foreignMatch.index + foreignMatch[0].length });
  }
  if (foreignPositions.length > 0) {
    foreignPositions.sort((a, b) => b.start - a.start);
    for (const { start, end } of foreignPositions) {
      fixed = fixed.slice(0, start) + fixed.slice(end);
    }
    fixes.push(`Removed foreign tags: ${Array.from(foreignTags).join(", ")}`);
  }

  // 9. Fix empty id attributes
  let emptyIdCount = 0;
  fixed = fixed.replace(/<mxCell([^>]*)\sid\s*=\s*["']\s*["']([^>]*)>/g, (_m, before, after) => {
    emptyIdCount++;
    return `<mxCell${before} id="cell_${Date.now()}_${emptyIdCount}"${after}>`;
  });
  if (emptyIdCount > 0) fixes.push(`Generated ${emptyIdCount} missing ID(s)`);

  // 10. Fix unclosed tags
  const tagStack: string[] = [];
  const parsedTags = parseXmlTags(fixed);
  for (const { tagName, isClosing, isSelfClosing } of parsedTags) {
    if (isClosing) {
      const lastIdx = tagStack.lastIndexOf(tagName);
      if (lastIdx !== -1) tagStack.splice(lastIdx, 1);
    } else if (!isSelfClosing) {
      tagStack.push(tagName);
    }
  }
  if (tagStack.length > 0) {
    const tagsToClose: string[] = [];
    for (const tagName of [...tagStack].reverse()) {
      const openCount = (fixed.match(new RegExp(`<${tagName}[\\s>]`, "gi")) || []).length;
      const closeCount = (fixed.match(new RegExp(`</${tagName}>`, "gi")) || []).length;
      if (openCount > closeCount) tagsToClose.push(tagName);
    }
    if (tagsToClose.length > 0) {
      fixed = fixed.trimEnd() + "\n" + tagsToClose.map((t) => `</${t}>`).join("\n");
      fixes.push(`Closed ${tagsToClose.length} unclosed tag(s)`);
    }
  }

  // 10b. Remove extra closing tags
  const tagCounts = new Map<string, { opens: number; closes: number }>();
  const fullTagPattern = /<(\/?[a-zA-Z][a-zA-Z0-9]*)[^>]*>/g;
  let tagCountMatch;
  while ((tagCountMatch = fullTagPattern.exec(fixed)) !== null) {
    if (isInsideQuotes(fixed, tagCountMatch.index)) continue;
    const fullMatch = tagCountMatch[0];
    const tagPart = tagCountMatch[1];
    const isClosing = tagPart.startsWith("/");
    const isSelfClosing = fullMatch.endsWith("/>");
    const tagName = isClosing ? tagPart.slice(1) : tagPart;
    if (!VALID_DRAWIO_TAGS.has(tagName)) continue;
    let counts = tagCounts.get(tagName);
    if (!counts) { counts = { opens: 0, closes: 0 }; tagCounts.set(tagName, counts); }
    if (isClosing) counts.closes++;
    else if (!isSelfClosing) counts.opens++;
  }
  for (const [tagName, counts] of tagCounts) {
    const extra = counts.closes - counts.opens;
    if (extra > 0) {
      let removed = 0;
      const closePattern = new RegExp(`</${tagName}>`, "g");
      const matches = [...fixed.matchAll(closePattern)];
      for (let i = matches.length - 1; i >= 0 && removed < extra; i--) {
        const m = matches[i];
        const idx = m.index ?? 0;
        fixed = fixed.slice(0, idx) + fixed.slice(idx + m[0].length);
        removed++;
      }
      if (removed > 0) fixes.push(`Removed ${removed} extra </${tagName}>`);
    }
  }

  // 11. Fix duplicate IDs
  const seenIds = new Map<string, number>();
  const idPattern = /\bid\s*=\s*["']([^"']+)["']/gi;
  let idMatch;
  while ((idMatch = idPattern.exec(fixed)) !== null) {
    seenIds.set(idMatch[1], (seenIds.get(idMatch[1]) || 0) + 1);
  }
  const duplicateIds = [...seenIds.entries()].filter(([, c]) => c > 1).map(([id]) => id);
  if (duplicateIds.length > 0) {
    const idCounters = new Map<string, number>();
    fixed = fixed.replace(/\bid\s*=\s*["']([^"']+)["']/gi, (match, id) => {
      if (!duplicateIds.includes(id)) return match;
      const count = idCounters.get(id) || 0;
      idCounters.set(id, count + 1);
      if (count === 0) return match;
      return match.replace(id, `${id}_dup${count}`);
    });
    fixes.push(`Renamed ${duplicateIds.length} duplicate ID(s)`);
  }

  // 12. Drop broken mxCell elements (aggressive, last resort)
  if (typeof DOMParser !== "undefined") {
    let droppedCells = 0;
    let maxIter = MAX_DROP_ITERATIONS;
    while (maxIter-- > 0) {
      const parser = new DOMParser();
      const doc = parser.parseFromString(fixed, "text/xml");
      const parseError = doc.querySelector("parsererror");
      if (!parseError) break;
      const errText = parseError.textContent || "";
      const match = errText.match(/(\d+):\d+:/);
      if (!match) break;
      const errLine = parseInt(match[1], 10) - 1;
      const lines = fixed.split("\n");
      let cellStart = errLine;
      let cellEnd = errLine;
      while (cellStart > 0 && !lines[cellStart].includes("<mxCell")) cellStart--;
      while (cellEnd < lines.length - 1) {
        if (lines[cellEnd].includes("</mxCell>") || lines[cellEnd].trim().endsWith("/>")) break;
        cellEnd++;
      }
      lines.splice(cellStart, cellEnd - cellStart + 1);
      fixed = lines.join("\n");
      droppedCells++;
    }
    if (droppedCells > 0) fixes.push(`Dropped ${droppedCells} unfixable mxCell(s)`);
  }

  return { fixed, fixes };
}
