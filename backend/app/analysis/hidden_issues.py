"""Detection of *hidden* issues.

A hidden issue is a problem that nobody has raised as an Issue record, but that
the structured project data already proves. Every detector must produce
evidence; a finding without evidence is dropped.
"""
from __future__ import annotations

from datetime import timedelta

from .findings import Action, Evidence, RawFinding, severity_rank
from .snapshot import ProjectSnapshot, TaskView

HIGH_SEVERITIES = ("high", "critical")


def _task_finding(view: TaskView, **kwargs) -> RawFinding:
    return RawFinding(
        category="hidden_issue",
        task_id=view.id,
        task_title=view.label(),
        **kwargs,
    )


# --------------------------------------------------------------------------- detectors
def detect_stalled_near_completion(s: ProjectSnapshot) -> list[RawFinding]:
    """90%+ で止まったまま期限を超えているTask - 「ほぼ終わり」の罠。"""
    out = []
    for v in s.overdue_views():
        if v.progress >= 90:
            out.append(
                _task_finding(
                    v,
                    finding_type="stalled_near_completion",
                    title=f"進捗{v.progress:.0f}%のまま停滞: {v.label()}",
                    severity="high" if v.days_overdue >= 5 else "medium",
                    confidence=0.8,
                    impact="残作業は小さいはずだが完了しないため、後続Taskの着手判断ができずスケジュール全体が固まらない",
                    evidence=[
                        Evidence("期限超過", f"予定終了日 {v.planned_end} を {v.days_overdue} 日超過"),
                        Evidence("進捗", f"{v.progress:.0f}% で停滞（Status: {v.status}）"),
                        Evidence("最終更新", f"{v.days_since_update} 日前"),
                    ],
                    actions=[
                        Action("残作業を洗い出し、完了条件(DoD)を明文化する", "残り10%の中身が共有されていないため完了判定ができない"),
                        Action("完了を妨げているレビュー/承認の待ち先を特定し期限を切る", "停滞の典型原因は承認待ちであり、期限設定で解消できる"),
                        Action("後続Taskを部分着手できるよう分割する", "100%完了を待たずに後続を開始でき、遅延の伝播を止められる", "low"),
                    ],
                )
            )
    return out


def detect_due_soon_low_progress(s: ProjectSnapshot) -> list[RawFinding]:
    """期限が近いのに進捗が低いTask。"""
    out = []
    for v in s.active_views():
        d = v.days_to_due
        if d is None or v.is_overdue or d > 7:
            continue
        if v.progress >= 60:
            continue
        out.append(
            _task_finding(
                v,
                finding_type="due_soon_low_progress",
                title=f"期限まで{d}日で進捗{v.progress:.0f}%: {v.label()}",
                severity="high" if d <= 3 else "medium",
                confidence=0.75,
                impact="このままのペースでは期限内完了は困難で、期限超過Taskが1件増える",
                evidence=[
                    Evidence("残日数", f"予定終了日 {v.planned_end} まで {d} 日"),
                    Evidence("進捗差", f"想定 {v.expected_progress:.0f}% に対し実績 {v.progress:.0f}%"),
                    Evidence("担当", s.owner_name(v.owner_id) or "未設定"),
                ],
                actions=[
                    Action("残作業を分解し、期限内に終わる範囲と溢れる範囲を切り分ける", "全量が間に合わないことを早期に確定させると打ち手が選べる"),
                    Action("担当者を追加投入する", "残日数が短く、単独では物理的に消化できない可能性が高い", "high"),
                    Action("期限を関係者と再合意する", "期限超過してから報告するより、事前調整のほうが影響が小さい"),
                ],
            )
        )
    return out


def detect_owner_missing(s: ProjectSnapshot) -> list[RawFinding]:
    out = []
    for v in s.active_views():
        if v.owner_id is None and v.is_leaf:
            severity = "high" if (v.days_to_due is not None and v.days_to_due <= 14) else "medium"
            out.append(
                _task_finding(
                    v,
                    finding_type="owner_missing",
                    title=f"Owner未設定: {v.label()}",
                    severity=severity,
                    confidence=0.9,
                    impact="推進責任者がいないため進捗が誰にも管理されず、期限直前まで放置される",
                    evidence=[
                        Evidence("Owner", "未設定"),
                        Evidence("予定終了日", str(v.planned_end) if v.planned_end else "未設定"),
                        Evidence("Status", f"{v.status} / 進捗 {v.progress:.0f}%"),
                    ],
                    actions=[
                        Action("Ownerを1名に確定する", "責任の所在が曖昧なTaskは進捗報告の対象から漏れる"),
                        Action("Owner未定の理由（要員未確保/役割未定義）をIssue化する", "根本原因が要員不足なら他Taskでも同じ問題が起きる", "low"),
                    ],
                )
            )
    return out


