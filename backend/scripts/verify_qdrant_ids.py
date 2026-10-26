import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hashlib
from pathlib import Path

from app.config import settings
from qdrant_client import QdrantClient
from scripts.ingest_textbook_gemini import MarkdownProcessor

docs = Path("..") / "frontend" / "docs"
chunks = MarkdownProcessor(str(docs)).process_all()

expected = set()
for i, chunk in enumerate(chunks):
    raw_id = "{}_{}_{}".format(chunk["file"], chunk["chunk_index"], i)
    point_id = int(hashlib.md5(raw_id.encode()).hexdigest()[:15], 16)
    expected.add(point_id)

client = QdrantClient(
    url=settings.qdrant_url,
    api_key=settings.qdrant_api_key,
)

actual = set()
offset = None

while True:
    points, offset = client.scroll(
        collection_name=settings.qdrant_collection_name,
        limit=100,
        offset=offset,
        with_payload=False,
        with_vectors=False,
    )
    actual.update(point.id for point in points)
    if offset is None:
        break

print("Expected IDs:", len(expected))
print("Actual IDs:", len(actual))
print("Missing IDs:", len(expected - actual))
print("Unexpected IDs:", len(actual - expected))
print("PASS:", expected == actual)


