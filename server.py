from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import List, Optional
from google.cloud import firestore
import os
from dotenv import load_dotenv
from pathlib import Path
from fastapi.responses import JSONResponse
import uuid

# Load environment variables
load_dotenv()

# Set path to serviceAccountKey.json
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / "serviceAccountKey.json"

if not env_path.exists():
    raise FileNotFoundError(f"serviceAccountKey.json not found at {env_path}")

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(env_path)

# Initialize Firestore
db = firestore.Client()
commands_ref = db.collection("commands")

# Create FastAPI app
app = FastAPI()

# Pydantic models
class SingleCommand(BaseModel):
    command: str

class MultipleCommands(BaseModel):
    commands: List[SingleCommand]
    batch: Optional[bool] = False

@app.post("/webhook")
async def receive_command(request: Request):
    payload = await request.json()

    # Handle single command
    if "command" in payload:
        doc_ref = commands_ref.document()
        doc_ref.set({
            "command": payload["command"],
            "status": "pending",
            "output": "",
            "batch_id": None,
            "order": None
        })
        return JSONResponse(status_code=200, content={"status": "ok", "id": doc_ref.id})

    # Handle multiple commands
    elif "commands" in payload:
        is_batch = payload.get("batch", False)
        batch_id = str(uuid.uuid4()) if is_batch else None
        created_ids = []
        for idx, cmd in enumerate(payload["commands"]):
            doc_ref = commands_ref.document()
            doc_ref.set({
                "command": cmd["command"],
                "status": "pending",
                "output": "",
                "batch_id": batch_id,
                "order": idx if is_batch else None
            })
            created_ids.append(doc_ref.id)
        return JSONResponse(status_code=200, content={"status": "ok", "ids": created_ids, "batch_id": batch_id})

    else:
        return JSONResponse(status_code=400, content={"error": "Invalid payload: expected 'command' or 'commands' field."})