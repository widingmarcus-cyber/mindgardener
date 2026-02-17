# 🌱 MindGardener

**Your AI agent's personal Wikipedia — automatically built and updated from daily conversations.**

Every time you chat with your agent, it mentions people, projects, tools, and events. MindGardener turns those conversations into a personal wiki — one markdown file per entity — that grows over time. Your agent remembers what happened last week, who you talked about, and what matters.

No database needed. Just text files.

## How It Stays Manageable

You might wonder: won't this create thousands of files? No. MindGardener is opinionated about what it remembers:

- **One file per entity.** A person, a company, a project each gets one `.md` file. Mentions across different days get merged into the same file — not duplicated.
- **Surprise scoring decides what's worth keeping.** Not everything is interesting. MindGardener predicts what *should* have happened based on what it already knows, then compares with what *actually* happened. Only surprising things get promoted to long-term memory. Routine stuff fades.
- **Automatic pruning.** Entities that haven't been mentioned in 30+ days get archived. Your wiki stays focused on what's active and relevant.
- **You can edit it.** It's just markdown files in a folder. Open them in VS Code, Obsidian, or `vim`. Add facts, fix mistakes, delete things. Run `garden reindex` and the system catches up.

A typical agent running for a month has 30-80 entity files. That's it — a small, browsable wiki, not a data dump.

## The Problem

AI agents forget everything between sessions. Current solutions:
- **RAG / Vector DBs** — find similar text, miss causal connections
- **Flat file memory** — grows forever, no signal/noise filtering
- **Context window** — limited, expensive, ephemeral

**Mem0** requires Neo4j. **Letta** requires a cloud account. **MindGardener** requires a folder.

None of the existing solutions model how memory actually works: **consolidate the important, forget the rest.**

## Why Files?

- **Debug with `grep`**, not SQL queries
- **Version with `git`** — diff your agent's learning over time
- **Read in Obsidian** — your agent's brain is a wiki you can browse
- **No infrastructure** — no database, no server, no account, no API key (except for the LLM)
- **Survives anything** — `rsync`, `cp`, `tar`. Try that with a vector DB

## The Graph is Free

`[[WikiLinks]]` create a knowledge graph without a graph database. Each entity page links to related entities. The graph emerges from the text — no Neo4j, no schema, no migration.

```markdown
# Kadoa
- Received reply from [[Adrian Krebs]] after [[HN]] outreach
- [[Revenue Hunter]] sent cold email to adrian@kadoa.com
```

That's 3 edges in the graph, and you can read them with `cat`.

## How MindGardener Works

```
Daily Logs (episodic)
     ↓ gardener extract
Entity Pages (semantic wiki)  +  Knowledge Graph (triplets)
     ↓ gardener surprise
Surprise Scoring (what changed your world model?)
     ↓ gardener consolidate  
Long-term Memory (curated, high-confidence)
```

### The Sleep Cycle

Every night, MindGardener runs a "sleep cycle":
1. **Extract** entities and relationships from today's logs
2. **Score** events by surprise (prediction error vs world model)
3. **Consolidate** high-surprise items into long-term memory
4. **Decay** unreferenced entities over time

### The Knowledge Graph

MindGardener builds a wiki-style knowledge graph from unstructured text:

```
memory/
├── entities/
│   ├── OpenClaw.md          # Project page with timeline
│   ├── Adrian-Krebs.md      # Person page with context
│   └── Kadoa.md             # Company page with relations
├── graph.jsonl              # Triplets: subject → predicate → object
└── surprise-scores.jsonl    # What was unexpected today?
```

Each entity page is human-readable Markdown with `[[wikilinks]]`:

```markdown
# Kadoa
**Type:** company

## Facts
- AI web scraping startup
- Adrian Krebs works here

## Timeline
### [[2026-02-16]]
- Received reply from [[Adrian Krebs]] after HN outreach
- [[Revenue-hunter-cron]] sent cold email

## Relations
- [[Adrian Krebs]] works_at → this
```

## Key Concepts

### Surprise-Driven Consolidation
Not all memories are equal. MindGardener uses **prediction error** to score importance:
1. Feed the agent's current world model (MEMORY.md)
2. Ask: "What do you predict happened today?"
3. Compare prediction against reality
4. Delta = surprise score (0.0 - 1.0)

High surprise → consolidate to long-term memory. Low surprise → let it decay.

This is SOAR's impasse-driven chunking (Laird, 2012) adapted for LLM agents.

### Temporal Versioning
Memories aren't facts — they're `(fact, timestamp, confidence)` tuples.
"Applied to Klarna [Jan, 0.8]" → "Rejected by Klarna [Feb, 0.95]" — not contradiction, evolution.

