"""Quick end-to-end check: can a Wahab compute node reach Vertex AI and call Gemini?

Run this before submitting any real extraction batch. If it fails, the job
will fail identically -- better to find out in 30 seconds than 8 hours in.
"""

import os
import socket
import sys

print(f"Running on node: {socket.gethostname()}")
print(f"GOOGLE_APPLICATION_CREDENTIALS = {os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')}")

try:
    import vertexai
    from vertexai.generative_models import GenerativeModel

    vertexai.init(project="rs-vertexai-czhu", location="us-central1")
    model = GenerativeModel("gemini-2.5-flash")
    response = model.generate_content("Say 'Wahab connectivity test successful' and nothing else.")
    print("SUCCESS:", response.text)
    sys.exit(0)
except Exception as exc:
    print("FAILED:", type(exc).__name__, str(exc)[:1000])
    sys.exit(1)
