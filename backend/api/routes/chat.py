# """
# RAG Chatbot API Routes (+50 points)
# Multi-provider: Gemini (primary), Groq, OpenAI
# """
# from fastapi import APIRouter, HTTPException
# from pydantic import BaseModel
# from typing import List, Optional
# import os
# import time
# from qdrant_client import QdrantClient
# from qdrant_client.models import Filter, FieldCondition, MatchValue
# from app.config import settings
# from app.services.llm_provider import llm_provider

# router = APIRouter()

# # Initialize Qdrant client
# qdrant_client = QdrantClient(
#     url=os.getenv("QDRANT_URL"),
#     api_key=os.getenv("QDRANT_API_KEY")
# )

# COLLECTION_NAME = settings.qdrant_collection_name


# class ChatQuery(BaseModel):
#     query: str
#     user_id: Optional[int] = None
#     selected_text: Optional[str] = None
#     module_filter: Optional[str] = None


# class Source(BaseModel):
#     module: str
#     chapter: str
#     section: Optional[str] = None
#     url: str
#     relevance_score: float


# class ChatResponse(BaseModel):
#     answer: str
#     sources: List[Source]
#     conversation_id: str
#     processing_time: int
#     timestamp: str


# @router.post("/query", response_model=ChatResponse)
# async def chat_query(query: ChatQuery):
#     """
#     RAG Chatbot Endpoint
#     - Embeds user query using configured embedding provider
#     - Searches Qdrant for relevant chunks
#     - Generates answer using configured chat provider
#     """
#     start_time = time.time()

#     try:
#         # Step 1: Generate embedding for the query
#         query_text = query.selected_text or query.query
#         query_embedding = llm_provider.generate_embedding(query_text)

#         # Step 2: Search Qdrant for relevant chunks
#         search_filter = None
#         if query.module_filter:
#             search_filter = Filter(
#                 must=[
#                     FieldCondition(
#                         key="module",
#                         match=MatchValue(value=query.module_filter)
#                     )
#                 ]
#             )

#         search_results = qdrant_client.search(
#             collection_name=COLLECTION_NAME,
#             query_vector=query_embedding,
#             query_filter=search_filter,
#             limit=5
#         )

#         # Step 3: Build context from retrieved chunks
#         context_parts = []
#         sources = []

#         for idx, result in enumerate(search_results):
#             payload = result.payload or {}
#             context_parts.append(
#                 f"[Source {idx + 1}] ({payload.get('file', payload.get('module', 'unknown'))})\n{payload.get('text', payload.get('content', ''))}\n"
#             )

#             sources.append(Source(
#                 module=payload.get('module', 'Unknown'),
#                 chapter=payload.get('chapter', 'Unknown'),
#                 section=payload.get('section'),
#                 url=payload.get('url', '/'),
#                 relevance_score=round(result.score, 3)
#             ))

#         context = "\n".join(context_parts)

#         # Step 4: Generate answer
#         system_prompt = """You are an expert AI assistant for the Physical AI & Humanoid Robotics textbook.

# Your role:
# - Answer questions accurately using ONLY the provided context
# - Cite sources using [Source N] notation
# - If the context doesn't contain the answer, say so clearly
# - Be concise but comprehensive
# - Use technical terminology appropriately

# Format your responses with:
# - Clear explanations
# - Code examples when relevant
# - References to specific modules/chapters"""

#         user_prompt = f"""Context from the textbook:
# {context}

# User Question: {query.query}

# Please provide a detailed answer based ONLY on the context above. Include source citations."""

#         messages = [
#             {"role": "system", "content": system_prompt},
#             {"role": "user", "content": user_prompt}
#         ]

#         answer = llm_provider.generate_chat_completion(messages, temperature=0.3, max_tokens=1600)

#         print("RAW ANSWER:", repr(answer), flush=True)
#         # print("UTF8 BYTES:", answer.encode("utf-8"))
#         # print("JSON CHECK:", repr(ChatResponse(
#         #     answer=answer,
#         #     sources=sources,
#         #     conversation_id="diagnostic",
#         #     processing_time=0,
#         #     timestamp="diagnostic"
#         # ).model_dump_json()))

#         # Calculate processing time
#         processing_time = int((time.time() - start_time) * 1000)

#         return ChatResponse(
#             answer=answer,
#             sources=sources,
#             conversation_id=f"conv_{int(time.time())}",
#             processing_time=processing_time,
#             timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
#         )

