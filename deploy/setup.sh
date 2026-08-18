#!/usr/bin/env bash
# deploy/setup.sh — provision all AWS resources and deploy the Loan RAG API.
# Uses ECR + ECS Fargate + ALB (no App Runner).
#
# Prerequisites:
#   - aws CLI configured (aws configure)
#   - Docker Desktop running
#   - IAM permissions: ECR, ECS, RDS, EC2, IAM, ELBv2, CloudWatch Logs
#
# Usage:
#   export AWS_REGION=us-east-2
#   export DB_PASSWORD=<password>   # avoid @ / # ? characters — they break the asyncpg URL
#   bash deploy/setup.sh

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
APP_NAME="loan-rag"
AWS_REGION="${AWS_REGION:-us-east-1}"
DB_PASSWORD="${DB_PASSWORD:?ERROR: DB_PASSWORD environment variable is required}"
DB_USERNAME="loan_rag"
DB_NAME="loan_rag"
EC2_INSTANCE_TYPE="t3.large"
RDS_INSTANCE_CLASS="db.t3.micro"
RDS_STORAGE_GB=20
ECS_CPU="1024"     # 1 vCPU
ECS_MEMORY="2048"  # 2 GB
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_FILE="${SCRIPT_DIR}/.state"

log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

command -v aws    >/dev/null 2>&1 || die "aws CLI not found — run: brew install awscli"
command -v docker >/dev/null 2>&1 || die "docker not found — install Docker Desktop"
docker info >/dev/null 2>&1       || die "Docker daemon is not running"

log "Fetching AWS account ID..."
AWS_ACCOUNT_ID="$(aws sts get-caller-identity \
  --query 'Account' --output text --region "${AWS_REGION}")"
log "Account: ${AWS_ACCOUNT_ID}  Region: ${AWS_REGION}"

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_REPO="${APP_NAME}"
ECR_URI="${ECR_REGISTRY}/${ECR_REPO}"
LOG_GROUP="/ecs/${APP_NAME}"
ECS_CLUSTER="${APP_NAME}-cluster"
ECS_EXEC_ROLE_NAME="${APP_NAME}-ecs-execution-role"
EC2_ROLE_NAME="${APP_NAME}-ec2-ssm-role"
EC2_PROFILE_NAME="${APP_NAME}-ec2-profile"
DB_SUBNET_GROUP="${APP_NAME}-db-subnet-group"


# ── 1. ECR repository ─────────────────────────────────────────────────────────
log "[1/13] ECR repository..."
aws ecr create-repository \
  --repository-name "${ECR_REPO}" \
  --region "${AWS_REGION}" \
  --image-scanning-configuration scanOnPush=true \
  2>/dev/null || log "  ECR repository already exists"


# ── 2. Docker build + push ────────────────────────────────────────────────────
if [[ "${SKIP_IMAGE_BUILD:-false}" == "true" ]]; then
  log "[2/13] Using image already pushed to ${ECR_URI}:latest"
else
  log "[2/13] Authenticating Docker with ECR..."
  if [[ "${SKIP_DOCKER_LOGIN:-false}" != "true" ]]; then
    aws ecr get-login-password --region "${AWS_REGION}" \
      | docker login --username AWS --password-stdin "${ECR_REGISTRY}"
  fi

  log "[2/13] Building Docker image (first build ~10 min — downloads embedding model)..."
  docker build -t "${APP_NAME}:latest" "${SCRIPT_DIR}/.."
  docker tag  "${APP_NAME}:latest" "${ECR_URI}:latest"
  docker push "${ECR_URI}:latest"
  log "  Pushed: ${ECR_URI}:latest"
fi


# ── 3. IAM roles ──────────────────────────────────────────────────────────────
log "[3/13] IAM roles..."

# ECS service-linked role (needed for ALB target registration; auto-created on first ECS use)
aws iam create-service-linked-role \
  --aws-service-name ecs.amazonaws.com \
  2>/dev/null || true

# ECS task execution role — allows ECS to pull from ECR + write CloudWatch Logs
ECS_EXEC_TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
ECS_EXEC_ROLE_ARN="$(aws iam create-role \
  --role-name "${ECS_EXEC_ROLE_NAME}" \
  --assume-role-policy-document "${ECS_EXEC_TRUST}" \
  --query 'Role.Arn' --output text 2>/dev/null \
  || aws iam get-role \
       --role-name "${ECS_EXEC_ROLE_NAME}" \
       --query 'Role.Arn' --output text)"
