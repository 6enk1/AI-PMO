"use client";

import { useEffect, useMemo, useRef } from "react";
import { formatFullDate } from "@/lib/format";
import type { Milestone, Task } from "@/lib/types";

const DAY = 86400000;

function parse(value: string | null): number | null {
  if (!value) return null;
  const time = new Date(`${value}T00:00:00`).getTime();
  return Number.isNaN(time) ? null : time;
}

function startOfToday(): number {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
}

/**
 * Lightweight dependency-free Gantt: one row per task, planned bar with a
 * progress overlay, an actual bar underneath, milestone markers and a today line.
 */
export function GanttChart({
  tasks,
  milestones,
  dayWidth = 22,
  onSelect,
}: {
  tasks: Task[];
  milestones: Milestone[];
  dayWidth?: number;
  onSelect?: (task: Task) => void;
}) {
  const { start, days, months } = useMemo(() => {
    const stamps: number[] = [startOfToday()];
    tasks.forEach((task) => {
      [task.effective_start, task.effective_end, task.actual_start, task.actual_end].forEach((value) => {
        const time = parse(value);
        if (time !== null) stamps.push(time);
      });
    });
    milestones.forEach((milestone) => {
      const time = parse(milestone.due_date);
      if (time !== null) stamps.push(time);
    });
    const min = Math.min(...stamps) - 3 * DAY;
    const max = Math.max(...stamps) + 3 * DAY;
    const total = Math.max(14, Math.round((max - min) / DAY) + 1);

    const monthBuckets: { label: string; span: number }[] = [];
    for (let index = 0; index < total; index += 1) {
      const date = new Date(min + index * DAY);
      const label = `${date.getFullYear()}/${date.getMonth() + 1}`;
      const last = monthBuckets[monthBuckets.length - 1];
      if (last && last.label === label) last.span += 1;
      else monthBuckets.push({ label, span: 1 });
    }
    return { start: min, days: total, months: monthBuckets };
  }, [tasks, milestones]);

  const width = days * dayWidth;
  const offsetOf = (time: number) => Math.round((time - start) / DAY) * dayWidth;
  const todayLeft = offsetOf(startOfToday());

  // A multi month plan is wider than the screen: open the view around today.
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scroller.current) {
      scroller.current.scrollLeft = Math.max(0, todayLeft - scroller.current.clientWidth / 3);
    }
  }, [todayLeft, dayWidth]);

  return (
    <div className="flex overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="w-64 shrink-0 border-r border-slate-200">
        <div className="h-12 border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-ink-500">
          タスク / 担当
        </div>
        {tasks.map((task) => (
          <div
            key={task.id}
            className="flex h-10 items-center gap-2 border-b border-slate-50 px-3 text-xs"
            title={[...task.path_titles, task.title].join(" / ")}
          >
            <div className="min-w-0 flex-1" style={{ paddingLeft: Math.min(3, task.depth) * 10 }}>
              {task.category && (
                <p className="truncate text-[10px] leading-3 text-ink-400">{task.category}</p>
              )}
              <button
                className={`block w-full truncate text-left leading-4 hover:underline ${
                  task.is_summary ? "font-semibold text-ink-900" : "font-medium text-ink-800"
                }`}
                onClick={() => onSelect?.(task)}
              >
                {task.title}
              </button>
            </div>
            <span className="shrink-0 text-[11px] text-ink-400">{task.owner_name ?? "未設定"}</span>
          </div>
        ))}
      </div>

      <div ref={scroller} className="flex-1 overflow-x-auto">
        <div style={{ width }} className="relative">
          <div className="sticky top-0 z-10 bg-slate-50">
            <div className="flex h-6 border-b border-slate-200">
              {months.map((month, index) => (
                <div
                  key={`${month.label}-${index}`}
                  className="border-r border-slate-200 px-2 text-[11px] font-medium leading-6 text-ink-500"
                  style={{ width: month.span * dayWidth }}
                >
                  {month.label}
                </div>
              ))}
            </div>
            <div className="flex h-6 border-b border-slate-200">
              {Array.from({ length: days }).map((_, index) => {
                const date = new Date(start + index * DAY);
                const weekend = date.getDay() === 0 || date.getDay() === 6;
                return (
                  <div
                    key={index}
                    className={`shrink-0 border-r border-slate-100 text-center text-[10px] leading-6 ${
                      weekend ? "bg-slate-100 text-ink-400" : "text-ink-400"
                    }`}
                    style={{ width: dayWidth }}
                  >
                    {date.getDate()}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="relative">
            <div
              className="pointer-events-none absolute top-0 z-20 h-full w-0.5 bg-rose-500/70"
              style={{ left: todayLeft }}
              title="本日"
            />
            {milestones
              .filter((milestone) => milestone.due_date)
              .map((milestone) => {
                const time = parse(milestone.due_date);
                if (time === null) return null;
                return (
                  <div
                    key={milestone.id}
                    className="pointer-events-none absolute top-0 z-10 h-full border-l border-dashed border-indigo-400"
                    style={{ left: offsetOf(time) }}
                  >
                    <span className="absolute -top-0.5 left-1 whitespace-nowrap rounded bg-indigo-50 px-1 text-[10px] text-indigo-700">
                      ◆ {milestone.title}
                    </span>
                  </div>
                );
              })}

            {tasks.map((task) => {
              const plannedStart = parse(task.effective_start);
              const plannedEnd = parse(task.effective_end);
              const actualStart = parse(task.actual_start);
              const actualEnd = parse(task.actual_end);
              const barStart = plannedStart ?? plannedEnd;
              const barEnd = plannedEnd ?? plannedStart;
              const left = barStart !== null ? offsetOf(barStart) : 0;
              const barWidth =
                barStart !== null && barEnd !== null
                  ? Math.max(dayWidth, (Math.round((barEnd - barStart) / DAY) + 1) * dayWidth)
                  : 0;

              const actualLeft = actualStart !== null ? offsetOf(actualStart) : null;
              const actualWidth =
                actualStart !== null
                  ? Math.max(
                      dayWidth / 2,
                      (Math.round(((actualEnd ?? startOfToday()) - actualStart) / DAY) + 1) * dayWidth,
                    )
                  : 0;

              const progress = task.effective_progress;
              const barColor = task.is_summary
                ? "bg-ink-100 border-ink-400"
                : task.is_overdue
                ? "bg-rose-200 border-rose-400"
                : task.status === "done"
                  ? "bg-emerald-100 border-emerald-300"
                  : task.is_critical_path
                    ? "bg-indigo-100 border-indigo-400"
                    : "bg-sky-100 border-sky-300";
              const fillColor = task.is_summary
                ? "bg-ink-500"
                : task.is_overdue
                  ? "bg-rose-500"
                  : task.status === "done"
                    ? "bg-emerald-500"
                    : "bg-sky-500";

              return (
                <div key={task.id} className="relative h-10 border-b border-slate-50">
                  {barWidth > 0 && (
                    <div
                      className={`absolute ${task.is_summary ? "top-3 h-2" : "top-2 h-4"} rounded border ${barColor}`}
                      style={{ left, width: barWidth }}
                      title={`${task.title}\n予定 ${formatFullDate(task.effective_start)} 〜 ${formatFullDate(
                        task.effective_end,
                      )}\n進捗 ${progress}% / Risk ${task.risk_score}${task.is_summary ? "（子Taskの集計）" : ""}`}
                    >
                      <div
                        className={`h-full rounded-l ${fillColor}`}
                        style={{ width: `${Math.min(100, progress)}%` }}
                      />
                      <span className="absolute -right-12 top-0 text-[10px] leading-4 text-ink-400">
                        {progress.toFixed(0)}%
                      </span>
                    </div>
                  )}
                  {actualLeft !== null && (
                    <div
                      className="absolute top-7 h-1 rounded bg-ink-500/60"
                      style={{ left: actualLeft, width: actualWidth }}
                      title={`実績 ${formatFullDate(task.actual_start)} 〜 ${formatFullDate(task.actual_end)}`}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
