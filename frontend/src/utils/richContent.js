import { unified } from 'unified';
import remarkParse from 'remark-parse';

const parser = unified().use(remarkParse);

export function contentText(content) {
  if (typeof content === 'string') return content;
  if (content == null) return '';
  return typeof content === 'object' ? JSON.stringify(content, null, 2) : String(content);
}

function prettyJson(source) {
  try {
    JSON.parse(source);
  } catch {
    return null;
  }
  // Format validated tokens instead of reserializing parsed numbers: large
  // integer literals in programming examples must never be rounded by JS.
  const tokens = source.match(/"(?:\\[\s\S]|[^"\\])*"|true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|[{}\[\],:]/g);
  let result = '';
  let depth = 0;
  const newline = () => '\n' + '  '.repeat(depth);
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === '{' || token === '[') {
      const closing = token === '{' ? '}' : ']';
      if (tokens[index + 1] === closing) {
        result += token + closing;
        index += 1;
      } else {
        depth += 1;
        result += token + newline();
      }
    } else if (token === '}' || token === ']') {
      depth -= 1;
      result += newline() + token;
    } else if (token === ',') {
      result += token + newline();
    } else {
      result += token === ':' ? ': ' : token;
    }
  }
  return result;
}

function jsonDocument(source) {
  const trimmed = source.trim();
  return trimmed.startsWith('{') || trimmed.startsWith('[') ? prettyJson(trimmed) : null;
}

function codeFence(content) {
  const longest = Math.max(0, ...(content.match(/`+/g) || []).map(run => run.length));
  const fence = '`'.repeat(Math.max(3, longest + 1));
  return `${fence}json\n${content}\n${fence}`;
}

function normalizeProse(source) {
  return source
    // Support the other common TeX delimiters without touching escaped slashes.
    .replace(/(?<!\\)\\\[([\s\S]*?)(?<!\\)\\\]/g, (_, math) => `\n$$\n${math.trim()}\n$$\n`)
    .replace(/(?<!\\)\\\(([^\n]*?)(?<!\\)\\\)/g, (_, math) => `$${math}$`);
}

/** Normalize presentation only: fenced, indented, and inline code stay intact. */
export function prepareMarkdown(content) {
  const source = contentText(content);
  const json = jsonDocument(source);
  if (json !== null) return codeFence(json);

  const protectedRanges = [];
  function collect(node) {
    if (node.type === 'code' || node.type === 'inlineCode') {
      protectedRanges.push([node.position.start.offset, node.position.end.offset]);
      return;
    }
    node.children?.forEach(collect);
  }
  collect(parser.parse(source));

  let cursor = 0;
  let result = '';
  for (const [start, end] of protectedRanges) {
    result += normalizeProse(source.slice(cursor, start)) + source.slice(start, end);
    cursor = end;
  }
  return result + normalizeProse(source.slice(cursor));
}

/** Repair model presentation only after Markdown has identified code boundaries. */
export function remarkRichContent() {
  return function transform(tree) {
    function splitHeading(node) {
      if (node.type !== 'paragraph' || node.children[0]?.type !== 'strong') return [node];
      const [strong, ...remaining] = node.children;
      const first = strong.children[0];
      const heading = first?.type === 'text' && /^(#{1,6})\s+/.exec(first.value);
      if (!heading || (remaining.length && (remaining[0].type !== 'text' || !remaining[0].value.startsWith('\n')))) return [node];
      const result = [{
        type: 'heading', depth: heading[1].length,
        children: [{ ...first, value: first.value.slice(heading[0].length) }, ...strong.children.slice(1)],
      }];
      if (remaining.length) {
        remaining[0] = { ...remaining[0], value: remaining[0].value.slice(1) };
        if (!remaining[0].value) remaining.shift();
        if (remaining.length) result.push({ ...node, children: remaining });
      }
      return result;
    }
    function visit(node) {
      if (node.type === 'code' && /^json$/i.test(node.lang || '')) {
        // Incomplete or illustrative JSON stays visible exactly as written.
        node.value = prettyJson(node.value) ?? node.value;
      }
      if (node.children) {
        node.children = node.children.flatMap(splitHeading);
        node.children.forEach(visit);
      }
    }
    visit(tree);
  };
}