def detect_owner_overload(s: ProjectSnapshot) -> list[RawFinding]:
    """特定担当者へのTask集中。"""
    out = []
    total_open = len(s.active_views())
    for load in s.loads.values():
        open_count = len(load.open_task_ids)
        if open_count == 0:
            continue
        share = open_count / total_open if total_open else 0
        # A concentration claim needs volume behind it: one task out of one is
        # not a bottleneck, however high the ratio looks.
        if open_count < 4:
            continue
        if load.load_level != "overloaded" and share < 0.5:
            continue
        severity = "high" if (load.load_ratio >= 1.5 or share >= 0.5) else "medium"
        out.append(
            RawFinding(
                category="hidden_issue",
                finding_type="owner_overload",
                title=f"Task集中: {load.person.name} が未完了 {open_count} 件",
                severity=severity,
                confidence=0.8,
                person_id=load.person.id,
                person_name=load.person.name,
                impact="1名の稼働がボトルネックになり、その担当者の遅延がプロジェクト全体に波及する",
                evidence=[
                    Evidence("担当件数", f"未完了 {open_count} 件 / capacity {load.capacity}（負荷率 {load.load_ratio:.2f}）"),
                    Evidence("プロジェクト内シェア", f"未完了Task全体の {share * 100:.0f}%"),
                    Evidence("期限超過", f"{len(load.overdue_task_ids)} 件"),
                    Evidence("直近7日期限", f"{len(load.due_this_week_ids)} 件"),
                ],
                actions=[
                    Action("優先度の低いTaskを他メンバーへ再配分する", "負荷率が capacity を超えており、単独消化は物理的に不可能"),
                    Action("この担当者のTaskを優先度順に並べ、着手順を合意する", "並行作業によるコンテキストスイッチ損失を減らせる", "low"),
                    Action("要員追加をエスカレーションする", "再配分先が居ない場合、体制側の解決が必要"),
                ],
            )
        )
    return out


def detect_critical_concentration(s: ProjectSnapshot) -> list[RawFinding]:
    """同一担当者への高優先度Task集中。"""
    out = []
    for load in s.loads.values():
        criticals = [s.views[t] for t in load.critical_task_ids]
        if len(criticals) < 3:
            continue
        on_cp = [v for v in criticals if v.is_critical_path]
        out.append(
            RawFinding(
                category="hidden_issue",
                finding_type="critical_task_concentration",
                title=f"高優先度Task集中: {load.person.name} に {len(criticals)} 件",
                severity="high" if on_cp else "medium",
                confidence=0.75,
                person_id=load.person.id,
                person_name=load.person.name,
                impact="重要Taskが1名に依存しており、その担当者の不在・遅延が単一障害点になる",
                evidence=[
                    Evidence("高優先度Task", "、".join(v.label() for v in criticals[:5])),
                    Evidence("クリティカルパス上", f"{len(on_cp)} 件"),
                    Evidence("負荷率", f"{load.load_ratio:.2f}"),
                ],
                actions=[
                    Action("最重要1件を除き、副担当を立てる", "属人化を解消し、不在時のリスクを下げる"),
                    Action("クリティカルパス上のTaskを優先させ、他は日程を後ろ倒す", "同時並行では重要Taskの完了が遅れる"),
                ],
            )
        )
    return out


