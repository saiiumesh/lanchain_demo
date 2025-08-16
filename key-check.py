import os

api_key = os.getenv("OPENAI_API_KEY")

if api_key:
    print("API key loaded successfully!")
else:
    print("API key not found!")
