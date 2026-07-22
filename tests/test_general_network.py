import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cim_app_histories.general.network as nt

def test_address_from_host():
    hostname = "warwick.ac.uk"
    net = nt.Network()
    n = net.addr_from_name(hostname)
    assert "137.205.28.41" == n