from pydantic import BaseModel
from typing import List, Optional


class CreateEmbeddingsRequest(BaseModel):
    youtube: bool
    blog: bool


class Recommendation(BaseModel):
    title: str
    url: str
    description: Optional[str] = None
    thumbnail: Optional[str] = None
    content_category_id: int
    score: float


class RecommendationsResponse(BaseModel):
    data: List[Recommendation]
