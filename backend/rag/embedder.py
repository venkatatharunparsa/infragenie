"""
Text Embedder
Converts raw text into dense vector embeddings using the Google Gemini
embedding model for storage in ChromaDB.
"""

import os
from typing import List

import google.generativeai as genai


def embed_text(text: str, task_type: str = "retrieval_document") -> List[float]:
    """
    Generate a vector embedding for the given text using Gemini.

    Parameters
    ----------
    text : str
        The text to embed.
    task_type : str
        Gemini embedding task type. Use ``"retrieval_document"`` when indexing
        and ``"retrieval_query"`` when searching.

    Returns
    -------
    List[float]
        A dense embedding vector.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY is not set.")

    genai.configure(api_key=api_key)
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type=task_type,
    )
    return result["embedding"]


def embed_batch(texts: List[str], task_type: str = "retrieval_document") -> List[List[float]]:
    """Embed a batch of texts."""
    return [embed_text(t, task_type) for t in texts]
