"""
Temporal Decay — Auto-archives stale entities and reinforces active ones.

Neuroscience parallel: Memories that aren't recalled fade. Memories that are
frequently accessed get strengthened. This is Hebbian learning applied to
the knowledge graph.

Mechanism:
1. Track last_accessed and access_count per entity (in frontmatter)
2. Entities not referenced in N days → moved to archive/
3. Entities accessed frequently → boosted in recall ranking
4. Graph triplets involving archived entities → marked stale
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from pathlib import Path


@dataclass
class DecayConfig:
    archive_after_days: int = 30       # Archive if not referenced in N days
    stale_warning_days: int = 14       # Warn about entities going stale
    min_timeline_entries: int = 1      # Don't archive entities with many entries
    protected_types: list[str] = None  # Entity types that never decay

    def __post_init__(self):
        if self.protected_types is None:
            self.protected_types = ["project", "tool"]  # Active things shouldn't decay


@dataclass
class EntityHealth:
    """Health status of an entity."""
    name: str
    file: Path
    entity_type: str
    last_referenced: date | None  # Most recent date in timeline
    timeline_entries: int
    days_stale: int              # Days since last reference
    status: str                  # "active" | "stale" | "archive_candidate"
    access_count: int = 0


def parse_last_date(content: str) -> date | None:
    """Extract the most recent date from timeline entries."""
    dates = re.findall(r'### \[\[(\d{4}-\d{2}-\d{2})\]\]', content)
    if not dates:
        return None
    return date.fromisoformat(max(dates))


def parse_entity_type(content: str) -> str:
    """Extract entity type from frontmatter."""
    match = re.search(r'\*\*Type:\*\*\s*(\w+)', content)
    return match.group(1) if match else "unknown"


def get_access_count(content: str) -> int:
    """Extract access count from frontmatter (if tracked)."""
    match = re.search(r'\*\*Accessed:\*\*\s*(\d+)', content)
    return int(match.group(1)) if match else 0


def increment_access(entity_path: Path):
    """Increment access counter on an entity file."""
    if not entity_path.exists():
        return
    
    content = entity_path.read_text()
    count = get_access_count(content)
    
    if "**Accessed:**" in content:
        content = re.sub(r'\*\*Accessed:\*\*\s*\d+', f'**Accessed:** {count + 1}', content)
    else:
        # Add after Type line
        content = re.sub(
            r'(\*\*Type:\*\*.*)',
            rf'\1\n**Accessed:** {count + 1}',
            content,
            count=1
        )
    
    entity_path.write_text(content)


def scan_health(entities_dir: Path, config: DecayConfig | None = None) -> list[EntityHealth]:
    """Scan all entities and assess their health."""
    if config is None:
        config = DecayConfig()
    
    today = date.today()
    results = []
    
    for f in sorted(entities_dir.glob("*.md")):
        content = f.read_text()
        entity_type = parse_entity_type(content)
        last_ref = parse_last_date(content)
        timeline_entries = len(re.findall(r'### \[\[', content))
        access_count = get_access_count(content)
        
        if last_ref:
            days_stale = (today - last_ref).days
        else:
            days_stale = 999  # No dates = very stale
        
        # Determine status
        if entity_type in config.protected_types:
            status = "protected"
        elif days_stale >= config.archive_after_days:
            status = "archive_candidate"
        elif days_stale >= config.stale_warning_days:
            status = "stale"
        else:
            status = "active"
        
        results.append(EntityHealth(
            name=f.stem.replace('-', ' '),
            file=f,
            entity_type=entity_type,
            last_referenced=last_ref,
            timeline_entries=timeline_entries,
            days_stale=days_stale,
            status=status,
            access_count=access_count,
        ))
    
    return results


def run_decay(entities_dir: Path, graph_file: Path | None = None,
              config: DecayConfig | None = None,
              dry_run: bool = True) -> list[str]:
    """
    Run the decay cycle.
    
    1. Scan entities for staleness
    2. Archive entities past the threshold
    3. Mark graph triplets as stale
    
    Returns list of actions taken.
    """
    if config is None:
        config = DecayConfig()
    
    archive_dir = entities_dir / "archive"
    health = scan_health(entities_dir, config)
    actions = []
    
    # Report
    active = [e for e in health if e.status == "active"]
    stale = [e for e in health if e.status == "stale"]
    candidates = [e for e in health if e.status == "archive_candidate"]
    protected = [e for e in health if e.status == "protected"]
    
    actions.append(f"📊 Health scan: {len(active)} active, {len(stale)} stale, "
                   f"{len(candidates)} archive candidates, {len(protected)} protected")
    
    # Warn about stale entities
    for e in stale:
        actions.append(f"⚠️ Stale ({e.days_stale}d): {e.name} ({e.entity_type})")
    
    # Archive candidates
    for e in candidates:
        if e.timeline_entries > config.min_timeline_entries:
            # Rich entities get a longer grace period
            if e.days_stale < config.archive_after_days * 2:
                actions.append(f"⏳ Grace period: {e.name} ({e.timeline_entries} entries, {e.days_stale}d stale)")
                continue
        
        if dry_run:
            actions.append(f"🗄️ Would archive: {e.name} ({e.days_stale}d stale)")
        else:
            archive_dir.mkdir(exist_ok=True)
            dest = archive_dir / e.file.name
            shutil.move(str(e.file), str(dest))
            actions.append(f"🗄️ Archived: {e.name} → archive/")
            
            # Mark graph triplets as stale
            if graph_file and graph_file.exists():
                _mark_graph_stale(graph_file, e.name)
    
    if not stale and not candidates:
        actions.append("✅ All entities healthy")
    
    return actions


def _mark_graph_stale(graph_file: Path, entity_name: str):
    """Mark graph triplets involving an archived entity."""
    lines = graph_file.read_text().strip().split('\n')
    updated = []
    
    for line in lines:
        if not line:
            continue
        try:
            t = json.loads(line)
            name_lower = entity_name.lower()
            if (t.get("subject", "").lower() == name_lower or 
                t.get("object", "").lower() == name_lower):
                t["stale"] = True
                t["archived_at"] = datetime.now().isoformat()
            updated.append(json.dumps(t))
        except:
            updated.append(line)
    
    graph_file.write_text('\n'.join(updated) + '\n')


def restore_entity(entities_dir: Path, entity_name: str) -> str:
    """Restore an archived entity."""
    archive_dir = entities_dir / "archive"
    
    # Find the file
    from .core import sanitize_filename
    filename = sanitize_filename(entity_name) + ".md"
    archived = archive_dir / filename
    
    if not archived.exists():
        # Try fuzzy match
        candidates = list(archive_dir.glob("*.md"))
        matches = [c for c in candidates if entity_name.lower() in c.stem.lower()]
        if matches:
            archived = matches[0]
        else:
            return f"Entity '{entity_name}' not found in archive"
    
    # Move back
    dest = entities_dir / archived.name
    shutil.move(str(archived), str(dest))
    
    return f"Restored: {archived.stem} from archive"
