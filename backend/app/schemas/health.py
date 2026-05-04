from pydantic import BaseModel


class HealthRead(BaseModel):
    status: str
