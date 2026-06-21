"""Doctor Q&A on report paragraphs via RAG + LLM."""
from __future__ import annotations

from src.llm.client import get_llm_client
from src.reports.paragraph_rag import ParagraphRAGIndex
from src.reports.report_store import ReportStore
from src.schemas import ReportAskRequest, ReportAskResponse, ReportParagraph


class ReportQAService:
    def __init__(self) -> None:
        self.store = ReportStore()
        self.llm = get_llm_client()

    def ask(self, req: ReportAskRequest) -> ReportAskResponse:
        report = self.store.get_report(req.patient_id, req.report_id)
        index = ParagraphRAGIndex(report)
        context = index.build_context(req.question, top_k=4)
        hits = index.search(req.question, top_k=3)
        related = [p for p, _ in hits]

        system = (
            "你是 MedSafe 临床报告助手。仅基于给定报告段落与补充记录回答医生问题。"
            "若信息不足请明确说明，不要编造。回答应简洁、临床化。"
        )
        user = f"报告上下文：\n{context}\n\n医生问题：{req.question}"
        answer = self.llm.chat(system, user, temperature=0.1)

        updated = self.store.append_supplement(
            req.patient_id,
            req.report_id,
            req.question,
            answer,
            related_paragraph_ids=[p.paragraph_id for p in related],
        )
        return ReportAskResponse(answer=answer, related_paragraphs=related, report=updated)
