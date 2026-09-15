import os
import pytest
from unittest.mock import patch, MagicMock
from lambda_handler import handler


def make_event(target_id="test-uuid-1"):
    return {"target_id": target_id}


def test_handler_writes_ssm_and_starts_ec2(monkeypatch):
    monkeypatch.setenv("EC2_INSTANCE_ID", "i-abc123")

    mock_ssm = MagicMock()
    mock_ec2 = MagicMock()

    def mock_boto_client(service, **kwargs):
        if service == "ssm":
            return mock_ssm
        if service == "ec2":
            return mock_ec2
        raise ValueError(f"Unexpected service: {service}")

    with patch("lambda_handler.boto3.client", side_effect=mock_boto_client):
        result = handler(make_event("target-xyz"), None)

    assert result["statusCode"] == 200
    mock_ssm.put_parameter.assert_called_once_with(
        Name="/resy-bot/pending-target-id",
        Value="target-xyz",
        Type="String",
        Overwrite=True,
    )
    mock_ec2.start_instances.assert_called_once_with(InstanceIds=["i-abc123"])


def test_handler_missing_target_id():
    result = handler({}, None)
    assert result["statusCode"] == 400


def test_handler_missing_instance_id(monkeypatch):
    monkeypatch.delenv("EC2_INSTANCE_ID", raising=False)
    result = handler(make_event("target-xyz"), None)
    assert result["statusCode"] == 500
