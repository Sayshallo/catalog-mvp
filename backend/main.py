from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPExeption

from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.concurrency import run_in_threadpool

from .database import get_db, engine, Base
from .models import Product
from .schemas import ProductOut
from .s3_client import ensure_bucket, upload_file, get_presigned_url

MAX_IMAGE_SIZE = 1024 * 1024 * 20
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp"
}

# 5. Исправляем backend/main.py

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await run_in_threadpool(ensure_bucket)

    yield

    await engine.dispose

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],
    allow_methods = ["POST", "GET"],
    allow_headers = ["*"],
)

@app.get("/api/products", response_model = list[ProductOut])
async def list_products( db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product).where(Product.is_active.is_(True)).order_by(product.created_at.desc())
    )

    product = result.scalars().all()

    response = []

    for p in products:
        image_url = await run_in_threadpool(get_presigned_url, product.image_key)

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
    db: AsyncSession = Depends(get_db)
):
    title = title.strip()

    if not title:
        raise HTTPExeption(status_code = 422, detail = "Атрибут title не был задан!")

    if image.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPExeption(status = 415, detail = "Поддерживаются только изображения типа: JPEG, PNG и WebP")

    content = await image.read()

    if not content:
        raise HTTPExeption(status_code = 400, detail = "Атрибут image не был задан!")

    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPExeption(status_code = 413, detail = "Атрибут image не должен весить более 20МБ!")

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
        raise HTTPExeption(statuse_code = 500, detail = "Произошла ошибка при добавлении товара...")

    image_url = await run_in_threadpool(get_presigned_url, key)

    return Product(
        id = product.id,
        title = product.title,
        image_url = image_url,
        created_at = product.created_at
    )