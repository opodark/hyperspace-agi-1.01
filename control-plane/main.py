# control-plane/main.py
# HyperSpace AGI v0.2 — Control Plane + Dashboard

from flask import Flask, request, jsonify, render_template_string
import os
import threading
import time
import requests
import json
import uuid
import random
from datetime import datetime

app = Flask(__name__)

# ── CONFIG ────────────────────────────────────────────────
NODE_ENDPOINTS = [
    e.strip() for e in os.getenv("NODE_ENDPOINTS", "node:8084").split(",") if e.strip()
]
OLLAMA_URL    = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "phi3")
_AUTHORITY_URL     = os.getenv("AUTHORITY_URL", "http://authority:8080")
_AUTHORITY_ENABLED = os.getenv("AUTHORITY_ENABLED", "false").lower() == "true"

LOG_LIMIT = 500

# ── STATE ─────────────────────────────────────────────────
tasks      = {}
event_logs = []

# Mesh node registry: endpoint -> info
_mesh_nodes: dict = {}
# Set di endpoint noti (statici da config + dinamici da /mesh/announce)
_known_endpoints: set = set(NODE_ENDPOINTS)

hb_state = {
    "cycle": 0, "last_tick": None, "last_conn": None,
    "last_dream": None, "last_chat": None,
    "nodes_seen": [], "running": False,
}

advanced_config = {
    "ollama":     {"url": OLLAMA_URL, "defaultModel": DEFAULT_MODEL},
    "mesh":       {"nodeEndpoints": NODE_ENDPOINTS, "heartbeatEvery": 15},
    "_authority": {"serverUrl": _AUTHORITY_URL, "enabled": _AUTHORITY_ENABLED},
    "security":   {"sharedSecret": "", "secretRotatedAt": None},
}

# ── LOG HELPERS ───────────────────────────────────────────
LOG_TYPES = {"connection_test", "inter_node_message", "dream", "node_chat", "system", "mesh_event"}

def push_log(type_, summary, detail="", source="control-plane", target="", status="info", trace_id=""):
    global event_logs
    entry = {
        "id": str(uuid.uuid4()),
        "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "type": type_ if type_ in LOG_TYPES else "system",
        "sourceNode": source, "targetNode": target,
        "status": status,
        "traceId": trace_id or str(uuid.uuid4())[:8],
        "summary": summary, "detail": detail,
    }
    event_logs.append(entry)
    if len(event_logs) > LOG_LIMIT:
        event_logs = event_logs[-LOG_LIMIT:]
    return entry

# ── LOG API ───────────────────────────────────────────────
@app.route('/logs', methods=['GET'])
def get_logs():
    type_filter   = request.args.get('type', '')
    status_filter = request.args.get('status', '')
    node_filter   = request.args.get('node', '')
    search        = request.args.get('q', '').lower()
    result = event_logs[:]
    if type_filter:   result = [l for l in result if l['type'] == type_filter]
    if status_filter: result = [l for l in result if l['status'] == status_filter]
    if node_filter:   result = [l for l in result if node_filter in l['sourceNode'] or node_filter in l['targetNode']]
    if search:        result = [l for l in result if search in l['summary'].lower() or search in l['detail'].lower()]
    return jsonify(list(reversed(result[-200:])))

@app.route('/logs/add', methods=['POST'])
def add_log():
    data = request.get_json(force=True, silent=True) or {}
    entry = push_log(
        type_=data.get('type', 'system'), summary=data.get('summary', ''),
        detail=data.get('detail', ''), source=data.get('sourceNode', 'unknown'),
        target=data.get('targetNode', ''), status=data.get('status', 'info'),
        trace_id=data.get('traceId', ''),
    )
    return jsonify(entry), 201

@app.route('/logs/clear', methods=['POST'])
def clear_logs():
    global event_logs
    event_logs = []
    return jsonify({"ok": True})

