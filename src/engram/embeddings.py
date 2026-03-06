#!/usr/bin/env python3
"""
Embedding-based semantic search for MindGardener.

Enables associative recall by finding semantically similar facts,
not just keyword matches.
"""

import json
import os
from pathlib import Path
from typing import Optional
import urllib.request

# Try to import numpy, but make it optional
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def get_embedding_gemini(text: str, api_key: str) -> list[float]:
    """Get embedding from Gemini API."""
    url = "https://generativelanguage.googleapis.com/v1beta/models/embedding-001:embedContent"
    
    payload = json.dumps({
        "model": "models/embedding-001",
        "content": {"parts": [{"text": text}]}
    }).encode()
    
    req = urllib.request.Request(
        f"{url}?key={api_key}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
        return result.get("embedding", {}).get("values", [])


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if HAS_NUMPY:
        a_np = np.array(a)
        b_np = np.array(b)
        return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np)))
    else:
        # Pure Python fallback
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


class EmbeddingIndex:
    """Simple embedding index stored as JSON."""
    
    def __init__(self, index_path: Path):
        self.index_path = index_path
        self.embeddings = {}  # fact_key -> embedding
        self._load()
    
    def _load(self):
        if self.index_path.exists():
            try:
                self.embeddings = json.loads(self.index_path.read_text())
            except:
                self.embeddings = {}
    
    def _save(self):
        self.index_path.write_text(json.dumps(self.embeddings))
    
    def _fact_key(self, fact: dict) -> str:
        """Generate unique key for a fact."""
        return f"{fact.get('subject')}|{fact.get('predicate')}|{fact.get('object')}"
    
    def add(self, fact: dict, embedding: list[float]):
        """Add embedding for a fact."""
        key = self._fact_key(fact)
        self.embeddings[key] = {
            "embedding": embedding,
            "fact": fact,
        }
        self._save()
    
    def search(self, query_embedding: list[float], limit: int = 10) -> list[tuple[dict, float]]:
        """Find most similar facts to query."""
        if not self.embeddings:
            return []
        
        results = []
        for key, data in self.embeddings.items():
            emb = data.get("embedding", [])
            if not emb:
                continue
            sim = cosine_similarity(query_embedding, emb)
            results.append((data.get("fact", {}), sim))
        
        # Sort by similarity (highest first)
        results.sort(key=lambda x: -x[1])
        return results[:limit]
    
    def has(self, fact: dict) -> bool:
        """Check if fact is already indexed."""
        return self._fact_key(fact) in self.embeddings


def build_embedding_index(
    graph_file: Path,
    index_path: Path,
    api_key: Optional[str] = None,
    force: bool = False,
) -> int:
    """Build embedding index for all facts in graph."""
    if api_key is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
    
    if not api_key:
        print("⚠️ No GEMINI_API_KEY set, skipping embedding index")
        return 0
    
    if not graph_file.exists():
        return 0
    
    index = EmbeddingIndex(index_path)
    added = 0
    
    for line in graph_file.read_text().strip().split('\n'):
        if not line:
            continue
        try:
            fact = json.loads(line)
            
            if not force and index.has(fact):
                continue
            
            # Create text representation for embedding
            text = f"{fact.get('subject')} {fact.get('predicate')} {fact.get('object')}"
            if fact.get('detail'):
                text += f" ({fact.get('detail')})"
            
            # Get embedding
            embedding = get_embedding_gemini(text, api_key)
            if embedding:
                index.add(fact, embedding)
                added += 1
                
        except Exception as e:
            print(f"⚠️ Failed to embed fact: {e}")
            continue
    
    return added


def semantic_search(
    query: str,
    index_path: Path,
    api_key: Optional[str] = None,
    limit: int = 10,
) -> list[tuple[dict, float]]:
    """Search for facts semantically similar to query."""
    if api_key is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
    
    if not api_key:
        return []
    
    if not index_path.exists():
        return []
    
    # Get query embedding
    query_embedding = get_embedding_gemini(query, api_key)
    if not query_embedding:
        return []
    
    # Search index
    index = EmbeddingIndex(index_path)
    return index.search(query_embedding, limit)
