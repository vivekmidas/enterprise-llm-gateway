from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog
from app.api.auth.dependencies import require_system_admin, require_admin
from app.core.database import get_db
from app.models.db_models import CategoryDB
from app.api.categories.schemas import CategoryCreate, CategoryUpdate, CategoryResponse, CategoryListResponse

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/categories", tags=["categories"])

@router.get("", response_model=CategoryListResponse)
async def get_workflow_categories(db: AsyncSession = Depends(get_db)):
    """Fetches all node categories from the database."""
    logger.info("get_workflow_categories_request")
    
    try:
        result = await db.execute(select(CategoryDB).order_by(CategoryDB.group.asc()))
        categories = result.scalars().all()
        logger.info("get_workflow_categories_response", count=len(categories))
        return {"categories": categories}
    except Exception as e:
        logger.error("failed_to_load_categories", error=str(e))
        return {"categories": []}

@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(category_in: CategoryCreate, db: AsyncSession = Depends(get_db), user=Depends(require_system_admin)):
    """Creates a new node category."""
    logger.info("create_category_request", group=category_in.group)
    db_category = CategoryDB(**category_in.model_dump())
    # logger.debug("create_category_db_object", category_data=db_category.model_dump())
    db.add(db_category)
    await db.commit()
    await db.refresh(db_category)
    logger.info("create_category_response", category_id=db_category.id)
    return db_category

@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(category_id: str, db: AsyncSession = Depends(get_db)):
    """Fetches a single category by ID."""
    result = await db.execute(select(CategoryDB).where(CategoryDB.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        logger.warning("get_category_not_found", category_id=category_id)
        raise HTTPException(status_code=404, detail="Category not found")
    return category

@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(category_id: str, category_in: CategoryUpdate, db: AsyncSession = Depends(get_db), user=Depends(require_system_admin)):
    """Updates an existing category."""
    result = await db.execute(select(CategoryDB).where(CategoryDB.id == category_id))
    db_category = result.scalar_one_or_none()
    if not db_category:
        logger.warning("update_category_not_found", category_id=category_id)
        raise HTTPException(status_code=404, detail="Category not found")
    
    update_data = category_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_category, field, value)
    
    await db.commit()
    await db.refresh(db_category)
    logger.info("update_category_success", category_id=category_id)
    return db_category

@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: str, db: AsyncSession = Depends(get_db), user=Depends(require_system_admin)):
    """Deletes a category."""
    logger.info("delete_category_request", category_id=category_id)
    result = await db.execute(select(CategoryDB).where(CategoryDB.id == category_id))
    db_category = result.scalar_one_or_none()
    logger.debug("delete_category_lookup", category_id=category_id, found=bool(db_category))
    if not db_category:
        logger.warning("delete_category_not_found", category_id=category_id)
        raise HTTPException(status_code=404, detail="Category not found")
    
    await db.delete(db_category)
    await db.commit()
    logger.info("delete_category_success", category_id=category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)