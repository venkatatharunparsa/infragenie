import axios from "axios";

const BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";
const API_KEY  = process.env.REACT_APP_API_KEY  || "";

const client = axios.create({
  baseURL: BASE_URL,
  headers: {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,
  },
  timeout: 600_000, // 10 minutes for long Terraform applies
});

/** POST /api/deploy */
export async function deployInfra(userInput, options = {}) {
  const { data } = await client.post("/api/deploy", {
    user_input:  userInput,
    request_id:  options.requestId,
    environment: options.environment || "dev",
    user_id:     options.userId      || "dashboard",
  });
  return data;
}

/** GET /api/history */
export async function getHistory(limit = 20, severity = null) {
  const params = { limit };
  if (severity) params.severity = severity;
  const { data } = await client.get("/api/history", { params });
  return data;
}

/** GET /api/resources */
export async function getResources() {
  const { data } = await client.get("/api/resources");
  return data;
}

/** GET /api/cost */
export async function getCost() {
  const { data } = await client.get("/api/cost");
  return data;
}

/** POST /api/approve/:requestId */
export async function approveAction(requestId, approved = true) {
  const { data } = await client.post(`/api/approve/${requestId}`, { approved });
  return data;
}

/** GET /health (no auth) */
export async function getHealth() {
  const { data } = await axios.get(`${BASE_URL}/health`);
  return data;
}

export default client;
