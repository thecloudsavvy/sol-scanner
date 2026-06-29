import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import dashboard_basic_auth_middleware, validate_security_config
from app.config.settings import settings
from app.database.session import get_db, init_db
from app.models.alert import SolAlert
from app.models.alert_performance import SolAlertPerformance
from app.models.token import SolToken
from app.scanner.engine import get_scanner_status

app = FastAPI(title=settings.PROJECT_NAME)
app.middleware("http")(dashboard_basic_auth_middleware)


@app.on_event("startup")
def on_startup() -> None:
    validate_security_config()
    init_db()


os.makedirs("templates", exist_ok=True)
os.makedirs("static/css", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def common_context(request: Request) -> Dict[str, Any]:
    return {
        "request": request,
        "project_name": settings.PROJECT_NAME,
        "scan_interval": settings.SOL_SCAN_INTERVAL_SECONDS,
    }


@app.get("/", response_class=HTMLResponse)
def page_overview(request: Request, db: Session = Depends(get_db)):
    ctx = common_context(request)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    alerts_today = (
        db.query(SolAlert).filter(SolAlert.alerted_at >= today_start).count()
    )
    total_tokens = db.query(SolToken).count()
    total_alerts = db.query(SolAlert).count()

    top_performers = (
        db.query(SolAlertPerformance, SolAlert, SolToken)
        .join(SolAlert, SolAlert.id == SolAlertPerformance.alert_id)
        .outerjoin(SolToken, SolToken.address == SolAlert.token_address)
        .filter(SolAlertPerformance.return_1h.isnot(None))
        .order_by(SolAlertPerformance.return_1h.desc())
        .limit(5)
        .all()
    )

    ctx.update({
        "status": get_scanner_status(),
        "alerts_today": alerts_today,
        "total_tokens": total_tokens,
        "total_alerts": total_alerts,
        "top_performers": top_performers,
        "active_tab": "overview",
    })
    return templates.TemplateResponse("overview.html", ctx)


@app.get("/alerts", response_class=HTMLResponse)
def page_alerts(request: Request, db: Session = Depends(get_db)):
    ctx = common_context(request)
    rows = (
        db.query(SolAlert, SolToken)
        .outerjoin(SolToken, SolToken.address == SolAlert.token_address)
        .order_by(SolAlert.alerted_at.desc())
        .limit(100)
        .all()
    )
    ctx.update({"alerts": rows, "active_tab": "alerts"})
    return templates.TemplateResponse("alerts.html", ctx)


@app.get("/performance", response_class=HTMLResponse)
def page_performance(request: Request, db: Session = Depends(get_db)):
    ctx = common_context(request)
    stats = compute_performance_stats(db)
    records = (
        db.query(SolAlertPerformance, SolAlert, SolToken)
        .join(SolAlert, SolAlert.id == SolAlertPerformance.alert_id)
        .outerjoin(SolToken, SolToken.address == SolAlert.token_address)
        .order_by(SolAlert.alerted_at.desc())
        .limit(100)
        .all()
    )
    ctx.update({"stats": stats, "records": records, "active_tab": "performance"})
    return templates.TemplateResponse("performance.html", ctx)


@app.get("/tokens", response_class=HTMLResponse)
def page_tokens(request: Request, db: Session = Depends(get_db)):
    ctx = common_context(request)
    tokens = (
        db.query(SolToken)
        .order_by(SolToken.last_scanned_at.desc())
        .limit(200)
        .all()
    )
    ctx.update({"tokens": tokens, "active_tab": "tokens"})
    return templates.TemplateResponse("tokens.html", ctx)


@app.get("/settings", response_class=HTMLResponse)
def page_settings(request: Request):
    ctx = common_context(request)
    ctx.update({
        "settings": settings,
        "active_tab": "settings",
    })
    return templates.TemplateResponse("settings.html", ctx)


def compute_performance_stats(db: Session) -> Dict[str, Any]:
    windows = [
        ("15m", SolAlertPerformance.return_15m),
        ("1h", SolAlertPerformance.return_1h),
        ("4h", SolAlertPerformance.return_4h),
        ("24h", SolAlertPerformance.return_24h),
    ]
    stats: Dict[str, Any] = {}
    for label, col in windows:
        rows = db.query(col).filter(col.isnot(None)).all()
        values = [r[0] for r in rows if r[0] is not None]
        if not values:
            stats[label] = {"count": 0, "win_rate": 0, "avg_return": 0}
            continue
        wins = sum(1 for v in values if v > 0)
        stats[label] = {
            "count": len(values),
            "win_rate": round(100.0 * wins / len(values), 1),
            "avg_return": round(sum(values) / len(values), 2),
        }
    return stats


@app.get("/api/alerts")
def api_alerts(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    alerts = db.query(SolAlert).order_by(SolAlert.alerted_at.desc()).limit(50).all()
    return [
        {
            "id": a.id,
            "token_address": a.token_address,
            "alerted_at": a.alerted_at.isoformat() if a.alerted_at else None,
            "filter_score": a.filter_score,
            "source": a.source,
            "liquidity_usd": a.liquidity_usd,
            "volume_5m": a.volume_5m,
            "price_usd": a.price_usd,
        }
        for a in alerts
    ]


@app.get("/api/performance")
def api_performance(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return compute_performance_stats(db)


@app.get("/api/status")
def api_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    status = get_scanner_status()
    status["alert_count"] = db.query(SolAlert).count()
    status["token_count"] = db.query(SolToken).count()
    return status
