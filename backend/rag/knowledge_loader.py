"""
Knowledge Loader
Pre-loads the RAG knowledge base with AWS and Terraform knowledge.
"""

import asyncio
import logging
import uuid
from typing import Any

from rules.security_rules import SECURITY_RULES

logger = logging.getLogger(__name__)


class KnowledgeLoader:
    """Pre-loads the ChromaDB RAG knowledge base with seed data."""

    def __init__(self, rag_client: Any, knowledge_dir: str):
        """
        Parameters
        ----------
        rag_client    : ChromaRAGClient instance
        knowledge_dir : str - directory path for file-based knowledge (if needed)
        """
        self.rag_client = rag_client
        self.knowledge_dir = knowledge_dir

    async def is_loaded(self, collection_name: str) -> bool:
        """Returns True if collection has > 0 documents."""
        stats = await self.rag_client.get_collection_stats()
        return stats.get(collection_name, 0) > 0

    async def load_all(self):
        """Calls all load methods in sequence. Skips if collection already has documents."""
        logger.info("[KnowledgeLoader] Starting knowledge base initialization...")

        if not await self.is_loaded("terraform_patterns"):
            await self.load_terraform_patterns()
        else:
            logger.info("[KnowledgeLoader] 'terraform_patterns' already loaded. Skipping.")

        if not await self.is_loaded("aws_best_practices"):
            await self.load_aws_best_practices()
        else:
            logger.info("[KnowledgeLoader] 'aws_best_practices' already loaded. Skipping.")

        if not await self.is_loaded("security_policies"):
            await self.load_security_policies()
        else:
            logger.info("[KnowledgeLoader] 'security_policies' already loaded. Skipping.")

        logger.info("[KnowledgeLoader] Knowledge base initialization complete.")

    async def load_terraform_patterns(self):
        """Load 10 Terraform patterns into 'terraform_patterns' collection."""
        logger.info("[KnowledgeLoader] Loading terraform_patterns...")
        patterns = [
            {
                "name": "web_app_basic",
                "description": "EC2 t3.micro + security group for 80/443 + S3 for static assets",
                "hcl": '''
resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.micro"
  vpc_security_group_ids = [aws_security_group.web_sg.id]
  tags = { Name = "BasicWebApp" }
}
resource "aws_security_group" "web_sg" {
  name = "web_sg"
  ingress { from_port = 80; to_port = 80; protocol = "tcp"; cidr_blocks = ["0.0.0.0/0"] }
  ingress { from_port = 443; to_port = 443; protocol = "tcp"; cidr_blocks = ["0.0.0.0/0"] }
}
resource "aws_s3_bucket" "static_assets" {
  bucket_prefix = "webapp-static-"
}
'''
            },
            {
                "name": "web_app_with_db",
                "description": "EC2 t3.micro + security group for 80/443 + S3 for static assets + RDS db.t3.micro MySQL + private subnet",
                "hcl": '''
resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.micro"
}
resource "aws_db_instance" "db" {
  allocated_storage = 20
  engine            = "mysql"
  instance_class    = "db.t3.micro"
  username          = "admin"
  password          = "change_me_later"
  skip_final_snapshot = true
}
'''
            },
            {
                "name": "static_website",
                "description": "S3 + CloudFront + Route53",
                "hcl": '''
resource "aws_s3_bucket" "website" {
  bucket_prefix = "static-site-"
}
resource "aws_cloudfront_distribution" "cdn" {
  origin {
    domain_name = aws_s3_bucket.website.bucket_regional_domain_name
    origin_id   = "S3Origin"
  }
  enabled             = true
  default_root_object = "index.html"
  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3Origin"
    viewer_protocol_policy = "redirect-to-https"
  }
  viewer_certificate {
    cloudfront_default_certificate = true
  }
  restrictions {
    geo_restriction { restriction_type = "none" }
  }
}
'''
            },
            {
                "name": "lambda_api",
                "description": "Lambda + API Gateway + DynamoDB",
                "hcl": '''
resource "aws_dynamodb_table" "table" {
  name           = "ApiData"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "id"
  attribute { name = "id"; type = "S" }
}
resource "aws_lambda_function" "api_func" {
  function_name = "ApiHandler"
  role          = aws_iam_role.lambda_exec.arn
  handler       = "index.handler"
  runtime       = "nodejs18.x"
  filename      = "function.zip"
}
resource "aws_iam_role" "lambda_exec" {
  name = "lambda_exec_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Action = "sts:AssumeRole", Principal = { Service = "lambda.amazonaws.com" }, Effect = "Allow" }]
  })
}
'''
            },
            {
                "name": "vpc_standard",
                "description": "VPC + 2 public subnets + 2 private subnets + IGW",
                "hcl": '''
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}
resource "aws_subnet" "public1" { vpc_id = aws_vpc.main.id; cidr_block = "10.0.1.0/24"; map_public_ip_on_launch = true }
resource "aws_subnet" "public2" { vpc_id = aws_vpc.main.id; cidr_block = "10.0.2.0/24"; map_public_ip_on_launch = true }
resource "aws_subnet" "private1" { vpc_id = aws_vpc.main.id; cidr_block = "10.0.3.0/24" }
resource "aws_subnet" "private2" { vpc_id = aws_vpc.main.id; cidr_block = "10.0.4.0/24" }
resource "aws_internet_gateway" "igw" { vpc_id = aws_vpc.main.id }
'''
            },
            {
                "name": "ec2_autoscaling",
                "description": "Launch template + ASG + CloudWatch alarm",
                "hcl": '''
resource "aws_launch_template" "app" {
  name_prefix   = "app-"
  image_id      = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.micro"
}
resource "aws_autoscaling_group" "asg" {
  desired_capacity    = 2
  max_size            = 4
  min_size            = 1
  vpc_zone_identifier = ["subnet-12345", "subnet-67890"]
  launch_template {
    id      = aws_launch_template.app.id
    version = "$Latest"
  }
}
'''
            },
            {
                "name": "s3_secure",
                "description": "S3 + versioning + encryption + lifecycle + block public access",
                "hcl": '''
resource "aws_s3_bucket" "secure" {
  bucket_prefix = "secure-data-"
}
resource "aws_s3_bucket_versioning" "secure_ver" {
  bucket = aws_s3_bucket.secure.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "secure_enc" {
  bucket = aws_s3_bucket.secure.id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } }
}
resource "aws_s3_bucket_public_access_block" "secure_pab" {
  bucket                  = aws_s3_bucket.secure.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
'''
            },
            {
                "name": "rds_production",
                "description": "RDS Multi-AZ + encryption + automated backups + subnet group",
                "hcl": '''
resource "aws_db_instance" "prod" {
  allocated_storage       = 100
  engine                  = "postgres"
  instance_class          = "db.m5.large"
  multi_az                = true
  storage_encrypted       = true
  backup_retention_period = 7
  skip_final_snapshot     = false
  username                = "dbadmin"
  password                = "secure_password_here"
}
'''
            },
            {
                "name": "monitoring_stack",
                "description": "CloudWatch dashboard + alarms for CPU/memory/disk",
                "hcl": '''
resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "cpu-utilization-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 85
}
'''
            },
            {
                "name": "iam_least_privilege",
                "description": "IAM role + policy with minimal permissions for EC2",
                "hcl": '''
resource "aws_iam_role" "ec2_role" {
  name = "ec2_minimal_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Action = "sts:AssumeRole", Principal = { Service = "ec2.amazonaws.com" }, Effect = "Allow" }]
  })
}
resource "aws_iam_role_policy" "s3_read" {
  name = "s3_read_only"
  role = aws_iam_role.ec2_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Action = ["s3:GetObject", "s3:ListBucket"], Resource = "*", Effect = "Allow" }]
  })
}
'''
            }
        ]

        collection = self.rag_client.collections["terraform_patterns"]
        for pattern in patterns:
            text = f"Pattern: {pattern['name']}\nDescription: {pattern['description']}"
            embedding = await self.rag_client.embed(text, task_type="RETRIEVAL_DOCUMENT")
            doc_id = str(uuid.uuid4())
            await asyncio.to_thread(
                collection.upsert,
                ids=[doc_id],
                embeddings=[embedding],
                documents=[text],
                metadatas=[{
                    "name": pattern["name"],
                    "description": pattern["description"],
                    "hcl": pattern["hcl"]
                }]
            )

    async def load_aws_best_practices(self):
        """Load 15 AWS best practice documents into 'aws_best_practices'."""
        logger.info("[KnowledgeLoader] Loading aws_best_practices...")
        practices = [
            "EC2 security: Use IMDSv2, attach IAM roles instead of long-term keys, restrict security groups to specific IPs.",
            "S3 security: Enable block public access, use bucket policies for least privilege, enable server-side encryption.",
            "RDS backup: Enable automated backups with a minimum 7-day retention period, enable multi-AZ for production.",
            "IAM least privilege: Grant only the permissions required to perform a task. Avoid using managed policies with full access.",
            "VPC design: Use a multi-tier architecture with public subnets for load balancers and private subnets for application/database instances.",
            "CloudWatch monitoring: Set up alarms for critical metrics like CPU utilization, memory, and database connections. Use dashboards for visibility.",
            "Cost optimization: Use AWS Cost Explorer and Budgets. Stop unused instances, right-size instances, and use Spot Instances for stateless workloads.",
            "Tagging strategy: Apply consistent tags across all resources for cost allocation, environment identification, and automation.",
            "Encryption at rest: Enable encryption for EBS volumes, RDS databases, S3 buckets, and DynamoDB tables using AWS KMS.",
            "Encryption in transit: Use TLS/SSL for all data in transit. Use AWS Certificate Manager for managing certificates.",
            "Multi-AZ design: Deploy critical workloads across multiple Availability Zones to ensure high availability and fault tolerance.",
            "Auto scaling: Use Auto Scaling Groups for EC2 instances to automatically handle variations in traffic and maintain performance.",
            "Load balancing: Use Application Load Balancers for HTTP/HTTPS traffic to distribute requests across multiple targets in different AZs.",
            "Disaster recovery: Have a defined RPO and RTO. Test backups regularly and use cross-region replication for critical data.",
            "CloudTrail audit: Enable AWS CloudTrail across all regions to log API activity and monitor for suspicious behavior."
        ]

        collection = self.rag_client.collections["aws_best_practices"]
        for idx, practice in enumerate(practices):
            embedding = await self.rag_client.embed(practice, task_type="RETRIEVAL_DOCUMENT")
            doc_id = str(uuid.uuid4())
            await asyncio.to_thread(
                collection.upsert,
                ids=[doc_id],
                embeddings=[embedding],
                documents=[practice],
                metadatas=[{"source": "aws_best_practices", "topic_index": idx}]
            )

    async def load_security_policies(self):
        """Load the security rules from SecurityRulesEngine into 'security_policies'."""
        logger.info("[KnowledgeLoader] Loading security_policies...")

        collection = self.rag_client.collections["security_policies"]
        for rule in SECURITY_RULES:
            text = f"Rule ID: {rule.get('id', 'N/A')}\nName: {rule.get('name', 'N/A')}\nDescription: {rule.get('description', 'N/A')}"
            embedding = await self.rag_client.embed(text, task_type="RETRIEVAL_DOCUMENT")
            doc_id = str(uuid.uuid4())

            # Sanitize metadata to only include strings, numbers, bools
            metadata = {}
            for k, v in rule.items():
                if isinstance(v, (str, int, float, bool)):
                    metadata[k] = v
                else:
                    metadata[k] = str(v)

            await asyncio.to_thread(
                collection.upsert,
                ids=[doc_id],
                embeddings=[embedding],
                documents=[text],
                metadatas=[metadata]
            )
