#!/usr/bin/env python3
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from qdrant_client import QdrantClient

def main():
    print('=== Qdrant Diagnostic ===')
    print(f'URL: {settings.qdrant_url[:30]}...' if len(settings.qdrant_url) > 30 else f'URL: {settings.qdrant_url}')
    print(f'API Key: {"SET" if settings.qdrant_api_key else "NOT SET"}')
    print(f'Collection: {settings.qdrant_collection_name}')
    print()
    
    try:
        client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        print('1. Connecting to Qdrant...')
        collections = client.get_collections()
        print(f'   OK - Found {len(collections.collections)} collections')
        for c in collections.collections:
            print(f'   - {c.name}')
        print()
        
        print(f'2. Checking collection "{settings.qdrant_collection_name}"...')
        exists = any(c.name == settings.qdrant_collection_name for c in collections.collections)
        if exists:
            print('   EXISTS')
            try:
                info = client.get_collection(settings.qdrant_collection_name)
                print(f'   Status: {getattr(info, "status", "unknown")}')
                print(f'   Vectors count: {getattr(info, "vectors_count", None) or getattr(info, "points_count", None)}')
                if hasattr(info, 'config'):
                    try:
                        params = info.config.params
                        if hasattr(params, 'vectors'):
                            if isinstance(params.vectors, dict):
                                for k,v in params.vectors.items():
                                    print(f'   Vector {k}: size={getattr(v,"size",None)}, distance={getattr(v,"distance",None)}')
                            else:
                                print(f'   Vector: size={getattr(params.vectors,"size",None)}, distance={getattr(params.vectors,"distance",None)}')
                    except Exception as e:
                        print(f'   Config error: {e}')
            except Exception as e:
                print(f'   Error getting info: {e}')
        else:
            print('   DOES NOT EXIST')
        print()
        print('=== Diagnostic Complete ===')
        
    except Exception as e:
        print(f'ERROR: {e}')
        print()
        print('=== Diagnostic Failed ===')

if __name__ == '__main__':
    main()
