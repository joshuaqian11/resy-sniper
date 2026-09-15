import logging
import os
import boto3

logger = logging.getLogger(__name__)

SSM_PARAM_NAME = "/resy-bot/pending-target-id"


def handler(event, context):
    target_id = event.get("target_id")
    if not target_id:
        logger.error("No target_id in event")
        return {"statusCode": 400, "body": "Missing target_id"}

    region = "us-east-1"
    instance_id = event.get("instance_id") or os.environ.get("EC2_INSTANCE_ID", "")
    if not instance_id:
        logger.error("No EC2 instance ID configured")
        return {"statusCode": 500, "body": "Missing EC2_INSTANCE_ID"}

    ssm = boto3.client("ssm", region_name=region)
    ec2 = boto3.client("ec2", region_name=region)

    # Write target ID to SSM so EC2 knows what to snipe
    ssm.put_parameter(
        Name=SSM_PARAM_NAME,
        Value=target_id,
        Type="String",
        Overwrite=True,
    )
    logger.info(f"Set SSM param {SSM_PARAM_NAME} = {target_id}")

    # Start the EC2 instance
    ec2.start_instances(InstanceIds=[instance_id])
    logger.info(f"Started EC2 instance {instance_id} for target {target_id}")

    return {"statusCode": 200, "body": f"Started EC2 for target {target_id}"}