def detect_successor_start_blocked(s: ProjectSnapshot) -> list[RawFinding]:
    """後続Taskの開始予定日が来ているのに前工程が終わっていない。"""
    out = []
    for v in s.active_views():
        if not v.predecessor_ids or v.planned_start is None:
            continue
        if v.planned_start > s.today + timedelta(days=3):
            continue
        blockers = [s.views[p] for p in v.predecessor_ids if not s.views[p].is_done]
        if not blockers:
            continue
        out.append(
            _task_finding(
                v,
                finding_type="successor_start_blocked",
                title=f"前工程未完了のまま開始日到来: {v.label()}",
                severity="high" if v.planned_start <= s.today else "medium",
                confidence=0.85,
                impact="着手できない待ち時間が発生し、遅延が下流へ連鎖する",
                evidence=[
                    Evidence("開始予定日", f"{v.planned_start}（本日 {s.today}）"),
                    Evidence(
                        "未完了の前工程",
                        "、".join(f"{b.label()}（進捗 {b.progress:.0f}%）" for b in blockers[:3]),
                    ),
                    Evidence("自Task状況", f"Status {v.status} / 進捗 {v.progress:.0f}%"),
                ],
                actions=[
                    Action("前工程の残作業と完了見込み日を確認する", "着手可能日が確定しないと後続の再計画ができない"),
                    Action("前工程の一部成果物で暫定着手できないか検討する", "全完了を待たずに並行着手できれば遅延を吸収できる"),
                    Action("後続Taskの日程をリスケジュールする", "実態に合わない計画のままでは他の遅延が見えなくなる", "low"),
                ],
            )
        )
    return out


def detect_dependency_conflicts(s: ProjectSnapshot) -> list[RawFinding]:
    """依存関係の矛盾（循環参照、日程の逆転）。"""
    out: list[RawFinding] = []
    for cycle in s.dependency_cycles:
        labels = "、".join(s.views[t].label() for t in cycle[:5])
        out.append(
            RawFinding(
                category="hidden_issue",
                finding_type="dependency_cycle",
                title=f"依存関係の循環を検出（{len(cycle)} Task）",
                severity="critical",
                confidence=0.95,
                impact="スケジュール計算が成立せず、クリティカルパスもFloatも信頼できない",
                evidence=[
                    Evidence("循環に含まれるTask", labels),
                    Evidence("影響", "順序が決まらないため着手順が定義できない"),
                ],
                actions=[
                    Action("循環している依存のうち1本を削除または双方向の分割Taskに変更する", "循環が残る限りスケジュール計算が成立しない"),
                ],
            )
        )
    for edge in s.edges:
        pred, succ = s.views[edge.predecessor_id], s.views[edge.successor_id]
        if pred.planned_end and succ.planned_start and succ.planned_start < pred.planned_end:
            overlap = (pred.planned_end - succ.planned_start).days
            out.append(
                _task_finding(
                    succ,
                    finding_type="dependency_date_conflict",
                    title=f"依存関係と日程の矛盾: {succ.label()}",
                    severity="medium" if overlap <= 3 else "high",
                    confidence=0.85,
                    impact="計画上すでに破綻しており、そのまま進めると必ず遅延が顕在化する",
                    evidence=[
                        Evidence("前工程", f"{pred.label()} 終了予定 {pred.planned_end}"),
                        Evidence("後続", f"{succ.label()} 開始予定 {succ.planned_start}"),
                        Evidence("矛盾量", f"{overlap} 日の逆転（{edge.dependency_type}依存）"),
                    ],
                    actions=[
                        Action("後続の開始日を前工程の終了日以降へ修正する", "計画の内部矛盾を解消しないと遅延検知が機能しない"),
                        Action("並行作業が前提なら依存タイプを SS に変更する", "実態が並行なら依存関係の定義側が誤っている", "low"),
                    ],
                )
            )
    return out


def detect_green_but_issue_heavy(s: ProjectSnapshot) -> list[RawFinding]:
    """予定上は順調に見えるがIssueが積み上がっているTask。"""
    out = []
    for v in s.active_views():
        open_issues = s.open_issues_for_task(v.id)
        if len(open_issues) < 2 or v.is_overdue:
            continue
        if v.progress_gap > 10:
            continue  # すでに進捗遅れとして見えているので「隠れて」いない
        severe = [i for i in open_issues if i.severity in HIGH_SEVERITIES]
        out.append(
            _task_finding(
                v,
                finding_type="green_but_issue_heavy",
                title=f"予定上は順調だが未解決Issue {len(open_issues)} 件: {v.label()}",
                severity="high" if severe else "medium",
                confidence=0.7,
                impact="進捗率は健全に見えるがIssueが解決しない限り完了できず、期限直前に一気に遅延化する",
                evidence=[
                    Evidence("進捗", f"{v.progress:.0f}%（想定 {v.expected_progress:.0f}%）で表面上は順調"),
                    Evidence("未解決Issue", "、".join(f"{i.title}[{i.severity}]" for i in open_issues[:4])),
                    Evidence("高Severity", f"{len(severe)} 件"),
                ],
                actions=[
                    Action("未解決Issueの解決期限とOwnerを設定する", "Issueが放置される限り進捗率は実態を表さない"),
                    Action("Issue解決までのリードタイムを日程に織り込む", "現在の日程はIssue解決時間を含んでいない"),
                ],
            )
        )
    return out


