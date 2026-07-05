import pytest

from edge.core.errors import LicenseLimitError
from edge.core.license import License
from edge.core.limits import check_limit, remaining, storage_within_cap


def _lic():
    return License(
        client="X",
        issued_at=None,
        expires_at=None,
        modules=frozenset(),
        limits={"cameras": 2, "storage_gb": 10},
        features={},
    )


def test_check_limit_under_and_at_cap():
    check_limit(_lic(), "cameras", 1)  # under → ok
    with pytest.raises(LicenseLimitError):
        check_limit(_lic(), "cameras", 2)  # at cap → raises


def test_remaining_and_storage():
    assert remaining(_lic(), "cameras", 1) == 1
    assert storage_within_cap(_lic(), 5)
    assert not storage_within_cap(_lic(), 12)


def test_unlimited_when_not_set():
    lic = License(client="X", issued_at=None, expires_at=None, modules=frozenset(), limits={}, features={})
    check_limit(lic, "cameras", 9999)  # no limit → never raises
    assert remaining(lic, "cameras", 5) is None
