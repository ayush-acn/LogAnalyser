import os

main_llm_config = {
    'model': "us.anthropic.claude-sonnet-4-6",
    'region_name': "us-east-1"
}
tool_llm_config = {
    # Use inference profile ID from list_inference_profiles(), NOT list_foundation_models()
    # 'model': "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    'model': "us.anthropic.claude-sonnet-4-6",
    'region_name': "us-east-1"
}

# Soft safeguard for tool↔orch loops (not a rigid product hard-stop).
DEFAULT_MAX_TOOL_ROUNDS = int(os.getenv("DEFAULT_MAX_TOOL_ROUNDS", "5"))

BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "5000"))
BACKEND_URL = os.getenv("BACKEND_URL", f"http://{BACKEND_HOST}:{BACKEND_PORT}")

