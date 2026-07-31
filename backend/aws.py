import json
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class AWSClient:
    def __init__(self, region: str, lambda_arn: str):
        self.region = region
        self.lambda_arn = lambda_arn
        self._events = boto3.client("events", region_name=region)

    def create_start_rule(self, rule_name: str, cron_expression: str, target_id: str):
        """Create an EventBridge rule that invokes the snipe Lambda on a schedule."""
        self._events.put_rule(
            Name=rule_name,
            ScheduleExpression=cron_expression,
            State="ENABLED",
            Description=f"Resy bot snipe trigger for target {target_id}",
        )
        self._events.put_targets(
            Rule=rule_name,
            Targets=[{
                "Id": "invoke-snipe-lambda",
                "Arn": self.lambda_arn,
                "Input": json.dumps({"target_id": target_id}),
            }],
        )

    def delete_rule(self, rule_name: str):
        """Remove targets then delete the EventBridge rule. No-op if rule doesn't exist."""
        try:
            self._events.remove_targets(Rule=rule_name, Ids=["invoke-snipe-lambda"])
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code not in ("ResourceNotFoundException", "ValidationException"):
                logger.error(f"Failed to remove targets for rule {rule_name}: {e}")
        try:
            self._events.delete_rule(Name=rule_name)
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                logger.error(f"Failed to delete rule {rule_name}: {e}")
