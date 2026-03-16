from fastapi import APIRouter
router = APIRouter()

@router.post("/")
def start_import():
    return {"message": "import run started"}