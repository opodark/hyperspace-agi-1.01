from fastapi import FastAPI
import asyncio

app = FastAPI()

worker_id = "worker-1"

@app.post("/execute")
async def execute_task(task: dict):
    print(f"[WORKER] received task: {task}")
    task_id = task.get("task_id")
    await asyncio.sleep(2)
    return {
        "worker": worker_id,
        "task_id": task_id,
        "status": "done"
    }

@app.get("/status")
def status():
    return {
        "worker_id": worker_id,
        "running": True
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8084)
