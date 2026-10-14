from fastapi import APIRouter, HTTPException, Request

from app.agents.photo_intake import PhotoInput, PhotoAnalysis, allow_photo, analyse_photo, validate_image

router = APIRouter(prefix='/api/intake', tags=['Photo observations'])


@router.post('/photo', response_model=PhotoAnalysis)
def photo_observations(payload: PhotoInput, request: Request):
    try:
        image = validate_image(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not allow_photo(request.client.host if request.client else 'unknown'):
        raise HTTPException(status_code=429, detail='Photo analysis limit reached; continue with text')
    return analyse_photo(payload, image)
