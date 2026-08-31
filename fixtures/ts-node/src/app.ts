// --- POSITIVE: express endpoints (explicit app./router. receivers) ---
import express from "express";

const app = express();

app.get("/orders", (_req, res) => res.json([]));
app.post("/orders", (req, res) => res.json(req.body));
app.delete("/orders/:id", (req, res) => res.json({}));

// --- NEGATIVE: non-HTTP calls with similar shapes must NOT match ---
const cache = { get: (_k: string) => 1, post: (_k: string) => 2 };
cache.get("orders");
cache.post("orders");
