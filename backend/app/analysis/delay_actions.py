"""Cause diagnosis and counter-measure proposals for delayed / high risk tasks.

The structured layer picks the *cause hypotheses* from measurable signals and
attaches a playbook of counter-measures. The LLM layer may rewrite the wording
and re-rank the options, but it can never introduce a cause that has no
supporting signal here.
"""
from __future__ import annotations

from dataclasses import dataclass

from .findings import Action, Evidence, RawFinding
from .risk import impact_statement
from .snapshot import ProjectSnapshot, TaskView

HIGH_SEVERITIES = ("high", "critical")


@dataclass
class Cause:
    category: str
    hypothesis: str
    weight: float
    evidence: list[Evidence]
    actions: list[Action]


def _text_of(view: TaskView, snapshot: ProjectSnapshot) -> str:
    parts = [view.title, view.task.description or "", view.task.notes or ""]
    for issue in snapshot.open_issues_for_task(view.id):
        parts += [issue.title, issue.description or "", issue.action_plan or ""]
    return " ".join(parts).lower()


KEYWORD_CAUSES: list[tuple[str, str, tuple[str, ...]]] = [
    ("顧客回答待ち", "customer_response", ("顧客", "客先", "先方", "回答待ち", "問い合わせ", "customer", "client")),
    ("意思決定待ち", "decision_pending", ("意思決定", "決裁", "承認待ち", "方針決定", "decision", "approval")),
    ("レビュー待ち", "review_pending", ("レビュー", "review", "査読", "指摘対応")),
    ("仕様変更", "spec_change", ("仕様変更", "要件変更", "change request", "手戻り")),
    ("Scope増加", "scope_creep", ("追加要望", "スコープ", "scope", "機能追加", "追加対応")),
    ("技術課題", "technical_issue", ("技術", "不具合", "バグ", "bug", "エラー", "性能", "環境構築", "検証失敗")),
]

KEYWORD_PLAYBOOK: dict[str, list[Action]] = {
    "customer_response": [
        Action("回答期限を明示した督促を出し、未回答時の暫定方針を通知する", "回答待ちは待つだけでは解消せず、期限提示が最も効果的"),
        Action("暫定仕様でFreezeし、後続Taskを再開する", "後続3件以上が止まっている場合、全体の停止コストが確定仕様の価値を上回る"),
        Action("回答不要な範囲を切り出して先行着手する", "待ち時間を作業時間に転換できる", "low"),
    ],
    "decision_pending": [
        Action("Decision Ownerを1名に確定し、決定期限を設定する", "意思決定者が不明確なままでは会議を重ねても決まらない"),
        Action("選択肢を2案に絞り、それぞれの影響を1枚で提示する", "判断材料が整理されていないことが決定遅延の主因になりやすい"),
        Action("期限までに決定されない場合の既定案（デフォルト決定）を合意する", "決定遅延そのものを時間制約に変換できる", "low"),
    ],
    "review_pending": [
        Action("レビュアーと締切を指定し、レビュー枠をカレンダーで確保する", "レビューは割り込み作業になりやすく、枠を取らない限り後回しにされる"),
        Action("レビュー範囲を分割し、部分承認で先へ進める", "全量レビュー完了を待たずに後続へ着手できる"),
        Action("指摘対応の完了基準を合意する", "指摘の往復が無限に続く状態を防ぐ", "low"),
    ],
    "spec_change": [
        Action("変更内容を確定し、追加工数と期日影響を見積り直す", "変更を織り込まない計画のままでは遅延が繰り返される"),
        Action("変更を次フェーズへ切り出す", "現行スケジュールを守る唯一の現実的手段になる場合が多い", "high"),
        Action("変更管理プロセス（受付・承認・反映）を明文化する", "同種の手戻りの再発を防ぐ"),
    ],
    "scope_creep": [
        Action("スコープ増分を一覧化し、必須/非必須を関係者と仕分けする", "増分が不可視のままだと工数超過の原因が特定できない"),
        Action("低優先機能を次Phaseへ移管する", "期日を維持するにはスコープ調整が最も確実", "low"),
        Action("追加要望の受付窓口と判断基準を設定する", "都度受け入れによる継続的な遅延を止める"),
    ],
    "technical_issue": [
        Action("技術課題をIssue化し、調査タイムボックス（例: 2日）を設定する", "原因不明の調査は青天井になりやすく、時間制約が必要"),
        Action("有識者をスポットでアサインする", "技術的難所は経験者投入が最も効果が大きい", "high"),
        Action("回避策（暫定実装）で先に進める判断をする", "根本解決を待つより後続の停止コストが大きい場合がある"),
    ],
}


