# worker/main.py
# HyperSpace AGI v0.2 — Worker Node
# Identità crittografica nativa ECDSA secp256k1

from fastapi import FastAPI
import asyncio
import httpx
import os
import sys
import threading
import time
import uuid

# Modulo identità condiviso
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.identity import generate_or_load_identity, sign_message, verify_message

app = FastAPI()

# -------- IDENTITÀ CRITTOGRAFICA --------
# Genera o ricarica keypair ECDSA secp256k1 persistente
_identity    = generate_or_load_identity()
WORKER_ID    = _identity["node_id"]
NODE_PUBKEY  = _identity["public_key"]
_private_key = _identity["_private_key"]

# -------- CONFIG --------
WORKER_HOSTNAME = os.getenv("WORKER_HOSTNAME", "worker")
WORKER_PORT     = int(os.getenv("WORKER_PORT", 8084))
AUTHORITY_URL   = os.getenv("AUTHORITY_URL", "http://authority:8080")
OLLAMA_URL      = os.getenv("OLLAMA_URL", "http://ollama:11434")
DEFAULT_MODEL   = os.getenv("OLLAMA_MODEL", "phi3")
HEARTBEAT_EVERY = int(os.getenv("HEARTBEAT_EVERY", 30))
_boot_time      = time.time()

NODE_PROFILE = {
    "node_id":      WORKER_ID,
    "pubkey":       NODE_PUBKEY,
    "tier":         "leaf",       # calcolato dinamicamente in Fase 3
    "endpoint":     f"{WORKER_HOSTNAME}:{WORKER_PORT}",
    "capabilities": ["ollama", "execute"],
    "vram_gb":      0.0,          # rilevato dinamicamente in Fase 3
    "version":      "0.2.0",
}

_registered = False


# -------- HELPERS --------

def build_signed_payload(data: dict) -> dict:
    """Aggiunge node_id e pubkey al payload e lo firma con la chiave privata."""
    payload = {**data, "pubkey": NODE_PUBKEY, "node_id": WORKER_ID}
    return sign_message(payload, _private_key)


# -------- OLLAMA HELPERS --------

async def ollama_generate(prompt: str, model: str = DEFAULT_MODEL) -> str:
    payload = {
        "model":  model,
        "prompt": prompt,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            r.raise_for_status()
            return r.json().get("response", "").strip()
    except Exception as e:
        return f"[OLLAMA ERROR] {e}"


async def ollama_health() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            return {"ok": True, "models": [m["name"] for m in r.json().get("models", [])]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# -------- AUTHORITY REGISTRATION --------

def register_on_authority():
    global _registered
    for attempt in range(20):
        try:
            import requests as req_lib
            payload = build_signed_payload({
                "host":         WORKER_HOSTNAME,
                "port":         WORKER_PORT,
                "capabilities": NODE_PROFILE["capabilities"],
                "version":      NODE_PROFILE["version"],
            })
            r = req_lib.post(
                f"{AUTHORITY_URL}/register",
                json=payload,
                timeout=5,
            )
            if r.status_code == 200:
                print(f"[WORKER:{WORKER_ID[:12]}] registered on authority")
                _registered = True
                return
        except Exception as e:
            print(f"[WORKER:{WORKER_ID[:12]}] register attempt {attempt+1} failed: {e}")
        time.sleep(min(3 + attempt * 2, 30))
    print(f"[WORKER:{WORKER_ID[:12]}] could not register after 20 attempts")


def heartbeat_loop():
    register_on_authority()
    while True:
        try:
            import requests as req_lib
            req_lib.post(
                f"{AUTHORITY_URL}/heartbeat",
                json=build_signed_payload({"uptime_s": int(time.time() - _boot_time)}),
                timeout=5,
            )
        except Exception as e:
            print(f"[WORKER:{WORKER_ID[:12]}] heartbeat error: {e}")
        time.sleep(HEARTBEAT_EVERY)


# -------- FASTAPI ENDPOINTS --------

@app.on_event("startup")
async def startup_event():
    t = threading.Thread(target=heartbeat_loop, daemon=True)
    t.start()


@app.get("/identity")
def get_identity():
    """Restituisce l'identità crittografica del nodo."""
    return {
        "node_id":      WORKER_ID,
        "public_key":   NODE_PUBKEY,
        "tier":         NODE_PROFILE["tier"],
        "version":      NODE_PROFILE["version"],
        "capabilities": NODE_PROFILE["capabilities"],
        "endpoint":     NODE_PROFILE["endpoint"],
    }


@app.get("/status")
def status():
    return {
        "node_id":         WORKER_ID,
        "public_key":      NODE_PUBKEY,
        "tier":            NODE_PROFILE["tier"],
        "version":         NODE_PROFILE["version"],
        "worker_hostname": WORKER_HOSTNAME,
        "running":         True,
        "registered":      _registered,
        "uptime_s":        int(time.time() - _boot_time),
        "authority":       AUTHORITY_URL,
        "ollama_url":      OLLAMA_URL,
        "default_model":   DEFAULT_MODEL,
    }


@app.get("/health")
def health():
    return {"status": "ok", "node_id": WORKER_ID}


@app.post("/verify")
async def verify_incoming(message: dict):
    """Verifica la firma ECDSA di un messaggio ricevuto da un peer."""
    valid = verify_message(message)
    return {"valid": valid, "node_id": message.get("node_id")}


@app.post("/execute")
async def execute_task(task: dict):
    task_id = task.get("task_id", "unknown")
    prompt  = task.get("prompt") or task.get("payload", {}).get("prompt") or f"Esegui task: {task_id}"
    model   = task.get("model") or task.get("payload", {}).get("model") or DEFAULT_MODEL

    print(f"[WORKER:{WORKER_ID[:12]}] executing task {task_id} model={model}")
    response_text = await ollama_generate(prompt, model)

    return {
        "worker":    WORKER_ID,
        "task_id":  task_id,
        "status":   "done",
        "model":    model,
        "response": response_text,
    }


@app.get("/ollama/health")
async def check_ollama():
    return await ollama_health()


@app.get("/ollama/models")
async def list_models():
    h = await ollama_health()
    if h["ok"]:
        return {"models": h.get("models", [])}
    return {"error": h.get("error")}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
