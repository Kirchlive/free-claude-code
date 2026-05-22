"""Sanity imports for modular transcript primitives."""

from __future__ import annotations


def test_transcript_public_surface_re_exports_buffer_and_render_ctx() -> None:
    import messaging.transcript as transcript_pkg
    from messaging.transcript_buffer import TranscriptBuffer
    from messaging.transcript_segments import RenderCtx
    from messaging.ui_updates import ThrottledTranscriptEditor

    assert transcript_pkg.RenderCtx is RenderCtx
    assert transcript_pkg.TranscriptBuffer is TranscriptBuffer
    assert transcript_pkg.ThrottledTranscriptEditor is ThrottledTranscriptEditor
