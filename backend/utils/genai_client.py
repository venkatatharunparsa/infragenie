import logging
import os
from typing import Any, Optional
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class GenAIClientPool:
    """
    Manages multiple Gemini API keys and provides a unified client.
    Automatically falls back to a secondary key if the primary fails.
    """

    def __init__(self, primary_key: str, fallback_key: Optional[str] = None):
        api_keys = [
            primary_key,
            os.getenv("GEMINI_API_KEY_2", ""),
            os.getenv("GEMINI_API_KEY_FALLBACK", ""),
            fallback_key or "",
        ]
        self.api_keys = []
        for key in api_keys:
            if key and key != "placeholder" and key not in self.api_keys:
                self.api_keys.append(key)
        self.current_key_index = 0

        self.primary_key = self.api_keys[0] if self.api_keys else primary_key
        self.fallback_key = self.api_keys[1] if len(self.api_keys) > 1 else fallback_key

        self.clients = [genai.Client(api_key=key) for key in self.api_keys]
        self.primary_client = self.clients[0] if self.clients else genai.Client(api_key=primary_key)
        self.fallback_client = self.clients[1] if len(self.clients) > 1 else None

        self.use_fallback = False

    def get_client(self) -> genai.Client:
        """Returns the currently active client."""
        if self.clients:
            return self.clients[self.current_key_index]
        if self.use_fallback and self.fallback_client:
            return self.fallback_client
        return self.primary_client

    def _switch_to_next_key(self) -> bool:
        """Switch to the next configured API key, if one is available."""
        if self.current_key_index + 1 >= len(self.clients):
            return False
        self.current_key_index += 1
        self.use_fallback = self.current_key_index > 0
        logger.warning("[GenAIClientPool] Switching to Gemini API key index %d.", self.current_key_index)
        return True

    async def execute_with_fallback(self, func_name: str, *args, **kwargs) -> Any:
        """
        Executes a client method (e.g., 'models.generate_content') with retry/fallback logic.
        """
        client = self.get_client()
        
        # Resolve the method (e.g., client.models.generate_content)
        parts = func_name.split('.')
        method = client
        for part in parts:
            method = getattr(method, part)

        try:
            return await method(*args, **kwargs)
        except Exception as exc:
            # Check if it's a quota or auth error
            error_msg = str(exc).lower()
            is_retryable = any(term in error_msg for term in ["429", "quota", "exhausted", "401", "unauthorized", "api_key_invalid"])
            
            if is_retryable and self._switch_to_next_key():
                logger.warning(f"[GenAIClientPool] Current key failed ({exc}). Retrying with next key.")
                return await self.execute_with_fallback(func_name, *args, **kwargs)
            else:
                logger.error(f"[GenAIClientPool] API call failed: {exc}")
                raise

    def generate_content(self, model: str, contents: Any, **kwargs):
        """Synchronous wrapper for generate_content with fallback."""
        client = self.get_client()
        try:
            return client.models.generate_content(model=model, contents=contents, **kwargs)
        except Exception as exc:
            if self._switch_to_next_key():
                logger.warning("[GenAIClientPool] Current key failed during generation. Retrying with next key.")
                return self.get_client().models.generate_content(model=model, contents=contents, **kwargs)
            raise

    def embed_content(self, model: str, contents: Any, config: Optional[dict] = None):
        """Synchronous wrapper for embed_content with fallback."""
        client = self.get_client()
        try:
            return client.models.embed_content(model=model, contents=contents, config=config)
        except Exception as exc:
            if self._switch_to_next_key():
                logger.warning("[GenAIClientPool] Current key failed during embedding. Retrying with next key.")
                return self.get_client().models.embed_content(model=model, contents=contents, config=config)
            raise

    @staticmethod
    def extract_text(response: Any) -> str:
        """Extract model-generated text from a Gemini response object."""
        if response is None:
            return ""

        if isinstance(response, str):
            return response.strip()

        text_parts = []

        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", []) or []:
                if getattr(part, "text", None):
                    text_parts.append(part.text)

        if text_parts:
            return "".join(text_parts).strip()

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, str):
            return parsed.strip()

        raw_text = getattr(response, "text", None)
        if isinstance(raw_text, str):
            return raw_text.strip()

        return ""
