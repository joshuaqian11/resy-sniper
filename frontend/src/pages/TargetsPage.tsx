import { useEffect, useState } from "react";
import type { InputHTMLAttributes } from "react";
import { api, Target, TargetCreate } from "../api";
import { StatusBadge } from "../components/StatusBadge";

const EMPTY_FORM: TargetCreate = {
  venue_id: "", venue_name: "", date: "", party_size: 2,
  opening_time: "", preferred_start: "", preferred_end: "",
};

export function TargetsPage() {
  const [targets, setTargets] = useState<Target[]>([]);
  const [form, setForm] = useState<TargetCreate>(EMPTY_FORM);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    try { setTargets(await api.targets.list()); } catch { setError("Failed to load targets"); }
  }

  useEffect(() => {
    let cancelled = false;
    api.targets.list()
      .then(data => { if (!cancelled) setTargets(data); })
      .catch(() => { if (!cancelled) setError("Failed to load targets"); });
    return () => { cancelled = true; };
  }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setAdding(true);
    setError("");
    try {
      await api.targets.add(form);
      setForm(EMPTY_FORM);
      await load();
    } catch {
      setError("Failed to add target");
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(id: number) {
    try { await api.targets.delete(id); await load(); }
    catch { setError("Failed to delete target (may not be pending)"); }
  }

  const field = (label: string, key: keyof TargetCreate, type = "text", extra?: InputHTMLAttributes<HTMLInputElement>) => (
    <div className="flex flex-col gap-1">
      <label htmlFor={key} className="text-sm font-medium text-gray-700">{label}</label>
      <input
        id={key}
        type={type}
        className="border rounded px-3 py-1.5 text-sm"
        value={String(form[key] ?? "")}
        onChange={e => setForm(f => ({ ...f, [key]: type === "number" ? Number(e.target.value) : e.target.value }))}
        {...extra}
      />
    </div>
  );

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-8">
      <h1 className="text-2xl font-bold">Snipe Targets</h1>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <form onSubmit={handleAdd} className="bg-white border rounded-lg p-5 grid grid-cols-2 gap-4 shadow-sm">
        <h2 className="col-span-2 font-semibold text-gray-800">Add Target</h2>
        {field("Venue ID", "venue_id", "text", { required: true })}
        {field("Venue Name", "venue_name", "text", { required: true })}
        {field("Date", "date", "date", { required: true })}
        {field("Party Size", "party_size", "number", { min: 1, max: 20, required: true })}
        {field("Opening Time (local)", "opening_time", "datetime-local", { required: true })}
        <div className="flex flex-col gap-1">
          <label htmlFor="preferred_start" className="text-sm font-medium text-gray-700">Preferred Start (optional)</label>
          <input id="preferred_start" type="time" className="border rounded px-3 py-1.5 text-sm"
            value={form.preferred_start ?? ""}
            onChange={e => setForm(f => ({ ...f, preferred_start: e.target.value }))} />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="preferred_end" className="text-sm font-medium text-gray-700">Preferred End (optional)</label>
          <input id="preferred_end" type="time" className="border rounded px-3 py-1.5 text-sm"
            value={form.preferred_end ?? ""}
            onChange={e => setForm(f => ({ ...f, preferred_end: e.target.value }))} />
        </div>
        <div className="col-span-2">
          <button type="submit" disabled={adding}
            className="bg-indigo-600 text-white px-5 py-2 rounded text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
            {adding ? "Adding…" : "Add Target"}
          </button>
        </div>
      </form>

      <div className="space-y-3">
        {targets.length === 0 && <p className="text-gray-500 text-sm">No targets yet.</p>}
        {targets.map(t => (
          <div key={t.id} className="bg-white border rounded-lg p-4 flex items-center justify-between shadow-sm">
            <div>
              <p className="font-medium">{t.venue_name}</p>
              <p className="text-sm text-gray-500">{t.date} · Party of {t.party_size} · Opens {t.opening_time}</p>
              {t.booked_at && <p className="text-xs text-green-600 mt-1">Booked at {t.booked_at}</p>}
            </div>
            <div className="flex items-center gap-3">
              <StatusBadge status={t.status} />
              {t.status === "pending" && (
                <button type="button" onClick={() => handleDelete(t.id)}
                  className="text-red-500 hover:text-red-700 text-sm">Delete</button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
