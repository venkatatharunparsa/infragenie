# InfraGenie Manual Setup and Run Instructions

This guide provides step-by-step instructions to set up and run InfraGenie manually on your local machine without using Docker.

## Prerequisites

Before starting, ensure you have the following installed:

- **Python 3.8+**: Download from [python.org](https://www.python.org/downloads/)
- **Node.js 16+**: Download from [nodejs.org](https://nodejs.org/)
- **Terraform 1.0+**: Download from [terraform.io](https://www.terraform.io/downloads)
- **AWS CLI**: Install from [aws.amazon.com/cli](https://aws.amazon.com/cli/)
- **Git**: For cloning the repository

## 1. Clone and Setup Project

```bash
# Clone the repository
git clone <repository-url>
cd infragenie

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
# source .venv/bin/activate
```

## 2. Backend Setup

### Install Python Dependencies

```bash
# Install requirements
pip install -r requirements.txt
```

### Configure Environment Variables

Create a `.env` file in the root directory with your AWS credentials:

```env
# AWS Credentials
AWS_ACCESS_KEY_ID=your-access-key-here
AWS_SECRET_ACCESS_KEY=your-secret-key-here
AWS_DEFAULT_REGION=us-east-1

# API Key for InfraGenie
API_KEY=tharunparsaagenticprojectinfragenie

# Google Gemini API Key (if using)
GOOGLE_API_KEY=your-gemini-api-key-here
```

### Setup Knowledge Base (Optional)

If you want to populate the RAG knowledge base:

```bash
# Run the knowledge base setup
python scripts/populate_rag.py
```

### Setup AWS (Optional)

If you need to configure AWS resources:

```bash
# Run AWS setup script
bash scripts/setup_aws.sh
```

## 3. Frontend Setup

### Install Node Dependencies

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Return to root
cd ..
```

## 4. Running the Application

### Start Backend Server

Open a new terminal and run:

```bash
# Activate virtual environment if not already
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
# source .venv/bin/activate

# Set Python path and start server
$env:PYTHONPATH="backend"
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The backend will be available at: http://localhost:8000

### Start Frontend Server

Open another terminal and run:

```bash
# Navigate to frontend
cd frontend

# Start development server
npm start
```

The frontend will be available at: http://localhost:3000

## 5. Testing the Setup

### Test Backend API

```bash
# Test health endpoint
curl http://localhost:8000/

# Test deploy endpoint (replace with your API key)
curl -X POST http://localhost:8000/api/deploy \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tharunparsaagenticprojectinfragenie" \
  -d '{"user_input": "Create a simple S3 bucket", "request_id": "test-manual-001"}'
```

### Test Frontend

Open http://localhost:3000 in your browser and verify the UI loads.

## 6. Troubleshooting

### Common Issues

1. **Port already in use**: Change ports in the commands above
2. **AWS credentials not working**: Verify your `.env` file and AWS CLI configuration
3. **Python import errors**: Ensure `PYTHONPATH` is set correctly
4. **Node modules issues**: Delete `node_modules` and run `npm install` again

### Logs

- Backend logs are displayed in the terminal where you run uvicorn
- Frontend logs are in the terminal where you run `npm start`
- Check `backend/logs/` for additional log files

## 7. Development Workflow

1. Make changes to backend code
2. The server will auto-reload due to `--reload` flag
3. For frontend changes, they will hot-reload automatically
4. Test your changes using the API endpoints or UI

## 8. Stopping the Application

- Press `Ctrl+C` in each terminal to stop the servers
- Deactivate virtual environment: `deactivate`

## Additional Notes

- The application uses ChromaDB for vector storage (stored in `./chroma_db/`)
- Terraform workspaces are created in `./terraform_workspace/`
- All sensitive data should be in the `.env` file, never committed to version control

For more detailed documentation, see the main README.md file.