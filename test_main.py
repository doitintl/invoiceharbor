import json
import pytest
import asyncio
from unittest.mock import patch, MagicMock
from main import AwsInvoiceCredit, remove_footer, scan_folder, get_sorted_column_values, extract_data


def test_aws_invoice_credit_model():
    data = {
        "file_name": "2024-04-06_Invoice_EUCNGB24_30944.pdf",
        "doit_payer_id": "doitintl-payer-1998",
        "document_type": "Credit Note",
        "aws_account_number": "206722881646",
        "address_company": "Texthelp LTD",
        "address_attn": "Vadim Solovey",
        "address_country": "United Kingdom",
        "tax_registration_number": "GB516805252",
        "billing_period": "March 1, 2024 - March 31, 2024",
        "invoice_number": "EUCNGB24-30944",
        "invoice_date": "April 6, 2024",
        "original_invoice_number": "EUINGB24-1596217",
        "original_invoice_date": "April 2, 2024",
        "total_amount": -320.8,
        "total_amount_currency": "USD",
        "total_vat_tax_amount": -42.28,
        "total_vat_tax_currency": "GBP",
        "net_charges_usd": -267.34,
        "net_charges_non_usd": None,
        "net_charges_currency": None,
        "vat_percentage": 20.0,
        "exchange_rate": 0.79095,
        "amazon_company_name": "AMAZON WEB SERVICES EMEA SARL",
        "amazon_company_branch": "UK BRANCH"
    }

    model = AwsInvoiceCredit(**data)
    assert model.dict() == data


def test_remove_footer():
    text = "This is a test text. * May include estimated US sales tax, VAT, ST, GST and CT."
    assert remove_footer(text) == "This is a test text. "


def test_remove_footer_no_footer():
    # New test case
    text = "This is a test text with no footer."
    assert remove_footer(text) == text


@patch('os.walk')
@patch('main.PyMuPDFLoader')
def test_scan_folder(mock_loader, mock_walk):
    # Mock the return value of PyMuPDFLoader.load method
    mock_loader.return_value.load.return_value = [MagicMock(page_content='test content')]

    mock_walk.return_value = [
        ('root', 'dirs', ['data/1234_doit-payer-1/file1.pdf', 'data/1234_doit-payer-1/file2.pdf'])
    ]
    assert len(scan_folder('folder', max_docs=1)) == 1


def test_get_sorted_column_values():
    with patch('builtins.open', new_callable=MagicMock) as mock_open:
        mock_open.return_value.__enter__.return_value.__iter__.return_value = iter(['header', 'value'])
        assert get_sorted_column_values('file.csv', 0) == ['value']


def test_get_sorted_column_values_file_not_found():
    # New test case
    with pytest.raises(FileNotFoundError):
        get_sorted_column_values('non_existent_file.csv', 0)


@pytest.mark.asyncio
@patch('main.LLMChain')
async def test_extract_data(mock_chain):
    mock_chain.return_value.ainvoke.return_value = asyncio.Future()
    mock_chain.return_value.ainvoke.return_value.set_result({
        "text": json.dumps({
            "file_name": "2024-04-06_Invoice_EUCNGB24_30944.pdf",
            "doit_payer_id": "doitintl-payer-1998",
            "document_type": "Credit Note",
            "aws_account_number": "206722881646",
            "address_company": "Texthelp LTD",
            "address_attn": "Vadim Solovey",
            "address_country": "United Kingdom",
            "tax_registration_number": "GB516805252",
            "billing_period": "March 1, 2024 - March 31, 2024",
            "invoice_number": "EUCNGB24-30944",
            "invoice_date": "April 6, 2024",
            "original_invoice_number": "EUINGB24-1596217",
            "original_invoice_date": "April 2, 2024",
            "total_amount": -320.8,
            "total_amount_currency": "USD",
            "total_vat_tax_amount": -42.28,
            "total_vat_tax_currency": "GBP",
            "net_charges_usd": -267.34,
            "net_charges_non_usd": None,
            "net_charges_currency": None,
            "vat_percentage": 20.0,
            "exchange_rate": 0.79095,
            "amazon_company_name": "AMAZON WEB SERVICES EMEA SARL",
            "amazon_company_branch": "UK BRANCH"
        })
    })
    document = "File name: file.pdf\nDoiT payer id: 123\nInvoice"
    sem = asyncio.Semaphore(1)
    model = MagicMock()
    result = await extract_data(model, document, sem)
    assert isinstance(result, AwsInvoiceCredit)