# ── MESH ANNOUNCE (push dai nodi) ─────────────────────────
@app.route('/mesh/announce', methods=['POST'])
def mesh_announce():
    """I nodi chiamano questo endpoint per auto-registrarsi.
    Funziona per nodi locali E remoti (ngrok, IP pubblico, ecc.).
    """
    data = request.get_json(force=True, silent=True) or {}
    ep   = data.get("endpoint", "").strip()
    nid  = data.get("node_id", "")[:16]

    if not ep or not data.get("node_id"):
        return jsonify({"ok": False, "error": "missing endpoint or node_id"}), 400

    # Registra / aggiorna il nodo
    _mesh_nodes[ep] = {
        **data,
        "status":    "active",
        "last_seen": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    # Aggiunge l'endpoint al set noto per il polling
    _known_endpoints.add(ep)

    push_log('mesh_event', f'Node announced: {nid}',
             f'endpoint={ep} tier={data.get("tier","?")} caps={data.get("capabilities",[])}',
             source=nid, status='success')

    return jsonify({"ok": True, "registered": ep})

# ── MESH NODE API ─────────────────────────────────────────
@app.route('/mesh/nodes', methods=['GET'])
def get_mesh_nodes():
    return jsonify(list(_mesh_nodes.values()))

@app.route('/mesh/node/<path:endpoint>/status', methods=['GET'])
def get_node_status(endpoint):
    try:
        url = endpoint if endpoint.startswith('http') else f'http://{endpoint}'
        r = requests.get(f"{url}/status", timeout=3)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e), "endpoint": endpoint}), 503

@app.route('/mesh/node/<path:endpoint>/peers', methods=['GET'])
def get_node_peers(endpoint):
    try:
        url = endpoint if endpoint.startswith('http') else f'http://{endpoint}'
        r = requests.get(f"{url}/peers", timeout=3)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e), "endpoint": endpoint}), 503

# ── HB STATUS ─────────────────────────────────────────────
@app.route('/hb/status', methods=['GET'])
def hb_status():
    return jsonify(dict(hb_state))

# ── ADVANCED CONFIG ───────────────────────────────────────
@app.route('/config/advanced', methods=['GET'])
def get_advanced_config():
    safe = json.loads(json.dumps(advanced_config))
    if safe["security"]["sharedSecret"]:
        safe["security"]["sharedSecret"] = "***"
    return jsonify(safe)

@app.route('/config/advanced', methods=['POST'])
def set_advanced_config():
    global advanced_config, OLLAMA_URL, DEFAULT_MODEL
    data   = request.get_json(force=True, silent=True) or {}
    sec    = data.get('security', {})
    mesh   = data.get('mesh', {})
    ollama = data.get('ollama', {})
    auth   = data.get('_authority', {})
    if 'sharedSecret' in sec and sec['sharedSecret'] not in ('', '***'):
        advanced_config['security']['sharedSecret']   = sec['sharedSecret']
        advanced_config['security']['secretRotatedAt'] = datetime.utcnow().isoformat()
    if 'url' in ollama:
        advanced_config['ollama']['url'] = ollama['url']
        OLLAMA_URL = ollama['url']
    if 'defaultModel' in ollama:
        advanced_config['ollama']['defaultModel'] = ollama['defaultModel']
        DEFAULT_MODEL = ollama['defaultModel']
    if 'nodeEndpoints' in mesh:
        advanced_config['mesh']['nodeEndpoints'] = mesh['nodeEndpoints']
        for ep in mesh['nodeEndpoints']:
            _known_endpoints.add(ep)
    if 'serverUrl' in auth:
        advanced_config['_authority']['serverUrl'] = auth['serverUrl']
    if 'enabled' in auth:
        advanced_config['_authority']['enabled'] = bool(auth['enabled'])
    push_log('system', 'Advanced config updated', json.dumps(data, default=str))
    return jsonify({"ok": True})

@app.route('/config/secret/rotate', methods=['POST'])
def rotate_secret():
    new_secret = str(uuid.uuid4()).replace('-', '')
    advanced_config['security']['sharedSecret']   = new_secret
    advanced_config['security']['secretRotatedAt'] = datetime.utcnow().isoformat()
    push_log('system', 'Shared secret rotated', status='success')
    return jsonify({"ok": True, "secret": new_secret,
                    "rotatedAt": advanced_config['security']['secretRotatedAt']})

