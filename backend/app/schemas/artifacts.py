from pydantic import BaseModel


class ArtifactDescriptor(BaseModel):
    kind: str
    label: str
    available: bool
    filename: str | None = None
    url: str | None = None


class GenerationArtifactBundle(BaseModel):
    generation_result_id: str
    artifacts: list[ArtifactDescriptor]
