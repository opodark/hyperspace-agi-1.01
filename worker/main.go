package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"time"
)

type Task struct {
	ID     string `json:"id"`
	Status string `json:"status"`
	Worker string `json:"worker"`
}

func main() {
	workerID := os.Getenv("WORKER_ID")
	if workerID == "" {
		log.Fatal("WORKER_ID environment variable is not set")
	}

	register(workerID)

	go func() {
		for {
			heartbeat(workerID)
			time.Sleep(5 * time.Second)
		}
	}()

	http.HandleFunc("/execute", func(w http.ResponseWriter, r *http.Request) {
		var task Task
		err := json.NewDecoder(r.Body).Decode(&task)
		if err != nil {
			http.Error(w, "invalid task", http.StatusBadRequest)
			return
		}
		log.Printf("Executing task: %s", task.ID)
		task.Status = "done"
		resp := map[string]interface{}{
			"worker":  workerID,
			"task_id": task.ID,
			"status":  "done",
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	})

	log.Println("Worker running on :8084")
	log.Fatal(http.ListenAndServe(":8084", nil))
}

func register(workerID string) {
	_, err := http.Post(
		"http://authority:8080/register",
		"application/json",
		http.NoBody,
	)
	if err != nil {
		log.Println("register failed:", err)
	}
}

func heartbeat(workerID string) {
	_, err := http.Post(
		"http://authority:8080/heartbeat",
		"application/json",
		http.NoBody,
	)
	if err != nil {
		log.Println("heartbeat failed:", err)
	}
}
