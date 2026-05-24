from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(title="AI Agent Backend")

# هذا السطر السحري سيجعل السيرفر يفتح الواجهة تلقائياً بمجرد الضغط على الرابط الأزرق!
@app.get("/", include_in_schema=False)
async def root():
    if os.path.exists("ai_app_ui.html"):
        with open("ai_app_ui.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return {"status": "Server is Live! Please visit /ai_app_ui.html"}

@app.get("/status")
async def status():
    return {"status": "online", "agent": "Cyber Agent Core v1.0.0"}
