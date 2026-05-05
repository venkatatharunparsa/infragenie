"""
InfraGenie RAG (Retrieval-Augmented Generation) Package
Provides vector-store access, text embedding, and knowledge-base loading
utilities used by all agents to ground LLM responses in verified facts.
"""

from .chroma_client import ChromaRAGClient
from .embedder import embed_text
from .knowledge_loader import KnowledgeLoader

__all__ = ["ChromaRAGClient", "embed_text", "KnowledgeLoader"]
