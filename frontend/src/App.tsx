import { useEffect, useState } from "react";
import { getUser, navigate } from "./api";
import Admin from "./pages/Admin";
import Clinic from "./pages/Clinic";
import Fund from "./pages/Fund";
import Patient from "./pages/Patient";
import { Login, StaffUser } from "./pages/Staff";

// Tiny router: /p/<token> (patient), /login, /clinic, /fund, /admin.
export default function App() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const on = () => setPath(window.location.pathname);
    window.addEventListener("popstate", on);
    return () => window.removeEventListener("popstate", on);
  }, []);

  const m = path.match(/^\/p\/([\w-]+)$/);
  if (m) return <Patient token={m[1]} />;

  const user = getUser<StaffUser>();
  const role = path.replace(/^\//, "");
  if (["clinic", "fund", "admin"].includes(role)) {
    if (!user) { navigate("/login"); return null; }
    if (user.role !== role) { navigate(`/${user.role}`); return null; }
    return role === "clinic" ? <Clinic /> : role === "fund" ? <Fund /> : <Admin />;
  }
  if (path === "/login" || path === "/") return <Login />;
  return <Login />;
}
