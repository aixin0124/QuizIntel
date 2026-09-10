"""趣测智研的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SurveyQuestion:
    """原始市场调研题目。"""

    question_id: str
    text: str
    question_type: str = "single_choice"
    options: list[str] = field(default_factory=list)
    research_tag: str = ""
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "text": self.text,
            "question_type": self.question_type,
            "options": self.options,
            "research_tag": self.research_tag,
            "required": self.required,
        }


@dataclass
class WrappedQuestion:
    """经过 AI 包装后展示给答题者的题目。"""

    question_id: str
    public_text: str
    question_type: str
    options: list[str] = field(default_factory=list)
    research_tag: str = ""
    source_text: str = ""
    required: bool = True
    research_refs: list[str] = field(default_factory=list)
    option_scores: dict[str, dict[str, float]] = field(default_factory=dict)
    dimension_weights: dict[str, float] = field(default_factory=dict)
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "public_text": self.public_text,
            "question_type": self.question_type,
            "options": self.options,
            "research_tag": self.research_tag,
            "source_text": self.source_text,
            "required": self.required,
            "research_refs": self.research_refs,
            "option_scores": self.option_scores,
            "dimension_weights": self.dimension_weights,
            "rationale": self.rationale,
        }


@dataclass
class WrappedSurvey:
    """互动测评包装结果。"""

    survey_name: str
    theme: str
    tagline: str
    intro: str
    disclosure: str
    result_types: list[dict[str, Any]]
    questions: list[WrappedQuestion]
    brand_goal: str = ""
    source: str = "llm"
    dimensions: list[dict[str, Any]] = field(default_factory=list)
    analysis_method: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "survey_name": self.survey_name,
            "theme": self.theme,
            "tagline": self.tagline,
            "intro": self.intro,
            "disclosure": self.disclosure,
            "result_types": self.result_types,
            "questions": [question.to_dict() for question in self.questions],
            "brand_goal": self.brand_goal,
            "source": self.source,
            "dimensions": self.dimensions,
            "analysis_method": self.analysis_method,
        }


@dataclass
class SurveyResponse:
    """一次答题记录。"""

    wrapped_survey_name: str
    answers: dict[str, Any]
    result_type: str
    research_answers: dict[str, Any]
    dimension_scores: dict[str, float] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "wrapped_survey_name": self.wrapped_survey_name,
            "answers": self.answers,
            "result_type": self.result_type,
            "research_answers": self.research_answers,
            "dimension_scores": self.dimension_scores,
            "analysis": self.analysis,
        }
