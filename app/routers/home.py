from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.overview import overview
from app.web.templates import render

router = APIRouter()


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    return render(request, "pages/home.html", o=overview(db))