aws iam attach-role-policy \
  --role-name "${ECS_EXEC_ROLE_NAME}" \
  --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy" \
  2>/dev/null || true

# Allow the task to call Bedrock (used as production LLM backend)
BEDROCK_POLICY='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["bedrock:InvokeModel"],"Resource":"*"}]}'
aws iam put-role-policy \
  --role-name "${ECS_EXEC_ROLE_NAME}" \
  --policy-name "BedrockInvokeModel" \
  --policy-document "${BEDROCK_POLICY}" \
  2>/dev/null || true
log "  ECS execution role: ${ECS_EXEC_ROLE_ARN}"

# EC2 instance role for Ollama (SSM access for remote management)
EC2_TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam create-role \
  --role-name "${EC2_ROLE_NAME}" \
  --assume-role-policy-document "${EC2_TRUST}" \
  2>/dev/null || true
aws iam attach-role-policy \
  --role-name "${EC2_ROLE_NAME}" \
  --policy-arn "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore" \
  2>/dev/null || true
aws iam create-instance-profile \
  --instance-profile-name "${EC2_PROFILE_NAME}" \
  2>/dev/null || true
aws iam add-role-to-instance-profile \
  --instance-profile-name "${EC2_PROFILE_NAME}" \
  --role-name "${EC2_ROLE_NAME}" \
  2>/dev/null || true

log "  IAM propagation delay (15 s)..."
sleep 15


# ── 4. VPC and subnets ────────────────────────────────────────────────────────
log "[4/13] VPC and subnets..."
VPC_ID="$(aws ec2 describe-vpcs \
  --filters "Name=isDefault,Values=true" \
  --query 'Vpcs[0].VpcId' --output text --region "${AWS_REGION}")"
[[ "${VPC_ID}" == "None" || -z "${VPC_ID}" ]] \
  && die "No default VPC found. Run: aws ec2 create-default-vpc --region ${AWS_REGION}"

# Tab-separated output → individual subnet IDs
SUBNET_RAW="$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=${VPC_ID}" \
  --query 'Subnets[*].SubnetId' --output text --region "${AWS_REGION}" | tr '\t' ' ')"
SUBNET_1="$(echo "${SUBNET_RAW}" | awk '{print $1}')"
SUBNET_2="$(echo "${SUBNET_RAW}" | awk '{print $2}')"
[[ -z "${SUBNET_1}" || -z "${SUBNET_2}" ]] \
  && die "Need at least 2 subnets in VPC ${VPC_ID} (ALB requires 2+ AZs)"
log "  VPC: ${VPC_ID}  Subnets: ${SUBNET_1} ${SUBNET_2}"


# ── 5. Security groups ────────────────────────────────────────────────────────
log "[5/13] Security groups..."

_sg() {
  local name="$1" desc="$2"
  local id
  id="$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=${name}" "Name=vpc-id,Values=${VPC_ID}" \
    --query 'SecurityGroups[0].GroupId' --output text --region "${AWS_REGION}")"
  if [[ "${id}" == "None" || -z "${id}" ]]; then
    aws ec2 create-security-group \
      --group-name "${name}" --description "${desc}" \
      --vpc-id "${VPC_ID}" \
      --query 'GroupId' --output text --region "${AWS_REGION}"
  else
    echo "${id}"
  fi
}

ALB_SG="$(_sg    "${APP_NAME}-alb-sg"    "Loan RAG ALB public HTTP")"
ECS_SG="$(_sg    "${APP_NAME}-ecs-sg"    "Loan RAG ECS Fargate tasks")"
RDS_SG="$(_sg    "${APP_NAME}-rds-sg"    "Loan RAG RDS PostgreSQL")"
OLLAMA_SG="$(_sg "${APP_NAME}-ollama-sg" "Loan RAG Ollama EC2")"

# ALB: allow inbound HTTP from the internet
aws ec2 authorize-security-group-ingress \
  --group-id "${ALB_SG}" --protocol tcp --port 80 --cidr 0.0.0.0/0 \
  --region "${AWS_REGION}" 2>/dev/null || true

# ECS tasks: port 8000 from ALB only
aws ec2 authorize-security-group-ingress \
  --group-id "${ECS_SG}" --protocol tcp --port 8000 \
  --source-group "${ALB_SG}" --region "${AWS_REGION}" 2>/dev/null || true

