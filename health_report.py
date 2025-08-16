import os
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI

# --- Load env vars ---
AZURE_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("OPENAI_API_BASE")
AZURE_OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION", "2024-02-15-preview")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4")

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "reports"

# --- Select report file interactively ---
print("Available reports:")
blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)
blobs = list(container_client.list_blobs())
for idx, blob in enumerate(blobs):
    print(f"{idx+1}. {blob.name}")

choice = int(input("Select report number: ")) - 1
BLOB_NAME = blobs[choice].name

# --- Download report text ---
blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=BLOB_NAME)
report_text = blob_client.download_blob().readall().decode("utf-8")
print(f"\n📄 Loaded report: {BLOB_NAME}\n")

# --- Connect to Azure OpenAI ---
client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

# --- Interactive Q&A loop ---
#print("You can now ask questions about the report! Type 'exit' to quit.\n")

import datetime

# Get current datetime
now = datetime.datetime.now()
hour = now.hour
day_of_week = now.strftime("%A")

# Determine time-based greeting
if 5 <= hour < 12:
    greeting = "Good morning"
elif 12 <= hour < 17:
    greeting = "Good afternoon"
elif 17 <= hour < 21:
    greeting = "Good evening"
else:
    greeting = "Hello"

# Format current time nicely
current_time = now.strftime("%I:%M %p")

# Display dynamic greeting
print("Hi Umesh.." f"\n{greeting}! It's {current_time} on {day_of_week}.")
print("you make now please start asking questions about the reports")



while True:
    question = input("Your question: ")
    if question.lower() in ["exit", "quit"]:
        print("Exiting. Goodbye! 👋")
        break

    response = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": "You are a medical assistant AI. Answer questions strictly based on the report text below."},
            {"role": "user", "content": f"Report:\n{report_text}\n\nQuestion: {question}"}
        ]
    )

    answer = response.choices[0].message.content
    print(f"🤖 Answer: {answer}\n")
