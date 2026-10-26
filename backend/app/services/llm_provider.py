"""
Multi-provider LLM service supporting Gemini (primary), Groq (optional), OpenAI (future/preserve).
Keeps provider logic separate from routes. 
"""
import os
from typing import List, Dict, Any
from dataclasses import dataclass

from fastapi import HTTPException


@dataclass
class ProviderConfig:
    provider: str
    chat_model: str
    embedding_model: str
    embedding_provider: str


class LLMProviderError(Exception):
    pass


class LLMProvider:
    def __init__(self):
        self.provider = os.getenv("AI_PROVIDER", "gemini").lower().strip()
        self.embedding_provider = os.getenv("EMBEDDING_PROVIDER", "gemini").lower().strip()
        if self.provider not in ("gemini", "groq", "openai"):
            raise HTTPException(status_code=500, detail=f"Unsupported AI_PROVIDER: {self.provider}. Use 'gemini', 'groq', or 'openai'.")
        if self.embedding_provider not in ("gemini", "openai"):
            raise HTTPException(status_code=500, detail=f"Unsupported EMBEDDING_PROVIDER: {self.embedding_provider}. Use 'gemini' or 'openai'.")
        self.chat_model = self._get_chat_model()
        self.embedding_model = self._get_embedding_model()
        
    def _get_chat_model(self) -> str:
        provider = self.provider
        if provider == "gemini":
            return os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
        elif provider == "groq":
            return os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()
        elif provider == "openai":
            return os.getenv("OPENAI_MODEL", "gpt-4o").strip()
        return os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    
    def _get_embedding_model(self) -> str:
        provider = self.embedding_provider
        if provider == "gemini":
            return os.getenv("GEMINI_EMBEDDING_MODEL", "text-embedding-004").strip()
        elif provider == "openai":
            return os.getenv("EMBEDDING_MODEL", "text-embedding-3-small").strip()
        return os.getenv("GEMINI_EMBEDDING_MODEL", "text-embedding-004").strip()
    
    def get_chat_client(self):
        provider = self.provider
        if provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise HTTPException(status_code=503, detail="GEMINI_API_KEY (or GOOGLE_API_KEY) is not configured. Set it in the environment (or backend/.env) to enable Gemini chat.")
            from google import genai
            return genai.Client(api_key=api_key)
        elif provider == "groq":
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise HTTPException(status_code=503, detail="GROQ_API_KEY is not configured. Set it in the environment (or backend/.env) to enable Groq chat.")
            from groq import Groq
            return Groq(api_key=api_key)
        elif provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured. Set it in the environment (or backend/.env) to enable OpenAI chat.")
            from openai import OpenAI
            return OpenAI(api_key=api_key)
        else:
            raise HTTPException(status_code=500, detail=f"Unsupported AI_PROVIDER: {provider}")
    
    def get_embedding_client(self):
        provider = self.embedding_provider
        if provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise HTTPException(status_code=503, detail="GEMINI_API_KEY (or GOOGLE_API_KEY) is not configured for embeddings.")
            from google import genai
            return genai.Client(api_key=api_key)
        elif provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured for embeddings.")
            from openai import OpenAI
            return OpenAI(api_key=api_key)
        else:
            raise HTTPException(status_code=500, detail=f"Unsupported embedding provider: {provider}")
    
    def generate_chat_completion(self, messages: List[Dict[str, str]], temperature: float = 0.3, max_tokens: int = 800, **kwargs) -> str:
        provider = self.provider
        try:
            if provider == "gemini":
                api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise HTTPException(status_code=503, detail="GEMINI_API_KEY (or GOOGLE_API_KEY) is not configured.")
                system_msg = ""
                user_parts = []
                for m in messages:
                    role = m.get("role", "")
                    content = m.get("content", "")
                    if role == "system":
                        system_msg = content
                    elif role == "user":
                        user_parts.append(content)
                    elif role == "assistant":
                        user_parts.append(content)
                user_msg = "\n\n".join([p for p in user_parts if p])
                prompt = f"{system_msg}\n\n{user_msg}" if system_msg and user_msg else (system_msg or user_msg)
                if not prompt:
                    raise HTTPException(status_code=400, detail="Empty prompt for Gemini request")
                try:
                    import httpx
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.chat_model}:generateContent"
                    payload = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": float(temperature),
                            "maxOutputTokens": int(max_tokens),
                        }
                    }
                    resp = httpx.post(url, params={"key": api_key}, json=payload, timeout=60)
                    if resp.status_code != 200:
                        err = resp.text
                        if resp.status_code == 404 or "not found" in err.lower():
                            raise HTTPException(status_code=400, detail=f"Gemini model not available: {self.chat_model}. Check GEMINI_MODEL in .env.")
                        if resp.status_code == 429:
                            raise HTTPException(status_code=429, detail="Gemini rate limit exceeded.")
                        raise HTTPException(status_code=500, detail=f"Gemini API error: {resp.status_code}")
                    data = resp.json()
                    try:
                        candidates = data.get("candidates") or []
                        if not candidates:
                            raise HTTPException(status_code=500, detail="Gemini returned no candidates")
                        cand = candidates[0]
                        finish_reason = cand.get("finishReason") or cand.get("finish_reason")
                        content = cand.get("content") or {}
                        parts = content.get("parts") or []
                        if not parts:
                            reason = finish_reason or "unknown"
                            raise HTTPException(status_code=500, detail=f"Gemini returned empty response (finishReason={reason})")
                        text = parts[0].get("text") if isinstance(parts[0], dict) else getattr(parts[0], "text", None)
                    except HTTPException:
                        raise
                    except Exception:
                        raise HTTPException(status_code=500, detail="Gemini returned unexpected response format")
                    if not text:
                        raise HTTPException(status_code=500, detail="Gemini returned empty response")
                    return str(text).strip()
                except HTTPException:
                    raise
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Gemini API error: {type(e).__name__}")
            elif provider == "groq":
                client = self.get_chat_client()
                try:
                    response = client.chat.completions.create(
                        model=self.chat_model,
                        messages=messages,
                        temperature=float(temperature),
                        max_tokens=int(max_tokens),
                        **kwargs
                    )
                except Exception as e:
                    err = str(e)
                    if "model" in err.lower() and ("not found" in err.lower() or "invalid" in err.lower()):
                        raise HTTPException(status_code=400, detail=f"Groq model not available: {self.chat_model}. Check GROQ_MODEL in .env.")
                    raise
                try:
                    return response.choices[0].message.content
                except Exception:
                    raise HTTPException(status_code=500, detail="Groq returned unexpected response format")
            elif provider == "openai":
                client = self.get_chat_client()
                try:
                    response = client.chat.completions.create(
                        model=self.chat_model,
                        messages=messages,
                        temperature=float(temperature),
                        max_tokens=int(max_tokens),
                        **kwargs
                    )
                except Exception as e:
                    err = str(e)
                    if "model" in err.lower() and ("not found" in err.lower() or "does not exist" in err.lower()):
                        raise HTTPException(status_code=400, detail=f"OpenAI model not available: {self.chat_model}. Check OPENAI_MODEL in .env.")
                    if "quota" in err.lower() or "insufficient" in err.lower():
                        raise HTTPException(status_code=429, detail="OpenAI quota/rate limit exceeded.")
                    raise
                try:
                    return response.choices[0].message.content
                except Exception:
                    raise HTTPException(status_code=500, detail="OpenAI returned unexpected response format")
            else:
                raise HTTPException(status_code=500, detail=f"Unsupported provider: {provider}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"{provider} API error: {type(e).__name__}")
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        provider = self.embedding_provider
        try:
            if provider == "gemini":
                api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise HTTPException(status_code=503, detail="GEMINI_API_KEY (or GOOGLE_API_KEY) is not configured for embeddings.")
                import httpx
                embeddings = []
                model = self.embedding_model
                for text in texts:
                    try:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
                        payload = {"content": {"parts": [{"text": text}]}}
                        resp = httpx.post(url, params={"key": api_key}, json=payload, timeout=60)
                        if resp.status_code != 200:
                            err = resp.text
                            if resp.status_code == 404 or "not found" in err.lower():
                                raise HTTPException(status_code=400, detail=f"Gemini embedding model not available: {model}. Check GEMINI_EMBEDDING_MODEL in .env.")
                            raise HTTPException(status_code=500, detail=f"Gemini embedding error: {resp.status_code}")
                        data = resp.json()
                        emb = data.get("embedding", {}).get("values") or data.get("embedding")
                        if not emb:
                            raise HTTPException(status_code=500, detail="Gemini embedding returned unexpected format")
                        embeddings.append(list(emb))
                    except HTTPException:
                        raise
                    except Exception as e:
                        raise HTTPException(status_code=500, detail=f"Gemini embedding error: {type(e).__name__}")
                return embeddings
            elif provider == "openai":
                client = self.get_embedding_client()
                model = self.embedding_model
                try:
                    response = client.embeddings.create(model=model, input=texts)
                    return [item.embedding for item in response.data]
                except Exception as e:
                    err = str(e)
                    if "quota" in err.lower() or "insufficient" in err.lower():
                        raise HTTPException(status_code=429, detail="OpenAI embedding quota/rate limit exceeded.")
                    raise HTTPException(status_code=500, detail=f"OpenAI embedding error: {type(e).__name__}")
            else:
                raise HTTPException(status_code=500, detail=f"Unsupported embedding provider: {provider}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"{provider} embedding error: {type(e).__name__}")

    def generate_embedding(self, text: str) -> List[float]:
        return self.generate_embeddings([text])[0]
    
    def get_embedding_dimension(self) -> int:
        try:
            emb = self.generate_embedding("test")
            if not emb:
                raise HTTPException(status_code=500, detail="Embedding generation returned empty vector; cannot determine dimension")
            return len(emb)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to determine embedding dimension: {type(e).__name__}")


llm_provider = LLMProvider()

