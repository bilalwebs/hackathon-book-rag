import type { Root } from 'mdast';
import type { Plugin } from 'unified';
import type { SourceCitation } from '../services/chatService';

export interface CitationTextPart {
  type: 'text';
  value: string;
}

export interface CitationLinkPart {
  type: 'citation';
  value: string;
  number: number;
  source: SourceCitation;
  url: string;
}

export type CitationPart = CitationTextPart | CitationLinkPart;

export interface RawCitationPart {
  type: 'text' | 'citation';
  value: string;
  number?: number;
}

export interface RemarkCitationsOptions {
  sources?: SourceCitation[] | null;
  resolveUrl?: (url: string) => string;
}

// Supports [Source 1], 【Source 1】, and 【Source 1†L1-L4】.
// \s also matches Unicode spaces such as U+202F and U+00A0.
const CITATION_PATTERN =
  /[\[【]\s*Source\s*(\d+)(?:\s*†\s*L\d+(?:\s*[-–]\s*L?\d+)?)?\s*[\]】]/gi;

export function splitCitationText(text: string): RawCitationPart[] {
  const parts: RawCitationPart[] = [];
  const regex = new RegExp(CITATION_PATTERN.source, CITATION_PATTERN.flags);
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', value: text.slice(lastIndex, match.index) });
    }

    parts.push({
      type: 'citation',
      value: match[0],
      number: Number.parseInt(match[1], 10),
    });

    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push({ type: 'text', value: text.slice(lastIndex) });
  }

  return parts;
}

export function buildSourceNumberMap(
  sources?: SourceCitation[] | null,
): Map<number, SourceCitation> {
  const sourceMap = new Map<number, SourceCitation>();

  for (const source of sources ?? []) {
    if (
      typeof source.source_number === 'number' &&
      !sourceMap.has(source.source_number)
    ) {
      sourceMap.set(source.source_number, source);
    }
  }

  return sourceMap;
}

export function isSafeUrl(url: string): boolean {
  const value = url.trim();

  if (!value || value.startsWith('//')) {
    return false;
  }

  if (/^[a-z][a-z0-9+.-]*:/i.test(value)) {
    return /^https?:/i.test(value);
  }

  return true;
}

function toCitationParts(
  text: string,
  sourceMap: Map<number, SourceCitation>,
  resolveUrl: (url: string) => string,
): CitationPart[] {
  return splitCitationText(text).map((part) => {
    if (part.type === 'text') {
      return { type: 'text', value: part.value };
    }

    const source =
      part.number !== undefined ? sourceMap.get(part.number) : undefined;

    if (!source) {
      return { type: 'text', value: part.value };
    }

    const url = resolveUrl(source.url);

    if (!isSafeUrl(url)) {
      return { type: 'text', value: part.value };
    }

    return {
      type: 'citation',
      value: part.value,
      number: part.number as number,
      source,
      url,
    };
  });
}

export function getCitationParts(
  text: string,
  sources?: SourceCitation[] | null,
  resolveUrl: (url: string) => string = (url) => url,
): CitationPart[] {
  return toCitationParts(text, buildSourceNumberMap(sources), resolveUrl);
}

function transformCitationNodes(
  node: any,
  sourceMap: Map<number, SourceCitation>,
  resolveUrl: (url: string) => string,
): void {
  if (!node || !Array.isArray(node.children)) {
    return;
  }

  const nextChildren: any[] = [];

  for (const child of node.children) {
    if (child.type === 'text') {
      for (const part of toCitationParts(child.value, sourceMap, resolveUrl)) {
        if (part.type === 'text') {
          nextChildren.push({ type: 'text', value: part.value });
        } else {
          nextChildren.push({
            type: 'link',
            url: part.url,
            title: `Source ${part.number}`,
            data: {
              hProperties: {
                target: '_blank',
                rel: 'noopener noreferrer',
              },
            },
            // Display a clean citation number while preserving its source link.
            children: [{ type: 'text', value: `[${part.number}]` }],
          });
        }
      }
    } else {
      // Do not descend into existing links, which would create nested links.
      if (child.type !== 'link') {
        transformCitationNodes(child, sourceMap, resolveUrl);
      }
      nextChildren.push(child);
    }
  }

  node.children = nextChildren;
}

export const remarkCitations: Plugin<[RemarkCitationsOptions?], Root> = (
  options = {},
) => {
  const sourceMap = buildSourceNumberMap(options.sources);
  const resolveUrl = options.resolveUrl ?? ((url: string) => url);

  return (tree) => {
    transformCitationNodes(tree, sourceMap, resolveUrl);
  };
};