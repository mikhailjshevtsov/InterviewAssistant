from pydantic import Field

from app.schemas.base import SchemaModel


class VacancyAnalysis(SchemaModel):
    position: str | None = Field(description="Название должности из вакансии.")
    company: str | None = Field(description="Название компании, если указано.")
    hard_skills: list[str] = Field(
        default_factory=list, description="Технические навыки и инструменты."
    )
    soft_skills: list[str] = Field(
        default_factory=list, description="Личные и коммуникативные качества."
    )
    experience: list[str] = Field(
        default_factory=list, description="Требования к опыту кандидата."
    )
    responsibilities: list[str] = Field(
        default_factory=list, description="Обязанности на позиции."
    )
    interview_topics: list[str] = Field(
        default_factory=list, description="Темы, которые вероятно обсудят на интервью."
    )