# RDS: port 5432 from ECS tasks only
aws ec2 authorize-security-group-ingress \
  --group-id "${RDS_SG}" --protocol tcp --port 5432 \
  --source-group "${ECS_SG}" --region "${AWS_REGION}" 2>/dev/null || true

# Ollama EC2: port 11434 from ECS tasks only
aws ec2 authorize-security-group-ingress \
  --group-id "${OLLAMA_SG}" --protocol tcp --port 11434 \
  --source-group "${ECS_SG}" --region "${AWS_REGION}" 2>/dev/null || true

log "  ALB=${ALB_SG}  ECS=${ECS_SG}  RDS=${RDS_SG}  Ollama=${OLLAMA_SG}"


# ── 6. RDS PostgreSQL 16 ─────────────────────────────────────────────────────
# Start RDS and EC2 creation now; we wait for them in step 11 while ALB is provisioned.
log "[6/13] RDS PostgreSQL 16 (starting — will await in step 11)..."
aws rds create-db-subnet-group \
  --db-subnet-group-name "${DB_SUBNET_GROUP}" \
  --db-subnet-group-description "Loan RAG DB" \
  --subnet-ids "${SUBNET_1}" "${SUBNET_2}" \
  --region "${AWS_REGION}" 2>/dev/null || true

RDS_ENGINE_VERSION="$(aws rds describe-db-engine-versions \
  --engine postgres \
  --query "sort_by(DBEngineVersions[?starts_with(EngineVersion,'16.')],&EngineVersion)[-1].EngineVersion" \
  --output text --region "${AWS_REGION}")"
[[ -z "${RDS_ENGINE_VERSION}" || "${RDS_ENGINE_VERSION}" == "None" ]] \
  && die "No PostgreSQL 16 version found in ${AWS_REGION}"
log "  PostgreSQL engine version: ${RDS_ENGINE_VERSION}"

aws rds create-db-instance \
  --db-instance-identifier "${APP_NAME}-db" \
  --db-instance-class "${RDS_INSTANCE_CLASS}" \
  --engine postgres \
  --engine-version "${RDS_ENGINE_VERSION}" \
  --master-username "${DB_USERNAME}" \
  --master-user-password "${DB_PASSWORD}" \
  --db-name "${DB_NAME}" \
  --allocated-storage "${RDS_STORAGE_GB}" \
  --storage-type gp2 \
  --no-multi-az \
  --no-publicly-accessible \
  --db-subnet-group-name "${DB_SUBNET_GROUP}" \
  --vpc-security-group-ids "${RDS_SG}" \
  --backup-retention-period 0 \
  --no-deletion-protection \
  --region "${AWS_REGION}" 2>/dev/null || log "  RDS instance already exists"


# ── 7. EC2 for Ollama (skipped — account restricts non-free-tier instance types) ──
log "[7/13] EC2 for Ollama — skipped (account does not permit non-free-tier EC2)."
log "       OLLAMA_BASE_URL will point to localhost; Ollama-dependent endpoints unavailable."
EC2_INSTANCE_ID="none"


# ── 8. CloudWatch log group ───────────────────────────────────────────────────
log "[8/13] CloudWatch log group ${LOG_GROUP}..."
aws logs create-log-group \
  --log-group-name "${LOG_GROUP}" \
  --region "${AWS_REGION}" 2>/dev/null || true
aws logs put-retention-policy \
  --log-group-name "${LOG_GROUP}" \
  --retention-in-days 30 \
  --region "${AWS_REGION}" 2>/dev/null || true


# ── 9. ECS cluster ────────────────────────────────────────────────────────────
log "[9/13] ECS cluster ${ECS_CLUSTER}..."
aws ecs create-cluster \
  --cluster-name "${ECS_CLUSTER}" \
  --region "${AWS_REGION}" 2>/dev/null || true


# ── 10. ALB + target group + listener ────────────────────────────────────────
log "[10/13] Application Load Balancer..."

ALB_ARN="$(aws elbv2 create-load-balancer \
  --name "${APP_NAME}-alb" \
  --type application \
  --scheme internet-facing \
  --subnets "${SUBNET_1}" "${SUBNET_2}" \
  --security-groups "${ALB_SG}" \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text \
  --region "${AWS_REGION}" 2>/dev/null \
  || aws elbv2 describe-load-balancers \
       --names "${APP_NAME}-alb" \
       --query 'LoadBalancers[0].LoadBalancerArn' --output text \
       --region "${AWS_REGION}")"
