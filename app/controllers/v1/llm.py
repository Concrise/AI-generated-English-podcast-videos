from fastapi import Depends, Request

from app.controllers import base
from app.controllers.v1.base import new_router
from app.models.schema import (
    PodcastScriptRequest,
    PodcastScriptResponse,
    PodcastTermsRequest,
    PodcastTermsResponse,
)
from app.services import llm
from app.utils import utils

# authentication dependency
router = new_router(dependencies=[Depends(base.verify_token)])


@router.post(
    "/scripts",
    response_model=PodcastScriptResponse,
    summary="Create a podcast script from article text",
)
def generate_podcast_script(request: Request, body: PodcastScriptRequest):
    podcast_script = llm.generate_podcast_script(
        article_text=body.article_text,
        language=body.language,
    )
    for item in podcast_script:
        item.speaker_1_voice = body.speaker_1_voice or item.speaker_1_voice
        item.speaker_2_voice = body.speaker_2_voice or item.speaker_2_voice

    response = {"podcast_script": podcast_script}
    return utils.get_response(200, response)


@router.post(
    "/terms",
    response_model=PodcastTermsResponse,
    summary="Generate material search terms from a podcast script",
)
def generate_podcast_terms(request: Request, body: PodcastTermsRequest):
    video_terms = llm.generate_terms_from_podcast(
        podcast_script=body.podcast_script,
        amount=body.amount,
    )
    response = {"video_terms": video_terms}
    return utils.get_response(200, response)