def detect_progress_inconsistency(s: ProjectSnapshot) -> list[RawFinding]:
    """進捗率と実態（Status/実績日/子Task）の不整合。"""
    out = []
    # 実績日を1件も記録していないプロジェクトで「実績開始日が未入力」を全Taskに
    # 出しても意味がない（WBSにその列が無いだけ）。運用している場合だけ指摘する。
    tracks_actuals = any(v.task.actual_start for v in s.task_views())
    for v in s.active_views():
        problems: list[Evidence] = []
        if v.progress >= 100 and v.status != "done":
            problems.append(Evidence("進捗100%", f"進捗100%だがStatusは {v.status}"))
        if v.task.actual_end and v.status != "done":
            problems.append(Evidence("実績終了日あり", f"実績終了日 {v.task.actual_end} が入力済みだがStatusは {v.status}"))
        if tracks_actuals and v.progress > 0 and v.task.actual_start is None:
            problems.append(Evidence("実績開始日なし", f"進捗 {v.progress:.0f}% だが実績開始日が未入力"))
        if v.status == "in_progress" and v.progress == 0:
            problems.append(Evidence("進捗0%", "Statusは進行中だが進捗率0%"))
        rollup = s.child_progress_rollup(v)
        # 子より親の進捗が高い＝過大申告のみを指摘する。親が未入力（0%）の場合は
        # 子の集計値が表示に使われるため、不整合ではない。
        if rollup is not None and v.progress - rollup >= 20:
            problems.append(
                Evidence("子Taskとの乖離", f"子Task加重平均 {rollup:.0f}% に対し親Task {v.progress:.0f}%")
            )
        if not problems:
            continue
        out.append(
            _task_finding(
                v,
                finding_type="progress_inconsistency",
                title=f"進捗と実態の不整合: {v.label()}",
                severity="medium",
                confidence=0.65,
                impact="ダッシュボード上の完了率が実態とずれ、遅延の検知が遅れる",
                evidence=problems,
                actions=[
                    Action("Status・進捗率・実績日を実態に合わせて更新する", "入力が揃わないと自動検知の精度が上がらない", "low"),
                    Action("週次で進捗更新のルール（更新タイミングと粒度）を合意する", "不整合が常態化しているとデータ全体の信頼性が落ちる"),
                ],
            )
        )
    return out


def detect_overdue_still_in_progress(s: ProjectSnapshot) -> list[RawFinding]:
    """予定終了日を過ぎているのにStatusが変わっていないTask。"""
    out = []
    for v in s.overdue_views():
        if v.progress >= 90:
            continue  # stalled_near_completion 側で扱う
        out.append(
            _task_finding(
                v,
                finding_type="overdue_status_unchanged",
                title=f"期限超過 {v.days_overdue} 日でStatus未更新: {v.label()}",
                severity="critical" if v.days_overdue >= 10 else "high",
                confidence=0.85,
                impact="遅延が申告されないまま滞留し、リカバリ判断のタイミングを逃す",
                evidence=[
                    Evidence("超過日数", f"{v.days_overdue} 日（予定終了日 {v.planned_end}）"),
                    Evidence("Status", f"{v.status} / 進捗 {v.progress:.0f}%"),
                    Evidence("最終更新", f"{v.days_since_update} 日前"),
                    Evidence("担当", s.owner_name(v.owner_id) or "未設定"),
                ],
                actions=[
                    Action("完了見込み日を再設定し、遅延として明示的に登録する", "遅延を可視化しないとリカバリ計画が立てられない"),
                    Action("遅延原因をIssueとして登録する", "同じ原因が他Taskでも発生している可能性がある"),
                ],
            )
        )
    return out


