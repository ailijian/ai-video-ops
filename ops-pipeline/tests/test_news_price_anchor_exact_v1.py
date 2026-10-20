import pytest
from news_delivery_v1 import _validate_title_against_fact,NewsDeliveryError


def test_exact_price_source_keeps_subject_across_numeric_span():
    source='午餐套餐29元，仅限到店自取，不含配送'
    _validate_title_against_fact(source,source)
    for changed in ('晚餐套餐29元，仅限到店自取，不含配送',
                    '午餐套餐29元，仅限到店自取','午餐套餐39元，仅限到店自取，不含配送'):
        with pytest.raises(NewsDeliveryError):_validate_title_against_fact(changed,source)
