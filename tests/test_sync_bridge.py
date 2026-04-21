"""Tests for NLE Sync-Bridge XML outputs."""

import pytest
from services.export_engine import get_export_engine

def test_sync_bridge_premiere_xmeml():
    engine = get_export_engine()
    # Mocking job data with minimal fields needed for XML
    import unittest.mock as mock
    with mock.patch("services.export_engine.get_job") as mock_get_job:
        mock_get_job.return_value = mock.Mock(
            clips_json=[{"start_time": 0, "end_time": 10, "final_score": 9}],
            source_video_url="file:///tmp/vid.mp4"
        )
        
        xml = engine.generate_sync_bridge_xml("job-123", format="premiere")
        assert '<?xml version="1.0" encoding="UTF-8"?>' in xml
        assert '<xmeml version="5">' in xml
        assert '<marker>' in xml
        assert 'Virality:' in xml

def test_sync_bridge_davinci_fcpxml():
    engine = get_export_engine()
    import unittest.mock as mock
    with mock.patch("services.export_engine.get_job") as mock_get_job:
        mock_get_job.return_value = mock.Mock(
            clips_json=[{"start_time": 0, "end_time": 10, "final_score": 9}],
            source_video_url="file:///tmp/vid.mp4"
        )
        
        xml = engine.generate_sync_bridge_xml("job-123", format="davinci")
        assert '<?xml version="1.0" encoding="UTF-8"?>' in xml
        assert '<fcpxml version="1.10">' in xml
        assert '<asset-clip' in xml
        assert 'Virality Score: 9' in xml
