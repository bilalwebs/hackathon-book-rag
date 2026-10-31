import React from 'react';
import type { SourceCitation } from '../../services/chatService';
import { getCitationParts } from '../../utils/citations';

interface CitationTextProps {
  text: string;
  sources?: SourceCitation[] | null;
}

/**
 * Render plain text with recognized inline citations turned into safe links.
 * Unrecognized or unmapped citations are left as plain text.
 */
export function CitationText({
  text,
  sources,
}: CitationTextProps): React.ReactElement {
  return (
    <>
      {getCitationParts(text, sources).map((part, index) =>
        part.type === 'citation' ? (
          <a
            key={index}
            href={part.url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {part.value}
          </a>
        ) : (
          <React.Fragment key={index}>{part.value}</React.Fragment>
        ),
      )}
    </>
  );
}
