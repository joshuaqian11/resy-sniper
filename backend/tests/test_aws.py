import pytest
import boto3
from moto import mock_aws
from aws import AWSClient

REGION = "us-east-1"
LAMBDA_ARN = "arn:aws:lambda:us-east-1:123456789:function:resy-bot-snipe"


@pytest.fixture
def aws_client(aws_env):
    return AWSClient(region=REGION, lambda_arn=LAMBDA_ARN)


@mock_aws
def test_create_start_rule(aws_client):
    aws_client.create_start_rule(
        rule_name="resy-bot-target-abc",
        cron_expression="cron(58 8 15 8 ? 2026)",
        target_id="abc-uuid",
    )
    events = boto3.client("events", region_name=REGION)
    rules = events.list_rules(NamePrefix="resy-bot-target-abc")["Rules"]
    assert len(rules) == 1
    assert rules[0]["Name"] == "resy-bot-target-abc"
    assert rules[0]["State"] == "ENABLED"


@mock_aws
def test_create_start_rule_sets_lambda_target(aws_client):
    aws_client.create_start_rule(
        rule_name="resy-bot-target-abc",
        cron_expression="cron(58 8 15 8 ? 2026)",
        target_id="abc-uuid",
    )
    events = boto3.client("events", region_name=REGION)
    targets = events.list_targets_by_rule(Rule="resy-bot-target-abc")["Targets"]
    assert len(targets) == 1
    assert targets[0]["Arn"] == LAMBDA_ARN
    assert '"target_id": "abc-uuid"' in targets[0]["Input"]


@mock_aws
def test_delete_rule(aws_client):
    events = boto3.client("events", region_name=REGION)
    events.put_rule(
        Name="resy-bot-target-99",
        ScheduleExpression="cron(0 9 15 6 ? 2026)",
        State="ENABLED",
    )
    aws_client.delete_rule("resy-bot-target-99")
    rules = events.list_rules(NamePrefix="resy-bot-target-99")["Rules"]
    assert len(rules) == 0


@mock_aws
def test_delete_rule_nonexistent_does_not_raise(aws_client):
    aws_client.delete_rule("does-not-exist")
