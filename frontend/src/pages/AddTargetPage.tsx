import { useState } from "react";
import type { InputHTMLAttributes } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { TargetCreate } from "../api";

const EMPTY_FORM: TargetCreate = {
  venue_id: "", venue_name: "", date: "", party_size: 2,
  opening_time: "", preferred_start: "", preferred_end: "",
};

export function AddTargetPage() {
  const [form, setForm] = useState<TargetCreate>(EMPTY_FORM);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setAdding(true);
    setError("");
    try {
      const payload = {
        ...form,
        opening_time: new Date(form.opening_time).toISOString(),
      };
      await api.targets.add(payload);
      navigate("/");
    } catch {
      setError("Failed to add target");
    } finally {
      setAdding(false);
    }
  }

  const field = (label: string, key: keyof TargetCreate, type = "text", extra?: InputHTMLAttributes<HTMLInputElement>) => (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={key} className="text-sm text-gray-400">{label}</label>
      <input
        id={key}
        type={type}
        className="bg-[#141419] border border-[#2a2a35] rounded-md px-3 py-2 text-sm text-white placeholder-gray-600 focus:border-green-500 focus:outline-none focus:ring-1 focus:ring-green-500"
        value={String(form[key] ?? "")}
        onChange={e => setForm(f => ({ ...f, [key]: type === "number" ? Number(e.target.value) : e.target.value }))}
        {...extra}
      />
    </div>
  );

  return (
    <div className="max-w-2xl mx-auto p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Add Target</h1>
        <p className="text-sm text-gray-500 mt-1">Set up a new reservation snipe.</p>
      </div>

      {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

      <form onSubmit={handleAdd} className="bg-[#1a1a23] border border-[#2a2a35] rounded-xl p-6 space-y-5">
        <div className="grid grid-cols-2 gap-4">
          {field("Venue ID", "venue_id", "text", { required: true })}
          {field("Venue Name", "venue_name", "text", { required: true })}
          {field("Date", "date", "date", { required: true })}
          {field("Party Size", "party_size", "number", { min: 1, max: 20, required: true })}
          {field("Opening Time (local)", "opening_time", "datetime-local", { required: true })}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="preferred_start" className="text-sm text-gray-400">Preferred Start (optional)</label>
            <input id="preferred_start" type="time" className="bg-[#141419] border border-[#2a2a35] rounded-md px-3 py-2 text-sm text-white placeholder-gray-600 focus:border-green-500 focus:outline-none focus:ring-1 focus:ring-green-500"
              value={form.preferred_start ?? ""}
              onChange={e => setForm(f => ({ ...f, preferred_start: e.target.value }))} />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="preferred_end" className="text-sm text-gray-400">Preferred End (optional)</label>
            <input id="preferred_end" type="time" className="bg-[#141419] border border-[#2a2a35] rounded-md px-3 py-2 text-sm text-white placeholder-gray-600 focus:border-green-500 focus:outline-none focus:ring-1 focus:ring-green-500"
              value={form.preferred_end ?? ""}
              onChange={e => setForm(f => ({ ...f, preferred_end: e.target.value }))} />
          </div>
        </div>
        <div className="pt-2">
          <button type="submit" disabled={adding}
            className="bg-green-600 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-green-500 disabled:opacity-50 transition-colors">
            {adding ? "Adding…" : "Add Target"}
          </button>
        </div>
      </form>
    </div>
  );
}
