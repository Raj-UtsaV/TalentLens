from pydantic import BaseModel, Field, model_validator


class JobCreate(BaseModel):
    description: str = Field(min_length=20, max_length=50000)
    title: str | None = Field(default=None, max_length=200)
    required_skills: list[str] | None = None
    preferred_skills: list[str] | None = None
    min_experience: float | None = Field(default=None, ge=0, le=60)
    qualifications: list[str] | None = None


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=20, max_length=50000)

    @model_validator(mode="after")
    def require_change(self):
        if self.title is None and self.description is None:
            raise ValueError("Provide a role title or job description to update")
        return self


class JobPreview(BaseModel):
    description: str = Field(min_length=20, max_length=50000)


class Weights(BaseModel):
    skills: float = Field(default=.50, ge=0, le=1)
    semantic: float = Field(default=.25, ge=0, le=1)
    experience: float = Field(default=.15, ge=0, le=1)
    education: float = Field(default=.10, ge=0, le=1)

    @model_validator(mode="after")
    def require_positive_weight(self):
        if not sum((self.skills, self.semantic, self.experience, self.education)):
            raise ValueError("At least one score weight must be positive")
        return self
