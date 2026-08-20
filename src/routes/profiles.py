import os
from datetime import date
from config import get_s3_storage_client, get_settings, get_jwt_auth_manager, BaseAppSettings
from database import UserModel, UserGroupEnum
from database.models.accounts import UserProfileModel
from exceptions import TokenExpiredError, BaseSecurityError, InvalidTokenError, S3FileUploadError
from fastapi import APIRouter, HTTPException, status, Form, File, Depends, UploadFile
from security.interfaces import JWTAuthManagerInterface
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from security.http import get_token
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from src.schemas.profiles import ProfileCreateSchema, ProfileResponseSchema
from sqlalchemy import select
from storages import S3StorageInterface
from pydantic import ValidationError

router = APIRouter()

@router.post("/users/{user_id}/profile/", response_model=ProfileResponseSchema, status_code=status.HTTP_201_CREATED)
async def user_profile(
        user_id: int,
        first_name: str = Form(...),
        last_name: str = Form(...),
        gender: str = Form(...),
        date_of_birth: date = Form(...),
        info: str = Form(...),
        avatar: UploadFile = File(...),
        jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
        settings: BaseAppSettings = Depends(get_settings),
        token: str = Depends(get_token),
        s3_client: S3StorageInterface = Depends(get_s3_storage_client),
        db: AsyncSession = Depends(get_db)
):

    try:
        decoded_token = jwt_manager.decode_access_token(token)
        current_user_id = decoded_token.get("user_id")
    except TokenExpiredError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired.")
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    stmt = select(UserModel).options(joinedload(UserModel.group)).where(UserModel.id == current_user_id)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user is None or not existing_user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or not active.")

    is_admin = existing_user.group is not None and existing_user.group.name == UserGroupEnum.ADMIN
    if not is_admin and current_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to edit this profile.")

    stmt = select(UserProfileModel).where(UserProfileModel.user_id == user_id)
    result = await db.execute(stmt)
    existing_profile = result.scalar_one_or_none()
    if existing_profile is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already has a profile.")
    try:
        profile_data = ProfileCreateSchema(
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            date_of_birth=date_of_birth,
            info=info,
            avatar=avatar,
        )
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))

    _, file_extension = os.path.splitext(avatar.filename)
    avatar_path = f"avatars/{user_id}_avatar{file_extension}"
    await avatar.seek(0)
    file_content = await avatar.read()

    try:
        await s3_client.upload_file(file_name=avatar_path, file_data=file_content)
    except S3FileUploadError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to upload avatar. Please try again later.")


    try:
        profile = UserProfileModel(
            user_id=user_id,
            first_name=profile_data.first_name,
            last_name=profile_data.last_name,
            gender=profile_data.gender,
            date_of_birth=profile_data.date_of_birth,
            info=profile_data.info,
            avatar=avatar_path,
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    except SQLAlchemyError:
        await db.rollback()
        await s3_client.delete_file(avatar_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    avatar_url = await s3_client.get_file_url(avatar_path)

    return ProfileResponseSchema(
        id=profile.id,
        user_id=profile.user_id,
        first_name=profile.first_name,
        last_name=profile.last_name,
        gender=profile.gender,
        date_of_birth=profile.date_of_birth,
        info=profile.info,
        avatar=avatar_url,
    )
