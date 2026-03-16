from fastapi import APIRouter
router = APIRouter()

@router.get("/")
def list_results():
    return {"message": "analysis results endpoint"}