# ── OLLAMA STATUS ─────────────────────────────────────────
@app.route('/ollama/status', methods=['GET'])
def ollama_status():
    url = advanced_config['ollama']['url']
    try:
        r = requests.get(f"{url}/api/tags", timeout=3)
        models = [m['name'] for m in r.json().get('models', [])]
        return jsonify({"ok": True, "url": url, "models": models})
    except Exception as e:
        return jsonify({"ok": False, "url": url, "error": str(e)})

# ── TASK API ──────────────────────────────────────────────
@app.route('/task/create', methods=['POST'])
def create_task():
    data    = request.get_json(force=True, silent=True) or {}
    task_id = data.get('task_id') or str(uuid.uuid4())[:8]
    prompt  = data.get('prompt', '')
    model   = data.get('model', advanced_config['ollama']['defaultModel'])
    tasks[task_id] = {
        "id": task_id, "status": "created", "node": None,
        "payload": {"prompt": prompt, "model": model},
    }
    push_log('system', f'Task created: {task_id}', detail=f'prompt={prompt[:80]}')
    return jsonify({"message": "Task created", "task_id": task_id}), 201

@app.route('/task/assign', methods=['POST'])
def assign_task():
    data    = request.get_json(force=True, silent=True) or {}
    task_id = data.get('task_id')
    if not task_id or task_id not in tasks:
        return jsonify({"error": "Task not found"}), 404
    active = [n for n in _mesh_nodes.values() if n.get("status") == "active"]
    if not active:
        return jsonify({"error": "No active nodes in mesh"}), 503
    selected = active[0]
    endpoint = selected["endpoint"]
    node_id  = selected["node_id"]
    task = tasks[task_id]
    task["status"] = "assigned"
    task["node"]   = node_id
    tid = str(uuid.uuid4())[:8]
    push_log('inter_node_message', f'Task {task_id} → {node_id}',
             json.dumps(task), target=node_id, status='pending', trace_id=tid)
    try:
        url = endpoint if endpoint.startswith('http') else f'http://{endpoint}'
        r = requests.post(f"{url}/execute", json=task, timeout=120)
        task["result"] = r.json()
        task["status"] = "done"
        push_log('inter_node_message', f'Task {task_id} done on {node_id}',
                 json.dumps(task.get("result", {})),
                 source=node_id, target='control-plane', status='success', trace_id=tid)
    except Exception as e:
        push_log('inter_node_message', f'Task {task_id} failed on {node_id}',
                 str(e), source=node_id, status='failed', trace_id=tid)
        return jsonify({"error": str(e)}), 500
    return jsonify({"message": "done", "task": task})

@app.route('/tasks')
def get_tasks():
    return jsonify(tasks)

# ── HEARTBEAT LOOP ────────────────────────────────────────
DREAM_PHRASES = [
    "autonomous planning cycle initiated",
    "memory consolidation phase started",
    "sub-task decomposition in progress",
    "latent space exploration #{}",
    "tool-use reflection completed",
    "goal re-prioritization triggered",
    "associative memory update: {} new links",
    "dream cycle #{} — context window cleared",
    "semantic embedding refresh triggered",
    "long-term memory write #{} completed",
]

CHAT_PHRASES = [
    ("can you handle a summarize task?",  "yes, {} slots free"),
    ("what is your current model?",        "running {}"),
    ("sync memory snapshot?",              "snapshot ready — {} KB"),
    ("queue depth?",                       "depth {} — capacity normal"),
    ("ready for next task?",               "ready, latency {}ms"),
    ("resource usage?",                    "cpu {}% — within limits"),
    ("can you accept a classification task?", "affirmative, priority slot {} open"),
]

def _ep_to_url(ep: str) -> str:
    if ep.startswith("http://") or ep.startswith("https://"):
        return ep.rstrip("/")
    return f"http://{ep}"

