import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import Careers from "./pages/Careers.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import LearningPath from "./pages/LearningPath.jsx";
import Market from "./pages/Market.jsx";
import ResumeAnalysis from "./pages/ResumeAnalysis.jsx";
import SkillGap from "./pages/SkillGap.jsx";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/resume" element={<ResumeAnalysis />} />
        <Route path="/careers" element={<Careers />} />
        <Route path="/skill-gap" element={<SkillGap />} />
        <Route path="/market" element={<Market />} />
        <Route path="/learning-path" element={<LearningPath />} />
        <Route path="*" element={<Dashboard />} />
      </Routes>
    </Layout>
  );
}
