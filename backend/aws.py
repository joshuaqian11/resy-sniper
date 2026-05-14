import logging
import os
import urllib.request
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class AWSClient:
    def __init__(self, region: str, instance_id: str):
        self.region = region
        self.instance_id = instance_id
        self._events = boto3.client("events", region_name=region)
        self._ec2 = boto3.client("ec2", region_name=region)

    @staticmethod
    def get_instance_id() -> str:
        """Fetch instance ID from EC2 metadata service (IMDSv2). Returns empty string outside EC2."""
        try:
            token_req = urllib.request.Request(
                "http://169.254.169.254/latest/api/token",
                method="PUT",
                headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
            )
            with urllib.request.urlopen(token_req, timeout=1) as r:
                token = r.read().decode()
            req = urllib.request.Request(
                "http://169.254.169.254/latest/meta-data/instance-id",
                headers={"X-aws-ec2-metadata-token": token},
            )
            with urllib.request.urlopen(req, timeout=1) as r:
                return r.read().decode()
        except Exception:
            return ""

    def create_start_rule(self, rule_name: str, cron_expression: str, instance_id: str):
        """Create an EventBridge rule that starts the EC2 instance on a schedule."""
        self._events.put_rule(
            Name=rule_name,
            ScheduleExpression=cron_expression,
            State="ENABLED",
            Description=f"Resy bot auto-start for {rule_name}",
        )
        role_arn = os.environ.get("EVENTBRIDGE_ROLE_ARN", "")
        if not role_arn:
            logger.warning("EVENTBRIDGE_ROLE_ARN not set — EventBridge target not attached")
            return
        self._events.put_targets(
            Rule=rule_name,
            Targets=[{
                "Id": "start-ec2",
                "Arn": f"arn:aws:ssm:{self.region}::automation-definition/AWS-StartEC2Instance",
                "RoleArn": role_arn,
                "Input": f'{{"InstanceId": ["{instance_id}"]}}',
            }],
        )

    def delete_rule(self, rule_name: str):
        """Remove targets then delete the EventBridge rule. No-op if rule doesn't exist."""
        try:
            self._events.remove_targets(Rule=rule_name, Ids=["start-ec2"])
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code not in ("ResourceNotFoundException", "ValidationException"):
                logger.error(f"Failed to remove targets for rule {rule_name}: {e}")
        try:
            self._events.delete_rule(Name=rule_name)
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                logger.error(f"Failed to delete rule {rule_name}: {e}")

    def stop_self(self):
        """Stop this EC2 instance."""
        if not self.instance_id:
            logger.warning("No instance ID — cannot stop self")
            return
        try:
            self._ec2.stop_instances(InstanceIds=[self.instance_id])
            logger.info(f"Stopping instance {self.instance_id}")
        except Exception as e:
            logger.error(f"Failed to stop instance: {e}")
