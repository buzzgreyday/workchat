from fastapi import APIRouter
from starlette.responses import JSONResponse
from starlette.status import HTTP_200_OK

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_class=JSONResponse,
    response_model=None,
    summary="Check server health.",
    description="Returns status 200 if server is up.",
    responses={
        200: {
            "content": {"application/json": {"schema": {"type": "object"}}},
            "description": "Server is up.",
        }
    },
)
async def health() -> JSONResponse:
    return JSONResponse(status_code=HTTP_200_OK, content={"status": "ok"})