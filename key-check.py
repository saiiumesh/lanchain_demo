import os

api_key = os.getenv("OPENAI_API_KEY")

if api_key:
    print("API key loaded successfully!")
else:
    print("API key not found!")




AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
if AZURE_STORAGE_CONNECTION_STRING:

    print(AZURE_STORAGE_CONNECTION_STRING)
else:
    print("sorry")
AZURE_OPENAI_ENDPOINT = os.getenv("OPENAI_API_BASE")
print(AZURE_OPENAI_ENDPOINT)