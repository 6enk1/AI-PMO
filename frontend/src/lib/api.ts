import type {
  AIPMOResponse,
  CategoryApplyResult,
  CategorySuggestResponse,
  ImportPlan,
  Dashboard,
  ImportAnalyze,
  ImportResult,
  Issue,
  Milestone,
  Person,
  Project,
  Task,
  TaskRisk,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) {
        message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* non JSON error body */
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function query(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "" || value === false) return;
    if (Array.isArray(value)) {
      value.forEach((item) => search.append(key, String(item)));
    } else {
      search.append(key, String(value));
    }
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  // projects
  listProjects: () => request<Project[]>("/api/projects"),
  createProject: (payload: Partial<Project>) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(payload) }),
  updateProject: (id: number, payload: Partial<Project>) =>
    request<Project>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteProject: (id: number) => request<void>(`/api/projects/${id}`, { method: "DELETE" }),
  dashboard: (id: number) => request<Dashboard>(`/api/projects/${id}/dashboard`),

  // tasks
  listTasks: (projectId: number, params: Record<string, unknown> = {}) =>
    request<Task[]>(`/api/projects/${projectId}/tasks${query(params)}`),
  createTask: (projectId: number, payload: Record<string, unknown>) =>
    request<Task>(`/api/projects/${projectId}/tasks`, { method: "POST", body: JSON.stringify(payload) }),
  updateTask: (taskId: number, payload: Record<string, unknown>) =>
    request<Task>(`/api/tasks/${taskId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteTask: (taskId: number) => request<void>(`/api/tasks/${taskId}`, { method: "DELETE" }),

  // people
  listPeople: (projectId: number) => request<Person[]>(`/api/projects/${projectId}/people`),
  createPerson: (projectId: number, payload: Record<string, unknown>) =>
    request<Person>(`/api/projects/${projectId}/people`, { method: "POST", body: JSON.stringify(payload) }),
  updatePerson: (personId: number, payload: Record<string, unknown>) =>
    request<Person>(`/api/people/${personId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deletePerson: (personId: number) => request<void>(`/api/people/${personId}`, { method: "DELETE" }),

  // issues
  listIssues: (projectId: number, params: Record<string, unknown> = {}) =>
    request<Issue[]>(`/api/projects/${projectId}/issues${query(params)}`),
  createIssue: (projectId: number, payload: Record<string, unknown>) =>
    request<Issue>(`/api/projects/${projectId}/issues`, { method: "POST", body: JSON.stringify(payload) }),
  updateIssue: (issueId: number, payload: Record<string, unknown>) =>
    request<Issue>(`/api/issues/${issueId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteIssue: (issueId: number) => request<void>(`/api/issues/${issueId}`, { method: "DELETE" }),

  // milestones
  listMilestones: (projectId: number) => request<Milestone[]>(`/api/projects/${projectId}/milestones`),
  createMilestone: (projectId: number, payload: Record<string, unknown>) =>
    request<Milestone>(`/api/projects/${projectId}/milestones`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteMilestone: (projectId: number, milestoneId: number) =>
    request<void>(`/api/projects/${projectId}/milestones/${milestoneId}`, { method: "DELETE" }),

  // ai pmo
  aiPmo: (projectId: number, useLlm = true) =>
    request<AIPMOResponse>(`/api/projects/${projectId}/ai-pmo${query({ use_llm: useLlm })}`),
  risks: (projectId: number, threshold = 40) =>
    request<TaskRisk[]>(`/api/projects/${projectId}/risks${query({ threshold })}`),
  llmStatus: (projectId: number) =>
    request<{ llm_available: boolean; model: string | null; note: string }>(
      `/api/projects/${projectId}/llm-status`,
    ),

  // categories
  suggestCategories: (projectId: number, params: Record<string, unknown> = {}) =>
    request<CategorySuggestResponse>(
      `/api/projects/${projectId}/categories/suggest${query(params)}`,
    ),
  applyCategories: (projectId: number, assignments: { task_id: number; category_name: string }[]) =>
    request<CategoryApplyResult>(`/api/projects/${projectId}/categories/apply`, {
      method: "POST",
      body: JSON.stringify({ assignments }),
    }),

  // import
  analyzeImport: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportAnalyze>("/api/imports/analyze", { method: "POST", body: form });
  },
  previewImport: (token: string, sheet?: string, headerRow?: number) =>
    request<ImportAnalyze>(`/api/imports/${token}/preview${query({ sheet, header_row: headerRow })}`),
  planImport: (payload: Record<string, unknown>) =>
    request<ImportPlan>("/api/imports/plan", { method: "POST", body: JSON.stringify(payload) }),
  commitImport: (payload: Record<string, unknown>) =>
    request<ImportResult>("/api/imports/commit", { method: "POST", body: JSON.stringify(payload) }),
};
