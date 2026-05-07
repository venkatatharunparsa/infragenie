import os
import sys
import asyncio
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

load_dotenv()

from rag.chroma_client import ChromaRAGClient
from rag.knowledge_loader import KnowledgeLoader

async def main():
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("Error: GEMINI_API_KEY not found in environment.")
        return

    persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    
    print(f"Initializing ChromaRAGClient with persist_dir: {persist_dir}")
    rag_client = ChromaRAGClient(persist_dir, gemini_key)
    
    loader = KnowledgeLoader(rag_client, "./knowledge")
    
    print("Starting knowledge base population (embedding generation)...")
    await loader.load_all()
    print("Success: Knowledge base populated!")

if __name__ == "__main__":
    asyncio.run(main())
