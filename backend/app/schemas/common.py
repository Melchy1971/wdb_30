from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TimestampedResponse(ApiModel):
    created_at: datetime
    updated_at: datetime
