"""GN-066: readable, read-only fusion diagnostics with manual delay previews.

All observations are caller-supplied; this is not a live sync or permission to
move the ball. Manual offsets affect only copies of aligned event timestamps.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import Field, model_validator

from app.contracts import Id, StrictModel
from app.fusion_conflicts import (
    FusionConflictRequest, FusionConflictResponse, preview_fusion_conflicts,
)
from app.source_delay import (
    RelativeDelayRequest, RelativeDelayResponse, preview_relative_delays,
)
from app.source_selection import (
    SourceSelectionRequest, SourceSelectionResponse, preview_active_source,
)


class ManualSourceOffset(StrictModel):
    source_id: Id
    seconds: float = Field(ge=-120, le=120, allow_inf_nan=False)


class FusionDiagnosticRequest(StrictModel):
    selection: SourceSelectionRequest
    fusion: FusionConflictRequest
    manual_offsets: list[ManualSourceOffset] = Field(default_factory=list)
    delay: RelativeDelayRequest | None = None

    @model_validator(mode="after")
    def check(self) -> "FusionDiagnosticRequest":
        if self.selection.evaluated_at != self.fusion.evaluated_at:
            raise ValueError("Selection and fusion must use one evaluation time")
        offsets = [row.source_id for row in self.manual_offsets]
        if len(set(offsets)) != len(offsets):
            raise ValueError("Duplicate manual offset for a source")
        if self.fusion.active_source_id is not None:
            raise ValueError("Active source is selected by GN-063, not supplied by caller")
        return self


class CalibratedObservation(StrictModel):
    source_id: Id
    segment_id: Id
    manual_offset_seconds: float
    original_aligned_at: datetime | None
    preview_aligned_at: datetime | None


class FusionTrace(StrictModel):
    step: Literal["delay", "selection", "source", "manual_offset", "fusion"]
    source_id: Id | None = None
    status: str
    reason: str


class FusionDiagnosticResponse(StrictModel):
    selection: SourceSelectionResponse
    fusion: FusionConflictResponse
    delay: RelativeDelayResponse | None = None
    calibration: list[CalibratedObservation]
    trace: list[FusionTrace]
    calibration_mode: Literal["manual_unverified"] = "manual_unverified"
    persisted: Literal[False] = False
    eligible_for_state_update: Literal[False] = False


def preview_fusion_diagnostics(
    request: FusionDiagnosticRequest, *, registered_source_ids: set[str],
) -> FusionDiagnosticResponse:
    """Explain selection, clock offsets and contradiction vetoes without writes."""
    referenced = (
        {x.source_id for x in request.selection.observations}
        | {x.source_id for x in request.fusion.observations}
        | {x.source_id for x in request.manual_offsets}
    )
    if request.selection.previous_source_id is not None:
        referenced.add(request.selection.previous_source_id)
    if request.delay is not None:
        referenced.add(request.delay.reference_source_id)
        referenced.update(x.source_id for x in request.delay.observations)
    if not referenced <= registered_source_ids:
        raise ValueError("Source identifiers must belong to this saved match")

    offsets = {offset.source_id: offset.seconds for offset in request.manual_offsets}
    selected = preview_active_source(request.selection)
    delay = preview_relative_delays(request.delay) if request.delay else None
    updated = []
    calibration = []
    for observation in request.fusion.observations:
        offset = offsets.get(observation.source_id, 0.)
        original = observation.aligned_at
        adjusted = original - timedelta(seconds=offset) if original is not None else None
        updated.append(observation.model_copy(update={"aligned_at": adjusted}))
        calibration.append(CalibratedObservation(
            source_id=observation.source_id, segment_id=observation.segment_id,
            manual_offset_seconds=offset,
            original_aligned_at=original, preview_aligned_at=adjusted,
        ))
    conflicts = preview_fusion_conflicts(request.fusion.model_copy(update={
        "active_source_id": selected.active_source_id, "observations": updated,
    }))

    trace = [FusionTrace(
        step="selection", source_id=selected.active_source_id,
        status=selected.transition, reason=selected.reason,
    )]
    trace.extend(FusionTrace(
        step="source", source_id=entry.source_id,
        status="eligible" if entry.eligible else "excluded",
        reason=entry.reason,
    ) for entry in selected.diagnostics)
    if delay is not None:
        trace.extend(FusionTrace(
            step="delay", source_id=row.source_id,
            status=row.status,
            reason=("relative_seconds=" + str(row.relative_delay_seconds)
                    if row.relative_delay_seconds is not None else "offset_unknown"),
        ) for row in delay.estimates)
    trace.extend(FusionTrace(
        step="manual_offset", source_id=row.source_id,
        status="preview_only",
        reason="subtract_seconds=" + str(row.seconds),
    ) for row in request.manual_offsets)
    trace.append(FusionTrace(
        step="fusion", source_id=selected.active_source_id,
        status="candidate_preview" if conflicts.accepted_for_preview else "rejected",
        reason=conflicts.reason,
    ))
    return FusionDiagnosticResponse(
        selection=selected, fusion=conflicts, delay=delay,
        calibration=calibration, trace=trace,
    )
