import logging
import os
import re
import datetime
import json
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI
import azure.functions as func

# --- Environment variables ---
AZURE_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("OPENAI_API_BASE")
AZURE_OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION", "2024-02-15-preview")
AZURE_OPENAI_DEPLOYMENT = os.getenv("OPENAI_OPENAI_DEPLOYMENT", "gpt-4")
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "reports"

# --- Greeting function ---
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

# --- Load reports from Azure Blob Storage ---
def load_reports():
    reports = {}
    if not AZURE_STORAGE_CONNECTION_STRING:
        logging.error("Missing AZURE_STORAGE_CONNECTION_STRING")
        return reports
    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)
        for blob in container_client.list_blobs():
            blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=blob.name)
            text = blob_client.download_blob().readall().decode("utf-8")
            match = re.search(r'Patient Name:\s*(.*)', text)
            patient_name = match.group(1).strip() if match else blob.name
            reports[patient_name] = text
    except Exception as e:
        logging.error("Error loading blobs: %s", str(e), exc_info=True)
    return reports

# --- Azure Function entry point ---
def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        patient_name = data.get("patient_name")
        question = data.get("question")

        if not patient_name or not question:
            return func.HttpResponse(
                json.dumps({"error": "Missing patient_name or question"}),
                status_code=400,
                mimetype="application/json"
            )

        reports = load_reports()
        if patient_name not in reports:
            return func.HttpResponse(
                json.dumps({"error": f"No report found for {patient_name}"}),
                status_code=404,
                mimetype="application/json"
            )

        report_text = reports[patient_name]

        if not all([AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT]):
            logging.error("Missing OpenAI configuration")
            return func.HttpResponse(
                json.dumps({"error": "OpenAI configuration not set"}),
                status_code=500,
                mimetype="application/json"
            )

        client = AzureOpenAI(
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT
        )

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
                "greeting": get_greeting(),
                "report": report_text,
                "question": question,
                "answer": answer
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error("Unhandled exception: %s", str(e), exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
