"""
Embedding service for generating embeddings using configured provider.
"""
import os
from typing import List
import logging
from app.services.llm_provider import llm_provider

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service for generating text embeddings using configured provider.
    """

    def __init__(self):
        """Initialize embedding service."""
        self.provider = llm_provider

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        """
        try:
            return self.provider.generate_embedding(text)
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        """
        try:
            return self.provider.generate_embeddings(texts)
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            raise


# Global service instance
embedding_service = EmbeddingService()
