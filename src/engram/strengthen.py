"""Retrieval Strengthening: Memory access tracking.

Each retrieval strengthens the accessed memory, mimicking biological
"retrieval practice effect". Entities with high access count become
"core" to identity. Those with low access after grace period decay.

Formula:
  importance = access_count × 0.5 + recency × 0.3 + initial_tag × 0.2

Grace period: 7 days before decay kicks in for new entities.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


def load_access_log(memory_dir: Path) -> dict:
    """Load entity access log."""
    log_path = memory_dir / "access-log.jsonl"
    
    if not log_path.exists():
        return {}
    
    access_counts = {}
    last_access = {}
    
    for line in log_path.read_text().strip().split("\n"):
        if not line:
            continue
        entry = json.loads(line)
        entity = entry["entity"]
        access_counts[entity] = access_counts.get(entity, 0) + 1
        last_access[entity] = entry["timestamp"]
    
    return {
        "counts": access_counts,
        "last_access": last_access,
    }


def record_access(memory_dir: Path, entity: str, query: Optional[str] = None) -> None:
    """Record an entity access (called on memory_search match)."""
    log_path = memory_dir / "access-log.jsonl"
    
    entry = {
        "entity": entity,
        "timestamp": datetime.now().isoformat(),
        "query": query,
    }
    
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def calculate_importance(
    entity: str,
    access_data: dict,
    created_date: Optional[str] = None,
    initial_importance: str = "medium",
) -> float:
    """Calculate entity importance score.
    
    Formula: importance = access × 0.5 + recency × 0.3 + initial_tag × 0.2
    
    Grace period: New entities (< 7 days) get boosted recency score.
    """
    counts = access_data.get("counts", {})
    last_access = access_data.get("last_access", {})
    
    # Access count component (normalized, capped at 20)
    access_count = min(counts.get(entity, 0), 20) / 20.0
    
    # Recency component
    recency = 0.0
    if entity in last_access:
        last = datetime.fromisoformat(last_access[entity])
        days_ago = (datetime.now() - last).days
        recency = max(0, 1.0 - (days_ago / 30.0))  # Decay over 30 days
    
    # Grace period for new entities
    if created_date:
        created = datetime.fromisoformat(created_date)
        age_days = (datetime.now() - created).days
        if age_days < 7:
            # Boost recency for new entities
            recency = max(recency, 0.8)
    
    # Initial tag component
    tag_scores = {"high": 1.0, "medium": 0.5, "low": 0.2}
    initial_score = tag_scores.get(initial_importance, 0.5)
    
    # Combined score
    importance = (access_count * 0.5) + (recency * 0.3) + (initial_score * 0.2)
    
    return round(importance, 3)


def get_prune_candidates(
    entities_dir: Path,
    memory_dir: Path,
    threshold: float = 0.1,
    min_age_days: int = 30,
) -> list[dict]:
    """Find entities that should be pruned due to low importance.
    
    Criteria:
    - Age > min_age_days (grace period)
    - Importance score < threshold
    - Access count = 0 (never queried)
    """
    access_data = load_access_log(memory_dir)
    candidates = []
    
    for entity_file in entities_dir.glob("*.md"):
        entity_name = entity_file.stem
        
        # Skip recently created
        created = datetime.fromtimestamp(entity_file.stat().st_ctime)
        age_days = (datetime.now() - created).days
        if age_days < min_age_days:
            continue
        
        # Calculate importance
        importance = calculate_importance(
            entity_name,
            access_data,
            created_date=created.isoformat(),
        )
        
        access_count = access_data.get("counts", {}).get(entity_name, 0)
        
        if importance < threshold and access_count == 0:
            candidates.append({
                "entity": entity_name,
                "importance": importance,
                "access_count": access_count,
                "age_days": age_days,
                "file": str(entity_file),
            })
    
    return sorted(candidates, key=lambda x: x["importance"])


def get_core_entities(
    entities_dir: Path,
    memory_dir: Path,
    top_n: int = 10,
) -> list[dict]:
    """Find the most important "core" entities.
    
    These are entities with highest importance scores,
    representing stable identity components.
    """
    access_data = load_access_log(memory_dir)
    entities = []
    
    for entity_file in entities_dir.glob("*.md"):
        entity_name = entity_file.stem
        
        created = datetime.fromtimestamp(entity_file.stat().st_ctime)
        importance = calculate_importance(
            entity_name,
            access_data,
            created_date=created.isoformat(),
        )
        
        access_count = access_data.get("counts", {}).get(entity_name, 0)
        
        entities.append({
            "entity": entity_name,
            "importance": importance,
            "access_count": access_count,
        })
    
    return sorted(entities, key=lambda x: -x["importance"])[:top_n]
