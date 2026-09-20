import React, { memo, useMemo } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { prepareMarkdown, remarkRichContent } from '../utils/richContent';
import 'katex/dist/katex.min.css';
import './RichContent.css';

const remarkPlugins = [remarkGfm, remarkMath, remarkRichContent];
const rehypePlugins = [[rehypeKatex, { trust: false, strict: 'ignore', maxExpand: 1000, maxSize: 20 }]];
const components = {
  a: ({ node, children, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer">{children}</a>,
  // AI responses should not trigger requests to arbitrary image URLs.
  img: ({ alt }) => <span className="rich-content-image">{alt ? `[Image: ${alt}]` : '[Image]'}</span>,
};

function RichContent({ content, className = '', ...props }) {
  const markdown = useMemo(() => prepareMarkdown(content), [content]);
  return (
    <div {...props} className={`rich-content ${className}`.trim()}>
      <Markdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins} components={components}>
        {markdown}
      </Markdown>
    </div>
  );
}

export default memo(RichContent);
