# HyperSpace AGI v1.01

Framework per agenti IA autonomi basati su SLM (Small Language Models), eseguiti localmente tramite Docker e Ollama.

## Stack

| Servizio | Porta | Descrizione |
|---|---|---|
| `control-plane` | 8085 | Dashboard + API orchestrazione |
| `authority` | 8080 | Registry nodi + heartbeat |
| `worker` | 8084 | Execution worker |
| `nats` | 4222 | Event bus |

## Quick Start

```bash
git clone https://github.com/opodark/hyperspace-agi-1.01.git
cd hyperspace-agi-1.01
docker compose up -d --build
```

Dashboard: http://localhost:8085/dashboard

## Dashboard v1.01 — Features

### Tasks
- Creazione e assegnazione task ai worker tramite UI

### Log Viewer
- **Connection Tests** — handshake, latenza, esito connessione tra nodi
- **Node Communication** — messaggi inter-nodo, dispatch task, ack, retry
- **Dreams / Autonomous Tasks** — cicli di pianificazione autonoma dei nodi
- **Node Chats** — dialogo e negoziazione tra nodi
- **Authority Events** — rotazione secret, update config, reachability
- Filtri per nodo, status, full-text search
- Auto-refresh ogni 4 secondi
- Inject sample logs per test rapido

### Diagnostics
- Authority reachability test
- Node list live
- Simulate Dream event
- Simulate Node Chat

### Advanced Setup
- **Security**: Shared secret con rotate automatico
- **Authority Server**: URL, auth mode (none/token/jwt/public-key), enable/disable, test connessione
- **Network Mode**: Authority-managed | Pure Mesh (MHT — coming soon)
- **Bootstrap Peers**: configurazione peers per modalità mesh

## Struttura

```
hyperspace-agi-1.01/
├── authority/          # Node registry (FastAPI)
├── control-plane/      # Dashboard + orchestration (Flask)
├── worker/             # Task executor (FastAPI)
├── shared/             # Modelli condivisi (Node, Task, Workflow)
├── infra-ui/           # OpenWebUI compose
├── docker-compose.yml  # Stack minimo (authority + control-plane + worker + nats)
└── docker-compose-2full.yml  # Stack completo (+ postgres + 3 worker)
```

## API Reference

### Control Plane (porta 8085)

| Method | Path | Descrizione |
|---|---|---|
| GET | `/dashboard` | Dashboard HTML |
| GET | `/tasks` | Lista tasks |
| POST | `/task/create` | Crea task |
| POST | `/task/assign` | Assegna ed esegui task |
| GET | `/logs` | Stream logs (filtri: type, status, node, q) |
| POST | `/logs/add` | Aggiungi log entry |
| POST | `/logs/clear` | Svuota log |
| GET | `/config/advanced` | Leggi config avanzata |
| POST | `/config/advanced` | Salva config avanzata |
| POST | `/config/authority/test` | Test reachability authority |
| POST | `/config/secret/rotate` | Ruota shared secret |

### Authority (porta 8080)

| Method | Path | Descrizione |
|---|---|---|
| POST | `/register` | Registra nodo |
| POST | `/heartbeat` | Heartbeat nodo |
| GET | `/nodes` | Lista nodi registrati |

## Roadmap

- [ ] Mesh pura con MHT (Modular Hash Tree)
- [ ] Ollama integration per inferenza locale
- [ ] Persistenza log su SQLite
- [ ] Multi-nodo con auto-discovery
- [ ] Auth JWT tra nodi
