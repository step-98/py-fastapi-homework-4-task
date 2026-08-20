from datetime import date
from fastapi import UploadFile, Form, File, HTTPException
from pydantic import BaseModel, field_validator, HttpUrl, ConfigDict

from validation import (
    validate_name,
    validate_image,
    validate_gender,
    validate_birth_date
)

class ProfileCreateSchema(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: UploadFile


    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        validate_name(value)
        return value.lower()

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, value: str) -> str:
        validate_gender(value)
        return value

    @field_validator("date_of_birth")
    @classmethod
    def validate_birth_date(cls, value: str) -> date:
        validate_birth_date(value)
        return value

    @field_validator("avatar")
    @classmethod
    def validate_avatar(cls, value: UploadFile) -> UploadFile:
        validate_image(value)
        return value

    @field_validator("info")
    @classmethod
    def validate_info(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Info field cannot be empty or contain only spaces.")
        return value


class ProfileResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: str
