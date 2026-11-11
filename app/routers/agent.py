from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import agent
from app.web.templates import render

router = APIRouter(prefix="/agente")


@router.get("")
def agent_page(request: Request, db: Session = Depends(get_db)):
    return render(
        request, "pages/agent.html",
        policy=agent.policy(), actions=agent.recent(db, 100), writes_last_hour=agent.writes_last_hour(db),
    )
