"""
AI Agent Backend Server
FastAPI server for Android app with /chat, /status, and /browse endpoints
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Optional, List
import httpx
import time
import uuid
import re
from datetime import datetime
from collections import deque

# ─────────────────────────────────────────────
#  App Setup
# ─────────────────────────────────────────────
app = FastAPI(
    title="AI Agent Backend",
    description="Backend server for Android AI Agent App",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
#  In-Memory State (replace with DB in production)
# ─────────────────────────────────────────────
class AgentMemory:
    def __init__(self, max_messages: int = 100):
        self.conversations: dict[str, deque] = {}   # session_id -> message list
        self.max_messages = max_messages
        self.agent_level: int = 1
        self.total_interactions: int = 0
        self.browse_history: List[dict] = []
        self.created_at: datetime = datetime.utcnow()

    def add_message(self, session_id: str, role: str, content: str):
        if session_id not in self.conversations:
            self.conversations[session_id] = deque(maxlen=self.max_messages)
        self.conversations[session_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self.total_interactions += 1
        # Level up every 50 interactions
        self.agent_level = 1 + self.total_interactions // 50

    def get_history(self, session_id: str) -> List[dict]:
        return list(self.conversations.get(session_id, []))

    def memory_usage_kb(self) -> float:
        import sys
        return round(sys.getsizeof(self.conversations) / 1024, 2)

    def total_messages(self) -> int:
        return sum(len(v) for v in self.conversations.values())


memory = AgentMemory()

# ─────────────────────────────────────────────
#  Pydantic Schemas
# ─────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    system_prompt: Optional[str] = "You are a helpful AI assistant."

class ChatResponse(BaseModel):
    reply: str
    session_id: str
    timestamp: str
    tokens_used: Optional[int] = None

class StatusResponse(BaseModel):
    status: str
    agent_level: int
    total_interactions: int
    active_sessions: int
    total_messages_in_memory: int
    memory_usage_kb: float
    browse_history_count: int
    uptime_seconds: float
    server_time: str

class BrowseRequest(BaseModel):
    url: str
    extract_links: bool = False
    summarize: bool = True

class BrowseResponse(BaseModel):
    url: str
    title: Optional[str]
    text_content: str
    links: Optional[List[str]] = None
    word_count: int
    fetched_at: str
    status_code: int

# ─────────────────────────────────────────────
#  Startup time
# ─────────────────────────────────────────────
_start_time = time.time()

# ─────────────────────────────────────────────
#  Helper: call Claude (Anthropic API)
# ─────────────────────────────────────────────
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

async def call_claude(system_prompt: str, messages: List[dict]) -> tuple[str, int]:
    """
    Calls the Anthropic Claude API.
    Set your ANTHROPIC_API_KEY as an environment variable.
    """
    import os
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Fallback echo for testing without API key
        last_msg = messages[-1]["content"] if messages else ""
        return f"[DEMO MODE – no API key] Echo: {last_msg}", 0

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": [
            {"role": m["role"], "content": m["content"]}
            for m in messages
        ],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(ANTHROPIC_API_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        reply = data["content"][0]["text"]
        tokens = data.get("usage", {}).get("output_tokens", 0)
        return reply, tokens


# ─────────────────────────────────────────────
#  Helper: simple HTML → plain text
# ─────────────────────────────────────────────
def html_to_text(html: str) -> str:
    # Remove scripts & styles
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text

def extract_title(html: str) -> Optional[str]:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return m.group(1).strip() if m else None

def extract_links(html: str, base_url: str) -> List[str]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, re.I)
    links = []
    for h in hrefs:
        if h.startswith("http"):
            links.append(h)
        elif h.startswith("/"):
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            links.append(f"{parsed.scheme}://{parsed.netloc}{h}")
    return list(set(links))[:30]  # max 30 unique links


# ─────────────────────────────────────────────
#  Endpoints
# ─────────────────────────────────────────────

@app.get("/", tags=["Root"])
async def root():
    return {"message": "AI Agent Backend is running 🚀", "docs": "/docs"}


# ── /chat ──────────────────────────────────────
@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(req: ChatRequest):
    """
    Send a message to the AI agent and receive a reply.
    Maintains conversation history per session_id.
    """
    session_id = req.session_id or str(uuid.uuid4())

    # Save user message
    memory.add_message(session_id, "user", req.message)

    # Build message history (last 20 turns to stay within context)
    history = memory.get_history(session_id)[-20:]
    messages = [{"role": m["role"], "content": m["content"]} for m in history]

    try:
        reply, tokens = await call_claude(req.system_prompt, messages)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Save assistant reply
    memory.add_message(session_id, "assistant", reply)

    return ChatResponse(
        reply=reply,
        session_id=session_id,
        timestamp=datetime.utcnow().isoformat(),
        tokens_used=tokens,
    )


# ── /status ────────────────────────────────────
@app.get("/status", response_model=StatusResponse, tags=["Status"])
async def status():
    """
    Returns agent health, memory usage, level, and activity stats.
    """
    return StatusResponse(
        status="ok",
        agent_level=memory.agent_level,
        total_interactions=memory.total_interactions,
        active_sessions=len(memory.conversations),
        total_messages_in_memory=memory.total_messages(),
        memory_usage_kb=memory.memory_usage_kb(),
        browse_history_count=len(memory.browse_history),
        uptime_seconds=round(time.time() - _start_time, 2),
        server_time=datetime.utcnow().isoformat(),
    )


# ── /browse ────────────────────────────────────
@app.post("/browse", response_model=BrowseResponse, tags=["Browse"])
async def browse(req: BrowseRequest):
    """
    Fetches a URL, extracts text content, and optionally returns links.
    """
    url = req.url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (AI Agent Bot)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Request timed out fetching the URL.")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"URL returned error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not fetch URL: {str(e)}")

    html = response.text
    title = extract_title(html)
    text = html_to_text(html)

    # Optionally truncate text for large pages
    max_chars = 4000
    if len(text) > max_chars:
        text = text[:max_chars] + "… [truncated]"

    links = extract_links(html, url) if req.extract_links else None

    result = {
        "url": str(response.url),
        "title": title,
        "text_content": text,
        "links": links,
        "word_count": len(text.split()),
        "fetched_at": datetime.utcnow().isoformat(),
        "status_code": response.status_code,
    }

    # Store in browse history
    memory.browse_history.append({
        "url": result["url"],
        "title": title,
        "fetched_at": result["fetched_at"],
    })

    return BrowseResponse(**result)


# ── /chat/history ──────────────────────────────
@app.get("/chat/history/{session_id}", tags=["Chat"])
async def get_history(session_id: str):
    """Returns full message history for a session."""
    history = memory.get_history(session_id)
    if not history:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"session_id": session_id, "messages": history, "count": len(history)}


# ── /chat/reset ────────────────────────────────
@app.delete("/chat/reset/{session_id}", tags=["Chat"])
async def reset_session(session_id: str):
    """Clears conversation memory for a session."""
    if session_id in memory.conversations:
        del memory.conversations[session_id]
        return {"message": f"Session {session_id} cleared."}
    raise HTTPException(status_code=404, detail="Session not found.")
