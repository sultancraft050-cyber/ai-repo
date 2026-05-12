from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.models.launch import (
    AnalyticsEventCreate,
    AnalyticsEventResponse,
    FeedbackSubmissionCreate,
    FeedbackSubmissionResponse,
)
from app.services.launch_analytics import record_feedback_submission, record_launch_event

router = APIRouter(tags=["launch-analytics-feedback"])


def _rate_limited(request: Request, key: str, label: str) -> None:
    client = request.client.host if request.client else "unknown"
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter and not limiter.allow(f"public:{key}:{client}"):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"Too many {label}. Try again later.")


@router.post("/analytics/events", response_model=AnalyticsEventResponse)
def record_analytics_event(request_body: AnalyticsEventCreate, request: Request) -> AnalyticsEventResponse:
    _rate_limited(request, "analytics-events", "analytics events")
    event = record_launch_event(request.app.state, request_body)
    return AnalyticsEventResponse(status="recorded", event_id=event.event_id)


@router.post("/feedback", response_model=FeedbackSubmissionResponse)
def submit_feedback(request_body: FeedbackSubmissionCreate, request: Request) -> FeedbackSubmissionResponse:
    _rate_limited(request, "feedback", "feedback submissions")
    feedback = record_feedback_submission(request.app.state, request_body)
    return FeedbackSubmissionResponse(
        status="accepted",
        feedback_id=feedback.feedback_id,
        message="Feedback received for founder review.",
    )
