import json
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

SSM_PARAM_NAME = "/resy-bot/pending-target-id"


class AWSClient:
    def __init__(self, region: str, instance_id: str, lambda_arn: str):
        self.region = region
        self.instance_id = instance_id
        self.lambda_arn = lambda_arn
        self._events = boto3.client("events", region_name=region)
        self._ec2 = boto3.client("ec2", region_name=region)
        self._ssm = boto3.client("ssm", region_name=region)

    def set_target_param(self, target_id: str):
        """Write the target ID to SSM so the EC2 instance knows what to snipe."""
        self._ssm.put_parameter(
            Name=SSM_PARAM_NAME,
            Value=target_id,
            Type="String",
            Overwrite=True,
        )
        logger.info(f"Set SSM param {SSM_PARAM_NAME} = {target_id}")

    def get_target_param(self) -> str:
        """Read the target ID from SSM."""
        resp = self._ssm.get_parameter(Name=SSM_PARAM_NAME)
        return resp["Parameter"]["Value"]

    def start_instance(self):
        """Start the snipe EC2 instance."""
        self._ec2.start_instances(InstanceIds=[self.instance_id])
        logger.info(f"Starting EC2 instance {self.instance_id}")

    def stop_instance(self):
        """Stop the snipe EC2 instance."""
        try:
            self._ec2.stop_instances(InstanceIds=[self.instance_id])
            logger.info(f"Stopping EC2 instance {self.instance_id}")
        except Exception as e:
            logger.error(f"Failed to stop instance: {e}")

    def create_start_rule(self, rule_name: str, cron_expression: str, target_id: str):
        """Create an EventBridge rule that invokes the trigger Lambda on a schedule."""
        self._events.put_rule(
            Name=rule_name,
            ScheduleExpression=cron_expression,
            State="ENABLED",
            Description=f"Resy bot snipe trigger for target {target_id}",
        )
        self._events.put_targets(
            Rule=rule_name,
            Targets=[{
                "Id": "invoke-trigger-lambda",
                "Arn": self.lambda_arn,
                "Input": json.dumps({"target_id": target_id}),
            }],
        )

    def delete_rule(self, rule_name: str):
        """Remove targets then delete the EventBridge rule."""
        try:
            self._events.remove_targets(Rule=rule_name, Ids=["invoke-trigger-lambda"])
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code not in ("ResourceNotFoundException", "ValidationException"):
                logger.error(f"Failed to remove targets for rule {rule_name}: {e}")
        try:
            self._events.delete_rule(Name=rule_name)
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                logger.error(f"Failed to delete rule {rule_name}: {e}")
