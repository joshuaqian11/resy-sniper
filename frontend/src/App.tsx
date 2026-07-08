import { BrowserRouter, Routes, Route } from "react-router-dom";
import { NavBar } from "./components/NavBar";
import { TargetsPage } from "./pages/TargetsPage";
import { AddTargetPage } from "./pages/AddTargetPage";
import { SettingsPage } from "./pages/SettingsPage";

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-[#141419] text-gray-300">
        <NavBar />
        <Routes>
          <Route path="/" element={<TargetsPage />} />
          <Route path="/add" element={<AddTargetPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
