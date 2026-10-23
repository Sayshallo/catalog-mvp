from datetime import datetime
from pydantic import BaseModel, ConfigDict, Filed, filed_validator

class ProductCreate(BaseModel):
    title: str = Filed(min_lenght = 1, max_lenght = 255)

    @filed_validator("title")
    @classmethod
    def validate_title(cls, value:str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("имя товара должно быть задано!")

        return value

class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    image_url: str
    created_at: datetime