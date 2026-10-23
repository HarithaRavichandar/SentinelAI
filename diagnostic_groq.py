# Diagnostic script to test Groq client with proper import path
import os, sys, traceback

# Add the src directory to PYTHONPATH
project_root = os.path.abspath(os.path.dirname(__file__))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

from sentinelai.triage.llm_client import get_chat_reply, LLMConfigurationError, LLMError

prompt = "Hello, can you respond with a short greeting?"

try:
    reply = get_chat_reply(prompt)
    print("SUCCESS: Reply received:")
    print(reply)
except LLMConfigurationError as e:
    print("CONFIGURATION ERROR:", e)
except LLMError as e:
    print("LLM ERROR:", e)
except Exception as e:
    print("UNEXPECTED EXCEPTION:")
    traceback.print_exc()
