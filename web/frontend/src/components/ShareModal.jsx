import { useEffect, useRef, useState } from "react";
import { shareProperty, waitForJob, describeError, isAbortError } from "../api/client";

export default function ShareModal({ deal, onClose }) {
  const [recipientName,  setRecipientName]  = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [senderName,     setSenderName]     = useState("");
  const [note,           setNote]           = useState("");
  const [status,         setStatus]         = useState("idle"); // idle | sending | success | error
  const [errorMsg,       setErrorMsg]       = useState("");
  const [progress,       setProgress]       = useState("");     // job message while sending
  const abortRef = useRef(null);

  // Closing the modal stops polling. The email job itself carries on server-side.
  useEffect(() => () => abortRef.current?.abort(), []);

  const canSend = recipientName.trim() && recipientEmail.trim();

  const handleSend = async () => {
    if (!canSend) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setStatus("sending");
    setErrorMsg("");
    setProgress("");
    try {
      // Only the sale_id is sent; the server emails the analysis it has stored.
      const { job_id } = await shareProperty({
        recipient_name:  recipientName.trim(),
        recipient_email: recipientEmail.trim(),
        sender_name:     senderName.trim() || undefined,
        note:            note.trim() || undefined,
        sale_id:         deal.sale_id,
      });
      await waitForJob(job_id, { signal: controller.signal, onUpdate: job => setProgress(job.message) });
      setStatus("success");
    } catch (err) {
      if (isAbortError(err)) return;
      setErrorMsg(describeError(err, "Failed to send. Please try again."));
      setStatus("error");
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-xl border border-brand-line shadow-xl w-full max-w-md">

        <div className="flex items-center justify-between px-5 py-4 border-b border-brand-line">
          <h2 className="text-base font-bold text-brand-charcoal">Send Property Analysis</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-brand-charcoal transition-colors text-xl leading-none"
          >
            ✕
          </button>
        </div>

        {status === "success" ? (
          <div className="px-5 py-8 text-center space-y-3">
            <p className="text-3xl">✅</p>
            <p className="text-brand-charcoal font-semibold">Analysis sent!</p>
            <p className="text-sm text-gray-500">
              The PDF report for{" "}
              <span className="font-medium">{deal.address}</span> was emailed to{" "}
              <span className="font-medium">{recipientEmail}</span>.
            </p>
            <button
              onClick={onClose}
              className="mt-2 bg-brand-orange text-white font-bold px-6 py-2 rounded-lg hover:bg-brand-dark transition-colors"
            >
              Done
            </button>
          </div>
        ) : (
          <div className="px-5 py-5 space-y-4">
            <div className="bg-brand-gray rounded-lg px-4 py-3">
              <p className="text-xs text-gray-500 mb-0.5">Property</p>
              <p className="text-sm font-semibold text-brand-charcoal leading-snug">
                {deal.address}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">
                {[
                  deal.municipality,
                  deal.verdict && `Verdict: ${deal.verdict}`,
                  deal.score != null && `Score: ${deal.score}/100`,
                ].filter(Boolean).join(" · ")}
              </p>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  Recipient Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={recipientName}
                  onChange={e => setRecipientName(e.target.value)}
                  placeholder="e.g. Jane Smith"
                  className="w-full border border-brand-line rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-orange"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  Recipient Email <span className="text-red-500">*</span>
                </label>
                <input
                  type="email"
                  value={recipientEmail}
                  onChange={e => setRecipientEmail(e.target.value)}
                  placeholder="jane@example.com"
                  className="w-full border border-brand-line rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-orange"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  Your Name{" "}
                  <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <input
                  type="text"
                  value={senderName}
                  onChange={e => setSenderName(e.target.value)}
                  placeholder="e.g. Estella Wilson"
                  className="w-full border border-brand-line rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-orange"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  Add a Note{" "}
                  <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <textarea
                  value={note}
                  onChange={e => setNote(e.target.value)}
                  placeholder="Add context or a personal message for the recipient…"
                  rows={3}
                  className="w-full border border-brand-line rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-orange resize-none"
                />
              </div>
            </div>

            {status === "sending" && progress && (
              <p className="text-xs text-gray-500" role="status">{progress}</p>
            )}

            {status === "error" && (
              <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                <p className="text-xs text-red-700">{errorMsg}</p>
              </div>
            )}

            <div className="flex gap-3 pt-1">
              <button
                onClick={onClose}
                disabled={status === "sending"}
                className="flex-1 border border-brand-line text-gray-600 font-semibold py-2 rounded-lg hover:bg-brand-gray transition-colors text-sm disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSend}
                disabled={status === "sending" || !canSend}
                className="flex-1 bg-brand-orange text-white font-bold py-2 rounded-lg hover:bg-brand-dark transition-colors text-sm disabled:opacity-40"
              >
                {status === "sending" ? "Sending…" : "Send Analysis"}
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
