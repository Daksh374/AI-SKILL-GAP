import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Api, errorMessage } from "../api/client.js";

const AppContext = createContext(null);

function readLS(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function writeLS(key, value) {
  try {
    if (value === null || value === undefined) localStorage.removeItem(key);
    else localStorage.setItem(key, String(value));
  } catch {
    /* storage unavailable: state still works for this tab */
  }
}

export function AppProvider({ children }) {
  const [health, setHealth] = useState(null);
  const [roles, setRoles] = useState([]);
  const [resumes, setResumes] = useState([]);
  const [resumeId, setResumeId] = useState(() => Number(readLS("career_engine_resume")) || null);
  const [resume, setResume] = useState(null); // { resume, profile, careers }
  const [role, setRoleState] = useState(() => readLS("career_engine_role"));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    Api.health().then(setHealth).catch((e) => setError(errorMessage(e)));
    Api.roles().then(setRoles).catch(() => {});
    Api.listResumes().then(setResumes).catch(() => {});
  }, []);

  const loadResume = useCallback(async (id) => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await Api.getResume(id);
      setResume(data);
      setResumeId(id);
      writeLS("career_engine_resume", id);
      setError(null);
    } catch (e) {
      if (e?.response?.status === 404) {
        setResume(null);
        setResumeId(null);
        writeLS("career_engine_resume", null);
      } else setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (resumeId && !resume) loadResume(resumeId);
  }, [resumeId, resume, loadResume]);

  const setRole = useCallback((r) => {
    setRoleState(r);
    writeLS("career_engine_role", r);
  }, []);

  const uploadResume = useCallback(
    async (file, onProgress) => {
      const data = await Api.uploadResume(file, onProgress);
      setResume(data);
      setResumeId(data.resume.id);
      writeLS("career_engine_resume", data.resume.id);
      setRole(data.careers.predictions[0]?.role || null);
      Api.listResumes().then(setResumes).catch(() => {});
      return data;
    },
    [setRole]
  );

  const deleteResume = useCallback(
    async (id) => {
      await Api.deleteResume(id);
      const list = await Api.listResumes();
      setResumes(list);
      if (id === resumeId) {
        setResume(null);
        setResumeId(null);
        writeLS("career_engine_resume", null);
      }
    },
    [resumeId]
  );

  // Fall back to the model's top role if the stored role is missing/invalid.
  const activeRole = useMemo(() => {
    const valid = roles.some((r) => r.role === role);
    if (role && (valid || roles.length === 0)) return role;
    return resume?.careers?.predictions?.[0]?.role || roles[0]?.role || null;
  }, [role, roles, resume]);

  const value = {
    health, roles, resumes, resumeId, resume, role: activeRole, setRole, loading, error, setError,
    loadResume, uploadResume, deleteResume,
  };
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
