from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.analytics import get_project_dashboard_metrics

router = APIRouter()


@router.get('/projects/{project_id}')
def project_dashboard(project_id: str):
    try:
        return get_project_dashboard_metrics(project_id)
    except Exception as err:
        return JSONResponse({'error': str(err)}, 500)