def _detect_causes(snapshot: ProjectSnapshot, view: TaskView) -> list[Cause]:
    causes: list[Cause] = []
    text = _text_of(view, snapshot)

    blockers = [snapshot.views[p] for p in view.predecessor_ids if not snapshot.views[p].is_done]
    if blockers:
        overdue_blockers = [b for b in blockers if b.is_overdue]
        causes.append(
            Cause(
                category="依存Task遅延",
                hypothesis="前工程が完了していないため着手・完了できていない",
                weight=3.0 + len(overdue_blockers),
                evidence=[
                    Evidence(
                        "未完了の前工程",
                        "、".join(f"{b.label()}（進捗 {b.progress:.0f}%）" for b in blockers[:3]),
                    ),
                    Evidence("うち期限超過", f"{len(overdue_blockers)} 件"),
                ],
                actions=[
                    Action("前工程の完了見込み日を確定し、本Taskの日程を引き直す", "前工程の完了日が決まらない限り本Taskの計画は成立しない"),
                    Action("前工程の中間成果物で部分着手する", "待ち時間を短縮し、遅延の伝播量を減らせる", "low"),
                    Action("前工程へ応援を投入し、クリティカルパスを短縮する", "上流の遅延解消が全体日程への効果が最も大きい", "high"),
                ],
            )
        )

    for label, key, keywords in KEYWORD_CAUSES:
        hits = [k for k in keywords if k in text]
        if not hits:
            continue
        related = [
            i
            for i in snapshot.open_issues_for_task(view.id)
            if any(k in f"{i.title} {i.description or ''}".lower() for k in keywords)
        ]
        evidence = [Evidence("検出キーワード", "、".join(hits[:4]))]
        if related:
            evidence.append(
                Evidence("関連Issue", "、".join(f"{i.title}[{i.status}/{i.severity}]" for i in related[:3]))
            )
        causes.append(
            Cause(
                category=label,
                hypothesis=f"{label}により作業が止まっている",
                weight=2.5 + (1.5 if related else 0),
                evidence=evidence,
                actions=list(KEYWORD_PLAYBOOK[key]),
            )
        )

    if view.owner_id is None:
        causes.append(
            Cause(
                category="Owner不明確",
                hypothesis="推進責任者が不在のため作業が進んでいない",
                weight=3.5,
                evidence=[Evidence("Owner", "未設定"), Evidence("Status", f"{view.status} / 進捗 {view.progress:.0f}%")],
                actions=[
                    Action("Ownerを1名に確定し、次回報告日を決める", "責任者不在のTaskは誰にも管理されない"),
                    Action("Owner確定を妨げている要因（要員未確保など）をエスカレーションする", "体制課題であれば現場では解決できない", "high"),
                ],
            )
        )
    else:
        load = snapshot.loads.get(view.owner_id)
        if load and load.load_level in ("overloaded", "high"):
            causes.append(
                Cause(
                    category="人員不足",
                    hypothesis="担当者の負荷超過により着手時間が確保できていない",
                    weight=2.0 + (1.5 if load.load_level == "overloaded" else 0),
                    evidence=[
                        Evidence(
                            "担当者負荷",
                            f"{load.person.name}: 未完了 {len(load.open_task_ids)} 件 / capacity {load.capacity}"
                            f"（負荷率 {load.load_ratio:.2f}）",
                        ),
                        Evidence("同担当の期限超過", f"{len(load.overdue_task_ids)} 件"),
                    ],
                    actions=[
                        Action("担当者の他Taskを再配分し、本Taskに集中させる", "負荷超過が解消しない限り着手時間が生まれない"),
                        Action("本Taskを分割して他メンバーへ一部委譲する", "単独消化が不可能な量であることが数値で示されている"),
                        Action("要員追加を体制側へエスカレーションする", "再配分先がない場合は体制の問題として扱う必要がある", "high"),
                    ],
                )
            )

    if view.status == "not_started" and view.planned_start and view.planned_start < snapshot.today:
        late = (snapshot.today - view.planned_start).days
        causes.append(
            Cause(
                category="着手遅れ",
                hypothesis="計画開始日を過ぎても着手されていない",
                weight=2.0 + min(2.0, late / 5),
                evidence=[Evidence("開始予定日", f"{view.planned_start} から {late} 日未着手")],
                actions=[
                    Action("着手日を確定し、初日の作業内容を具体化する", "着手のハードルは「最初の一歩が不明確」なことが多い"),
                    Action("着手できない理由（前提未整備/優先度衝突）を特定する", "理由が特定できなければ再発する"),
                ],
            )
        )

    if view.is_overdue and view.progress >= 90:
        causes.append(
            Cause(
                category="完了処理待ち",
                hypothesis="残作業はわずかだが、レビュー・承認・完了処理が終わっていない",
                weight=2.6,
                evidence=[
                    Evidence("進捗", f"{view.progress:.0f}% で {view.days_overdue} 日超過"),
                    Evidence("最終更新", f"{view.days_since_update} 日前"),
                ],
                actions=[
                    Action("残作業と完了条件(DoD)を確認し、完了日を確定する", "残り数%の内容が共有されていないことが停滞の主因"),
                    Action("レビュー/承認の待ち先を特定し、期限を切って依頼する", "完了間際の停滞はほぼ承認待ちであり、期限設定で解消できる"),
                    Action("後続Taskを先行着手できる範囲で開始する", "100%完了を待たずに後続を進め、遅延の伝播を止める", "low"),
                ],
            )
        )

    gap = view.progress_gap
    if gap >= 25 and not blockers:
        causes.append(
            Cause(
                category="工数見積誤り",
                hypothesis="当初見積より実作業量が大きく、計画期間に収まっていない",
                weight=1.8 + min(2.0, gap / 25),
                evidence=[
                    Evidence("進捗差", f"想定 {view.expected_progress:.0f}% に対し実績 {view.progress:.0f}%（差 {gap:.0f}pt）"),
                    Evidence("計画期間", f"{view.planned_start} 〜 {view.planned_end}（{view.duration_days} 日）"),
                ],
                actions=[
                    Action("残作業を再見積りし、完了予定日を更新する", "誤った見積のままでは以降の計画もすべてずれる"),
                    Action("Taskを分割し、価値の高い部分を先に完了させる", "全量完了を待たず部分的な成果を確定できる", "low"),
                    Action("見積前提（想定作業量・スキル前提）を見直し、他Taskへ反映する", "同じ見積根拠を使った他Taskも同様に破綻している可能性が高い"),
                ],
            )
        )

    open_issues = snapshot.open_issues_for_task(view.id)
    severe_issues = [i for i in open_issues if i.severity in HIGH_SEVERITIES]
    if severe_issues:
        causes.append(
            Cause(
                category="未解決課題",
                hypothesis="高Severityの未解決Issueが完了を阻んでいる",
                weight=2.2 + 0.5 * len(severe_issues),
                evidence=[
                    Evidence(
                        "高Severity Issue",
                        "、".join(f"{i.title}[{i.severity}]" for i in severe_issues[:3]),
                    ),
                    Evidence("未解決Issue総数", f"{len(open_issues)} 件"),
                ],
                actions=[
                    Action("高Severity Issueに解決期限とOwnerを設定する", "Issueが閉じない限りTaskは完了しない"),
                    Action("Issue解決を待たずに進められる範囲を切り出す", "全停止を避け、部分的にでも前進させる", "low"),
                ],
            )
        )

    if not causes:
        causes.append(
            Cause(
                category="要因未特定",
                hypothesis="明確な阻害要因が記録されていないため、担当者ヒアリングが必要",
                weight=1.0,
                evidence=[
                    Evidence("進捗", f"{view.progress:.0f}%（想定 {view.expected_progress:.0f}%）"),
                    Evidence("記録状況", "阻害要因を示すIssue・備考・依存関係が登録されていない"),
                ],
                actions=[
                    Action("担当者に15分ヒアリングし、阻害要因をIssue化する", "原因が記録されていないため、まず可視化が必要", "low"),
                    Action("完了予定日を再設定する", "現在の期日は既に実態と乖離している"),
                ],
            )
        )

    return sorted(causes, key=lambda c: c.weight, reverse=True)