log "  ALB: ${ALB_ARN}"

TG_ARN="$(aws elbv2 create-target-group \
  --name "${APP_NAME}-tg" \
  --protocol HTTP \
  --port 8000 \
  --target-type ip \
  --vpc-id "${VPC_ID}" \
  --health-check-protocol HTTP \
  --health-check-path /api/v1/health \
  --health-check-interval-seconds 30 \
  --health-check-timeout-seconds 10 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3 \
  --query 'TargetGroups[0].TargetGroupArn' --output text \
  --region "${AWS_REGION}" 2>/dev/null \
  || aws elbv2 describe-target-groups \
       --names "${APP_NAME}-tg" \
       --query 'TargetGroups[0].TargetGroupArn' --output text \
       --region "${AWS_REGION}")"
log "  Target group: ${TG_ARN}"

LISTENER_ARN="$(aws elbv2 create-listener \
  --load-balancer-arn "${ALB_ARN}" \
  --protocol HTTP --port 80 \
  --default-actions "Type=forward,TargetGroupArn=${TG_ARN}" \
  --query 'Listeners[0].ListenerArn' --output text \
  --region "${AWS_REGION}" 2>/dev/null \
  || aws elbv2 describe-listeners \
       --load-balancer-arn "${ALB_ARN}" \
       --query 'Listeners[0].ListenerArn' --output text \
       --region "${AWS_REGION}")"
log "  Listener: ${LISTENER_ARN}"

log "  Waiting for ALB to become active..."
aws elbv2 wait load-balancer-available \
  --load-balancer-arns "${ALB_ARN}" \
  --region "${AWS_REGION}"

ALB_DNS="$(aws elbv2 describe-load-balancers \
  --load-balancer-arns "${ALB_ARN}" \
  --query 'LoadBalancers[0].DNSName' --output text \
  --region "${AWS_REGION}")"
log "  ALB DNS: ${ALB_DNS}"


# ── 11. Wait for RDS + EC2 ───────────────────────────────────────────────────
log "[11/13] Waiting for RDS (up to 20 minutes)..."
aws rds wait db-instance-available \
  --db-instance-identifier "${APP_NAME}-db" \
  --region "${AWS_REGION}"
RDS_ENDPOINT="$(aws rds describe-db-instances \
  --db-instance-identifier "${APP_NAME}-db" \
  --query 'DBInstances[0].Endpoint.Address' --output text \
  --region "${AWS_REGION}")"
log "  RDS endpoint: ${RDS_ENDPOINT}"

OLLAMA_PRIVATE_IP="localhost"
log "  EC2 skipped — Ollama unavailable (non-free-tier EC2 not permitted on this account)"


# ── 12. ECS task definition ───────────────────────────────────────────────────
log "[12/13] ECS task definition..."

DATABASE_URL="postgresql+asyncpg://${DB_USERNAME}:${DB_PASSWORD}@${RDS_ENDPOINT}:5432/${DB_NAME}"

CONTAINER_DEFS="$(cat <<EOF
[{
  "name": "${APP_NAME}",
  "image": "${ECR_URI}:latest",
  "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
  "environment": [
    {"name": "DATABASE_URL",      "value": "${DATABASE_URL}"},
    {"name": "LLM_PROVIDER",      "value": "bedrock"},
    {"name": "BEDROCK_MODEL_ID",  "value": "amazon.nova-lite-v1:0"},
    {"name": "BEDROCK_REGION",    "value": "${AWS_REGION}"},
    {"name": "EMBEDDING_MODEL",   "value": "sentence-transformers/all-MiniLM-L6-v2"},
    {"name": "ENVIRONMENT",       "value": "production"},
    {"name": "DEBUG",             "value": "false"},
    {"name": "LOG_LEVEL",         "value": "INFO"}
  ],
  "logConfiguration": {
    "logDriver": "awslogs",
    "options": {
      "awslogs-group":         "${LOG_GROUP}",
      "awslogs-region":        "${AWS_REGION}",
      "awslogs-stream-prefix": "ecs"
    }
  },
  "essential": true
}]
EOF
)"

