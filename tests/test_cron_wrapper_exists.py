import os
def test_cron_script_exists():
    assert os.path.exists("scripts/cron_rca_test.sh")
