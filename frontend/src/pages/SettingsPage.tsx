import { useEffect, useState } from "react";
import { api, AppSettings } from "../api";

const EMPTY: AppSettings = {
  resy_api_key: "", resy_auth_token: "",
  twilio_account_sid: "", twilio_auth_token: "",
  twilio_from: "", phone_number: "",
};

export function SettingsPage() {
  const [form, setForm] = useState<AppSettings>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.settings.get().then(setForm).catch(() => setError("Failed to load settings"));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true); setError(""); setSaved(false);
    try {
      await api.settings.update(form);
      setSaved(true);
    } catch {
      setError("Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  const field = (label: string, key: keyof AppSettings, type = "text") => (
    <div className="flex flex-col gap-1">
      <label htmlFor={key} className="text-sm font-medium text-gray-700">{label}</label>
      <input id={key} type={type} className="border rounded px-3 py-1.5 text-sm font-mono"
        value={form[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
    </div>
  );

  return (
    <div className="max-w-xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>
      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}
      {saved && <p className="text-green-600 text-sm mb-4">Settings saved.</p>}
      <form onSubmit={handleSubmit} className="bg-white border rounded-lg p-5 space-y-4 shadow-sm">
        <h2 className="font-semibold text-gray-800">Resy Credentials</h2>
        <p className="text-xs text-gray-500">Find these in your browser's Network tab when browsing Resy.</p>
        {field("API Key", "resy_api_key")}
        {field("Auth Token", "resy_auth_token")}
        <h2 className="font-semibold text-gray-800 pt-2">Twilio (SMS)</h2>
        {field("Account SID", "twilio_account_sid")}
        {field("Auth Token", "twilio_auth_token")}
        {field("From Number", "twilio_from", "tel")}
        {field("Your Phone Number", "phone_number", "tel")}
        <button type="submit" disabled={saving}
          className="bg-indigo-600 text-white px-5 py-2 rounded text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
          {saving ? "Saving…" : "Save Settings"}
        </button>
      </form>
    </div>
  );
}
