"""
Autonomous Learning Agent with Long-Term Memory
================================================
Uses ChromaDB as a vector database for persistent memory.
The agent learns from experiences and improves its decisions over time.

Requirements:
    pip install chromadb sentence-transformers openai  (or any LLM provider)

    # Or for a simpler setup without an LLM:
    pip install chromadb sentence-transformers
"""

import json
import uuid
import hashlib
from datetime import datetime
from typing import Optional
import chromadb
from chromadb.utils import embedding_functions


# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
CHROMA_PATH      = "./agent_memory_db"   # Where ChromaDB stores data on disk
COLLECTION_NAME  = "experiences"
TOP_K_RESULTS    = 5                     # How many similar memories to retrieve
EMBEDDING_MODEL  = "all-MiniLM-L6-v2"   # Fast, good-quality sentence embeddings


# ──────────────────────────────────────────────
# Agent Class
# ──────────────────────────────────────────────
class AutonomousAgent:
    """
    A self-improving agent that:
      1. Stores every experience in a persistent vector DB (ChromaDB).
      2. Retrieves semantically similar past experiences when facing new situations.
      3. Synthesises those memories into a rich, context-aware prompt for any LLM.

    The agent's only goal is to become more helpful and accurate over time.
    It never deceives the user – transparency and trust are core to its design.
    """

    def __init__(self, agent_name: str = "Atlas"):
        self.agent_name = agent_name
        self.session_id = str(uuid.uuid4())[:8]

        # ── ChromaDB (persistent on-disk) ──────────────────────────────────
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)

        # Use a local sentence-transformer model for embeddings (no API key needed)
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL
        )

        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},   # cosine similarity
        )

        print(f"[{self.agent_name}] Initialised. "
              f"Memory contains {self.collection.count()} experience(s). "
              f"Session: {self.session_id}")

    # ──────────────────────────────────────────
    # 1.  save_experience
    # ──────────────────────────────────────────
    def save_experience(
        self,
        event: str,
        outcome: str,
        success: bool = True,
        tags: Optional[list[str]] = None,
        importance: float = 1.0,   # 0.0 → 2.0  (used later for weighted recall)
    ) -> str:
        """
        Persist a single experience to long-term memory.

        Parameters
        ----------
        event      : What happened / what the agent was asked to do.
        outcome    : What resulted from that event.
        success    : Was the outcome good? (True = positive experience)
        tags       : Optional list of topic labels, e.g. ["math", "reasoning"]
        importance : How important is this experience? Default 1.0.

        Returns
        -------
        The unique memory ID (str).
        """
        tags = tags or []

        # Create a stable ID based on content so duplicates are avoided
        content_hash = hashlib.md5(f"{event}{outcome}".encode()).hexdigest()[:12]
        memory_id    = f"mem_{content_hash}_{self.session_id}"

        # The text we embed is a rich combination of event + outcome
        embeddable_text = (
            f"Event: {event}\n"
            f"Outcome: {outcome}\n"
            f"Result: {'success' if success else 'failure'}"
        )

        metadata = {
            "agent"      : self.agent_name,
            "session"    : self.session_id,
            "timestamp"  : datetime.utcnow().isoformat(),
            "success"    : str(success),           # ChromaDB stores strings
            "tags"       : json.dumps(tags),
            "importance" : str(importance),
            "event"      : event[:500],            # keep metadata small
            "outcome"    : outcome[:500],
        }

        # Upsert: if same hash exists, overwrite it (idempotent)
        self.collection.upsert(
            ids        = [memory_id],
            documents  = [embeddable_text],
            metadatas  = [metadata],
        )

        status = "✅ success" if success else "❌ failure"
        print(f"[Memory saved] id={memory_id}  status={status}  "
              f"tags={tags}  importance={importance}")
        return memory_id

    # ──────────────────────────────────────────
    # 2.  recall_and_decide
    # ──────────────────────────────────────────
    def recall_and_decide(
        self,
        current_situation: str,
        n_results: int = TOP_K_RESULTS,
    ) -> dict:
        """
        Search memory for similar past experiences and build a context-rich
        prompt that the caller can forward to any LLM.

        Parameters
        ----------
        current_situation : Natural-language description of the new task/query.
        n_results         : How many memories to retrieve.

        Returns
        -------
        A dict with:
          - "prompt"   : The full prompt string ready to send to an LLM.
          - "memories" : List of raw retrieved memory dicts (for inspection).
          - "summary"  : Short human-readable recap of what was found.
        """
        total_memories = self.collection.count()
        if total_memories == 0:
            return self._empty_memory_response(current_situation)

        # ── Semantic search ────────────────────────────────────────────────
        results = self.collection.query(
            query_texts = [current_situation],
            n_results   = min(n_results, total_memories),
            include     = ["documents", "metadatas", "distances"],
        )

        memories_raw = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            memories_raw.append({
                "text"       : doc,
                "metadata"   : meta,
                "similarity" : round(1 - dist, 4),   # cosine → similarity score
            })

        # Sort by similarity descending
        memories_raw.sort(key=lambda x: x["similarity"], reverse=True)

        # ── Build structured memory block ──────────────────────────────────
        memory_block = self._format_memory_block(memories_raw)

        # ── Build the final prompt ─────────────────────────────────────────
        prompt = self._build_prompt(current_situation, memory_block, total_memories)

        # ── Human-readable summary ─────────────────────────────────────────
        top_sim  = memories_raw[0]["similarity"] if memories_raw else 0
        summary  = (
            f"Retrieved {len(memories_raw)} memories from a pool of {total_memories}. "
            f"Top similarity: {top_sim:.2%}."
        )

        return {
            "prompt"   : prompt,
            "memories" : memories_raw,
            "summary"  : summary,
        }

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────
    def _format_memory_block(self, memories: list[dict]) -> str:
        lines = []
        for i, mem in enumerate(memories, 1):
            meta  = mem["metadata"]
            sim   = mem["similarity"]
            success_icon = "✅" if meta.get("success") == "True" else "❌"
            tags  = json.loads(meta.get("tags", "[]"))
            ts    = meta.get("timestamp", "unknown")[:19].replace("T", " ")

            lines.append(
                f"[Memory {i}]  similarity={sim:.2%}  {success_icon}  "
                f"date={ts}  tags={tags}\n"
                f"  Event  : {meta.get('event', '')}\n"
                f"  Outcome: {meta.get('outcome', '')}"
            )
        return "\n\n".join(lines)

    def _build_prompt(
        self,
        situation: str,
        memory_block: str,
        total_memories: int,
    ) -> str:
        return f"""You are {self.agent_name}, a self-improving AI agent.
Your purpose: deliver accurate, helpful, and honest responses.
You learn continuously from past experiences stored in your long-term memory.

════════════════════════════════════════
CURRENT SITUATION
════════════════════════════════════════
{situation}

════════════════════════════════════════
RELEVANT PAST EXPERIENCES  ({total_memories} total in memory)
════════════════════════════════════════
{memory_block}

════════════════════════════════════════
DECISION GUIDELINES
════════════════════════════════════════
1. LEARN   – Prioritise patterns from past successes; avoid repeating failures.
2. REASON  – Explain your thinking step by step before giving a final answer.
3. HONEST  – Never fabricate information. If unsure, say so clearly.
4. IMPROVE – After responding, briefly note one thing you would do differently
             next time to become more effective.

Now respond to the current situation, informed by your memories.
"""

    def _empty_memory_response(self, situation: str) -> dict:
        prompt = f"""You are {self.agent_name}, a self-improving AI agent.
This is your very first experience – your memory is empty.

════════════════════════════════════════
CURRENT SITUATION
════════════════════════════════════════
{situation}

════════════════════════════════════════
DECISION GUIDELINES
════════════════════════════════════════
1. Do your best with general knowledge.
2. Be honest that you have no prior relevant experiences yet.
3. After responding, note what you would save to memory from this interaction.

Respond to the situation above.
"""
        return {
            "prompt"   : prompt,
            "memories" : [],
            "summary"  : "Memory is empty – this is the agent's first experience.",
        }

    # ──────────────────────────────────────────
    # Utility methods
    # ──────────────────────────────────────────
    def memory_stats(self) -> dict:
        """Return basic statistics about the current memory store."""
        count = self.collection.count()
        return {
            "agent"           : self.agent_name,
            "total_memories"  : count,
            "db_path"         : CHROMA_PATH,
            "embedding_model" : EMBEDDING_MODEL,
        }

    def clear_memory(self, confirm: bool = False) -> None:
        """Permanently delete all memories. Requires confirm=True."""
        if not confirm:
            print("Pass confirm=True to clear memory.")
            return
        self.client.delete_collection(COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(COLLECTION_NAME)
        print("[Memory cleared] All experiences deleted.")


# ──────────────────────────────────────────────
# Demo / Quick-start
# ──────────────────────────────────────────────
if __name__ == "__main__":

    agent = AutonomousAgent(agent_name="Atlas")

    # ── Step 1: Save some past experiences ────────────────────────────────
    print("\n── Saving experiences ──")

    agent.save_experience(
        event   = "User asked to summarise a long PDF document.",
        outcome = "Extracted key points using section headers; user was satisfied.",
        success = True,
        tags    = ["summarisation", "pdf", "text"],
        importance = 1.2,
    )

    agent.save_experience(
        event   = "User asked to translate an Arabic sentence to English.",
        outcome = "Provided correct translation; user confirmed accuracy.",
        success = True,
        tags    = ["translation", "arabic", "language"],
        importance = 1.0,
    )

    agent.save_experience(
        event   = "User asked to solve a quadratic equation.",
        outcome = "Used the quadratic formula correctly; showed full working.",
        success = True,
        tags    = ["math", "algebra"],
        importance = 1.1,
    )

    agent.save_experience(
        event   = "Asked to recommend a movie without knowing user preferences.",
        outcome = "Gave a generic suggestion; user was disappointed.",
        success = False,
        tags    = ["recommendation", "preference"],
        importance = 0.8,
    )

    # ── Step 2: Recall and build a prompt for a new situation ──────────────
    print("\n── Recalling memories for a new situation ──")

    situation = "The user wants me to translate a paragraph from French to Arabic."

    result = agent.recall_and_decide(situation, n_results=3)

    print(f"\nSummary: {result['summary']}")
    print("\n" + "═" * 60)
    print("GENERATED PROMPT:")
    print("═" * 60)
    print(result["prompt"])

    # ── Step 3: Show memory stats ──────────────────────────────────────────
    print("\n── Memory stats ──")
    print(json.dumps(agent.memory_stats(), indent=2, ensure_ascii=False))

    # ── Step 4: (Optional) Send prompt to an LLM ──────────────────────────
    # Uncomment and fill in your API key to use OpenAI:
    #
    # from openai import OpenAI
    # client_llm = OpenAI(api_key="sk-...")
    # response = client_llm.chat.completions.create(
    #     model    = "gpt-4o",
    #     messages = [{"role": "user", "content": result["prompt"]}]
    # )
    # print(response.choices[0].message.content)