#     except HTTPException:
#         raise
#     except Exception as e:
#         print(f"RAG Error: {str(e)}")
#         raise HTTPException(
#             status_code=500,
#             detail=f"RAG processing error: {str(e)}"
#         )


# @router.get("/health")
# async def health_check():
#     """
#     Check if RAG system is operational
#     """
#     try:
#         provider_info = {
#             "ai_provider": llm_provider.provider,
#             "chat_model": llm_provider.chat_model,
#             "embedding_provider": llm_provider.embedding_provider,
#             "embedding_model": llm_provider.embedding_model
#         }

#         # Check API keys
#         key_status = {
#             "gemini": "configured" if os.getenv("GEMINI_API_KEY") else "missing",
#             "groq": "configured" if os.getenv("GROQ_API_KEY") else "missing",
#             "openai": "configured" if os.getenv("OPENAI_API_KEY") else "missing",
#         }

#         # Check Qdrant
#         try:
#             collections = qdrant_client.get_collections()
#             qdrant_status = "connected"
#             collection_exists = any(c.name == COLLECTION_NAME for c in collections.collections)
#             collection_info = {}
#             if collection_exists:
#                 try:
#                     info = qdrant_client.get_collection(COLLECTION_NAME)
#                     collection_info = {
#                         "vectors_count": getattr(info, 'vectors_count', None) or getattr(info, 'points_count', None),
#                         "status": str(getattr(info, 'status', 'unknown'))
#                     }
#                 except:
#                     pass
#         except Exception as e:
#             qdrant_status = "disconnected"
#             collection_exists = False
#             collection_info = {"error": str(e)[:100]}

#         return {
#             "status": "healthy" if collection_exists and qdrant_status == "connected" else "degraded",
#             "provider": provider_info,
#             "api_keys": key_status,
#             "services": {
#                 "qdrant": qdrant_status,
#                 "collection_exists": collection_exists,
#                 "collection_name": COLLECTION_NAME,
#                 "collection_info": collection_info
#             }
#         }
#     except Exception as e:
#         return {
#             "status": "unhealthy",
#             "error": str(e)
#         }


# @router.get("/history/{user_id}")
# async def get_chat_history(user_id: int, limit: int = 10):
#     """Get chat history for a user (Future: implement with database)"""
#     return {
#         "user_id": user_id,
#         "messages": [],
#         "note": "Chat history feature will be implemented in Phase 2"
#     }


"""
RAG Chatbot API Routes (+50 points)
Multi-provider: Gemini (primary), Groq, OpenAI
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os
import time
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from app.config import settings
from app.services.llm_provider import llm_provider

router = APIRouter()

# Initialize Qdrant client
qdrant_client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY")
)

COLLECTION_NAME = settings.qdrant_collection_name


class ChatQuery(BaseModel):
    query: str
    user_id: Optional[int] = None
    selected_text: Optional[str] = None
    module_filter: Optional[str] = None


class Source(BaseModel):
    module: str
    chapter: str
    section: Optional[str] = None
    url: str
    relevance_score: float
    source_number: Optional[int] = None


class ChatResponse(BaseModel):
    answer: str
    sources: List[Source]
    conversation_id: str
    processing_time: int
    timestamp: str


@router.post("/query", response_model=ChatResponse)
async def chat_query(query: ChatQuery):
    """
    RAG Chatbot Endpoint
    - Embeds user query using configured embedding provider
    - Searches Qdrant for relevant chunks
    - Generates answer using configured chat provider
    """

    start_time = time.time()

    try:
        # Step 1: Generate embedding for the query
        query_text = query.selected_text or query.query
        query_embedding = llm_provider.generate_embedding(query_text)

        # Step 2: Search Qdrant for relevant chunks
        search_filter = None

        if query.module_filter:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="module",
                        match=MatchValue(value=query.module_filter)
                    )
                ]
            )

        search_results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_embedding,
            query_filter=search_filter,
            limit=5
        )

        # Step 3: Build context and source mapping
        context_parts = []
        sources = []
        source_map = {}

        # Keep all retrieved chunks in the context.
        # Deduplicate only the displayed source links.
        seen_sources = {}

        for idx, result in enumerate(search_results):
            payload = result.payload or {}

            url = payload.get("url", "/")
            module = payload.get("module", "Unknown")
            chapter = payload.get("chapter", "Unknown")
            section = payload.get("section")

            # Each retrieved chunk gets its own citation number.
            source_number = idx + 1

            context_parts.append(
                f"[Source {source_number}] "
                f"({payload.get('file', module)})\n"
                f"{payload.get('text', payload.get('content', ''))}\n"
            )

            # Keep a mapping for each citation number.
            source_map[source_number] = {
                "module": module,
                "chapter": chapter,
                "section": section,
                "url": url,
            }

            # Deduplicate source links by URL.
            # If multiple chunks come from the same URL, keep the
            # highest-ranked occurrence in the displayed sources.
            if url not in seen_sources:
                seen_sources[url] = Source(
                    module=module,
                    chapter=chapter,
                    section=section,
                    url=url,
                    relevance_score=round(result.score, 3),
                    source_number=source_number
                )
            else:
                # Preserve a citation number for the duplicate URL group
                # if none assigned yet (keeps backward compatibility)
                if seen_sources[url].source_number is None:
                    seen_sources[url].source_number = source_number

        context = "\n".join(context_parts)

        # Sources are unique URLs, in relevance order.
        sources = list(seen_sources.values())

        # Step 4: Generate answer
        system_prompt = """You are an expert AI assistant for the Physical AI & Humanoid Robotics textbook.

