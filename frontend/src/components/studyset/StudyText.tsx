import { useMemo } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

interface StudyTextProps {
  text: string | number | null | undefined;
  className?: string;
  highlight?: string;
}

function plainText(value: string, highlight: string | undefined, key: string) {
  const term = highlight?.trim();
  if (!term) return value;
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return value.split(new RegExp(`(${escaped})`, "gi")).map((part, index) =>
    part.toLowerCase() === term.toLowerCase()
      ? <mark key={`${key}-${index}`}>{part}</mark>
      : part,
  );
}

/** Render display LaTeX delimited by $$ while leaving all other text unchanged. */
export function StudyText({ text, className = "", highlight }: StudyTextProps) {
  const value = text == null ? "" : String(text);
  const parts = useMemo(() => {
    const output: Array<{ kind: "text" | "math"; value: string }> = [];
    const pattern = /\$\$([\s\S]*?)\$\$/g;
    let cursor = 0;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(value)) !== null) {
      if (match.index > cursor) output.push({ kind: "text", value: value.slice(cursor, match.index) });
      if (match[1].trim()) output.push({ kind: "math", value: match[1].trim() });
      else output.push({ kind: "text", value: match[0] });
      cursor = match.index + match[0].length;
    }
    if (cursor < value.length) output.push({ kind: "text", value: value.slice(cursor) });
    return output.length ? output : [{ kind: "text" as const, value }];
  }, [value]);

  return (
    <span className={`study-text ${className}`.trim()}>
      {parts.map((part, index) =>
        part.kind === "math" ? (
          <span
            className="study-math"
            key={`math-${index}`}
            dangerouslySetInnerHTML={{
              __html: katex.renderToString(part.value, {
                displayMode: true,
                throwOnError: false,
                trust: false,
                strict: "ignore",
              }),
            }}
          />
        ) : (
          <span className="study-plain-text" key={`text-${index}`}>
            {plainText(part.value, highlight, `text-${index}`)}
          </span>
        ),
      )}
    </span>
  );
}
