#!/usr/bin/env bash
# ================================================================
# InfraGenie — AWS Remote State Bootstrap
# Creates the S3 bucket and DynamoDB table required for Terraform
# remote state storage and locking.
#
# Prerequisites:
#   - AWS CLI v2 installed and configured (or env vars set)
#   - .env file present in the project root (../  relative to this script)
#
# Usage:
#   chmod +x scripts/setup_aws.sh
#   ./scripts/setup_aws.sh
# ================================================================

set -euo pipefail

# ── Colour helpers ─────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Locate .env ────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"

if [ ! -f "$ENV_FILE" ]; then
  error ".env file not found at $ENV_FILE. Run 'make setup' first."
fi

# ── Load variables from .env (ignore comments and blank lines) ──
set -a
# shellcheck disable=SC1090
source <(grep -v '^\s*#' "$ENV_FILE" | grep -v '^\s*$')
set +a

# ── Validate required variables ────────────────────────────────
: "${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID is not set in .env}"
: "${AWS_SECRET_ACCESS_KEY:?AWS_SECRET_ACCESS_KEY is not set in .env}"
: "${AWS_DEFAULT_REGION:?AWS_DEFAULT_REGION is not set in .env}"
: "${TERRAFORM_STATE_BUCKET:?TERRAFORM_STATE_BUCKET is not set in .env}"
: "${TERRAFORM_LOCK_TABLE:?TERRAFORM_LOCK_TABLE is not set in .env}"

BUCKET="${TERRAFORM_STATE_BUCKET}"
TABLE="${TERRAFORM_LOCK_TABLE}"
REGION="${AWS_DEFAULT_REGION}"

info "AWS Region         : $REGION"
info "Terraform S3 bucket: $BUCKET"
info "DynamoDB lock table: $TABLE"
echo ""

# ── Check AWS CLI ──────────────────────────────────────────────
if ! command -v aws &>/dev/null; then
  error "AWS CLI is not installed. Install it from https://aws.amazon.com/cli/"
fi

AWS_IDENTITY=$(aws sts get-caller-identity --output json 2>/dev/null) || \
  error "AWS CLI authentication failed. Check your credentials in .env."

AWS_ACCOUNT=$(echo "$AWS_IDENTITY" | grep -o '"Account": "[^"]*"' | cut -d'"' -f4)
info "Authenticated as AWS account: $AWS_ACCOUNT"
echo ""

# ── Create S3 bucket ───────────────────────────────────────────
info "Creating S3 bucket: $BUCKET ..."

# us-east-1 doesn't accept a LocationConstraint
if [ "$REGION" = "us-east-1" ]; then
  CREATE_BUCKET_ARGS="--bucket $BUCKET"
else
  CREATE_BUCKET_ARGS="--bucket $BUCKET --create-bucket-configuration LocationConstraint=$REGION"
fi

if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  warn "Bucket '$BUCKET' already exists — skipping creation."
else
  # shellcheck disable=SC2086
  aws s3api create-bucket $CREATE_BUCKET_ARGS --region "$REGION"
  info "Bucket created."
fi

# Enable versioning (required for safe Terraform state)
aws s3api put-bucket-versioning \
  --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled
info "Versioning enabled on $BUCKET."

# Enable server-side encryption
aws s3api put-bucket-encryption \
  --bucket "$BUCKET" \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'
info "AES-256 encryption enabled on $BUCKET."

# Block all public access
aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
info "Public access blocked on $BUCKET."

echo ""

# ── Create DynamoDB table ──────────────────────────────────────
info "Creating DynamoDB table: $TABLE ..."

if aws dynamodb describe-table --table-name "$TABLE" --region "$REGION" 2>/dev/null | grep -q "TableName"; then
  warn "DynamoDB table '$TABLE' already exists — skipping creation."
else
  aws dynamodb create-table \
    --table-name "$TABLE" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "$REGION"

  info "Waiting for table to become ACTIVE..."
  aws dynamodb wait table-exists --table-name "$TABLE" --region "$REGION"
  info "DynamoDB table '$TABLE' is ACTIVE."
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅  Terraform remote state backend is ready!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""
echo "  S3 bucket   : s3://$BUCKET"
echo "  DynamoDB    : $TABLE (region: $REGION)"
echo ""
echo "  Add this backend block to your Terraform configs:"
echo ""
echo '  terraform {'
echo '    backend "s3" {'
echo "      bucket         = \"$BUCKET\""
echo '      key            = "infragenie/<env>/terraform.tfstate"'
echo "      region         = \"$REGION\""
echo "      dynamodb_table = \"$TABLE\""
echo '      encrypt        = true'
echo '    }'
echo '  }'
echo ""
