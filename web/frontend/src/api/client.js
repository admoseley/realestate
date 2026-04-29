import axios from "axios";

// In production VITE_API_URL = https://your-app.onrender.com/api
// In dev the Vite proxy forwards /api → localhost:8000
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api",
});

export const sheriffSaleFromUrl = (url, enrich = true) =>
  api.post("/sheriff-sale/from-url", { url, enrich }).then(r => r.data);

export const sheriffSaleUpload = (file, enrich = true) => {
  const form = new FormData();
  form.append("file", file);
  form.append("enrich", enrich);
  return api.post("/sheriff-sale/upload", form).then(r => r.data);
};

export const pollJob = (jobId) =>
  api.get(`/jobs/${jobId}`).then(r => r.data);

export const runSpotCheck = (payload) =>
  api.post("/spot-check", payload).then(r => r.data);

export const listReports = (skip = 0, limit = 50) =>
  api.get("/reports", { params: { skip, limit } }).then(r => r.data);

export const getReport = (id) =>
  api.get(`/reports/${id}`).then(r => r.data);

export const deleteReport = (id) =>
  api.delete(`/reports/${id}`);

export const pdfUrl = (id) => `${import.meta.env.VITE_API_URL || "/api"}/reports/${id}/pdf`;

export default api;
