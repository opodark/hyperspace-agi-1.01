from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime

app = FastAPI()

nodes = {}

# -------- MODELS --------

class RegisterRequest(BaseModel):
    node_id: str

class HeartbeatRequest(BaseModel):
    node_id: str

# -------- ENDPOINTS --------

@app.post("/register")
def register(req: RegisterRequest):
    nodes[req.node_id] = {
        "last_seen": datetime.utcnow()
    }
    return {"status": "registered", "node_id": req.node_id}

@app.post("/heartbeat")
def heartbeat(req: HeartbeatRequest):
    if req.node_id in nodes:
        nodes[req.node_id]["last_seen"] = datetime.utcnow()
    return {"status": "ok"}

@app.get("/nodes")
def get_nodes():
    return nodes

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
