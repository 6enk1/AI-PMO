import type { Task } from "./types";

/**
 * 親 → その子 の順（WBS階層順）に並べ替える。
 * フィルタで親が消えている場合は、その子をルート扱いにして落とさない。
 */
export function orderAsTree(tasks: Task[]): Task[] {
  const present = new Set(tasks.map((task) => task.id));
  const children = new Map<number | null, Task[]>();
  tasks.forEach((task) => {
    const key = task.parent_task_id && present.has(task.parent_task_id) ? task.parent_task_id : null;
    children.set(key, [...(children.get(key) ?? []), task]);
  });

  const byStart = (a: Task, b: Task) => {
    const left = a.effective_start ?? a.effective_end ?? "9999-12-31";
    const right = b.effective_start ?? b.effective_end ?? "9999-12-31";
    return left === right ? a.id - b.id : left.localeCompare(right);
  };

  const ordered: Task[] = [];
  const walk = (parentId: number | null, depth: number) => {
    if (depth > 10) return;
    (children.get(parentId) ?? []).sort(byStart).forEach((task) => {
      ordered.push(task);
      walk(task.id, depth + 1);
    });
  };
  walk(null, 0);
  return ordered.length === tasks.length ? ordered : tasks;
}
