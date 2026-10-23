from pydantic import BaseModel, Field


class CreateTicketRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    subject: str = Field(..., max_length=500)
    body: str = Field(...)
