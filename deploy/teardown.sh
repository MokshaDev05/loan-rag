#!/usr/bin/env bash
# deploy/teardown.sh — delete all AWS resources created by setup.sh.
#
# Reads resource IDs from deploy/.state so no manual input is needed.
# Resources are deleted in reverse dependency order.
# RDS is deleted without a final snapshot (--skip-final-snapshot) to avoid
# leaving orphaned snapshots that continue to incur storage costs.

set -euo pipefail

STATE_FILE="$(dirname "$0")/.state"
[[ -f "${STATE_FILE}" ]] || { echo "ERROR: ${STATE_FILE} not found — has setup.sh been run?"; exit 1; }

# shellcheck disable=SC1090
source "${STATE_FILE}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }


log "Tearing down ${APP_NAME} in ${AWS_REGION}..."


# ── ECS service ───────────────────────────────────────────────────────────────
log "Scaling ECS service to 0 and deleting..."
aws ecs update-service \
  --cluster "${ECS_CLUSTER}" \
  --service "${ECS_SERVICE}" \
  --desired-count 0 \
  --region "${AWS_REGION}" 2>/dev/null || true

# --force stops running tasks immediately instead of waiting for draining
aws ecs delete-service \
  --cluster "${ECS_CLUSTER}" \
  --service "${ECS_SERVICE}" \
  --force \
  --region "${AWS_REGION}" 2>/dev/null || true


# ── ECS task definitions ───────────────────────────────────────────────────────
log "Deregistering task definitions (family: ${TASK_DEF_FAMILY})..."
TASK_DEF_ARNS="$(aws ecs list-task-definitions \
  --family-prefix "${TASK_DEF_FAMILY}" \
  --query 'taskDefinitionArns[*]' --output text \
  --region "${AWS_REGION}" 2>/dev/null | tr '\t' ' ')"
for arn in ${TASK_DEF_ARNS}; do
  aws ecs deregister-task-definition \
    --task-definition "${arn}" \
    --region "${AWS_REGION}" 2>/dev/null || true
done


# ── ALB listener, ALB, target group ──────────────────────────────────────────
log "Deleting ALB listener..."
aws elbv2 delete-listener \
  --listener-arn "${LISTENER_ARN}" \
  --region "${AWS_REGION}" 2>/dev/null || true

log "Deleting ALB..."
aws elbv2 delete-load-balancer \
  --load-balancer-arn "${ALB_ARN}" \
  --region "${AWS_REGION}" 2>/dev/null || true

log "Waiting for ALB to be fully deleted (up to 3 minutes)..."
aws elbv2 wait load-balancers-deleted \
  --load-balancer-arns "${ALB_ARN}" \
  --region "${AWS_REGION}" 2>/dev/null || true

log "Deleting target group..."
aws elbv2 delete-target-group \
  --target-group-arn "${TG_ARN}" \
  --region "${AWS_REGION}" 2>/dev/null || true


# ── ECS cluster ───────────────────────────────────────────────────────────────
log "Deleting ECS cluster ${ECS_CLUSTER}..."
aws ecs delete-cluster \
  --cluster "${ECS_CLUSTER}" \
  --region "${AWS_REGION}" 2>/dev/null || true


# ── EC2 Ollama ────────────────────────────────────────────────────────────────
log "Terminating EC2 instance ${EC2_INSTANCE_ID}..."
aws ec2 terminate-instances \
  --instance-ids "${EC2_INSTANCE_ID}" \
  --region "${AWS_REGION}" 2>/dev/null || true
aws ec2 wait instance-terminated \
  --instance-ids "${EC2_INSTANCE_ID}" \
  --region "${AWS_REGION}" 2>/dev/null || true


# ── RDS ───────────────────────────────────────────────────────────────────────
log "Deleting RDS instance ${RDS_IDENTIFIER} (no final snapshot)..."
aws rds delete-db-instance \
  --db-instance-identifier "${RDS_IDENTIFIER}" \
  --skip-final-snapshot \
  --delete-automated-backups \
  --region "${AWS_REGION}" 2>/dev/null || true

log "Waiting for RDS deletion (~5 minutes)..."
aws rds wait db-instance-deleted \
  --db-instance-identifier "${RDS_IDENTIFIER}" \
  --region "${AWS_REGION}" 2>/dev/null || true

log "Deleting RDS subnet group..."
aws rds delete-db-subnet-group \
  --db-subnet-group-name "${DB_SUBNET_GROUP}" \
  --region "${AWS_REGION}" 2>/dev/null || true


# ── CloudWatch log group ──────────────────────────────────────────────────────
log "Deleting CloudWatch log group ${LOG_GROUP}..."
aws logs delete-log-group \
  --log-group-name "${LOG_GROUP}" \
  --region "${AWS_REGION}" 2>/dev/null || true


# ── Security groups ────────────────────────────────────────────────────────────
# Revoke cross-SG ingress rules first; otherwise delete-security-group fails
# because SGs referencing each other count as "in use".
log "Revoking cross-SG ingress rules..."
aws ec2 revoke-security-group-ingress \
  --group-id "${RDS_SG}" --protocol tcp --port 5432 \
  --source-group "${ECS_SG}" --region "${AWS_REGION}" 2>/dev/null || true
aws ec2 revoke-security-group-ingress \
  --group-id "${OLLAMA_SG}" --protocol tcp --port 11434 \
  --source-group "${ECS_SG}" --region "${AWS_REGION}" 2>/dev/null || true
aws ec2 revoke-security-group-ingress \
  --group-id "${ECS_SG}" --protocol tcp --port 8000 \
  --source-group "${ALB_SG}" --region "${AWS_REGION}" 2>/dev/null || true

log "Deleting security groups..."
for sg_id in "${RDS_SG}" "${OLLAMA_SG}" "${ECS_SG}" "${ALB_SG}"; do
  aws ec2 delete-security-group \
    --group-id "${sg_id}" \
    --region "${AWS_REGION}" 2>/dev/null \
    || log "  SG ${sg_id} not deleted (may have remaining dependencies — check console)"
done


# ── IAM ───────────────────────────────────────────────────────────────────────
log "Deleting IAM roles..."

aws iam detach-role-policy \
  --role-name "${ECS_EXEC_ROLE_NAME}" \
  --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy" \
  2>/dev/null || true
aws iam delete-role \
  --role-name "${ECS_EXEC_ROLE_NAME}" \
  2>/dev/null || true

aws iam remove-role-from-instance-profile \
  --instance-profile-name "${EC2_PROFILE_NAME}" \
  --role-name "${EC2_ROLE_NAME}" \
  2>/dev/null || true
aws iam delete-instance-profile \
  --instance-profile-name "${EC2_PROFILE_NAME}" \
  2>/dev/null || true
aws iam detach-role-policy \
  --role-name "${EC2_ROLE_NAME}" \
  --policy-arn "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore" \
  2>/dev/null || true
aws iam delete-role \
  --role-name "${EC2_ROLE_NAME}" \
  2>/dev/null || true


# ── ECR ───────────────────────────────────────────────────────────────────────
log "Deleting ECR repository ${APP_NAME} (all images will be lost)..."
aws ecr delete-repository \
  --repository-name "${APP_NAME}" \
  --force \
  --region "${AWS_REGION}" 2>/dev/null || true


# ── State file ─────────────────────────────────────────────────────────────────
rm -f "${STATE_FILE}"

log ""
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log " Teardown complete. All ${APP_NAME} AWS resources deleted."
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
