import sys
import os
from types import SimpleNamespace
from unittest.mock import patch

# Add the backend directory to sys.path
sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_citation_numbers_match_retrieved_sources():
    """
    Verify that each [Source N] citation maps to the matching
    retrieved source, including when two sources share a URL.
    """

    fake_results = [
        SimpleNamespace(
            payload={
                "file": "module-1.md",
                "text": "Content from module 1",
                "module": "Module 1",
                "chapter": "Chapter 1",
                "section": "Section 1",
                "url": "/docs/module-1",
            },
            score=0.95,
        ),
        SimpleNamespace(
            payload={
                "file": "module-2.md",
                "text": "Content from module 2",
                "module": "Module 2",
                "chapter": "Chapter 2",
                "section": "Section 2",
                "url": "/docs/shared-page",
            },
            score=0.90,
        ),
        SimpleNamespace(
            payload={
                "file": "module-3.md",
                "text": "Another chunk from module 2",
                "module": "Module 2",
                "chapter": "Chapter 2",
                "section": "Section 3",
                "url": "/docs/shared-page",
            },
            score=0.85,
        ),
    ]

    fake_answer = (
        "Module 1 is about the first topic [Source 1]. "
        "Module 2 covers the second topic [Source 2] "
        "and additional details [Source 3]."
    )

    with (
        patch(
            "api.routes.chat.llm_provider.generate_embedding",
            return_value=[0.1, 0.2, 0.3],
        ),
        patch(
            "api.routes.chat.qdrant_client.search",
            return_value=fake_results,
        ),
        patch(
            "api.routes.chat.llm_provider.generate_chat_completion",
            return_value=fake_answer,
        ),
    ):
        response = client.post(
            "/api/chat/query",
            json={"query": "Explain the retrieved topics"},
        )

    assert response.status_code == 200

    data = response.json()
    sources = data["sources"]

    # Each retrieved chunk should have its own numbered source.
    assert [source["source_number"] for source in sources] == [1, 2, 3]

    # Citation numbers must map to the correct source metadata.
    assert sources[0]["module"] == "Module 1"
    assert sources[0]["url"] == "/docs/module-1"

    assert sources[1]["module"] == "Module 2"
    assert sources[1]["url"] == "/docs/shared-page"

    assert sources[2]["module"] == "Module 2"
    assert sources[2]["section"] == "Section 3"
    assert sources[2]["url"] == "/docs/shared-page"

    # Duplicate URLs must not cause source entries to be merged.
    assert len(sources) == 3
    assert sources[1]["source_number"] != sources[2]["source_number"]

    # The answer should retain the citation labels.
    assert "[Source 1]" in data["answer"]
    assert "[Source 2]" in data["answer"]
    assert "[Source 3]" in data["answer"]

def test_out_of_scope_question_returns_context_limitation():
    """
    Verify that when retrieved context does not answer the question,
    the endpoint returns the provider's context-limitation response.
    """

    fake_results = [
        SimpleNamespace(
            payload={
                "file": "module-1.md",
                "text": "This textbook section explains robot sensors.",
                "module": "Module 1",
                "chapter": "Chapter 1",
                "section": "Sensors",
                "url": "/docs/module-1",
            },
            score=0.80,
        )
    ]

    fake_answer = (
        "The provided textbook context does not contain information "
        "about the capital of France."
    )

    with (
        patch(
            "api.routes.chat.llm_provider.generate_embedding",
            return_value=[0.1, 0.2, 0.3],
        ),
        patch(
            "api.routes.chat.qdrant_client.search",
            return_value=fake_results,
        ),
        patch(
            "api.routes.chat.llm_provider.generate_chat_completion",
            return_value=fake_answer,
        ) as mock_completion,
    ):
        response = client.post(
            "/api/chat/query",
            json={"query": "What is the capital of France?"},
        )

    assert response.status_code == 200
    assert response.json()["answer"] == fake_answer

    # Verify the system prompt instructs the model to stay within context.
    messages = mock_completion.call_args.args[0]
    system_prompt = messages[0]["content"]

    assert "ONLY the provided context" in system_prompt
    assert "context doesn't contain the answer" in system_prompt
