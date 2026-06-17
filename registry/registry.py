from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from time import time
from threading import Lock
import uvicorn
import os

app = FastAPI(title="HyperSpace Registry", version="1.01")
lock = Lock()

TTL_SECONDS = int(os.getenv("NODE_TTL", "60"))  # rimuovi nodi inattivi dopo N secondi

class NodeRegistration(BaseModel):
    node_id: str
    public_address: str
    role: Optional[str] = "worker"
    metadata: Dict[str, str] = Field(default_factory=dict)

class NodeRecord(NodeRegistration):
    last_seen: float

nodes: Dict[str, NodeRecord] = {}


def prune_stale_nodes():
    now = time()
    stale = [nid for nid, rec in nodes.items() if now - rec.last_seen > TTL_SECONDS]
    for nid in stale:
        del nodes[nid]


@app.post("/register", summary="Registra o aggiorna un nodo")
def register(node: NodeRegistration):
    with lock:
        nodes[node.node_id] = NodeRecord(**node.model_dump(), last_seen=time())
    return {"ok": True, "node_id": node.node_id}


@app.post("/heartbeat", summary="Aggiorna last_seen del nodo")
def heartbeat(node_id: str):
    with lock:
        if node_id not in nodes:
            raise HTTPException(status_code=404, detail=f"Nodo '{node_id}' non trovato")
        nodes[node_id].last_seen = time()
    return {"ok": True, "node_id": node_id}


@app.delete("/nodes/{node_id}", summary="Deregistra un nodo")
def deregister(node_id: str):
    with lock:
        if node_id not in nodes:
            raise HTTPException(status_code=404, detail=f"Nodo '{node_id}' non trovato")
        del nodes[node_id]
    return {"ok": True, "node_id": node_id}


@app.get("/nodes", response_model=List[NodeRecord], summary="Lista nodi attivi")
def list_nodes():
    with lock:
        prune_stale_nodes()
        return list(nodes.values())


@app.get("/health")
def health():
    return {"status": "ok", "nodes_count": len(nodes)}


if __name__ == "__main__":
    port = int(os.getenv("REGISTRY_PORT", "8086"))
    uvicorn.run("registry:app", host="0.0.0.0", port=port, reload=False)
