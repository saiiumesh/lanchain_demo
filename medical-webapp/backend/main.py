import os
from fastapi import FastAPI
from pydantic import BaseModel
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI
import re

app = FastAPI()

# Load environment variables
AZURE_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("OPENAI_API_BASE")
AZURE_OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION", "2024-02-15-preview")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4")
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "reports"

# Connect to Blob Storage
blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)

# Connect to Azure OpenAI
client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

# Load all reports
reports = {}
for blob in container_client.list_blobs():
    blob_client = container_client.get_blob_client(blob)
    text = blob_client.download_blob().readall().decode("utf-8")
    match = re.search(r'Patient Name:\s*(.*)', text)
    patient_name = match.group(1).strip() if match else blob.name
    reports[patient_name] = text

# Request model
class QuestionRequest(BaseModel):
    patient_name: str
    question: str

# API endpoints
@app.get("/patients")
def get_patients():
    return list(reports.keys())

@app.post("/ask")
def ask_question(req: QuestionRequest):
    report_text = reports.get(req.patient_name)
    if not report_text:
        return {"answer": "Patient not found."}

    response = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": "You are a medical assistant AI. Answer questions strictly based on the report text below."},
            {"role": "user", "content": f"Report:\n{report_text}\n\nQuestion: {req.question}"}
        ]
    )
    return {"answer": response.choices[0].message.content}
