# Medical Report Q&A Web App

This is a demo web app using **Azure OpenAI GPT-4** and **Azure Blob Storage** to interactively query patient reports.

## Setup

1. Create Azure resources:
   - Storage Account (upload reports in `reports` container)
   - Azure OpenAI deployment (GPT-4)
   
2. Set environment variables:
   - `OPENAI_API_KEY`
   - `OPENAI_API_BASE`
   - `OPENAI_API_VERSION`
   - `AZURE_OPENAI_DEPLOYMENT`
   - `AZURE_STORAGE_CONNECTION_STRING`

3. Run backend locally:
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
