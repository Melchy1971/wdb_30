from fastapi import APIRouter
router = APIRouter()

@router.post("/")
def start_analysis():
    return {"message": "analysis run started"}