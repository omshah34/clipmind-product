import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from services.video_processor import build_subtitle_filter, SubtitleStyle

def test_build_subtitle_filter_simple_vertical():
    srt_path = Path("C:/test/subs.srt")
    style = SubtitleStyle()
    
    # Mocking LayoutEngine to avoid actual detection logic
    with patch("services.layout_engine.LayoutEngine.get_filtergraph") as mock_geo:
        mock_geo.return_value = "crop=607:1080:656:0"
        
        vf = build_subtitle_filter(
            srt_path=srt_path,
            style=style,
            output_width=1080,
            output_height=1920,
            input_width=1920,
            input_height=1080,
            layout_type="vertical"
        )
        
        assert "crop=607:1080:656:0" in vf
        assert "scale=1080:1920" in vf
        assert "subtitles=" in vf
        # Check that the path is escaped (C\\:/test/subs.srt on Windows)
        assert "C\\\\:/test/subs.srt" in vf

def test_build_subtitle_filter_split_screen():
    srt_path = Path("C:/test/subs.srt")
    
    with patch("services.layout_engine.LayoutEngine.get_filtergraph") as mock_geo:
        mock_geo.return_value = "[0:v]split=2[top_raw][bot_raw];[top_raw]crop=T[top];[bot_raw]crop=B[bot];[top][bot]vstack=2"
        
        vf = build_subtitle_filter(
            srt_path=srt_path,
            layout_type="split_screen",
            input_width=1920,
            input_height=1080
        )
        
        assert "vstack=2" in vf
        assert "scale=1080:1920" in vf

@patch("services.video_processor._run_command")
@patch("services.video_processor.get_video_dimensions")
def test_render_command_generation(mock_dims, mock_run):
    mock_dims.return_value = (1920, 1080)
    
    from services.video_processor import render_vertical_captioned_clip
    
    raw_path = Path("raw.mp4")
    srt_path = Path("subs.srt")
    out_path = Path("out.mp4")
    wm_path = Path("logo.png")
    
    # Mocking Path.exists for the watermark
    with patch.object(Path, "exists", return_value=True):
        render_vertical_captioned_clip(
            raw_path, srt_path, out_path,
            watermark_path=wm_path
        )
        
        # Verify the command was called with list of args
        args = mock_run.call_args[0][0]
        assert isinstance(args, list)
        assert "ffmpeg" == args[0]
        assert "-filter_complex" in args
        # Ensure logo.png is a discrete element
        assert str(wm_path) in args
