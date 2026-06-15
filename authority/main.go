package main

import (
    "encoding/json"
    "fmt"
    "github.com/gorilla/mux"
    "log"
    "net/http"
    "sync"
)

type Node struct {
    ID     string `json:"id"`
    Status string `json:"status"`
}

var (
    nodes = make(map[string]Node)
    lock  sync.Mutex
)

func main() {
    router := mux.NewRouter()
    router.HandleFunc("/register", register).Methods("POST")
    router.HandleFunc("/heartbeat", heartbeat).Methods("POST")
    router.HandleFunc("/nodes", listNodes).Methods("GET")

    log.Fatal(http.ListenAndServe(":8080", router))
}

func register(w http.ResponseWriter, r *http.Request) {
    var node Node
    err := json.NewDecoder(r.Body).Decode(&node)
    if err != nil {
        http.Error(w, "Invalid request", http.StatusBadRequest)
        return
    }
    lock.Lock()
    defer lock.Unlock()
    nodes[node.ID] = Node{ID: node.ID, Status: "active"}
    w.WriteHeader(http.StatusOK)
}

func heartbeat(w http.ResponseWriter, r *http.Request) {
    var node Node
    err := json.NewDecoder(r.Body).Decode(&node)
    if err != nil {
        http.Error(w, "Invalid request", http.StatusBadRequest)
        return
    }
    lock.Lock()
    defer lock.Unlock()
    nodes[node.ID] = Node{ID: node.ID, Status: "active"}
    w.WriteHeader(http.StatusOK)
}

func listNodes(w http.ResponseWriter, r *http.Request) {
    lock.Lock()
    defer lock.Unlock()
    nodeList := make([]Node, 0, len(nodes))
    for _, node := range nodes {
        nodeList = append(nodeList, node)
    }
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(nodeList)
}

// suppress unused import warning
var _ = fmt.Sprintf