TASK_DEF_ARN="$(aws ecs register-task-definition \
  --family "${APP_NAME}" \
  --network-mode awsvpc \
  --requires-compatibilities FARGATE \
  --cpu "${ECS_CPU}" \
  --memory "${ECS_MEMORY}" \
  --execution-role-arn "${ECS_EXEC_ROLE_ARN}" \
  --task-role-arn "${ECS_EXEC_ROLE_ARN}" \
  --container-definitions "${CONTAINER_DEFS}" \
  --runtime-platform "cpuArchitecture=ARM64,operatingSystemFamily=LINUX" \
  --query 'taskDefinition.taskDefinitionArn' --output text \
  --region "${AWS_REGION}")"
log "  Task definition: ${TASK_DEF_ARN}"


# ── 13. ECS Fargate service ───────────────────────────────────────────────────
log "[13/13] ECS Fargate service..."

# assignPublicIp ENABLED lets Fargate tasks in public subnets reach ECR without a NAT gateway
NET_CFG="$(printf \
  '{"awsvpcConfiguration":{"subnets":["%s","%s"],"securityGroups":["%s"],"assignPublicIp":"ENABLED"}}' \
  "${SUBNET_1}" "${SUBNET_2}" "${ECS_SG}")"

LB_CFG="$(printf \
  '[{"targetGroupArn":"%s","containerName":"%s","containerPort":8000}]' \
  "${TG_ARN}" "${APP_NAME}")"

ECS_SERVICE_ARN="$(aws ecs create-service \
  --cluster "${ECS_CLUSTER}" \
  --service-name "${APP_NAME}-service" \
  --task-definition "${TASK_DEF_ARN}" \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "${NET_CFG}" \
  --load-balancers "${LB_CFG}" \
  --health-check-grace-period-seconds 120 \
  --query 'service.serviceArn' --output text \
  --region "${AWS_REGION}" 2>/dev/null \
  || aws ecs update-service \
       --cluster "${ECS_CLUSTER}" \
       --service "${APP_NAME}-service" \
       --task-definition "${TASK_DEF_ARN}" \
       --force-new-deployment \
       --query 'service.serviceArn' --output text \
       --region "${AWS_REGION}")"
log "  Service: ${ECS_SERVICE_ARN}"

log "  Waiting for service to stabilize (up to 10 minutes)..."
log "  Tip: stream logs with:  aws logs tail ${LOG_GROUP} --follow --region ${AWS_REGION}"
aws ecs wait services-stable \
  --cluster "${ECS_CLUSTER}" \
  --services "${APP_NAME}-service" \
  --region "${AWS_REGION}"
log "  Service is stable."


# ── Save state ─────────────────────────────────────────────────────────────────
cat > "${STATE_FILE}" <<EOF
AWS_REGION=${AWS_REGION}
APP_NAME=${APP_NAME}
ECR_URI=${ECR_URI}
ECS_CLUSTER=${ECS_CLUSTER}
ECS_SERVICE=${APP_NAME}-service
TASK_DEF_FAMILY=${APP_NAME}
TASK_DEF_ARN=${TASK_DEF_ARN}
ALB_ARN=${ALB_ARN}
ALB_DNS=${ALB_DNS}
TG_ARN=${TG_ARN}
LISTENER_ARN=${LISTENER_ARN}
EC2_INSTANCE_ID=${EC2_INSTANCE_ID}
RDS_IDENTIFIER=${APP_NAME}-db
ALB_SG=${ALB_SG}
ECS_SG=${ECS_SG}
RDS_SG=${RDS_SG}
OLLAMA_SG=${OLLAMA_SG}
LOG_GROUP=${LOG_GROUP}
DB_SUBNET_GROUP=${DB_SUBNET_GROUP}
ECS_EXEC_ROLE_NAME=${ECS_EXEC_ROLE_NAME}
EC2_ROLE_NAME=${EC2_ROLE_NAME}
EC2_PROFILE_NAME=${EC2_PROFILE_NAME}
EOF

log ""
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log " Deployment complete!"
log ""
log "  Public API:  http://${ALB_DNS}"
log "  Health:      http://${ALB_DNS}/api/v1/health"
log "  Docs:        http://${ALB_DNS}/docs"
log ""
log "  Ollama is still pulling llama3.2 in the background (~2 GB)."
log "  The first /ask request may take 1-2 minutes."
log ""
log "  View live logs:"
log "    aws logs tail ${LOG_GROUP} --follow --region ${AWS_REGION}"
log ""
log "  To tear down all resources:"
log "    bash deploy/teardown.sh"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
