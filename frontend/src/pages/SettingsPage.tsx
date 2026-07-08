import { useEffect, useState } from "react";
import { api } from "../api";
import type { AppSettings } from "../api";

const EMPTY: AppSettings = {
  resy_api_key: "", resy_email: "", resy_password: "", resy_cookies: "",
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
    <div className="flex flex-col gap-1.5">
      <label htmlFor={key} className="text-sm text-gray-400">{label}</label>
      <input id={key} type={type} className="bg-[#141419] border border-[#2a2a35] rounded-md px-3 py-2 text-sm font-mono text-white placeholder-gray-600 focus:border-green-500 focus:outline-none focus:ring-1 focus:ring-green-500"
        value={form[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
    </div>
  );

  return (
    <div className="max-w-2xl mx-auto p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-sm text-gray-500 mt-1">Configure your Resy and Twilio credentials.</p>
      </div>
      {error && <p className="text-red-400 text-sm mb-4">{error}</p>}
      {saved && <p className="text-green-400 text-sm mb-4">Settings saved.</p>}
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="bg-[#1a1a23] border border-[#2a2a35] rounded-xl p-6 space-y-4">
          <div>
            <h2 className="font-semibold text-white">Resy Credentials</h2>
            <p className="text-xs text-gray-500 mt-1">Your Resy login — the bot will automatically refresh its session token.</p>
          </div>
          {field("API Key", "resy_api_key")}
          {field("Email", "resy_email", "email")}
          {field("Password", "resy_password", "password")}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="resy_cookies" className="text-sm text-gray-400">Browser Cookies</label>
            <p className="text-xs text-gray-500">In Chrome DevTools → Network tab, find any request to api.resy.com, right-click → Copy → Copy as cURL, then paste the Cookie header value here. Required to bypass bot protection. Valid for ~1 year.</p>
            <textarea id="resy_cookies" rows={3}
              className="bg-[#141419] border border-[#2a2a35] rounded-md px-3 py-2 text-sm font-mono text-white placeholder-gray-600 focus:border-green-500 focus:outline-none focus:ring-1 focus:ring-green-500"
              value={form.resy_cookies}
              onChange={e => setForm(f => ({ ...f, resy_cookies: e.target.value }))} />
          </div>
        </div>

        <div className="bg-[#1a1a23] border border-[#2a2a35] rounded-xl p-6 space-y-4">
          <h2 className="font-semibold text-white">Twilio (SMS)</h2>
          {field("Account SID", "twilio_account_sid")}
          {field("Auth Token", "twilio_auth_token")}
          {field("From Number", "twilio_from", "tel")}
          {field("Your Phone Number", "phone_number", "tel")}
        </div>

        <button type="submit" disabled={saving}
          className="bg-green-600 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-green-500 disabled:opacity-50 transition-colors">
          {saving ? "Saving…" : "Save Settings"}
        </button>
      </form>
    </div>
  );
}
