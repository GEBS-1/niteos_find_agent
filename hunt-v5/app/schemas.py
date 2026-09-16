from pydantic import BaseModel, Field

class HuntCreate(BaseModel):
    city: str = Field(min_length=2, max_length=200)
    query: str = Field(min_length=2, max_length=300)
    count: int = Field(default=10, ge=1, le=50)
