# InfraGenie — Deployment & Configuration Guide

This document provides detailed instructions for deploying InfraGenie to production environments and configuring advanced features.

---

## ☁️ Deploying to AWS EC2

To host the InfraGenie dashboard and backend on an EC2 instance:

### 1. Provision the Instance
*   **Instance Type**: `t3.medium` (minimum 4GB RAM recommended for ChromaDB).
*   **AMI**: Ubuntu 22.04 LTS.
*   **Security Group**: Open ports `80` (HTTP), `443` (HTTPS), and `22` (SSH).

### 2. Install Dependencies
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv nodejs npm terraform
```

### 3. Setup Application
```bash
git clone https://github.com/yourusername/infragenie.git
cd infragenie
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 4. Running with Docker Compose (Recommended)
InfraGenie is pre-configured for Docker. Ensure `docker` and `docker-compose` are installed:
```bash
docker-compose up -d --build
```

---

## 💰 Enabling AWS Cost Explorer

If your dashboard shows an `AccessDenied` error in the Cost Widget, follow these steps:

1.  **Enable in AWS Console**:
    *   Log in to the **AWS Management Console**.
    *   Navigate to **AWS Cost Management** → **Cost Explorer**.
    *   Click **Launch Cost Explorer**. (Note: It may take up to 24 hours for data to populate).

2.  **IAM Permissions**:
    Ensure the IAM user associated with your `AWS_ACCESS_KEY_ID` has the following policy attached:
    ```json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ce:GetCostAndUsage",
                    "ce:GetCostForecast"
                ],
                "Resource": "*"
            }
        ]
    }
    ```

---

## 📜 Increasing Audit Logging

By default, InfraGenie logs agent actions to the system console. To enable persistent SQLite logging:

1.  **Backend Integration**:
    *   Currently, the `AuditLogger` is initialized in `backend/main.py`.
    *   To record all agent decisions, ensure the `OrchestratorAgent` calls `audit_logger.log()` inside its `_observe()` method.

2.  **Database Inspection**:
    *   Audit logs are stored in `infragenie.db`.
    *   You can query the `agent_results_records` table to see historical AI decisions and Terraform plans.

---

## 🔒 Security Best Practices

*   **API Key Rotation**: Periodically rotate your `GEMINI_API_KEY` and `INFRAGENIE_SECRET`.
*   **State Management**: For production, configure a remote Terraform backend (S3 + DynamoDB) in the `PlannerAgent` templates to ensure state consistency.
*   **Least Privilege**: Ensure the AWS IAM user used by the `ExecutorAgent` has only the permissions necessary for the resources you intend to manage.