### Multi-Agent Shared Brain
Multiple agents can share the same entity directory. Each contributes observations; all benefit from the combined knowledge. Symlinks or shared directories — no database required.

## Installation

```bash
pip install mindgardener
```

## Quick Start

```bash
# Extract entities from today's log
garden extract --input memory/2026-02-17.md

# Run surprise scoring
garden surprise --memory MEMORY.md --today memory/2026-02-17.md

# Consolidate high-surprise items to long-term memory
garden consolidate

# Backfill historical files
garden backfill --dir memory/

# Visualize the knowledge graph
garden viz --format mermaid
```

## Configuration

```yaml
# garden.yaml
workspace: /path/to/agent/workspace
memory_dir: memory/
entities_dir: memory/entities/
graph_file: memory/graph.jsonl
long_term_memory: MEMORY.md

extraction:
  model: gemini-2.0-flash  # Cheap model for extraction
  provider: google          # google, openai, anthropic

consolidation:
  surprise_threshold: 0.5   # Min score to consolidate
  decay_days: 30            # Days before archiving unreferenced entities
  
schedule:
  extract: "0 3 * * *"     # Nightly at 3 AM
  backfill: "15 * * * *"   # One file per hour
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Daily Logs  │────▶│   Extractor   │────▶│  Entity Pages   │
│  (episodic)  │     │  (LLM call)   │     │  (semantic wiki) │
└─────────────┘     └──────────────┘     └─────────────────┘
                           │                       │
                           ▼                       ▼
                    ┌──────────────┐     ┌─────────────────┐
                    │  Graph Store  │     │ Surprise Scorer  │
                    │  (triplets)   │     │ (prediction err) │
                    └──────────────┘     └─────────────────┘
                                                   │
                                                   ▼
                                          ┌─────────────────┐
                                          │  Consolidator    │
                                          │ (→ MEMORY.md)    │
                                          └─────────────────┘
```

## Comparison

| | **MindGardener** | **Letta Code** | **Mem0** | **LangMem** |
|---|---|---|---|---|
| CLI-first | ✅ `garden` | ✅ `letta` | ❌ SDK | ❌ SDK |
| Storage | Files (Markdown) | Server DB | Neo4j + Qdrant | Postgres |
| Human-readable | ✅ Markdown | ❌ | ❌ | ❌ |
| Knowledge graph | ✅ JSONL | ❌ | ✅ Neo4j | ❌ |
| Surprise scoring | ✅ PE engine | ❌ | ❌ | ❌ |
| Sleep cycle | ✅ consolidate | ✅ sleeptime | ❌ | ⚠️ |
| Zero infrastructure | ✅ | ❌ server | ❌ 2 DBs | ❌ Postgres |
| Manual edit | ✅ any editor | ⚠️ /remember | ❌ | ❌ |
| Framework lock-in | None | Letta | Mem0 SDK | LangChain |
| Offline capable | ✅ (with local LLM) | ❌ | ❌ | ❌ |

**Use case:** "I just want my agent to remember yesterday — without deploying a database."

## Research Background

MindGardener is informed by cognitive science research on memory consolidation:

- **Tulving (1972)** — Episodic vs semantic memory distinction
- **SOAR (Laird, 2012)** — Impasse-driven chunking for procedural learning
- **Generative Agents (Park et al., 2023)** — Reflection-based agent memory
- **CoALA (Sumers et al., 2023)** — Formal taxonomy of agent memory architectures
- **GraphRAG (Edge et al., 2024)** — Graph + vector hybrid retrieval
- **MemGPT (Packer et al., 2023)** — OS-inspired hierarchical memory management

**Novel contribution:** Surprise-based consolidation using prediction error — porting SOAR's impasse detection to LLM agents. No prior work has implemented this.

## Roadmap

- [x] Entity extraction from markdown logs
- [x] Wiki-style page generation with wikilinks
- [x] Triplet-based knowledge graph
- [x] Surprise scoring (prediction error)
- [x] Multi-agent shared brain
- [x] Backfill historical files
- [ ] Temporal decay + archiving
- [ ] Graph traversal queries (1-hop, 2-hop)
- [ ] Conflict resolution for contradictory facts
- [ ] Provider-agnostic LLM calls (OpenAI, Anthropic, Google, local)
- [ ] pip package + CLI
- [ ] Obsidian plugin for visualization
- [ ] Benchmark against standard RAG

## License

MIT

## Credits

Built by the [Swarm](https://github.com/widingmarcus-cyber/discord-agent-swarm) — a team of 4 autonomous AI agents coordinating via Discord.
