import type { CSSProperties, ReactNode } from "react";
import { Fragment, isValidElement, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { BundledLanguage, ThemedTokenWithVariants } from "shiki";

type MarkdownContentProps = {
  markdown: string;
};

export function MarkdownContent({ markdown }: MarkdownContentProps) {
  return (
    <div className="markdown-content text-body text-ink min-w-0">
      <ReactMarkdown
        components={{
          pre: ({ children }) => {
            if (
              !isValidElement<{ className?: string; children?: ReactNode }>(
                children,
              )
            ) {
              return <pre>{children}</pre>;
            }
            const className = children.props.className ?? "";
            const language = /language-([\w-]+)/.exec(className)?.[1] ?? "text";
            return (
              <pre className="bg-surface-subtle my-4 overflow-x-auto rounded-md p-4">
                <HighlightedCode
                  code={String(children.props.children ?? "").replace(
                    /\n$/,
                    "",
                  )}
                  language={language}
                />
              </pre>
            );
          },
          code: ({ children, className }) => (
            <code
              className={
                className ?? "bg-surface-subtle rounded-xs px-1 py-0.5"
              }
            >
              {children}
            </code>
          ),
          h1: ({ children }) => (
            <h1 className="text-headline font-headline text-ink-strong mt-7 mb-3">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-section font-section text-ink-strong mt-6 mb-2">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-body text-ink-strong mt-5 mb-2 font-semibold">
              {children}
            </h3>
          ),
          p: ({ children }) => <p className="my-3 leading-7">{children}</p>,
          ul: ({ children }) => (
            <ul className="my-3 list-disc space-y-2 pl-5">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="my-3 list-decimal space-y-2 pl-5">{children}</ol>
          ),
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}

function HighlightedCode({
  code,
  language,
}: {
  code: string;
  language: string;
}) {
  const [tokens, setTokens] = useState<ThemedTokenWithVariants[][] | null>(
    null,
  );

  useEffect(() => {
    let active = true;
    void import("shiki")
      .then(({ codeToTokensWithThemes }) =>
        codeToTokensWithThemes(code, {
          lang: language as BundledLanguage,
          themes: { light: "github-light", dark: "github-dark" },
        }),
      )
      .then((result) => {
        if (active) setTokens(result);
      })
      .catch(() => {
        if (active) setTokens(null);
      });
    return () => {
      active = false;
    };
  }, [code, language]);

  return (
    <code
      className={`language-${language}`}
      data-shiki={tokens ? "true" : "false"}
    >
      {tokens
        ? tokens.map((line, lineIndex) => (
            <Fragment key={lineIndex}>
              {line.map((token, tokenIndex) => (
                <span
                  key={`${lineIndex}-${tokenIndex}`}
                  className="markdown-code-token"
                  style={
                    {
                      "--shiki-light": token.variants.light?.color,
                      "--shiki-dark": token.variants.dark?.color,
                    } as CSSProperties
                  }
                >
                  {token.content}
                </span>
              ))}
              {lineIndex < tokens.length - 1 ? "\n" : null}
            </Fragment>
          ))
        : code}
    </code>
  );
}
