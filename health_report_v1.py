import os
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI
import datetime
import re

# --- Load env vars ---
AZURE_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("OPENAI_API_BASE")
AZURE_OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION", "2024-02-15-preview")
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
    
    # Extract patient name from text, fallback to blob name if not found
    match = re.search(r'Patient Name:\s*(.*)', text)
    patient_name = match.group(1).strip() if match else blob.name
    reports[patient_name.lower()] = text  # store lowercase key for easier matching

# --- Dynamic greeting ---
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
print("Hi Umesh" f"\n{greeting}! It's {current_time} on {day_of_week}.\n")

# --- Ask whether to show patients ---
show_patients = input("Would you like to see the list of patients? (yes/no): ").strip().lower()

if show_patients in ["yes", "y"]:
    print("\nPatients available:")
    for idx, name in enumerate(reports.keys()):
        print(f"{idx+1}. {name.title()}")
    
    choice = int(input("\nSelect patient number to view details: ")) - 1
    selected_patient = list(reports.keys())[choice]
    current_patient = selected_patient
    print(f"\nYou selected patient: {current_patient.title()}")
    print("You can now start asking questions about the reports. Type 'exit' to quit.\n")

    # --- Connect to Azure OpenAI ---
    client = AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT
    )

    # --- Interactive Q&A loop ---
    while True:
        question = input("Ask your Question: ")
        if question.lower() in ["exit", "quit"]:
            print("Exiting. Goodbye!")
            break

        # Check if another patient name is mentioned in the question
        switch_to = None
        for name in reports.keys():
            if name in question.lower():
                switch_to = name
                break

        if switch_to:
            current_patient = switch_to
            print(f"(Switching context to {current_patient.title()} based on your question)")

        report_text = reports[current_patient]

        response = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are a medical assistant AI. Answer questions strictly based on the report text below."},
                {"role": "user", "content": f"Report:\n{report_text}\n\nQuestion: {question}"}
            ]
        )

        answer = response.choices[0].message.content
        print(f"Answer: {answer}\n")
else:
    print("Okay, no patients selected. Exiting program.")
