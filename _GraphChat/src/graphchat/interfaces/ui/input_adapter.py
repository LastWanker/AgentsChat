from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class InputDraft:
    session_id: str
    chunks: list[str] = field(default_factory=list)

    def add_chunk(self, text: str) -> None:
        self.chunks.append(text)

    def commit(self) -> str:
        content = "".join(self.chunks)
        self.chunks.clear()
        return content


class InputAdapter:
    def __init__(self):
        self._drafts: dict[str, InputDraft] = {}

    def input_chunk(self, session_id: str, text: str) -> None:
        draft = self._drafts.setdefault(session_id, InputDraft(session_id=session_id))
        draft.add_chunk(text)

    def input_commit(self, session_id: str) -> str:
        draft = self._drafts.setdefault(session_id, InputDraft(session_id=session_id))
        # 待拓展：可在此接入输入质量校验、去抖与节流策略。
        return draft.commit()

