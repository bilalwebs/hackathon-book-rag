import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  buildSourceNumberMap,
  getCitationParts,
  remarkCitations,
  splitCitationText,
} from '../src/utils/citations.ts';

const sources = [
  {
    module: 'Module 1',
    chapter: 'Chapter 1',
    url: '/docs/shared',
    relevance_score: 0.9,
    source_number: 1,
  },
  {
    module: 'Module 2',
    chapter: 'Chapter 2',
    url: '/docs/shared',
    relevance_score: 0.8,
    source_number: 2,
  },
  {
    module: 'Module 3',
    chapter: 'Chapter 3',
    url: '/docs/third',
    relevance_score: 0.7,
    source_number: 3,
  },
  {
    module: 'Module 4',
    chapter: 'Chapter 4',
    url: '/docs/fourth',
    relevance_score: 0.6,
    source_number: 4,
  },
];

test('recognizes supported ASCII and Unicode citation formats', () => {
  const cases = [
    ['[Source 1]', 1],
    ['【Source 2】', 2],
    ['【Source 3†L1-L4】', 3],
    ['【Source\u202f4†L1-L4】', 4],
    ['[Source\u00A01]', 1],
    ['【Source 1†L1–L4】', 1],
  ];

  for (const [text, expectedNumber] of cases) {
    const parts = splitCitationText(text);
    assert.equal(parts.length, 1, text);
    assert.equal(parts[0].type, 'citation', text);
    assert.equal(parts[0].number, expectedNumber, text);
    assert.equal(parts[0].value, text, text);
  }
});

test('maps citation 4 by source_number, not array index', () => {
  const parts = getCitationParts('See 【Source 4†L1-L3】.', sources);
  const link = parts.find((part) => part.type === 'citation');

  assert.ok(link);
  assert.equal(link.number, 4);
  assert.equal(link.source.source_number, 4);
  assert.equal(link.url, '/docs/fourth');
});

test('handles adjacent citations independently', () => {
  const parts = getCitationParts(
    '【Source 1†L1-L4】【Source 4†L1-L3】',
    sources,
  );
  const citations = parts.filter((part) => part.type === 'citation');

  assert.deepEqual(
    citations.map((part) => part.number),
    [1, 4],
  );
  assert.deepEqual(
    citations.map((part) => part.url),
    ['/docs/shared', '/docs/fourth'],
  );
});

test('leaves unknown citations as plain text', () => {
  const parts = getCitationParts('See 【Source 99】.', sources);

  assert.equal(
    parts.some((part) => part.type === 'citation'),
    false,
  );
  assert.equal(
    parts.map((part) => part.value).join(''),
    'See 【Source 99】.',
  );
});

test('does not map sources without a source_number', () => {
  const sourceMap = buildSourceNumberMap([
    {
      module: 'Module 1',
      chapter: 'Chapter 1',
      url: '/docs/no-number',
      relevance_score: 0.9,
    },
  ]);

  assert.equal(sourceMap.size, 0);
});

test('does not link unsafe source URLs', () => {
  const parts = getCitationParts('【Source 4】', [
    {
      ...sources[3],
      url: 'javascript:alert(1)',
    },
  ]);

  assert.equal(
    parts.some((part) => part.type === 'citation'),
    false,
  );
});

test('applies a custom URL resolver', () => {
  const parts = getCitationParts('【Source 4】', sources, (url) => {
    return `https://example.com${url}`;
  });
  const link = parts.find((part) => part.type === 'citation');

  assert.ok(link);
  assert.equal(link.url, 'https://example.com/docs/fourth');
});

test('remark plugin creates safe links and keeps unknown citations as text', () => {
  const tree = {
    type: 'root',
    children: [
      {
        type: 'paragraph',
        children: [
          {
            type: 'text',
            value: 'See 【Source 4†L1-L3】 and 【Source 99】.',
          },
        ],
      },
    ],
  };

  const transformer = remarkCitations({ sources });
  transformer(tree);

  const paragraph = tree.children[0];
  const link = paragraph.children.find((node) => node.type === 'link');
  const text = paragraph.children
    .filter((node) => node.type === 'text')
    .map((node) => node.value)
    .join('');

  assert.ok(link);
  assert.equal(link.url, '/docs/fourth');

  // Citation links now display only the clean source number.
  assert.equal(link.children[0].value, '[4]');

  assert.deepEqual(link.data.hProperties, {
    target: '_blank',
    rel: 'noopener noreferrer',
  });

  assert.equal(text, 'See  and 【Source 99】.');
});

test('does not transform citations inside code', () => {
  const tree = {
    type: 'root',
    children: [
      { type: 'code', value: '【Source 4】' },
      {
        type: 'paragraph',
        children: [{ type: 'inlineCode', value: '【Source 4】' }],
      },
    ],
  };

  const transformer = remarkCitations({ sources });
  transformer(tree);

  assert.equal(tree.children[0].value, '【Source 4】');
  assert.equal(tree.children[1].children[0].type, 'inlineCode');
  assert.equal(tree.children[1].children[0].value, '【Source 4】');
});

test('ReactMarkdown renders mapped citations as safe links only', () => {
  const html = renderToStaticMarkup(
    React.createElement(ReactMarkdown, {
      remarkPlugins: [remarkGfm, [remarkCitations, { sources }]],
      children: 'See 【Source 4†L1-L3】 and 【Source 99】.',
    }),
  );

  assert.match(
    html,
    /<a href="\/docs\/fourth" title="Source 4" target="_blank" rel="noopener noreferrer">\[4\]<\/a>/,
  );

  assert.doesNotMatch(html, /<a[^>]*>【Source 99】/);
  assert.match(html, /【Source 99】/);
});