#!/usr/bin/env python3
import os
import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.services.llm_provider import llm_provider
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import tiktoken
from tqdm import tqdm
import hashlib

class MarkdownChunker:
    def __init__(self, max_tokens: int = 1000, overlap_tokens: int = 200):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")

    def chunk_text(self, text: str):
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current_chunk = []
        current_tokens = 0
        for sentence in sentences:
            if not sentence.strip():
                continue
            sentence_tokens = len(self.encoding.encode(sentence))
            if current_tokens + sentence_tokens > self.max_tokens and current_chunk:
                chunks.append(" ".join(current_chunk))
                overlap = []
                overlap_tokens = 0
                for s in reversed(current_chunk):
                    s_tokens = len(self.encoding.encode(s))
                    if overlap_tokens + s_tokens <= self.overlap_tokens:
                        overlap.insert(0, s)
                        overlap_tokens += s_tokens
                    else:
                        break
                current_chunk = overlap
                current_tokens = overlap_tokens
            current_chunk.append(sentence)
            current_tokens += sentence_tokens
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        return chunks

class MarkdownProcessor:
    def __init__(self, docs_dir: str):
        self.docs_dir = Path(docs_dir)
        self.chunker = MarkdownChunker(max_tokens=1000, overlap_tokens=200)

    def extract_metadata(self, file_path: Path):
        rel_path = file_path.relative_to(self.docs_dir)
        parts = rel_path.parts
        module = 'Unknown'
        chapter = file_path.stem
        section = None
        if len(parts) > 0 and parts[0].startswith('module-'):
            module_num = parts[0].split('-')[1]
            module_name_parts = parts[0].split('-')[2:]
            module_name = ' '.join(module_name_parts).replace('-', ' ').title()
            module = f'Module {module_num}: {module_name}'
        if len(parts) >= 2:
            chapter = parts[1].replace('-', ' ').replace('.md', '').title()
        url = '/' + str(rel_path).replace('\\', '/').replace('.md', '')
        return {'module': module, 'chapter': chapter, 'section': section, 'url': url}

    def process_all(self):
        all_chunks = []
        md_files = list(self.docs_dir.rglob('*.md'))
        for md_file in tqdm(md_files, desc='Processing files'):
            try:
                content = md_file.read_text(encoding='utf-8')
                # Remove frontmatter
                content = re.sub(r'^---\n.*?\n---\n', '', content, flags=re.DOTALL)
                metadata = self.extract_metadata(md_file)
                chunks = self.chunker.chunk_text(content)
                for i, chunk in enumerate(chunks):
                    all_chunks.append({
                        'text': chunk,
                        'module': metadata['module'],
                        'chapter': metadata['chapter'],
                        'section': metadata['section'],
                        'url': metadata['url'],
                        'file': str(md_file.relative_to(self.docs_dir)),
                        'chunk_index': i
                    })
            except Exception as e:
                print(f'Error processing {md_file}: {e}')
        return all_chunks

def main():
    print('=== Textbook Ingestion (Gemini Embeddings) ===')
    print(f'Embedding provider: {llm_provider.embedding_provider}')
    print(f'Embedding model: {llm_provider.embedding_model}')
    print()
    
    # Check Qdrant
    try:
        client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        collections = client.get_collections()
        print(f'Qdrant connected. Collections: {[c.name for c in collections.collections]}')
    except Exception as e:
        print(f'ERROR: Cannot connect to Qdrant: {e}')
        return
    
    # Find docs
    docs_dir = Path(__file__).parent.parent.parent / 'frontend' / 'docs'
    if not docs_dir.exists():
        docs_dir = Path(__file__).parent.parent / 'docs'
    print(f'Docs directory: {docs_dir}')
    print(f'Exists: {docs_dir.exists()}')
    
    if not docs_dir.exists():
        print('ERROR: Docs directory not found')
        return
    
    processor = MarkdownProcessor(str(docs_dir))
    chunks = processor.process_all()
    print(f'\nTotal chunks: {len(chunks)}')
    
    if len(chunks) == 0:
        print('No chunks to process')
        return
    
    # Check dimension
    try:
        dim = llm_provider.get_embedding_dimension()
        print(f'Embedding dimension: {dim}')
    except Exception as e:
        print(f'ERROR getting dimension: {e}')
        return
    
    collection_name = settings.qdrant_collection_name
    
    # Check if collection exists
    collections = client.get_collections()
    exists = any(c.name == collection_name for c in collections.collections)
    
    if exists:
        print(f'\nCollection {collection_name} exists. NOT recreating (as per instructions).')
        print('To update, would need approval. Skipping.')
        return
    else:
        print(f'\nCreating collection {collection_name}...')
        try:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            print('Collection created')
        except Exception as e:
            print(f'ERROR creating collection: {e}')
            return
    
    # Generate embeddings and upload
    print('\nGenerating embeddings and uploading...')
    batch_size = 10
    uploaded = 0
    failed = 0
    
    for i in tqdm(range(0, len(chunks), batch_size)):
        batch = chunks[i:i+batch_size]
        texts = [c['text'] for c in batch]
        try:
            embeddings = llm_provider.generate_embeddings(texts)
            points = []
            for j, (chunk, emb) in enumerate(zip(batch, embeddings)):
                point_id = int(hashlib.md5(f"{chunk['file']}_{chunk['chunk_index']}_{i+j}".encode()).hexdigest()[:15], 16)
                points.append(PointStruct(
                    id=point_id,
                    vector=emb,
                    payload={
                        'text': chunk['text'],
                        'module': chunk['module'],
                        'chapter': chunk['chapter'],
                        'section': chunk['section'],
                        'url': chunk['url'],
                        'file': chunk['file'],
                        'chunk_index': chunk['chunk_index']
                    }
                ))
            client.upsert(collection_name=collection_name, points=points)
            uploaded += len(points)
        except Exception as e:
            print(f'\nError in batch {i}: {e}')
            failed += len(batch)
    
    print(f'\n=== Ingestion Complete ===')
    print(f'Chunks processed: {len(chunks)}')
    print(f'Uploaded: {uploaded}')
    print(f'Failed: {failed}')

if __name__ == '__main__':
    main()
