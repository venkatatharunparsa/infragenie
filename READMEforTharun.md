# InfraGenie: AI-Powered Infrastructure Automation Platform

## Overview

InfraGenie is an advanced AI-driven infrastructure automation platform that transforms natural-language requests into production-ready Terraform configurations. Built with a multi-agent architecture, it implements a Perceive-Reason-Plan-Act-Observe (PRPAO) loop powered by Google Gemini, enabling autonomous infrastructure management with human oversight.

### Key Features
- **Natural Language Processing**: Convert plain English requests into Terraform HCL code
- **Multi-Agent Orchestration**: 5 specialized agents coordinate complex infrastructure tasks
- **Security & Compliance**: Multi-layer security scanning with auto-fix capabilities
- **Cost Management**: Real-time budget tracking and threshold enforcement
- **Real-Time Monitoring**: Continuous infrastructure observation and anomaly detection
- **Human-in-the-Loop**: Approval workflows for critical changes
- **Audit Trail**: Complete logging of all actions and decisions
- **RAG-Enhanced Generation**: Retrieval-Augmented Generation using ChromaDB for context-aware code generation

## Architecture

### Core Components

#### Backend Agents (Microservice-like Specialization)
- **OrchestratorAgent**: Master controller running the PRPAO loop, routes requests via 4-tier intelligence router
- **PlannerAgent**: Translates natural-language to Terraform HCL using RAG and Gemini
- **ExecutorAgent**: Executes Terraform plans with self-correction and real-time streaming
- **SecurityAgent**: Multi-layer security gatekeeper (rules, tfsec, Checkov, AWS audits)
- **MonitorAgent**: Continuous infrastructure monitoring via CloudWatch, Cost Explorer, CloudTrail

#### RAG System
- **ChromaDB Vector Store**: 6 specialized collections for patterns, best practices, policies, etc.
- **Google Gemini Embeddings**: Modern embedding model for semantic search
- **Retrieval Flow**: Query → embedding → top-5 documents → context-enhanced Gemini generation

#### Rules Engines
- **Security Rules**: 5 rules covering IAM, S3, encryption, security groups
- **Policy Rules**: 5 rules for budget, regions, tagging, approvals

#### AWS Integration
- CloudWatch, Cost Explorer, CloudTrail, SSM RunCommand
- Multi-service support for EC2, S3, IAM, etc.

#### Database & Persistence
- SQLAlchemy ORM with async SQLite (swappable to PostgreSQL)
- Audit logging for compliance and debugging
- Terraform workspace isolation per request

#### Frontend
- React dashboard with Tailwind CSS
- Real-time WebSocket updates
- Pages: Dashboard, Deploy, Monitor, Audit Log

## Technology Stack

### Backend
- **FastAPI**: Web framework and REST API
- **Uvicorn**: ASGI server
- **Google Gemini**: AI reasoning and code generation
- **ChromaDB**: Vector database for RAG
- **Boto3**: AWS SDK integration
- **SQLAlchemy**: Database ORM
- **WebSockets**: Real-time communication

### Frontend
- **React**: UI framework
- **Tailwind CSS**: Styling
- **WebSocket API**: Real-time updates

### Infrastructure
- **Docker & Docker Compose**: Containerization
- **Terraform**: Infrastructure as Code
- **Python 3.11+**: Backend runtime
- **Node.js 18+**: Frontend tooling

## Data Flow

### User Request → Deployment Flow
1. User submits request via API/Dashboard
2. OrchestratorAgent perceives current state via MonitorAgent
3. Routes to PlannerAgent for HCL generation
4. SecurityAgent scans for violations
5. If approved, ExecutorAgent applies changes
6. Real-time streaming to UI via WebSocket
7. Audit logging to database

### Continuous Monitoring Loop
- Hourly PRPAO cycle for autonomous observation
- Anomaly detection and self-healing
- Cost tracking and budget alerts

## Security & Policy Features

### Multi-Layer Security
1. **Credential Management**: Environment-based AWS/Gemini keys
2. **Static Analysis**: Rule engines, tfsec, Checkov scanning
3. **Policy Enforcement**: Budget, region, tagging requirements
4. **Audit & Compliance**: Complete action logging

### Human-in-the-Loop
- Approval required for high-impact changes
- Triggers: destructive operations, high costs, security violations

## Setup & Installation

### Prerequisites
- Docker & Docker Compose
- AWS account with appropriate permissions
- Google Gemini API key

### Environment Setup
```bash
# Clone repository
git clone <repository-url>
cd infragenie

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
# GEMINI_API_KEY=your_key_here
# AWS_ACCESS_KEY_ID=your_aws_key
# AWS_SECRET_ACCESS_KEY=your_aws_secret
# etc.
```

### Quick Start
```bash
# Build and start services
make build
make up

# Access:
# Backend API: http://localhost:8000
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs
```

### Development
```bash
# Run tests
make test

# Format code
make format

# Access backend shell
make shell-backend
```

## Usage

### API Endpoints
- `POST /api/deploy`: Submit infrastructure request
- `POST /api/approve/{request_id}`: Approve pending request
- `GET /api/requests`: List request history
- `WebSocket /ws`: Real-time updates

