from pathlib import Path
import sys
import re
import hashlib
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

import app.config
from app.config import settings
from app.services.llm_provider import llm_provider
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from scripts.ingest_textbook_gemini import MarkdownProcessor


def main():
    collection = settings.qdrant_collection_name

    docs_dir = Path(__file__).parent.parent.parent / "frontend" / "docs"
    if not docs_dir.exists():
        docs_dir = Path(__file__).parent.parent / "docs"

    if not docs_dir.exists():
        raise SystemExit(f"Docs directory not found: {docs_dir}")

    if llm_provider.embedding_provider != "gemini":
        raise SystemExit("STOP: Expected Gemini embedding provider.")

    if llm_provider.embedding_model != "gemini-embedding-001":
        raise SystemExit("STOP: Unexpected embedding model.")

    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key
    )

    info = client.get_collection(collection)

    vector_config = info.config.params.vectors
    if vector_config.size != 3072:
        raise SystemExit(
            f"STOP: Expected 3072 dimensions, found {vector_config.size}."
        )

    chunks = MarkdownProcessor(str(docs_dir)).process_all()
    if len(chunks) != 95:
        raise SystemExit(
            f"STOP: Expected 95 chunks, found {len(chunks)}. "
            "Do not upload until chunk count is investigated."
        )

    expected = []
    for i, chunk in enumerate(chunks):
        point_id = int(
            hashlib.md5(
                f"{chunk['file']}_{chunk['chunk_index']}_{i}".encode()
            ).hexdigest()[:15],
            16
        )
        expected.append((point_id, chunk))

    existing_ids = set()
    offset = None

    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=100,
            offset=offset,
            with_payload=False,
            with_vectors=False
        )
        existing_ids.update(point.id for point in points)
        if offset is None:
            break

    expected_ids = {point_id for point_id, _ in expected}
    unexpected = existing_ids - expected_ids
    if unexpected:
        raise SystemExit(
            f"STOP: Found {len(unexpected)} unexpected existing IDs."
        )

    missing = [
        (point_id, chunk)
        for point_id, chunk in expected
        if point_id not in existing_ids
    ]

    print(f"Documents directory: {docs_dir}")
    print(f"Expected chunks: {len(chunks)}")
    print(f"Existing points: {len(existing_ids)}")
    print(f"Missing points: {len(missing)}")

    if not missing:
        print("Nothing to upload.")
        return

    if input("Type UPLOAD to upload only missing points: ").strip() != "UPLOAD":
        print("Cancelled. No points uploaded.")
        return

    uploaded = 0
    failed = []

    for point_id, chunk in missing:
        success = False

        for attempt in range(1, 4):
            try:
                embeddings = llm_provider.generate_embeddings([chunk["text"]])
                if len(embeddings) != 1 or len(embeddings[0]) != 3072:
                    raise ValueError("Unexpected embedding count or dimension.")

                point = PointStruct(
                    id=point_id,
                    vector=embeddings[0],
                    payload={
                        "text": chunk["text"],
                        "module": chunk["module"],
                        "chapter": chunk["chapter"],
                        "section": chunk["section"],
                        "url": chunk["url"],
                        "file": chunk["file"],
                        "chunk_index": chunk["chunk_index"]
                    }
                )

                client.upsert(collection_name=collection, points=[point])
                uploaded += 1
                success = True
                print(f"Uploaded {uploaded}/{len(missing)}: {chunk['file']} #{chunk['chunk_index']}")
                time.sleep(1)
                break

            except Exception as exc:
                print(
                    f"Attempt {attempt}/3 failed for "
                    f"{chunk['file']} #{chunk['chunk_index']}: "
                    f"{type(exc).__name__}: {str(exc)[:200]}"
                )
                if attempt < 3:
                    time.sleep(2 ** attempt)

        if not success:
            failed.append(point_id)
            print("Stopping after repeated failure to avoid excessive API requests.")
            break

    final_info = client.get_collection(collection)

    final_ids = set()
    offset = None

    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=100,
            offset=offset,
            with_payload=False,
            with_vectors=False
        )
        final_ids.update(point.id for point in points)
        if offset is None:
            break

    missing_after = expected_ids - final_ids
    unexpected_after = final_ids - expected_ids

    print("\n=== Resume summary ===")
    print("Uploaded during this run:", uploaded)
    print("Unresolved IDs:", len(failed))
    print("Final Qdrant point count:", final_info.points_count)
    print("Expected final count: 95")
    print("Missing expected IDs:", len(missing_after))
    print("Unexpected IDs:", len(unexpected_after))

    if len(final_ids) == 95 and not missing_after and not unexpected_after and not failed:
        print("PASS: All 95 expected IDs are present.")
    else:
        print("INCOMPLETE: Verify missing IDs before retrying.")


if __name__ == "__main__":
    main()



