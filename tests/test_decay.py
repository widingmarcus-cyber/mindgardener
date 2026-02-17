"""Tests for the decay/archival module."""

import json
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from engram.decay import (
    DecayConfig, EntityHealth, parse_last_date, parse_entity_type,
    scan_health, run_decay, increment_access, restore_entity
)


@pytest.fixture
def entity_dir(tmp_path):
    entities = tmp_path / "entities"
    entities.mkdir()
    return entities


def make_entity(entity_dir, name, entity_type="person", days_ago=0, entries=1):
    """Create a test entity file with timeline entries N days ago."""
    ref_date = date.today() - timedelta(days=days_ago)
    
    content = f"# {name}\n**Type:** {entity_type}\n\n## Timeline\n"
    for i in range(entries):
        d = ref_date - timedelta(days=i)
        content += f"\n### [[{d.isoformat()}]]\n- Event on {d}\n"
    
    safe_name = name.replace(' ', '-')
    (entity_dir / f"{safe_name}.md").write_text(content)


class TestParsers:
    def test_parse_last_date(self):
        content = "### [[2026-02-10]]\n- old\n### [[2026-02-16]]\n- new\n"
        assert parse_last_date(content) == date(2026, 2, 16)
    
    def test_parse_last_date_none(self):
        assert parse_last_date("No dates here") is None
    
    def test_parse_entity_type(self):
        assert parse_entity_type("**Type:** person") == "person"
        assert parse_entity_type("**Type:** company") == "company"
        assert parse_entity_type("No type") == "unknown"


class TestScanHealth:
    def test_active_entity(self, entity_dir):
        make_entity(entity_dir, "Fresh", days_ago=2)
        health = scan_health(entity_dir)
        
        assert len(health) == 1
        assert health[0].status == "active"
        assert health[0].days_stale == 2
    
    def test_stale_entity(self, entity_dir):
        make_entity(entity_dir, "Aging", days_ago=20)
        health = scan_health(entity_dir, DecayConfig(stale_warning_days=14))
        
        assert health[0].status == "stale"
    
    def test_archive_candidate(self, entity_dir):
        make_entity(entity_dir, "Old", days_ago=35)
        health = scan_health(entity_dir, DecayConfig(archive_after_days=30))
        
        assert health[0].status == "archive_candidate"
    
    def test_protected_type(self, entity_dir):
        make_entity(entity_dir, "MyProject", entity_type="project", days_ago=100)
        health = scan_health(entity_dir, DecayConfig(protected_types=["project"]))
        
        assert health[0].status == "protected"
    
    def test_mixed_health(self, entity_dir):
        make_entity(entity_dir, "Active", days_ago=1)
        make_entity(entity_dir, "Stale", days_ago=20)
        make_entity(entity_dir, "Archive", days_ago=40)
        make_entity(entity_dir, "Protected", entity_type="tool", days_ago=60)
        
        health = scan_health(entity_dir, DecayConfig(
            stale_warning_days=14,
            archive_after_days=30,
            protected_types=["tool"]
        ))
        
        statuses = {h.name: h.status for h in health}
        assert statuses["Active"] == "active"
        assert statuses["Stale"] == "stale"
        assert statuses["Archive"] == "archive_candidate"
        assert statuses["Protected"] == "protected"


class TestRunDecay:
    def test_dry_run(self, entity_dir):
        make_entity(entity_dir, "OldEntity", days_ago=40)
        
        actions = run_decay(entity_dir, config=DecayConfig(archive_after_days=30), dry_run=True)
        
        assert any("Would archive" in a for a in actions)
        assert (entity_dir / "OldEntity.md").exists()  # Not moved in dry run
    
    def test_actual_archive(self, entity_dir):
        make_entity(entity_dir, "OldEntity", days_ago=40)
        
        actions = run_decay(entity_dir, config=DecayConfig(archive_after_days=30), dry_run=False)
        
        assert any("Archived" in a for a in actions)
        assert not (entity_dir / "OldEntity.md").exists()
        assert (entity_dir / "archive" / "OldEntity.md").exists()
    
    def test_grace_period_for_rich_entities(self, entity_dir):
        make_entity(entity_dir, "RichOld", days_ago=35, entries=5)
        
        actions = run_decay(
            entity_dir,
            config=DecayConfig(archive_after_days=30, min_timeline_entries=1),
            dry_run=True
        )
        
        # Rich entity (5 entries) gets grace period at 35 days (< 60 = 30*2)
        assert any("Grace period" in a for a in actions)
    
    def test_healthy_report(self, entity_dir):
        make_entity(entity_dir, "Fresh", days_ago=1)
        
        actions = run_decay(entity_dir, dry_run=True)
        assert any("healthy" in a.lower() for a in actions)
    
    def test_graph_stale_marking(self, entity_dir, tmp_path):
        make_entity(entity_dir, "OldEntity", days_ago=40)
        
        graph = tmp_path / "graph.jsonl"
        graph.write_text(json.dumps({
            "subject": "OldEntity", "predicate": "knows", "object": "Someone"
        }) + '\n')
        
        run_decay(entity_dir, graph_file=graph,
                  config=DecayConfig(archive_after_days=30), dry_run=False)
        
        triplet = json.loads(graph.read_text().strip())
        assert triplet.get("stale") is True


class TestAccessTracking:
    def test_increment_access(self, entity_dir):
        make_entity(entity_dir, "TestEntity")
        path = entity_dir / "TestEntity.md"
        
        increment_access(path)
        assert "**Accessed:** 1" in path.read_text()
        
        increment_access(path)
        assert "**Accessed:** 2" in path.read_text()
    
    def test_increment_nonexistent(self, entity_dir):
        # Should not crash
        increment_access(entity_dir / "nonexistent.md")


class TestRestore:
    def test_restore_archived(self, entity_dir):
        make_entity(entity_dir, "Archived", days_ago=40)
        
        # Archive it
        run_decay(entity_dir, config=DecayConfig(archive_after_days=30), dry_run=False)
        assert not (entity_dir / "Archived.md").exists()
        
        # Restore it
        result = restore_entity(entity_dir, "Archived")
        assert "Restored" in result
        assert (entity_dir / "Archived.md").exists()
    
    def test_restore_missing(self, entity_dir):
        (entity_dir / "archive").mkdir()
        result = restore_entity(entity_dir, "DoesNotExist")
        assert "not found" in result
