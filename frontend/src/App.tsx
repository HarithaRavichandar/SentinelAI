import { Routes, Route } from "react-router-dom";
import { AlertStatsProvider } from "./components/AlertStatsContext";
import Sidebar from "./components/Sidebar";
import Dashboard from "./components/Dashboard";
import TriageView from "./components/TriageView";
import LiveCapture from "./components/LiveCapture";
import ChatView from "./components/ChatView";
import BatchUpload from "./components/BatchUpload";

export default function App() {
  return (
    <AlertStatsProvider>
      <Sidebar />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/triage" element={<TriageView />} />
          <Route path="/live" element={<LiveCapture />} />
          <Route path="/chat" element={<ChatView />} />
          <Route path="/batch" element={<BatchUpload />} />
        </Routes>
      </main>
    </AlertStatsProvider>
  );
}