def _rank_actions(view: TaskView, actions: list[Action]) -> list[Action]:
    """Prefer actions that unblock downstream work and are cheap to execute."""
    effort_bonus = {"low": 2.0, "medium": 1.0, "high": 0.0}
    unblock_words = ("後続", "着手", "並行", "部分", "暫定", "Freeze", "分割")

    def score(index: int, action: Action) -> float:
        value = 10.0 - index  # playbook order is the base preference
        value += effort_bonus.get(action.effort, 1.0)
        if view.successor_ids and any(w in action.action or w in action.why for w in unblock_words):
            value += 3.0 + min(3.0, len(view.successor_ids))
        if view.is_critical_path and action.effort == "high":
            value += 1.0  # on the critical path, spending more is often justified
        return value

    return [a for _, a in sorted(
        ((score(i, a), a) for i, a in enumerate(actions)),
        key=lambda pair: pair[0],
        reverse=True,
    )]


def build_delay_action(snapshot: ProjectSnapshot, view: TaskView) -> RawFinding:
    causes = _detect_causes(snapshot, view)
    primary = causes[0]

    evidence: list[Evidence] = []
    if view.is_overdue:
        evidence.append(Evidence("Due Date超過", f"{view.days_overdue} 日（予定終了日 {view.planned_end}）"))
    elif view.days_to_due is not None:
        evidence.append(Evidence("残日数", f"{view.days_to_due} 日（予定終了日 {view.planned_end}）"))
    evidence.append(Evidence("進捗", f"{view.progress:.0f}%（想定 {view.expected_progress:.0f}%）"))
    evidence.append(Evidence("Risk Score", f"{view.risk_score:.0f} / 100（{view.risk_level}）"))
    evidence.extend(primary.evidence)
    for extra in causes[1:3]:
        evidence.append(Evidence(f"副次要因: {extra.category}", extra.evidence[0].detail if extra.evidence else extra.hypothesis))
    if view.successor_ids:
        evidence.append(
            Evidence(
                "後続Task",
                f"{len(view.successor_ids)} 件が待機中: "
                + "、".join(snapshot.views[s].label() for s in view.successor_ids[:3]),
            )
        )

    actions: list[Action] = []
    seen: set[str] = set()
    for cause in causes[:2]:
        for action in cause.actions:
            if action.action not in seen:
                seen.add(action.action)
                actions.append(action)
    ranked = _rank_actions(view, actions)[:4]
    recommended = ranked[0] if ranked else None

    severity = (
        "critical"
        if view.risk_score >= 80
        else "high"
        if view.risk_score >= 60
        else "medium"
    )
    return RawFinding(
        category="delay_action",
        finding_type="delay_diagnosis",
        title=f"{view.label()}: {primary.category}",
        severity=severity,
        confidence=round(min(0.95, 0.45 + primary.weight / 10), 2),
        risk_score=view.risk_score,
        task_id=view.id,
        task_title=view.label(),
        person_id=view.owner_id,
        person_name=snapshot.owner_name(view.owner_id),
        cause_category=primary.category,
        cause_hypothesis=primary.hypothesis,
        explanation=(
            f"{view.label()} は Risk Score {view.risk_score:.0f} / 100。"
            f"推定原因は「{primary.category}」で、{primary.hypothesis}。"
        ),
        reasoning_summary=(
            "構造化分析で検出した" + "、".join(c.category for c in causes[:3]) + " の各シグナルを重み付けし、"
            f"最も裏付けの強い「{primary.category}」を主要因と判定した。"
        ),
        impact=impact_statement(snapshot, view),
        evidence=evidence,
        actions=ranked,
        recommended_action=recommended.action if recommended else None,
        recommended_action_why=recommended.why if recommended else None,
    )


def build_delay_actions(
    snapshot: ProjectSnapshot, risk_threshold: float = 50.0, limit: int = 15
) -> list[RawFinding]:
    """Diagnose every overdue task plus anything above the risk threshold."""
    targets = {
        v.id: v
        for v in snapshot.active_views()
        if v.is_overdue or v.risk_score >= risk_threshold
    }
    ordered = sorted(targets.values(), key=lambda v: (v.risk_score, v.days_overdue), reverse=True)
    return [build_delay_action(snapshot, v) for v in ordered[:limit]]
