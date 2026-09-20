import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { contentText, prepareMarkdown, remarkRichContent } from './richContent.js';

function render(content) {
  return renderToStaticMarkup(React.createElement(Markdown, {
    remarkPlugins: [remarkGfm, remarkMath, remarkRichContent],
    rehypePlugins: [[rehypeKatex, { trust: false, strict: 'ignore', maxExpand: 1000, maxSize: 20 }]],
  }, prepareMarkdown(content)));
}

test('renders the checksum explanation with heading, list, inline and display math', () => {
  const html = render(String.raw`**### The Core Problem Rule (Checksum Property)**
For an **original** word of length $N$, $4 \le N \le 1000$.

1. A multiple of $(N + 1)$.
2. Exactly $0$.

**#### Processing Word 1: \`"1011"\` (Length = 4)**

\[ \sum_{i=1}^{N} i x_i \equiv 0 \pmod{N+1} \]

\(0 \to 1\) implies a change.`.replaceAll('\\`', '`'));
  assert.match(html, /<h3>The Core Problem Rule/);
  assert.match(html, /<h4>Processing Word 1: <code>/);
  assert.match(html, /<strong>original<\/strong>/);
  assert.match(html, /<ol>/);
  assert.match(html, /class="katex"/);
  assert.match(html, /class="katex-display"/);
  assert.match(html, /<math/);
  assert.doesNotMatch(html, /katex-error/);
});

test('preserves fenced, inline, indented, nested, and unclosed code during TeX normalization', () => {
  const code = String.raw`Inline \`\(x\) $N$\`.

\`\`\`cpp
cout << "\\[" << "$N$";
// \(untouched\)
\`\`\`

    \(also untouched\)

> \`\`\`python
> print(r"\[raw\]")
> \`\`\`

\`\`\`text
\(unfinished fence\)`.replaceAll('\\`', '`');
  assert.equal(prepareMarkdown(code), code);
  assert.equal(prepareMarkdown(String.raw`Math \(x\), literal \`\(x\)\`.`.replaceAll('\\`', '`')), 'Math $x$, literal `\\(x\\)`.');
  assert.equal(prepareMarkdown(String.raw`Escaped \\(x\\)`), String.raw`Escaped \\(x\\)`);
});

test('pretty prints object, bare JSON, and fenced JSON while preserving invalid JSON and ordinary code', () => {
  const value = { input: '2 3', output: '5', notes: ['a', 'b'] };
  assert.equal(contentText(value), JSON.stringify(value, null, 2));
  assert.match(prepareMarkdown(JSON.stringify(value)), /```json\n\{\n  "input": "2 3",/);
  assert.match(render('```json\n{"ok":true,"values":[1,2]}\n```'), /\n  &quot;ok&quot;: true,\n/);
  assert.match(render('```json\n{"incomplete":\n```'), /\{&quot;incomplete&quot;:\n/);
  assert.match(render('```python\n{"ok":true}\n```'), /\{&quot;ok&quot;:true\}/);
  assert.match(render('[{"a":1}]'), /class="language-json"/);
  assert.match(render(value), /class="language-json"/);
  assert.equal(contentText(null), '');
});

test('JSON strings containing backtick fences remain a single code block', () => {
  const value = { markdown: '```\n<script>alert(1)</script>\n```' };
  const html = render(value);
  assert.equal((html.match(/<pre>/g) || []).length, 1);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
});

test('JSON formatting preserves large numbers, exponents, escapes and duplicate keys', () => {
  const source = String.raw`{"n":9223372036854775807,"n":-9007199254740993,"tiny":1e-400,"path":"C:\\tmp\\a.cpp","escaped":"\u0041","empty":[{},[]]}`;
  const prepared = prepareMarkdown(source);
  assert.match(prepared, /9223372036854775807/);
  assert.match(prepared, /-9007199254740993/);
  assert.match(prepared, /1e-400/);
  assert.match(prepared, /\\u0041/);
  assert.match(prepared, /C:\\\\tmp\\\\a.cpp/);
  assert.match(render('```json\n' + source + '\n```'), /9223372036854775807/);
  assert.equal((prepared.match(/"n":/g) || []).length, 2);
});

test('unsafe HTML and URLs cannot execute, including KaTeX trusted extensions', () => {
  const html = render(String.raw`<script>alert(1)</script>

[bad](javascript:alert%281%29)

$\href{javascript:alert(1)}{unsafe}$

$\htmlClass{unsafe}{x}$`);
  assert.doesNotMatch(html, /<script>|href="javascript:|class="unsafe"/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /href=""/);
});

test('unsupported LaTeX stays readable and does not crash the reply', () => {
  const html = render('Before $\\notARealCommand{x}$ after.');
  assert.match(html, /Before/);
  assert.match(html, /after/);
  assert.match(html, /notARealCommand/);
});
