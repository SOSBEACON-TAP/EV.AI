"""
check_env.py
-------------
Run this to sanity-check your .env setup WITHOUT exposing your full API
key anywhere (only the first/last few characters are shown). Safe to
share the output of this script in chat if you need help debugging.

Usage:
    python check_env.py
"""

from dotenv import load_dotenv, find_dotenv
import os

resolved_path = find_dotenv(usecwd=True)
load_dotenv(resolved_path)

provider = os.getenv("AI_PROVIDER", "(not set)")
model = os.getenv("AI_MODEL", "(not set, will use default)")
key = os.getenv("AI_API_KEY", "")

print("=" * 50)
print("EV AI .env diagnostic")
print("=" * 50)
print(f".env file used = {resolved_path or '(none found!)'}")
print(f"AI_PROVIDER = {provider!r}")
print(f"AI_MODEL    = {model!r}")

if not key:
    print("AI_API_KEY  = (EMPTY — nothing was read from .env)")
else:
    masked = key[:4] + "..." + key[-4:] if len(key) > 8 else "(too short?)"
    print(f"AI_API_KEY  = {masked}  (length: {len(key)})")
    if key != key.strip():
        print("  WARNING: key has leading/trailing whitespace!")
    if key.startswith('"') or key.startswith("'"):
        print("  WARNING: key appears to have quote characters included!")

print("=" * 50)

if provider.strip().lower() not in ("gemini", "anthropic", "groq", "openai", "openrouter", "deepseek", "mistral", "xai", "custom"):
    print(f"NOTE: AI_PROVIDER is set to {provider!r}, which EV AI doesn't recognize.")
    print("      Use one of: gemini, anthropic, groq, openai, openrouter, deepseek, mistral, xai, custom")

if not key:
    print("NOTE: No key was loaded at all. Check that:")
    print("  1. The file is named exactly '.env' (not '.env.txt')")
    print("  2. It's in the same folder as main.py")
    print("  3. The line reads AI_API_KEY=yourkeyhere with no spaces around =")
