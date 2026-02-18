"""
StoryVault Knowledge Graph Extractor
Extracts entities and relationships from canon + all KB documents,
returning a force-directed graph structure. Results cached to disk.
"""

import os
import json
import hashlib
from datetime import datetime


EXTRACTION_PROMPT = """\
You are a story analyst. Extract a comprehensive knowledge graph from the provided story content.

Return ONLY valid JSON in this exact structure — no explanation, no markdown fences:
{
  "nodes": [
    {
      "id": "snake_case_identifier",
      "label": "Display Name",
      "type": "character|location|object|event|organization|concept|theme",
      "description": "One sentence describing this entity and its role.",
      "weight": 1
    }
  ],
  "edges": [
    {
      "source": "source_node_id",
      "target": "target_node_id",
      "label": "relationship verb (short, 2-4 words)",
      "strength": 1
    }
  ]
}

Rules:
- Be EXHAUSTIVE. Extract every named entity — aim for 20-60 nodes depending on content richness.
- Extract all significant relationships. Every named entity must appear in at least one edge.
- The four PRIMARY categories (prioritise these first):
    character    = named people, protagonists, antagonists, supporting characters
    location     = physical places, settings, regions, realms, buildings, landscapes
    object       = physical items, artefacts, named props, tools, documents, relics, archives
    event        = specific incidents, plot turning points, backstory moments, named occurrences
- The three SECONDARY categories:
    organization = institutions, factions, courts, companies, groups
    concept      = abstract ideas, powers, abilities, states, conditions, forces
    theme        = story-level thematic elements
- Edge labels should be short active verbs/phrases: "inherits", "guards", "seeks",
  "belongs to", "located in", "threatens", "grieves for", "enables", "fears",
  "contains", "created by", "connected to", "journeys to", "unlocks", etc.
- weight: importance 1-3 (3 = most central to the story)
- strength: relationship strength 1-3 (3 = most important connection)
- Keep ids lowercase with underscores, unique across all nodes.
- Merge duplicate entities (same person/place appearing in multiple documents) into one node.
"""


class CanonGraphExtractor:
    def __init__(self, openai_client):
        self.client = openai_client

    def extract(
        self,
        canon_text: str,
        cache_path: str | None = None,
        extra_context: str = "",
    ) -> dict:
        """
        Extract knowledge graph from canon text + any extra KB document context.
        Cache is invalidated whenever either the canon or extra context changes.

        Returns:
            {"nodes": [...], "edges": [...], "extracted_at": "...", "cached": bool}
        """
        combined = canon_text + "\n\n" + extra_context if extra_context else canon_text
        content_hash = hashlib.md5(combined.encode()).hexdigest()

        # Check cache
        if cache_path and os.path.exists(cache_path):
            try:
                with open(cache_path, encoding="utf-8") as f:
                    cached = json.load(f)
                if cached.get("canon_hash") == content_hash:
                    return {**cached, "cached": True}
            except (json.JSONDecodeError, KeyError):
                pass

        # Build user message
        user_content = f"## CANON\n\n{canon_text}"
        if extra_context:
            user_content += f"\n\n---\n\n## KNOWLEDGE BASE DOCUMENTS\n\n{extra_context}"

        messages = [
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user",   "content": user_content},
        ]

        raw, usage = self.client.complete(
            messages,
            temperature=0.1,
            max_tokens=5000,
        )

        # Strip accidental markdown fences
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        try:
            data = json.loads(clean)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}\n\nRaw:\n{raw[:500]}")

        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        # Validate: remove edges referencing non-existent nodes
        node_ids = {n["id"] for n in nodes}
        edges = [
            e for e in edges
            if e.get("source") in node_ids and e.get("target") in node_ids
        ]

        result = {
            "nodes":        nodes,
            "edges":        edges,
            "extracted_at": datetime.now().isoformat(),
            "canon_hash":   content_hash,
            "usage":        usage,
            "cached":       False,
        }

        # Save cache
        if cache_path:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)

        return result
