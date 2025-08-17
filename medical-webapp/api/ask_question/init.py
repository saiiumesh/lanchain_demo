import os
import datetime
import azure.functions as func
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI
import json

# --- Load env vars ---
AZURE_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("OPENAI_API_BASE")
AZURE_OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION", "2024-02-15-preview")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4")

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "reports"

# --- Azure OpenAI client ---
client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

def get_greeting():
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

def get_report_by_patient(patient_name):
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(CONTAINER_NAME)
    blobs = list(container_client.list_blobs())
    
    # match patient_name substring in blob name
    for blob in blobs:
        if patient_name.lower() in blob.name.lower():
            blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=blob.name)
            return blob_client.download_blob().readall().decode("utf-8"), blob.name
    return None, None

# --- Azure Function entry point ---
def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
        patient_name = req_body.get("patient_name")
        question = req_body.get("question")
        if not patient_name or not question:
            return func.HttpResponse(
                json.dumps({"error": "Provide 'patient_name' and 'question'"}),
                status_code=400,
                mimetype="application/json"
            )

        report_text, report_name = get_report_by_patient(patient_name)
        if not report_text:
            return func.HttpResponse(
                json.dumps({"error": f"No report found for patient: {patient_name}"}),
                status_code=404,
                mimetype="application/json"
            )

        greeting_msg = get_greeting()

        # Call Azure OpenAI
        response = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are a medical assistant AI. Answer questions strictly based on the report text below."},
                {"role": "user", "content": f"Report:\n{report_text}\n\nQuestion: {question}"}
            ]
        )
        answer = response.choices[0].message.content

        return func.HttpResponse(
            json.dumps({
                "report": report_name,
                "greeting": greeting_msg,
                "question": question,
                "answer": answer
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
