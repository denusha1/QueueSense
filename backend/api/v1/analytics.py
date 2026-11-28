"""Aggregate reports over the same arrival cohort as the clinic workspace."""

from typing import Annotated

from fastapi import APIRouter, Query

from backend.api.dependencies import AppSettings
from backend.api.v1.dependencies import V1User
from backend.schemas.v1 import (
    AnalyticsQuery,
    Data,
    PeakHour,
    QueuePerformance,
    WaitingTime,
)
from backend.services import reporting
from backend.services.metrics import PERFORMANCE_AGGREGATES, WAIT_AGGREGATES

router = APIRouter(prefix='/analytics', tags=['v1 analytics'])


@router.get('/waiting-time', response_model=Data[WaitingTime])
def waiting_time(
    query: Annotated[AnalyticsQuery, Query()], settings: AppSettings, user: V1User
):
    return {
        'data': reporting.cohort_metrics(settings, user, query, projection=WAIT_AGGREGATES),
    }


@router.get('/peak-hours', response_model=Data[list[PeakHour]])
def peak_hours(
    query: Annotated[AnalyticsQuery, Query()], settings: AppSettings, user: V1User
):
    return {'data': reporting.peak_metrics(settings, user, query)}


@router.get('/queue-performance', response_model=Data[QueuePerformance])
def queue_performance(
    query: Annotated[AnalyticsQuery, Query()], settings: AppSettings, user: V1User
):
    return {
        'data': reporting.cohort_metrics(settings, user, query, projection=PERFORMANCE_AGGREGATES),
    }
