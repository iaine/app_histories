import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cim_app_histories.general.network import NetworkAddr

def test_address_from_host():
    hostname = "warwick.ac.uk"
    nt = NetworkAddr()
    n = nt.addr_from_name(hostname)
    assert "137.205.28.41" == n