def detect_milestone_buffer(s: ProjectSnapshot) -> list[RawFinding]:
    """マイルストーン直前の余裕日数不足。"""
    out = []
    for m in s.milestones:
        if m.status != "pending" or not m.due_date:
            continue
        days_left = (m.due_date - s.today).days
        if days_left < 0 or days_left > 21:
            continue
        blockers = [
            v
            for v in s.active_views()
            if v.planned_end and v.planned_end <= m.due_date
        ]
        overdue_blockers = [v for v in blockers if v.is_overdue]
        risky = [v for v in blockers if v.risk_score >= 60]
        if not overdue_blockers and not risky:
            continue
        out.append(
            RawFinding(
                category="hidden_issue",
                finding_type="milestone_buffer_insufficient",
                title=f"マイルストーン「{m.title}」まで {days_left} 日、未完了 {len(blockers)} 件",
                severity="critical" if overdue_blockers else "high",
                confidence=0.8,
                impact="マイルストーン未達となり、対外コミットや後続フェーズの開始日に影響する",
                evidence=[
                    Evidence("期日", f"{m.due_date}（残り {days_left} 日）"),
                    Evidence("未完了Task", f"{len(blockers)} 件（うち期限超過 {len(overdue_blockers)} 件）"),
                    Evidence("高リスクTask", f"{len(risky)} 件: " + "、".join(v.label() for v in risky[:3])),
                ],
                actions=[
                    Action("マイルストーン達成に必須のTaskを選別し、残りを次期へ送る", "残日数では全量消化できず、優先順位付けが唯一の現実解"),
                    Action("期限超過Taskのリカバリ計画を当日中に確定する", "超過分がそのままマイルストーン遅延に直結する"),
                    Action("マイルストーン日程の見直しを関係者に打診する", "達成不能が確実な場合は早期の再合意が損失を最小化する", "high"),
                ],
            )
        )
    return out


def detect_unowned_issues(s: ProjectSnapshot) -> list[RawFinding]:
    """Owner不在または期限切れの未解決Issue。"""
    out = []
    stale = [
        i
        for i in s.open_issues()
        if i.owner_id is None or (i.due_date and i.due_date < s.today)
    ]
    if not stale:
        return out
    overdue = [i for i in stale if i.due_date and i.due_date < s.today]
    unowned = [i for i in stale if i.owner_id is None]
    out.append(
        RawFinding(
            category="hidden_issue",
            finding_type="issue_governance_gap",
            title=f"管理されていないIssueが {len(stale)} 件",
            severity="high" if overdue else "medium",
            confidence=0.85,
            impact="課題が解決されないままTaskの完了を阻み、原因不明の遅延として表面化する",
            evidence=[
                Evidence("Owner未設定", f"{len(unowned)} 件: " + "、".join(i.title for i in unowned[:3])),
                Evidence("期限超過", f"{len(overdue)} 件: " + "、".join(f"{i.title}({i.due_date})" for i in overdue[:3])),
            ],
            actions=[
                Action("各IssueにOwnerとDue Dateを設定する", "担当と期限のないIssueは構造的に解決されない"),
                Action("期限超過Issueをレビューし、エスカレーション要否を判断する", "期限を過ぎた課題は自然解決しない"),
            ],
        )
    )
    return out


DETECTORS = (
    detect_stalled_near_completion,
    detect_due_soon_low_progress,
    detect_owner_missing,
    detect_owner_overload,
    detect_critical_concentration,
    detect_successor_start_blocked,
    detect_dependency_conflicts,
    detect_green_but_issue_heavy,
    detect_progress_inconsistency,
    detect_overdue_still_in_progress,
    detect_milestone_buffer,
    detect_unowned_issues,
)


def detect_hidden_issues(snapshot: ProjectSnapshot, limit: int | None = None) -> list[RawFinding]:
    findings: list[RawFinding] = []
    for detector in DETECTORS:
        findings.extend(detector(snapshot))

    # Evidence is mandatory - drop anything a detector could not substantiate.
    findings = [f for f in findings if f.evidence]

    # De-duplicate on (type, target), keeping the most severe.
    unique: dict[str, RawFinding] = {}
    for f in findings:
        existing = unique.get(f.key())
        if existing is None or severity_rank(f.severity) > severity_rank(existing.severity):
            unique[f.key()] = f

    ordered = sorted(
        unique.values(),
        key=lambda f: (
            severity_rank(f.severity),
            snapshot.views[f.task_id].risk_score if f.task_id in snapshot.views else 50,
        ),
        reverse=True,
    )
    return ordered[:limit] if limit else ordered
