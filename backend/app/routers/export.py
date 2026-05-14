"""Harmoniq export router — GP5 to MIDI/MusicXML, JSON to MusicXML."""

from __future__ import annotations

import binascii
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.exporter import ExportDisabledError, ExportUnsupportedError, export_gp5_base64, export_musicxml_from_json
from app.schemas import ExportRequest, MusicXMLJsonExportRequest

logger = logging.getLogger("harmoniq.api.export")

router = APIRouter(tags=["Export"])


@router.post(
    "/export",
    summary="POST /export — GP5 to MIDI or MusicXML",
    responses={
        422: {"description": "Invalid payload, bad base64, or format not available"},
        503: {"description": "Export disabled (HARMONIQ_SKIP_EXPORT=1)"},
    },
)
async def export_tab(req: ExportRequest) -> Response:
    try:
        data, mime, ext, stem = export_gp5_base64(req.gp5_base64, req.export_format, title_hint=req.title)
    except ExportDisabledError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ExportUnsupportedError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except binascii.Error:
        raise HTTPException(status_code=422, detail="Invalid GP5 base64.") from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    filename = f"{stem}{ext}"
    return Response(content=data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post(
    "/export/musicxml-from-json",
    summary="POST /export/musicxml-from-json — MusicXML from Harmoniq JSON artifacts",
    responses={422: {"description": "Invalid payload or data for MusicXML generation."}},
)
async def export_musicxml_json(req: MusicXMLJsonExportRequest) -> Response:
    try:
        data, mime, ext, stem = export_musicxml_from_json(
            beat_grid=req.beat_grid,
            chord_timeline=req.chord_timeline,
            solo_notes=req.solo_notes,
            title=req.title,
            artist=req.artist,
            key_signature=req.key_signature,
        )
    except Exception as e:
        logger.exception("MusicXML generation failed")
        raise HTTPException(status_code=422, detail=f"MusicXML generation failed: {e}") from e
    filename = f"{stem}{ext}"
    return Response(content=data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
