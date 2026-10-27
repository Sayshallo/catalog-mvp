from contextlib import asynccontextmanager
from uuid import uuid4
import logging

from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from .database import get_db, engine, Base
from .models import Product
from .schemas import ProductOut
from .s3_client import ensure_bucket, upload_file, get_presigned_url, delete_file, get_image_object, MINIO_BUCKET, minio_client

from io import BytesIO
from PIL import Image, UnidentifiedImageError
import os
import secrets

logger = logging.getLogger(__name__)
BOT_API_TOKEN = os.getenv("BOT_API_TOKEN")
MAX_IMAGE_SIZE = 1024 * 1024 * 20

def validate_image_content(content: bytes, content_type: str) -> None:
    image_formats = {
        "image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP" }

    try:
        with Image.open(BytesIO(content)) as image:
            expected_type = image_formats.get(content_type)

            if expected_type is None or image.format != expected_type:
                raise HTTPException(status_code = 415, detail = "Поддреживаются только файлы с расширением: JPEG, WEBP и PNG")        
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise HTTPException(status_code = 415, detail = "Файл не является корректным изображением")

def verify_bot_token(authorization: str | None = Header(default=None)):
    if not BOT_API_TOKEN: raise RuntimeError("Не был задан BOT_API_TOKEN")

    if authorization is None or not secrets.compare_digest(
        authorization,
        f"Bearer {BOT_API_TOKEN}"
    ): raise HTTPException(status_code = 401, detail = "Необходима авторизация")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await run_in_threadpool(ensure_bucket)

    yield

    await engine.dispose()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],
    allow_methods = ["POST", "GET"],
    allow_headers = ["*"],
)

@app.get("/api/products", response_model = list[ProductOut])
async def list_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product).where(Product.is_active.is_(True)).order_by(Product.created_at.desc())
    )

    products = result.scalars().all()

    response = []

    for p in products:
        image_url = await run_in_threadpool(get_presigned_url, p.image_key)

        response.append(ProductOut(
            id = p.id,
            title = p.title,
            image_url = image_url,
            created_at = p.created_at
        ))

    return response

@app.post("/api/products", response_model = ProductOut)
async def create_product(
    title: str = Form(...),
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_bot_token)
):
    title = title.strip()

    if not title:
        raise HTTPException(status_code = 422, detail = "Атрибут title не был задан!")

    if len(title) > 255:
        raise HTTPException(status_code = 422, detail = "Название товара не должно превышать 255 символов!")

    content = await image.read(MAX_IMAGE_SIZE + 1)

    if not content:
        raise HTTPException(status_code = 400, detail = "Атрибут image не был задан!")

    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code = 413, detail = "Атрибут image не должен весить более 20МБ!")

    validate_image_content(content, image.content_type)

    extension_by_type = {
        "image/jpeg" : "jpg",
        "image/png" : "png",
        "image/webp" : "webp",
    }
    extension = extension_by_type[image.content_type]

    key = f"products/{uuid4()}.{extension}"

    await run_in_threadpool(upload_file, key, content, image.content_type)

    product = Product(title=title, image_key = key)
    try:
        db.add(product)
        await db.commit()
        await db.refresh(product)
    except Exception:
        await db.rollback()
        logger.exception("Не удалось сохранить товар в БД!")

        try:
            await run_in_threadpool(delete_file, key)
        except Exception:
            logger.exception("Не удалось удалить файл из minio!")

        raise HTTPException(status_code = 500, detail = "Произошла ошибка при добавлении товара...")

    image_url = await run_in_threadpool(get_presigned_url, key)

    return ProductOut(
        id = product.id,
        title = product.title,
        image_url = image_url,
        created_at = product.created_at
    )

@app.get("/api/products/{product_id}/image")
async def get_product_image(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.is_active.is_(True))
    )

    product = result.scalar_one_or_none()

    if product is None: raise HTTPException(status_code = 404, detail = "Товар не найден...")

    try: image = await run_in_threadpool(get_image_object, product.image_key)
    except Exception: 
        logger.exception(f"Не удалось получить изображение товара id[{product_id}]")
        raise HTTPException(status_code = 404, detail = "Изображение не найдено")

    def stream_image():
        try:
            while True:
                chunk = image.read(64 * 1024)

                if not chunk: break

                yield chunk
        finally:
            image.clone()
            image.release_conn()

    content_type = "application/octet-stream"
    image_key = product.image_key.lower()

    if image_key.endswith((".jpg", ".jpeg")): content_type = "image/jpeg"
    elif image_key.endswith(".png"): content_type = "image/png"
    elif image_key.endswith(".webp"): content_type = "image/webp"

    return StreamingResponse(
        stream_image(),
        media_type = content_type,
        headers = {
            "Cache-Control": "public, max-age=3600",
            "X-Content-Type-Options": "nosniff"
        }
    )