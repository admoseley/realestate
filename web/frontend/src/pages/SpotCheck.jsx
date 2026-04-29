import { useState } from "react";
import { runSpotCheck, pdfUrl } from "../api/client";
import PropertyCard from "../components/PropertyCard";

export default function SpotCheck() {
  const [form, setForm] = useState({
    address: "", price: "", fmv: "", sqft: "", year: "", beds: "", baths: "",
    parcel: "", municipality: "", no_lookup: false,
  });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);
  const [result,  setResult]  = useState(null);

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const payload = {
        address:      form.address,
        price:        parseFloat(form.price),
        fmv:          form.fmv   ? parseFloat(form.fmv)   : null,
        sqft:         form.sqft  ? parseInt(form.sqft)     : null,
        year:         form.year  ? parseInt(form.year)     : null,
        beds:         form.beds  ? parseInt(form.beds)     : null,
        baths:        form.baths ? parseFloat(form.baths)  : null,
        parcel:       form.parcel       || null,
        municipality: form.municipality || null,
        no_lookup:    form.no_lookup,
      };
      const data = await runSpotCheck(payload);
      setResult(data);
    } catch (err) {
      setError(err.response?.data?.detail || "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  const Field = ({ label, name, type = "text", placeholder = "" }) => (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
      <input
        type={type}
        value={form[name]}
        onChange={set(name)}
        placeholder={placeholder}
        className="w-full border border-brand-line rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-orange"
      />
    </div>
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-brand-charcoal">Property Spot Check</h1>
        <p className="text-sm text-gray-500 mt-1">Full investment analysis on any single property</p>
      </div>

      <form onSubmit={submit} className="bg-white rounded-xl border border-brand-line p-6 space-y-5">
        {/* Address — large */}
        <div>
          <label className="block text-sm font-semibold text-brand-charcoal mb-1">Property Address</label>
          <input
            type="text"
            value={form.address}
            onChange={set("address")}
            required
            placeholder="e.g. 124 Preston Dr N, Braddock, PA 15104"
            className="w-full border-2 border-brand-line rounded-xl px-4 py-3 text-base focus:outline-none focus:border-brand-orange"
          />
        </div>

        {/* Price */}
        <div className="max-w-xs">
          <label className="block text-sm font-semibold text-brand-charcoal mb-1">Purchase / Listed Price ($)</label>
          <input
            type="number"
            value={form.price}
            onChange={set("price")}
            required
            min={0}
            placeholder="e.g. 58000"
            className="w-full border border-brand-line rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-orange"
          />
        </div>

        {/* Auto-lookup toggle */}
        <label className="flex items-center gap-3 cursor-pointer">
          <div
            onClick={() => setForm(f => ({ ...f, no_lookup: !f.no_lookup }))}
            className={`w-10 h-6 rounded-full transition-colors ${!form.no_lookup ? "bg-brand-orange" : "bg-brand-line"} relative`}
          >
            <span className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-all ${!form.no_lookup ? "left-5" : "left-1"}`} />
          </div>
          <span className="text-sm text-gray-600">Auto-lookup property data (WPRDC / Allegheny County)</span>
        </label>

        {/* Advanced */}
        <button type="button" onClick={() => setShowAdvanced(a => !a)}
          className="text-sm text-brand-orange font-semibold hover:underline">
          {showAdvanced ? "▲ Hide" : "▼ Show"} Advanced Options
        </button>

        {showAdvanced && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 border-t border-brand-line pt-4">
            <Field label="FMV Override ($)"   name="fmv"          type="number" />
            <Field label="Sqft"               name="sqft"         type="number" />
            <Field label="Year Built"         name="year"         type="number" />
            <Field label="Bedrooms"           name="beds"         type="number" />
            <Field label="Bathrooms"          name="baths"        type="number" />
            <Field label="Parcel ID"          name="parcel"       />
            <div className="col-span-2 md:col-span-3">
              <Field label="Municipality"     name="municipality" />
            </div>
          </div>
        )}

        <button
          type="submit"
          disabled={loading || !form.address || !form.price}
          className="bg-brand-orange text-white font-bold px-8 py-3 rounded-xl disabled:opacity-40 hover:bg-brand-dark transition-colors flex items-center gap-2"
        >
          {loading && <span className="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />}
          {loading ? "Analyzing…" : "Analyze Property"}
        </button>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">{error}</div>
        )}
      </form>

      {result && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-brand-charcoal">Analysis Results</h2>
            <a href={pdfUrl(result.report_id)} target="_blank" rel="noreferrer"
              className="bg-brand-charcoal text-white text-sm font-semibold px-4 py-2 rounded-lg hover:bg-black transition-colors">
              ↓ Download PDF
            </a>
          </div>
          {result.warning && (
            <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-4 py-3 text-sm">
              <span className="text-lg leading-none flex-shrink-0">⚠</span>
              <span>{result.warning}</span>
            </div>
          )}
          <PropertyCard deal={result.deal} />
        </div>
      )}
    </div>
  );
}
