import os
import pytest
import boto3
from moto import mock_aws
from aws import AWSClient

REGION = "us-east-1"

@pytest.fixture(autouse=True)
def aws_credentials():
    """Set dummy AWS credentials so boto3 client creation doesn't fail outside moto context."""
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
    os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
    os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
    os.environ.setdefault("AWS_DEFAULT_REGION", REGION)

@pytest.fixture
def aws_client():
    return AWSClient(region=REGION, instance_id="i-0abc123")

@mock_aws
def test_create_start_rule(aws_client):
    aws_client.create_start_rule(
        rule_name="resy-bot-target-1",
        cron_expression="cron(50 13 16 5 ? 2026)",
        instance_id="i-0abc123",
    )
    events = boto3.client("events", region_name=REGION)
    rules = events.list_rules(NamePrefix="resy-bot-target-1")["Rules"]
    assert len(rules) == 1
    assert rules[0]["Name"] == "resy-bot-target-1"
    assert rules[0]["State"] == "ENABLED"

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
    aws_client.delete_rule("does-not-exist")  # Should not raise
