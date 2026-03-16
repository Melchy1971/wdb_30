from fastapi import APIRouter
router = APIRouter()

@router.get("/")
def list_sources():
    return {"message": "list sources endpoint"}