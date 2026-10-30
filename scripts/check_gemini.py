"""Manual check that GEMINI_API_KEY works. Makes one real (billed) API call.
Run: python scripts/check_gemini.py. Not a test; pytest never collects it."""

import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

if not api_key:
    print("ERROR: GEMINI_API_KEY is missing from .env")
else:
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents="Reply with exactly: SafeSOP AI connected"
        )
        print("SUCCESS:", response.text)
    except Exception as error:
        print("CONNECTION FAILED:", error)