Your role:
- Answer questions accurately using ONLY the provided context.
- Cite sources using the exact [Source N] labels shown in the context.
- Never invent source numbers.
- If multiple chunks support an answer, cite each relevant source.
- If the context doesn't contain the answer, say so clearly.
- Be concise but comprehensive.
- Use technical terminology appropriately.

Format your responses with:
- Clear explanations.
- Code examples when relevant.
- References to specific modules/chapters.
- Citations such as [Source 1] or [Source 2].

Important:
The source numbers refer to retrieved context chunks, not to the
position of items in the displayed sources list. A single displayed
source URL may correspond to multiple context chunks.
"""

        user_prompt = f"""Context from the textbook:
{context}

User Question: {query.query}

Please provide a detailed answer based ONLY on the context above.
Include accurate citations using the exact [Source N] labels.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        answer = llm_provider.generate_chat_completion(
            messages,
            temperature=0.3,
            max_tokens=1600
        )

        print("RAW ANSWER:", repr(answer), flush=True)

        # Step 5: Calculate processing time
        processing_time = int((time.time() - start_time) * 1000)

        return ChatResponse(
            answer=answer,
            sources=sources,
            conversation_id=f"conv_{int(time.time())}",
            processing_time=processing_time,
            timestamp=time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime()
            )
        )

    except HTTPException:
        raise

    except Exception as e:
        print(f"RAG Error: {str(e)}", flush=True)

        raise HTTPException(
            status_code=500,
            detail=f"RAG processing error: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """
    Check if RAG system is operational.
    """

    try:
        provider_info = {
            "ai_provider": llm_provider.provider,
            "chat_model": llm_provider.chat_model,
            "embedding_provider": llm_provider.embedding_provider,
            "embedding_model": llm_provider.embedding_model
        }

        # Check API keys
        key_status = {
            "gemini": "configured" if os.getenv("GEMINI_API_KEY") else "missing",
            "groq": "configured" if os.getenv("GROQ_API_KEY") else "missing",
            "openai": "configured" if os.getenv("OPENAI_API_KEY") else "missing",
        }

        # Check Qdrant
        try:
            collections = qdrant_client.get_collections()
            qdrant_status = "connected"

            collection_exists = any(
                c.name == COLLECTION_NAME
                for c in collections.collections
            )

            collection_info = {}

            if collection_exists:
                try:
                    info = qdrant_client.get_collection(COLLECTION_NAME)

                    collection_info = {
                        "vectors_count": (
                            getattr(info, "vectors_count", None)
                            or getattr(info, "points_count", None)
                        ),
                        "status": str(
                            getattr(info, "status", "unknown")
                        )
                    }

                except Exception:
                    pass

        except Exception as e:
            qdrant_status = "disconnected"
            collection_exists = False
            collection_info = {"error": str(e)[:100]}

        return {
            "status": (
                "healthy"
                if collection_exists and qdrant_status == "connected"
                else "degraded"
            ),
            "provider": provider_info,
            "api_keys": key_status,
            "services": {
                "qdrant": qdrant_status,
                "collection_exists": collection_exists,
                "collection_name": COLLECTION_NAME,
                "collection_info": collection_info
            }
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@router.get("/history/{user_id}")
async def get_chat_history(user_id: int, limit: int = 10):
    """Get chat history for a user (Future: implement with database)."""

    return {
        "user_id": user_id,
        "messages": [],
        "note": "Chat history feature will be implemented in Phase 2"
    }
