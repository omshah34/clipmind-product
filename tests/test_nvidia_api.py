import os
import sys

import pytest
from openai import OpenAI
from core.config import settings

def test_nvidia_api():
    print(f"Testing NVIDIA NIM API endpoint...")
    print(f"Base URL: {settings.openai_base_url}")
    print(f"Model ID: {settings.clip_detector_model}")
    print("-" * 50)
    
    if not settings.openai_base_url:
        pytest.skip("OPENAI_BASE_URL is not set")
        
    if not settings.openai_api_key:
        pytest.skip("OPENAI_API_KEY is not set")

    try:
        # Initialize OpenAI client with NVIDIA base URL
        client = OpenAI(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key
        )
        
        # Test basic completion
        print("Sending test request...")
        response = client.chat.completions.create(
            model=settings.clip_detector_model,
            messages=[
                {"role": "user", "content": "Hello! Reply with 'NVIDIA API is working!' if you receive this."}
            ],
            max_tokens=100
        )
        
        print("\nSUCCESS!")
        print("Raw response:")
        print(response.model_dump_json(indent=2))
        
        content = response.choices[0].message.content
        if content is not None:
            reply = content.strip()
            print(f"\nExtracted message: {reply}")
        else:
            print("\nMessage content was None")
        
    except Exception as e:
        print("\nFAILED!")
        print(f"Error details: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    test_nvidia_api()
