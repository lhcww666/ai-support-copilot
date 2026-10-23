from __future__ import annotations

from dataclasses import dataclass

from app.knowledge import KnowledgeService


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    question: str
    expected_title: str


CASES = [
    EvaluationCase("员工密码至少需要多少位？", "账号与密码策略"),
    EvaluationCase("密码连续输错几次会锁定账号？", "账号与密码策略"),
    EvaluationCase("标准订单付款后多久发货？", "订单与配送规则"),
    EvaluationCase("物流轨迹超过 48 小时没更新怎么办？", "订单与配送规则"),
    EvaluationCase("退款超过多少金额需要主管审批？", "退款与售后规则"),
    EvaluationCase("定制商品可以七天无理由退货吗？", "退款与售后规则"),
    EvaluationCase("发生 P1 事故后多久必须响应？", "管理员故障响应手册"),
    EvaluationCase("事故复盘需要在多久内提交？", "管理员故障响应手册"),
    EvaluationCase("哪些情况必须升级到人工专家？", "客服升级流程"),
    EvaluationCase("知识库没有明确依据时客服应该怎么做？", "客服升级流程"),
]


class EvaluationService:
    def __init__(self, knowledge: KnowledgeService) -> None:
        self.knowledge = knowledge

    def run_rag_evaluation(self) -> dict:
        results: list[dict] = []
        hits = 0
        for case in CASES:
            retrieved = self.knowledge.search(case.question, "admin", limit=4)
            titles = [source.title for source in retrieved]
            passed = case.expected_title in titles
            if passed:
                hits += 1
            results.append(
                {
                    "question": case.question,
                    "expected_title": case.expected_title,
                    "retrieved_titles": titles,
                    "passed": passed,
                }
            )
        return {
            "suite": "rag-retrieval",
            "total": len(CASES),
            "hits": hits,
            "pass_rate": round(hits / len(CASES), 4) if CASES else 0.0,
            "cases": results,
        }
