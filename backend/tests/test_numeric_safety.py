import asyncio
import math
import pytest
from pydantic import ValidationError
from src.models import AgentPermissions, BuyerSession, PaymentConstraints, ShippingOption
from src.onboarding.normalizer import _clean_price, _clean_stock, normalize

@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'), True, False])
def test_non_finite_and_boolean_prices_are_not_money(value):
    assert _clean_price(value) is None

@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'), 'NaN', 'Infinity', '-Infinity'])
def test_non_finite_stock_is_unavailable_without_crashing(value):
    assert _clean_stock(value) == 0

@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_bad_price_is_reported_as_a_row_error(value):
    result = asyncio.run(normalize([{'name': 'Test product', 'price': value, 'stock': 2}], infer_categories=False))
    assert not result.success
    assert not result.products
    assert result.errors[0].field == 'price'

@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'), -1])
@pytest.mark.parametrize('model,field,base', [
    (BuyerSession, 'spending_limit_inr', {'merchant_id': 'test', 'purchase_intent': 'test'}),
    (AgentPermissions, 'max_transaction_inr', {}),
    (AgentPermissions, 'requires_confirmation_above_inr', {}),
    (AgentPermissions, 'auto_approve_below_inr', {}),
    (ShippingOption, 'cost_inr', {}),
    (PaymentConstraints, 'min_order_inr', {}),
    (PaymentConstraints, 'max_order_inr', {}),
])
def test_money_bounds_must_be_non_negative_and_finite(value, model, field, base):
    with pytest.raises(ValidationError):
        model(**base, **{field: value})

@pytest.mark.parametrize('raw,expected', [('₹1,299.50', 1299.5), ('Rs.750', 750), (42, 42)])
def test_normal_prices_remain_supported(raw, expected):
    assert _clean_price(raw) == expected

def test_valid_catalog_and_permission_defaults_remain_supported():
    result = asyncio.run(normalize([{'name': 'Test product', 'price': '₹750', 'stock': 'yes'}], infer_categories=False))
    assert result.success
    assert result.products[0].price_inr == 750
    assert result.products[0].stock_count == 1
    assert math.isfinite(AgentPermissions().max_transaction_inr)