### Example Request
```bash
curl -X POST http://localhost:8000/api/deploy \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_secret" \
  -d '{
    "user_input": "Create an EC2 instance with port 22 open to 0.0.0.0/0",
    "request_id": "test-001"
  }'
```

### Frontend Features
- **Dashboard**: Live logs, cost tracking, infrastructure map
- **Deploy Page**: Request submission with streaming results
- **Monitor Page**: Real-time metrics and alerts
- **Audit Log**: Historical request tracking

## Configuration

### Key Environment Variables
- `GEMINI_API_KEY`: Primary Gemini API key
- `AWS_ACCESS_KEY_ID`: AWS access key
- `BUDGET_THRESHOLD`: Cost limit in USD
- `INFRAGENIE_SECRET`: API authentication key
- `DB_URL`: Database connection string

### Rules Customization
Edit `backend/rules/security_rules.py` and `backend/rules/policy_rules.py` to modify security and policy rules.

### RAG Knowledge Base
Add documents to `knowledge/` directories:
- `aws_best_practices/`
- `terraform_patterns/`
- `policies/`

## Testing

### Run Tests
```bash
# Backend tests
cd backend
python -m pytest tests/ -v

# Or via Docker
make test
```

### Test Coverage
- Agent models and logic
- Terraform runner functionality
- Security and policy rule engines
- AWS client integrations (mocked)

## Deployment Considerations

### Production Setup
- Use remote Terraform state (S3 + DynamoDB)
- AWS Secrets Manager for credentials
- PostgreSQL for database scaling
- Load balancer for multiple instances
- Monitoring and alerting setup

### Scaling
- Stateless agents support horizontal scaling
- Shared persistence layer required
- WebSocket connections need sticky sessions or broadcast mechanism

## Project Status

✅ **Operational Features:**
- Backend API and WebSocket streaming
- Frontend dashboard with real-time updates
- Gemini integration with RAG
- Basic Terraform generation and execution
- Security scanning and policy enforcement
- Audit logging and approval workflows

🔄 **Development Focus:**
- End-to-end testing and validation
- Advanced monitoring and anomaly detection
- Performance optimization
- Additional AWS service integrations

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        INFRAGENIE PLATFORM                      │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────┐         ┌──────────────────────┐
│   React Frontend     │◄────WS──┤  FastAPI Backend     │
│  (Dashboard, Deploy) │         │  (Agents, API)       │
└──────────────────────┘         └──────────────────────┘
                                         ▲ │
                                         │ │
    ┌────────────────────────────────────┼─┼────────────────────┐
    │                                    │ │                    │
    ▼ REST (/api/deploy)    ┌───────────┴─┴────────────┐        │
    │                       │                          │        │
    └──────────────────►   ORCHESTRATOR AGENT        ◄─┘        │
                          (PRPAO Loop)                          │
                           │    │    │    │                     │
          ┌────────────────┘    │    │    └──────────────────┐  │
          │                     │    │                       │  │
          ▼                     ▼    ▼                       ▼  │
      ┌─────────┐        ┌──────────┐      ┌──────────┐   ┌──────┐
      │ PLANNER │        │EXECUTOR  │      │MONITOR   │   │SEC   │
      │         │        │          │      │          │   │AGENT │
      │ Generate│ ──────►│ Terraform│      │ CloudW   │   │      │
      │ HCL     │        │ Apply    │      │ CostExpl │   │Scan  │
      └────┬────┘        └──────────┘      └──────────┘   │ HCL  │
           │                                               └──────┘
           │                                                    ▲
           ▼                                                    │
      ┌─────────────────────────────────────────────────────────┘
      │
      ▼
 ┌──────────────┐        ┌──────────────────┐
 │  RAG Client  │        │  Rules Engines   │
 │  (ChromaDB)  │        │  (Security &     │
 │              │        │   Policy)        │
 │ • Patterns   │        │                  │
 │ • Best Prac  │        │ • SEC-001..005   │
 │ • Policies   │        │ • POL-001..005   │
 └──────────────┘        └──────────────────┘
      │                           ▲
      └───────────────────────────┘

 ┌────────────────────────────────────────┐
 │         AWS Integration                │
 │  ┌────────────────────────────────┐   │
 │  │  CloudWatch  CloudTrail        │   │
 │  │  Cost Explorer  EC2  RDS  S3   │   │
 │  │  IAM  Systems Manager          │   │
 │  └────────────────────────────────┘   │
 └────────────────────────────────────────┘

 ┌────────────────────────────────────────┐
 │       Persistence Layer                │
 │  ┌──────────┐  ┌──────────┐  ┌──────┐│
 │  │ SQLite   │  │ ChromaDB │  │ S3   ││
 │  │(Audit)   │  │(Vector)  │  │State ││
 │  └──────────┘  └──────────┘  └──────┘│
 └────────────────────────────────────────┘
```

## Contributing

1. Follow the existing code patterns and async-first architecture
2. Add tests for new functionality
3. Update documentation for API changes
4. Ensure security rules are updated for new AWS services

## License

[Add license information here]

---

**InfraGenie represents a sophisticated approach to AI-driven infrastructure automation, combining advanced LLM capabilities with robust security, compliance, and monitoring features for safe, autonomous infrastructure management.**