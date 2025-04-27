from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import List, Optional
from fastapi.responses import JSONResponse
from google.cloud import firestore
from google.oauth2 import service_account
from pathlib import Path
from dotenv import load_dotenv
import os
import json
import uuid

# Load environment variables
load_dotenv()

# Setup Firestore client
if "GOOGLE_APPLICATION_CREDENTIALS_JSON" in os.environ:
    credentials_info = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"])
    credentials = service_account.Credentials.from_service_account_info(credentials_info)
    db = firestore.Client(credentials=credentials, project=credentials.project_id)
else:
    BASE_DIR = Path(__file__).resolve().parent
    service_account_path = BASE_DIR / "serviceAccountKey.json"
    if not service_account_path.exists():
        raise FileNotFoundError(f"serviceAccountKey.json not found at {service_account_path}")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(service_account_path)
    db = firestore.Client()

commands_ref = db.collection("commands")

app = FastAPI()

# Pydantic models
class SingleCommand(BaseModel):
    command: str

class MultipleCommands(BaseModel):
    commands: List[SingleCommand]
    batch: Optional[bool] = False

# Webhook endpoint
@app.post("/webhook")
async def receive_command(request: Request):
    try:
        payload = await request.json()
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Invalid JSON: {str(e)}"})

    # Handle single command
    if "command" in payload:
        command_text = payload["command"].strip()
        if not command_text:
            return JSONResponse(status_code=400, content={"error": "Empty command not allowed."})

        try:
            doc_ref = commands_ref.document()
            doc_ref.set({
                "command": command_text,
                "status": "pending",
                "output": "",
                "batch_id": None,
                "order": None,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            return JSONResponse(status_code=200, content={"status": "ok", "id": doc_ref.id})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": f"Failed to save command: {str(e)}"})

    # Handle batch of commands
    elif "commands" in payload:
        commands_list = payload["commands"]
        if not isinstance(commands_list, list) or not commands_list:
            return JSONResponse(status_code=400, content={"error": "Commands must be a non-empty list."})

        is_batch = payload.get("batch", False)
        batch_id = str(uuid.uuid4()) if is_batch else None
        created_ids = []

        try:
            for idx, cmd_entry in enumerate(commands_list):
                command_text = cmd_entry.get("command", "").strip()
                if not command_text:
                    continue

                doc_ref = commands_ref.document()
                doc_ref.set({
                    "command": command_text,
                    "status": "pending",
                    "output": "",
                    "batch_id": batch_id,
                    "order": idx if is_batch else None,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                created_ids.append(doc_ref.id)

            if not created_ids:
                return JSONResponse(status_code=400, content={"error": "No valid commands provided."})

            return JSONResponse(status_code=200, content={"status": "ok", "ids": created_ids, "batch_id": batch_id})

        except Exception as e:
            return JSONResponse(status_code=500, content={"error": f"Failed to save batch: {str(e)}"})

    else:
        return JSONResponse(status_code=400, content={"error": "Invalid payload: expected 'command' or 'commands' field."})