import unittest
from uuid import uuid4

from db.repositories.jobs import create_job, delete_job


class JobDedupBehaviorTests(unittest.TestCase):
    def test_same_video_upload_creates_new_job_each_time(self) -> None:
        user_id = str(uuid4())
        source_video_url = f"file:///tmp/{uuid4().hex}.mp4"

        job_one = create_job(
            user_id=user_id,
            source_video_url=source_video_url,
            prompt_version="v4",
            estimated_cost_usd=1.0,
            status="uploaded",
            language="en",
        )
        job_two = create_job(
            user_id=user_id,
            source_video_url=source_video_url,
            prompt_version="v4",
            estimated_cost_usd=1.0,
            status="uploaded",
            language="en",
        )

        try:
            self.assertNotEqual(str(job_one.id), str(job_two.id))
        finally:
            delete_job(job_one.id)
            delete_job(job_two.id)


if __name__ == "__main__":
    unittest.main()
