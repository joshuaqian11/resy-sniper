from unittest.mock import MagicMock, call, patch

import snipe_runner


def test_stop_instance_waits_for_log_flush_before_stopping():
    order = MagicMock()
    with patch("snipe_runner.get_instance_id", return_value="i-123"), \
            patch("snipe_runner.time.sleep", order.sleep), \
            patch("snipe_runner.boto3.client", return_value=order.ec2):
        snipe_runner.stop_instance()

    assert order.mock_calls == [
        call.sleep(snipe_runner.LOG_FLUSH_SECONDS),
        call.ec2.stop_instances(InstanceIds=["i-123"]),
    ]
    assert snipe_runner.LOG_FLUSH_SECONDS >= 10


def test_stop_instance_without_instance_id_does_nothing():
    with patch("snipe_runner.get_instance_id", return_value=""), \
            patch("snipe_runner.time.sleep") as sleep, \
            patch("snipe_runner.boto3.client") as client:
        snipe_runner.stop_instance()

    sleep.assert_not_called()
    client.assert_not_called()
