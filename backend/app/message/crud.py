from datetime import datetime
from typing import Tuple

from app.message import models, schemas
from app.open_ai import process_message_with_openai
from app.user.crud import check_user_exists
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_messages(
    db: AsyncSession,
    user_id: int,
    skip: int = 0,
    limit: int = 10,
    max_limit: int = 100,
):
    limit = min(limit, max_limit)
    if skip < 0:
        skip = 0

    total = await db.scalar(
        select(func.count()).filter(models.Message.user_id == user_id)
    )

    result = await db.execute(
        select(models.Message)
        .filter(models.Message.user_id == user_id)
        .order_by(models.Message.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = result.scalars().all()

    return {"items": items, "total": total, "has_more": (skip + limit) < total}


async def create_message(
    db: AsyncSession, user_id: int, message_data: schemas.MessageCreate
) -> Tuple[schemas.MessageResponse, schemas.MessageResponse]:
    if not await check_user_exists(db, user_id):
        raise HTTPException(status_code=400, detail="User not found")

    user_message = models.Message(
        user_id=user_id,
        content=message_data.content,
        created_at=datetime.utcnow(),
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)

    try:
        gpt_response = await process_message_with_openai(message_data.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GPT error: {str(e)}")

    gpt_message = models.Message(
        user_id=user_id, content=gpt_response, created_at=datetime.utcnow()
    )
    db.add(gpt_message)
    await db.commit()
    await db.refresh(gpt_message)

    return schemas.MessageResponse.model_validate(
        user_message
    ), schemas.MessageResponse.model_validate(gpt_message)
