"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";

interface ProjectContextValue {
  projects: Project[];
  project: Project | null;
  projectId: number | null;
  loading: boolean;
  error: string | null;
  selectProject: (id: number) => void;
  reloadProjects: () => Promise<Project[]>;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);
const STORAGE_KEY = "ai-pmo:selected-project";

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reloadProjects = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.listProjects();
      setProjects(list);
      setError(null);
      setProjectId((current) => {
        if (current && list.some((p) => p.id === current)) return current;
        const stored = Number(window.localStorage.getItem(STORAGE_KEY));
        if (stored && list.some((p) => p.id === stored)) return stored;
        return list[0]?.id ?? null;
      });
      return list;
    } catch (err) {
      setError(err instanceof Error ? err.message : "プロジェクトを取得できませんでした");
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reloadProjects();
  }, [reloadProjects]);

  const selectProject = useCallback((id: number) => {
    setProjectId(id);
    window.localStorage.setItem(STORAGE_KEY, String(id));
  }, []);

  const value = useMemo<ProjectContextValue>(
    () => ({
      projects,
      project: projects.find((p) => p.id === projectId) ?? null,
      projectId,
      loading,
      error,
      selectProject,
      reloadProjects,
    }),
    [projects, projectId, loading, error, selectProject, reloadProjects],
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProjects(): ProjectContextValue {
  const context = useContext(ProjectContext);
  if (!context) throw new Error("useProjects must be used inside ProjectProvider");
  return context;
}
