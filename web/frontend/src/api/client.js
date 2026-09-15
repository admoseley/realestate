import axios from "axios";

// "/api" is same-origin both in production (Static Web Apps proxies it to the
// API container) and in development (the Vite proxy forwards it to
// localhost:8000). VITE_API_URL only exists to point a build at an API on
// another origin.
export const API_BASE = import.meta.env.VITE_API_URL || "/api";

const api = axios.create({ baseURL: API_BASE });

/** Resolve after `ms`, or reject with the abort reason if `signal` aborts first. */
export function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const onAbort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

export const isAbortError = (err) => axios.isCancel(err) || err?.name === "AbortError";

// ── Database wake-up ─────────────────────────────────────────────────────────
// The Azure SQL free-offer database pauses when idle. The API retries for
// about 25 seconds while it resumes, then answers 503 with a Retry-After
// header. Those requests are retried here after the suggested delay, and a
// banner (Layout) explains the wait. A 503 *without* Retry-After, such as
// "email sharing is not configured", is a real error and fails immediately.
//
// Resuming usually takes well under a minute, and each 503 already includes
// the API's own retrying, so a handful of attempts covers a slow resume
// without leaving a page hanging indefinitely.
const MAX_WAKE_RETRIES = 5;
const MAX_RETRY_DELAY_SECONDS = 30;

let wakingRequests = 0;
const wakingListeners = new Set();

function changeWakingRequests(delta) {
  wakingRequests += delta;
  wakingListeners.forEach(listener => listener());
}

/** Subscribe to wake-up state changes (for useSyncExternalStore). */
export function subscribeDatabaseWaking(listener) {
  wakingListeners.add(listener);
  return () => wakingListeners.delete(listener);
}

/** True while any request is waiting for the database to resume. */
export const isDatabaseWaking = () => wakingRequests > 0;

api.interceptors.response.use(undefined, async (error) => {
  const { config, response } = error;
  const retryAfter = response?.status === 503 ? response.headers?.["retry-after"] : undefined;
  if (!config || retryAfter === undefined) throw error;

  const attempt = (config.wakeRetries ?? 0) + 1;
  if (attempt > MAX_WAKE_RETRIES) throw error;
  config.wakeRetries = attempt;

  // Retries nest: each retry's failure re-enters this handler. Only the
  // outermost attempt counts toward the banner, so one slow request shows it
  // once and hides it when that request finally settles either way.
  if (attempt === 1) changeWakingRequests(1);
  try {
    const seconds = Math.min(Number(retryAfter) || 5, MAX_RETRY_DELAY_SECONDS);
    await sleep(seconds * 1000, config.signal);
    return await api(config);
  } finally {
    if (attempt === 1) changeWakingRequests(-1);
  }
});

/** Start resuming the database as the app loads, so it's likely ready by the
 * time a page needs data. Failures are ignored; real requests report their own. */
export const warmUpDatabase = () => api.get("/health/db").catch(() => {});

// ── Background jobs ──────────────────────────────────────────────────────────
// Sheriff-sale analysis, spot checks, and shares return {job_id} immediately
// and do their work in the background, because Static Web Apps cuts proxied
// API requests off after 45 seconds. Results are read by polling the job.

const POLL_INTERVAL_MS = 2000;
// Consecutive failed polls (network blips, the API restarting) before giving up.
const MAX_POLL_FAILURES = 10;

export class JobFailedError extends Error {
  constructor(job) {
    super(job.message || "The job failed.");
    this.name = "JobFailedError";
    this.job = job;
  }
}

export const pollJob = (jobId, signal) =>
  api.get(`/jobs/${jobId}`, { signal }).then(r => r.data);

/**
 * Poll a job until it finishes, calling `onUpdate` with each status.
 *
 * Polls run one at a time: the next is scheduled only after the previous one
 * answers. A setInterval loop would stack up overlapping requests whenever one
 * is held up waiting for the database to wake.
 *
 * Resolves with the finished job. Rejects with JobFailedError if the job
 * failed, or with an abort error once `signal` aborts (e.g. on unmount).
 */
export async function waitForJob(jobId, { onUpdate, signal } = {}) {
  let failures = 0;
  for (;;) {
    await sleep(POLL_INTERVAL_MS, signal);
    let job;
    try {
      job = await pollJob(jobId, signal);
    } catch (err) {
      // A 404 means the job no longer exists, so polling again can't help.
      if (isAbortError(err) || err.response?.status === 404 || ++failures >= MAX_POLL_FAILURES) {
        throw err;
      }
      continue;
    }
    failures = 0;
    onUpdate?.(job);
    if (job.status === "done") return job;
    if (job.status === "error") throw new JobFailedError(job);
  }
}

/** A readable message for a failed request or job. */
export function describeError(err, fallback = "Something went wrong. Please try again.") {
  if (err instanceof JobFailedError) return err.message;
  const detail = err.response?.data?.detail;
  if (detail) {
    return `Error ${err.response.status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`;
  }
  return err.message ? `Error: ${err.message}` : fallback;
}

// ── Endpoints ────────────────────────────────────────────────────────────────

/** Upload a sheriff-sale PDF. Resolves with {job_id}. */
export const sheriffSaleUpload = (file, enrich = true) => {
  const form = new FormData();
  form.append("file", file);
  form.append("enrich", enrich);
  return api.post("/sheriff-sale/upload", form).then(r => r.data);
};

/** Queue a spot check. Resolves with {job_id}; the finished job has
 * report_id and result = {deal, warning}. */
export const runSpotCheck = (payload) =>
  api.post("/spot-check", payload).then(r => r.data);

export const listReports = (skip = 0, limit = 50) =>
  api.get("/reports", { params: { skip, limit } }).then(r => r.data);

export const getReport = (id) =>
  api.get(`/reports/${id}`).then(r => r.data);

export const deleteReport = (id) =>
  api.delete(`/reports/${id}`);

export const pdfUrl = (id) => `${API_BASE}/reports/${id}/pdf`;

export const debugAnalyzePdf = async (file) => {
  const form = new FormData();
  form.append("file", file);
  const resp = await api.post("/debug/analyze-pdf", form, { responseType: "blob" });
  const url  = URL.createObjectURL(new Blob([resp.data], { type: "text/plain" }));
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `sheriff_debug_${Date.now()}.txt`;
  a.click();
  URL.revokeObjectURL(url);
};

/** Email one deal: {recipient_name, recipient_email, sender_name?, note?, sale_id}.
 * Resolves with {job_id}. The server loads the deal itself by sale_id. */
export const shareProperty = (payload) =>
  api.post("/share/property", payload).then(r => r.data);

/** Email several deals: like shareProperty, with `sale_ids` (at most 100). */
export const shareFavorites = (payload) =>
  api.post("/share/favorites", payload).then(r => r.data);

export const listDeals = (skip = 0, limit = 500, source = null) => {
  const params = { skip, limit };
  if (source) params.source = source;
  return api.get("/deals", { params }).then(r => r.data);
};

export const clearDeals = (source = null) => {
  const params = source ? { source } : {};
  return api.delete("/deals", { params }).then(r => r.data);
};

export const updateDealAddress = (saleId, address) =>
  api.patch(`/deals/${encodeURIComponent(saleId)}/address`, { address }).then(r => r.data);

export default api;
