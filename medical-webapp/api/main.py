import os
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI
import datetime
import re

app = FastAPI()

# Allow all origins for testing; adjust in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Load env vars ---
AZURE_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("OPENAI_API_BASE")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-02-15-preview")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4")
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "reports"

# --- Connect to Blob ---
blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)
blobs = list(container_client.list_blobs())

# --- Load all reports content ---
reports = {}
for blob in blobs:
    blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=blob.name)
    text = blob_client.download_blob().readall().decode("utf-8")
    match = re.search(r'Patient Name:\s*(.*)', text)
    patient_name = match.group(1).strip() if match else blob.name
    reports[patient_name] = text

# --- Connect to Azure OpenAI ---
client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

# --- Dynamic greeting utility ---
def get_dynamic_greeting():
    now = datetime.datetime.now()
    hour = now.hour
    day_of_week = now.strftime("%A")
    if 5 <= hour < 12:
        greeting = "Good morning"
    elif 12 <= hour < 17:
        greeting = "Good afternoon"
    elif 17 <= hour < 21:
        greeting = "Good evening"
    else:
        greeting = "Hello"
    current_time = now.strftime("%I:%M %p")
    return f"{greeting}! It's {current_time} on {day_of_week}."

# --- Endpoint to list patients with greeting ---
@app.get("/patients")
def list_patients():
    greeting = get_dynamic_greeting()
    return {
        "greeting": greeting,
        "patients": list(reports.keys())
    }

# --- Endpoint to ask questions about a patient report ---
@app.post("/ask")
def ask_question(patient_name: str = Form(...), question: str = Form(...)):
    if patient_name not in reports:
        return {"error": "Patient not found"}
    
    report_text = reports[patient_name]
    prompt = (
        "You are a medical assistant AI. Answer questions strictly based on the report text below.\n\n"
        f"Report:\n{report_text}\n\nQuestion: {question}"
    )
    
    response = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[{"role": "user", "content": prompt}]
    )
    
    answer = response.choices[0].message.content
    greeting = get_dynamic_greeting()
    return {
        "greeting": greeting,
        "patient": patient_name,
        "question": question,
        "answer": answer
    }
