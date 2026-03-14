"""Inbox: Quick-capture with immediate tagging, deferred processing.

Biological memory model:
- Encoding happens at event time (add to inbox)
- Tagging for importance in realtime
- Consolidation during idle (process inbox)
- Retrieval strengthens memory
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, Literal
import json

ImportanceLevel = Literal["high", "medium", "low"]


def add_to_inbox(
    memory_dir: Path,
    event: str,
    importance: ImportanceLevel = "medium",
    source: Optional[str] = None,
    topics: Optional[list[str]] = None,
) -> str:
    """Add an event to inbox.md for later processing.
    
    Fast, low overhead. Deferred extraction during nightly cycle.
    
    Args:
        memory_dir: Path to memory/ directory
        event: The event/fact to capture
        importance: high, medium, or low
        source: Where this came from (e.g., "email", "interview", "discord")
        topics: Optional topic tags for context-aware injection
        
    Returns:
        Confirmation message
    """
    inbox_path = memory_dir / "inbox.md"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Format importance tag
    tag = {"high": "[HIGH]", "medium": "[MED]", "low": "[LOW]"}[importance]
    
    # Build line
    line = f"- [ ] {timestamp} {tag} {event}"
    if source:
        line += f" (via {source})"
    if topics:
        line += f" #{' #'.join(topics)}"
    line += "\n"
    
    # Append to inbox
    if not inbox_path.exists():
        inbox_path.write_text("# Inbox — Quick Capture\n\n> Process with: garden inbox --process\n\n")
    
    with open(inbox_path, "a") as f:
        f.write(line)
    
    return f"Added to inbox: {event[:50]}..."


def list_inbox(memory_dir: Path, unprocessed_only: bool = True) -> list[dict]:
    """List inbox items.
    
    Args:
        memory_dir: Path to memory/ directory
        unprocessed_only: Only return unchecked items
        
    Returns:
        List of inbox items
    """
    inbox_path = memory_dir / "inbox.md"
    
    if not inbox_path.exists():
        return []
    
    items = []
    for line in inbox_path.read_text().split("\n"):
        if not line.startswith("- ["):
            continue
            
        checked = line.startswith("- [x]")
        if unprocessed_only and checked:
            continue
            
        # Parse line
        parts = line[6:].strip()  # Remove "- [ ] " or "- [x] "
        
        # Extract importance
        importance = "medium"
        for tag, level in [("[HIGH]", "high"), ("[MED]", "medium"), ("[LOW]", "low")]:
            if tag in parts:
                importance = level
                parts = parts.replace(tag, "").strip()
                break
        
        # Extract timestamp (first 16 chars: YYYY-MM-DD HH:MM)
        timestamp = parts[:16] if len(parts) > 16 else None
        text = parts[17:] if timestamp else parts
        
        # Extract source
        source = None
        if "(via " in text:
            source_start = text.rfind("(via ")
            source_end = text.rfind(")", source_start)
            if source_end > source_start:
                source = text[source_start + 5:source_end]
                text = text[:source_start].strip() + text[source_end + 1:].strip()
        
        # Extract topics
        topics = []
        while " #" in text:
            hash_pos = text.rfind(" #")
            topic = text[hash_pos + 2:].split()[0]
            topics.insert(0, topic)
            text = text[:hash_pos]
        
        items.append({
            "text": text.strip(),
            "importance": importance,
            "timestamp": timestamp,
            "source": source,
            "topics": topics,
            "processed": checked,
        })
    
    return items


def process_inbox(memory_dir: Path, extract_fn: callable = None) -> dict:
    """Process inbox items, running extraction on high-importance items.
    
    Args:
        memory_dir: Path to memory/ directory
        extract_fn: Optional extraction function to call for each item
        
    Returns:
        Processing statistics
    """
    inbox_path = memory_dir / "inbox.md"
    
    if not inbox_path.exists():
        return {"processed": 0, "skipped": 0}
    
    items = list_inbox(memory_dir, unprocessed_only=True)
    
    processed = 0
    skipped = 0
    
    for item in items:
        if item["importance"] == "high" and extract_fn:
            # Run extraction immediately for high-importance items
            try:
                extract_fn(item["text"], source=item.get("source"))
                processed += 1
            except Exception as e:
                print(f"  ⚠ Failed to extract: {e}")
                skipped += 1
        else:
            # Mark as ready for batch processing
            processed += 1
    
    # Mark all items as processed
    content = inbox_path.read_text()
    content = content.replace("- [ ]", "- [x]")
    inbox_path.write_text(content)
    
    return {
        "processed": processed,
        "skipped": skipped,
        "total": len(items),
    }


def clear_processed(memory_dir: Path) -> int:
    """Remove processed items from inbox.
    
    Args:
        memory_dir: Path to memory/ directory
        
    Returns:
        Number of items cleared
    """
    inbox_path = memory_dir / "inbox.md"
    
    if not inbox_path.exists():
        return 0
    
    lines = inbox_path.read_text().split("\n")
    new_lines = []
    cleared = 0
    
    for line in lines:
        if line.startswith("- [x]"):
            cleared += 1
        else:
            new_lines.append(line)
    
    inbox_path.write_text("\n".join(new_lines))
    return cleared
