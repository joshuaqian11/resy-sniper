import { Link, useLocation } from "react-router-dom";

export function NavBar() {
  const { pathname } = useLocation();
  const link = (to: string, label: string) => (
    <Link
      to={to}
      className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${pathname === to ? "bg-[#2a2a35] text-white" : "text-gray-400 hover:text-white hover:bg-[#1e1e28]"}`}
    >
      {label}
    </Link>
  );
  return (
    <nav className="bg-[#1a1a23] border-b border-[#2a2a35] px-6 py-3 flex items-center gap-2">
      <span className="text-white font-bold mr-4 text-lg">Resy Bot</span>
      {link("/", "Dashboard")}
      {link("/add", "Add Target")}
      {link("/settings", "Settings")}
    </nav>
  );
}