def _poll_mesh_nodes():
    """Interroga /status di ogni endpoint noto. Aggiorna _mesh_nodes.
    Gli endpoint registrati via /mesh/announce sono già in _known_endpoints.
    """
    discovered = set()
    for ep in list(_known_endpoints):
        try:
            r = requests.get(f"{_ep_to_url(ep)}/status", timeout=3)
            if r.status_code == 200:
                info = r.json()
                info["endpoint"]  = ep
                info["status"]    = "active"
                info["last_seen"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                _mesh_nodes[ep]   = info
                discovered.add(ep)
                # PEX leggero
                try:
                    rp = requests.get(f"{_ep_to_url(ep)}/peers", timeout=2)
                    for peer in rp.json().get("peers", []):
                        pep = peer.get("endpoint", "")
                        if pep and pep not in _mesh_nodes:
                            _known_endpoints.add(pep)
                except Exception:
                    pass
        except Exception:
            if ep in _mesh_nodes:
                _mesh_nodes[ep]["status"] = "unreachable"
    return [_mesh_nodes[ep] for ep in discovered]


def heartbeat_loop():
    time.sleep(3)
    push_log('system', 'Control-plane v0.2 started',
             detail=f'port=8085 | nodes={list(_known_endpoints)}', status='info')
    hb_state["running"] = True

    while True:
        cycle = hb_state["cycle"] + 1
        hb_state["cycle"]     = cycle
        hb_state["last_tick"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"

        active = _poll_mesh_nodes()
        hb_state["nodes_seen"] = [n.get("node_id", n.get("endpoint", "?"))[:12] for n in active]

        for node in active:
            nid = node.get("node_id", node.get("endpoint", "unknown"))[:12]
            ep  = node.get("endpoint", "")
            tid = str(uuid.uuid4())[:8]
            try:
                t0  = time.time()
                requests.get(f"{_ep_to_url(ep)}/health", timeout=2)
                lat = int((time.time() - t0) * 1000)
                push_log('connection_test', f'HB#{cycle} ping OK → {nid}',
                         f'latency: {lat}ms | tier: {node.get("tier","?")} | endpoint: {ep}',
                         source='control-plane', target=nid, status='success', trace_id=tid)
                hb_state["last_conn"] = hb_state["last_tick"]
            except Exception as e:
                push_log('connection_test', f'HB#{cycle} ping FAILED → {nid}',
                         str(e), source='control-plane', target=nid, status='failed', trace_id=tid)

        if cycle % 3 == 0:
            pool = [n.get("node_id", n.get("endpoint", "node-sim"))[:16] for n in active] or ["node-sim"]
            nid  = random.choice(pool)
            phrase = random.choice(DREAM_PHRASES).format(random.randint(1, 99))
            push_log('dream', f'{nid}: {phrase}', f'cycle={cycle}', source=nid, status='info')
            hb_state["last_dream"] = hb_state["last_tick"]

        if cycle % 5 == 0:
            pool = [n.get("node_id", n.get("endpoint", ""))[:16] for n in active]
            if len(pool) < 2:
                pool = (pool + ["node-sim"])[:2]
            src, dst = random.sample(pool, 2)
            q, a_tpl = random.choice(CHAT_PHRASES)
            answer   = a_tpl.format(random.randint(1, 8))
            tid = str(uuid.uuid4())[:8]
            push_log('node_chat', f'{src} → {dst}: "{q}"',
                     f'cycle={cycle}', source=src, target=dst, status='info', trace_id=tid)
            push_log('node_chat', f'{dst} → {src}: "{answer}"',
                     f'reply to {tid}', source=dst, target=src, status='info', trace_id=tid)
            hb_state["last_chat"] = hb_state["last_tick"]

        time.sleep(15)


# ── DASHBOARD HTML (invariata) ────────────────────────────
# (riutilizza la stessa DASHBOARD_HTML del commit precedente)
DASHBOARD_HTML = open(
    os.path.join(os.path.dirname(__file__), "dashboard.html"), "r"
).read() if os.path.exists(
    os.path.join(os.path.dirname(__file__), "dashboard.html")
) else "<h1>Dashboard not found</h1>"

@app.route('/dashboard')
def dashboard():
    return DASHBOARD_HTML

# ── MAIN ──────────────────────────────────────────────────
def main():
    print("[control-plane] v0.2 starting on :8085")
    print(f"[control-plane] known endpoints: {_known_endpoints}")
    hb = threading.Thread(target=heartbeat_loop, daemon=True)
    hb.start()
    app.run(host="0.0.0.0", port=8085)

if __name__ == "__main__":
    main()
